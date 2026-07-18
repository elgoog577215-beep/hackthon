"""Course-scoped, immutable question-bank compilation and review domain."""

from __future__ import annotations

import json
import os
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from course_versioning import stable_hash
from storage import DATA_DIR

QUESTION_BANK_SCHEMA = "question_bank_bundle_v1"
QUESTION_ITEM_SCHEMA = "question_bank_item_v1"
QUESTION_SOURCE_TYPES = {"imported", "web_reference", "generated", "variant", "legacy_compiled"}
QUESTION_LIFECYCLE_STATES = {"candidate", "needs_review", "approved", "rejected", "retired"}
QUESTION_REVIEW_DECISIONS = {"approved", "rejected"}
FINAL_ASSESSMENT_ROLES = {"coverage_task", "cross_chapter_transfer"}
_STORAGE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")

_QUESTION_RE = re.compile(
    r"(?:^|\n)\s*(?:题目|问题|练习|试题)\s*[:：]\s*(.+?)(?=(?:\n|[。；;]\s*)(?:参考答案|答案|解析|解答)\s*[:：]|$)",
    re.IGNORECASE | re.DOTALL,
)
_ANSWER_RE = re.compile(
    r"(?:参考答案|答案)\s*[:：]\s*(.+?)(?=(?:\n|[。；;]\s*)(?:解析|解答)\s*[:：]|$)",
    re.IGNORECASE | re.DOTALL,
)
_EXPLANATION_RE = re.compile(
    r"(?:解析|解答)\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_SCORE_RE = re.compile(r"(?:分值|满分)\s*[:：]?\s*(\d{1,3})\s*分?")
_OPTION_RE = re.compile(
    r"(?:^|\s)([A-H])[\.\u3001\uff0e:：]\s*(.+?)"
    r"(?=(?:\s+[A-H][\.\u3001\uff0e:：]\s*)|$)",
    re.IGNORECASE | re.DOTALL,
)


def build_question_bank(
    course_data: dict[str, Any],
    *,
    legacy_tasks: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Compile one course-local question bank from teacher evidence and the CKB."""
    course_id = str(course_data.get("course_id") or "").strip()
    if not course_id:
        raise ValueError("course_id is required to build a question bank")

    nodes = [
        deepcopy(node)
        for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    ]
    bindings = {
        str(binding.get("asset_id") or ""): deepcopy(binding)
        for binding in course_data.get("material_bindings") or []
        if binding.get("asset_id")
    }
    evidence = [
        deepcopy(item)
        for item in (
            course_data.get("evidence_catalog")
            or course_data.get("_question_evidence_catalog")
            or []
        )
        if item.get("kind") == "question" or item.get("purpose") == "question_source"
    ]
    evidence_nodes = _evidence_node_bindings(nodes)

    imported: list[dict[str, Any]] = []
    for source in evidence:
        node = _best_node_for_evidence(source, nodes, evidence_nodes)
        imported.append(_imported_item(course_data, node, source, bindings))
    imported = _deduplicate_imported_items(imported)

    generated = _generated_course_items(course_data, nodes, imported)
    finals = _comprehensive_items(course_data, nodes, imported)
    legacy = [_legacy_item(course_data, item) for item in legacy_tasks]
    items = [*imported, *generated, *finals, *legacy]
    _mark_near_duplicate_risks(items)

    coverage = _coverage_report(course_data, nodes, items, imported)
    assessment_blueprint = _assessment_blueprint(course_data, finals, imported)
    bundle = {
        "schema_version": QUESTION_BANK_SCHEMA,
        "course_id": course_id,
        "course_scope": {"course_id": course_id, "cross_course_access": False},
        "source_priority": [
            "teacher_question_bank",
            "course_materials",
            "trusted_web_reference",
            "general_model_knowledge",
        ],
        "items": items,
        "coverage": coverage,
        "assessment_blueprint": assessment_blueprint,
        "review_queue": _review_queue(items),
        "web_enrichment": {
            "enabled": bool(
                ((course_data.get("generation_request") or {}).get("web_question_enrichment") or {}).get("enabled")
                or (course_data.get("web_question_enrichment") or {}).get("enabled")
            ),
            "status": "not_started",
            "query_count": 0,
            "source_count": 0,
            "query_limit": 12,
            "source_limit": 24,
        },
        "compiled_at": _now(),
    }
    return refresh_question_bank_bundle(bundle)


def review_question_bank_item(
    bundle: dict[str, Any],
    revision_id: str,
    *,
    decision: str,
    reviewer_id: str,
    note: str = "",
) -> dict[str, Any]:
    if decision not in QUESTION_REVIEW_DECISIONS:
        raise ValueError("decision must be approved or rejected")
    if not str(reviewer_id or "").strip():
        raise ValueError("reviewer_id is required")

    result = deepcopy(bundle)
    item = _find_item(result, revision_id)
    item["lifecycle_status"] = decision
    item["review_status"] = decision
    item["review_required"] = False if decision == "approved" else bool(item.get("review_required"))
    item["review_history"] = [
        *(item.get("review_history") or []),
        {
            "decision": decision,
            "reviewer_id": str(reviewer_id)[:200],
            "note": str(note or "")[:2000],
            "reviewed_at": _now(),
            "item_revision_id": item.get("revision_id"),
        },
    ]
    result["review_queue"] = _review_queue(result.get("items") or [])
    return refresh_question_bank_bundle(result)


def revise_question_bank_item(
    bundle: dict[str, Any],
    revision_id: str,
    *,
    patch: dict[str, Any],
    editor_id: str,
) -> dict[str, Any]:
    if not str(editor_id or "").strip():
        raise ValueError("editor_id is required")
    if len(json.dumps(patch, ensure_ascii=False).encode("utf-8")) > 100_000:
        raise ValueError("question item revision patch is too large")
    allowed_fields = {
        "prompt",
        "subquestions",
        "options",
        "answer_spec",
        "explanation",
        "score",
        "estimated_minutes",
        "question_type",
        "difficulty",
        "practice_levels",
        "assessment_role",
        "course_knowledge_refs",
        "course_skill_refs",
        "course_misconception_refs",
        "course_mastery_refs",
        "deliverable",
        "input_materials",
        "constraints",
        "reference_concepts",
        "result_checks",
    }
    unknown = set(patch) - allowed_fields
    if unknown:
        raise ValueError(f"unsupported question item fields: {sorted(unknown)}")
    for field in ("prompt", "explanation", "deliverable"):
        if field in patch and len(str(patch[field] or "")) > 12_000:
            raise ValueError(f"{field} exceeds the 12000 character limit")

    result = deepcopy(bundle)
    item = _find_item(result, revision_id)
    previous_revision = str(item.get("revision_id") or "")
    for field, value in patch.items():
        item[field] = deepcopy(value)
    item["parent_revision_id"] = previous_revision
    item["edited_by"] = str(editor_id)[:200]
    item["edited_at"] = _now()
    item["lifecycle_status"] = "needs_review"
    item["review_status"] = "needs_review"
    item["review_required"] = True
    item["hint_contract"] = _hint_contract(item)
    item["quality_report"] = evaluate_question_item_quality(item)
    item["revision_id"] = _item_revision_id(item)
    item["formal_task"] = _formal_task_from_item(item)
    item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
    result["review_queue"] = _review_queue(result.get("items") or [])
    return refresh_question_bank_bundle(result)


def filter_question_bank_items(
    bundle: dict[str, Any],
    *,
    node_id: str | None = None,
    source_type: str | None = None,
    lifecycle_status: str | None = None,
    risk: str | None = None,
) -> list[dict[str, Any]]:
    items = list(bundle.get("items") or [])
    if node_id:
        items = [item for item in items if item.get("node_id") == node_id or node_id in (item.get("node_ids") or [])]
    if source_type:
        items = [item for item in items if item.get("source_type") == source_type]
    if lifecycle_status:
        items = [item for item in items if item.get("lifecycle_status") == lifecycle_status]
    if risk:
        items = [item for item in items if risk in (item.get("risk_flags") or [])]
    return deepcopy(items)


def approved_formal_tasks(
    bundle: dict[str, Any],
    *,
    assessment_role: str | None = None,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for item in bundle.get("items") or []:
        if item.get("lifecycle_status") != "approved":
            continue
        if assessment_role and item.get("assessment_role") != assessment_role:
            continue
        formal = item.get("formal_task")
        if isinstance(formal, dict):
            projected = deepcopy(formal)
            projected["review_status"] = "approved"
            projected["question_bank_item_revision_id"] = item.get("revision_id")
            tasks.append(projected)
    return tasks


def formal_task_from_question_bank_item(item: dict[str, Any]) -> dict[str, Any]:
    return _formal_task_from_item(item)


def refresh_question_bank_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(bundle)
    result["review_queue"] = _review_queue(result.get("items") or [])
    payload = {
        "schema_version": result.get("schema_version"),
        "course_id": result.get("course_id"),
        "items": result.get("items") or [],
        "coverage": result.get("coverage") or {},
        "assessment_blueprint": result.get("assessment_blueprint") or {},
        "web_enrichment": result.get("web_enrichment") or {},
    }
    result["bundle_revision_id"] = stable_hash(
        _without_volatile_timestamps(payload),
        prefix="qbb_",
    )
    return result


def reconcile_question_bank(
    previous: dict[str, Any] | None,
    rebuilt: dict[str, Any],
) -> dict[str, Any]:
    """Carry reviewed/edited revisions forward and tombstone removed items."""
    if not previous:
        return refresh_question_bank_bundle(rebuilt)
    if str(previous.get("course_id") or "") != str(rebuilt.get("course_id") or ""):
        raise ValueError("cannot reconcile question banks from different course scopes")

    old_by_item = {
        str(item.get("item_id") or ""): item
        for item in previous.get("items") or []
        if item.get("item_id")
    }
    merged: list[dict[str, Any]] = []
    present_ids: set[str] = set()
    for fresh_item in rebuilt.get("items") or []:
        item_id = str(fresh_item.get("item_id") or "")
        present_ids.add(item_id)
        old_item = old_by_item.get(item_id)
        if old_item and (
            old_item.get("review_history")
            or old_item.get("edited_by")
            or (
                old_item.get("lifecycle_status") in {"approved", "rejected"}
                and old_item.get("review_required")
            )
        ):
            merged.append(deepcopy(old_item))
        else:
            merged.append(deepcopy(fresh_item))
    for item_id, old_item in old_by_item.items():
        if item_id in present_ids:
            continue
        retired = deepcopy(old_item)
        retired["lifecycle_status"] = "retired"
        retired["review_status"] = "retired"
        retired["review_required"] = False
        merged.append(retired)
    result = {
        **deepcopy(rebuilt),
        "items": merged,
    }
    return refresh_question_bank_bundle(result)


def evaluate_question_item_quality(item: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    prompt = str(item.get("prompt") or "").strip()
    answer_spec = item.get("answer_spec") or {}
    criteria = [str(value).strip() for value in answer_spec.get("criteria") or [] if str(value).strip()]
    if len(prompt) < 12:
        issues.append({"code": "question:prompt_too_short", "severity": "critical"})
    if not criteria and answer_spec.get("correct_answer") is None and answer_spec.get("correct_option_id") is None:
        issues.append({"code": "question:answer_not_executable", "severity": "critical"})
    if not item.get("course_knowledge_refs"):
        issues.append({"code": "question:knowledge_unbound", "severity": "major"})
    if not item.get("source_records"):
        issues.append({"code": "question:source_missing", "severity": "major"})
    if item.get("source_type") == "imported" and answer_spec.get("correct_answer") is None:
        issues.append({"code": "question:imported_answer_missing", "severity": "major"})
    if item.get("parse_confidence") == "low":
        issues.append({"code": "question:low_parse_confidence", "severity": "major"})
    if "near_duplicate" in (item.get("risk_flags") or []):
        issues.append({"code": "question:near_duplicate", "severity": "major"})
    if "answer_conflict" in (item.get("risk_flags") or []):
        issues.append({"code": "question:answer_conflict", "severity": "critical"})

    critical = [issue for issue in issues if issue["severity"] == "critical"]
    status = "failed" if critical else ("needs_review" if issues else "passed")
    return {
        "schema_version": "question_item_quality_v1",
        "passed": not critical,
        "status": status,
        "issues": issues,
        "checks": {
            "structure": not any(issue["code"].startswith("question:prompt") for issue in issues),
            "knowledge_and_difficulty": bool(item.get("course_knowledge_refs")) and bool(item.get("difficulty")),
            "source_and_rights": bool(item.get("source_records")),
            "answer_and_rubric": not any("answer" in issue["code"] for issue in critical),
            "semantic_alignment": len(prompt) >= 12 and bool(criteria or answer_spec.get("correct_answer") is not None),
            "hint_safety": bool((item.get("hint_contract") or {}).get("leakage_check", {}).get("passed", True)),
        },
    }


class QuestionBankRepository:
    """Immutable per-course bundle storage with an explicit active pointer."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "question_banks")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save_bundle(
        self,
        course_id: str,
        bundle: dict[str, Any],
        *,
        activate: bool = True,
    ) -> dict[str, Any]:
        normalized_course_id = _storage_id(course_id)
        if not normalized_course_id or str(bundle.get("course_id") or "") != normalized_course_id:
            raise ValueError("question bank course scope does not match repository path")
        stored = refresh_question_bank_bundle(bundle)
        revision_id = str(stored["bundle_revision_id"])
        path = self.root_dir / normalized_course_id / "revisions" / f"{revision_id}.json"
        if not path.exists():
            self._atomic_write(path, stored)
        if activate:
            self.activate_bundle(normalized_course_id, revision_id)
        return stored

    def activate_bundle(self, course_id: str, bundle_revision_id: str) -> None:
        course_id = _storage_id(course_id)
        bundle_revision_id = _storage_id(bundle_revision_id)
        path = self.root_dir / course_id / "revisions" / f"{bundle_revision_id}.json"
        if not path.exists():
            raise KeyError(f"Unknown question bank bundle: {bundle_revision_id}")
        self._atomic_write(
            self.root_dir / course_id / "current.json",
            {"bundle_revision_id": bundle_revision_id},
        )

    def load_bundle(
        self,
        course_id: str,
        bundle_revision_id: str | None = None,
    ) -> dict[str, Any] | None:
        course_id = _storage_id(course_id)
        directory = self.root_dir / course_id
        if bundle_revision_id is None:
            pointer = directory / "current.json"
            if not pointer.exists():
                return None
            bundle_revision_id = str(self._read(pointer).get("bundle_revision_id") or "")
        bundle_revision_id = _storage_id(bundle_revision_id)
        path = directory / "revisions" / f"{bundle_revision_id}.json"
        value = self._read(path) if path.exists() else None
        if value and str(value.get("course_id") or "") != str(course_id):
            raise ValueError("question bank course scope is invalid")
        return value

    def delete_bundle(self, course_id: str, bundle_revision_id: str) -> bool:
        course_id = _storage_id(course_id)
        bundle_revision_id = _storage_id(bundle_revision_id)
        directory = self.root_dir / course_id
        pointer = directory / "current.json"
        if pointer.exists() and self._read(pointer).get("bundle_revision_id") == bundle_revision_id:
            return False
        path = directory / "revisions" / f"{bundle_revision_id}.json"
        if not path.exists():
            return False
        path.unlink()
        return True

    def delete_course(self, course_id: str) -> bool:
        course_id = _storage_id(course_id)
        directory = self.root_dir / course_id
        if not directory.exists():
            return False
        shutil.rmtree(directory)
        return True

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("question bank repository expected a JSON object")
        return value

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


def _imported_item(
    course_data: dict[str, Any],
    node: dict[str, Any] | None,
    evidence: dict[str, Any],
    bindings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_text = str(evidence.get("source_text") or evidence.get("summary") or "").strip()
    raw_prompt = _extract(_QUESTION_RE, source_text) or source_text
    prompt, options = _split_options(raw_prompt)
    answer = _clean_answer(_extract(_ANSWER_RE, source_text))
    correct_option_id = (
        answer.upper()
        if options and answer and re.fullmatch(r"[A-H]", answer, re.IGNORECASE)
        else None
    )
    explanation = _clean_text(_extract(_EXPLANATION_RE, source_text))
    binding = bindings.get(str(evidence.get("asset_id") or ""), {})
    node = node or {}
    node_id = str(node.get("node_id") or "")
    knowledge_refs = _node_knowledge_refs(course_data, node)
    item_id = stable_hash(
        {
            "course": course_data.get("course_id"),
            "source": evidence.get("content_hash") or evidence.get("evidence_id"),
            "prompt": _normalize_text(prompt),
        },
        prefix="qbi_",
    )
    source_record = _teacher_source_record(evidence, binding)
    risk_flags: list[str] = []
    confidence = str(evidence.get("confidence") or "medium")
    if confidence == "low":
        risk_flags.append("low_parse_confidence")
    if answer is None:
        risk_flags.append("missing_answer")
    item = {
        "schema_version": QUESTION_ITEM_SCHEMA,
        "course_id": str(course_data.get("course_id") or ""),
        "item_id": item_id,
        "parent_item_id": None,
        "parent_revision_id": None,
        "node_id": node_id,
        "node_ids": [node_id] if node_id else [],
        "prompt": prompt[:12000],
        "subquestions": [],
        "options": options,
        "answer_spec": {
            "type": (
                "single_choice"
                if correct_option_id
                else ("exact" if answer is not None else "rubric")
            ),
            "correct_answer": answer,
            "correct_option_id": correct_option_id,
            "criteria": (
                [f"答案与教师资料中的参考答案一致：{answer}"] if answer is not None
                else ["给出明确结论", "说明关键步骤或依据", "检查结果"]
            ),
            "expected_keywords": _node_key_points(node)[:6],
            "max_score": _extract_score(source_text) or 100,
            "pass_score": 70,
        },
        "explanation": explanation,
        "score": _extract_score(source_text),
        "estimated_minutes": _estimated_minutes(prompt),
        "question_type": "single_choice" if options else "short_answer",
        "difficulty": _node_difficulty(course_data, node),
        "practice_levels": ["objective_practice", "mastery_check"],
        "assessment_role": "imported_practice",
        "course_objective_refs": [_objective_ref(course_data, node)] if node_id else [],
        "course_knowledge_refs": knowledge_refs,
        "course_skill_refs": _node_refs(node, "course_skill_refs"),
        "course_misconception_refs": _node_refs(node, "course_misconception_refs"),
        "course_mastery_refs": _node_refs(node, "course_mastery_refs"),
        "source_type": "imported",
        "source_records": [source_record],
        "parse_confidence": confidence,
        "risk_flags": risk_flags,
        "review_required": bool(risk_flags),
        "lifecycle_status": "candidate",
        "review_status": "candidate",
        "review_history": [],
        "formal_task_revision_id": None,
        "deliverable": "提交答案及必要的计算或推理过程",
        "input_materials": [prompt],
        "constraints": ["使用题目给定条件", "不得引入未说明的假设"],
        "reference_concepts": _node_key_points(node),
        "result_checks": ["结果满足题目条件", "关键步骤可以复核"],
        "created_at": _now(),
    }
    item["hint_contract"] = _hint_contract(item)
    item["quality_report"] = evaluate_question_item_quality(item)
    item["lifecycle_status"] = _initial_status(item)
    item["review_status"] = item["lifecycle_status"]
    item["revision_id"] = _item_revision_id(item)
    item["formal_task"] = _formal_task_from_item(item)
    item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
    return item


def _generated_course_items(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    imported: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    imported_by_node = {
        str(item.get("node_id") or ""): item
        for item in imported
        if item.get("node_id") and item.get("lifecycle_status") in {"approved", "needs_review"}
    }
    level_specs = (
        ("concept_check", "概念辨析"),
        ("objective_practice", "情境应用"),
        ("mastery_check", "独立达标"),
    )
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        key_points = _node_key_points(node)
        assessments = _assessment_items(node)
        source_item = imported_by_node.get(node_id)
        for index, (level, label) in enumerate(level_specs):
            condition = _variant_condition(course_data, node, index)
            source_type = "variant" if source_item else "generated"
            item_id = stable_hash(
                {
                    "course": course_data.get("course_id"),
                    "node": node_id,
                    "level": level,
                    "source": source_item.get("item_id") if source_item else None,
                    "objective": node.get("learning_objective"),
                    "knowledge": key_points,
                },
                prefix="qbi_",
            )
            task_text = (
                "；".join(f"（{task_index}）{task}" for task_index, task in enumerate(assessments, start=1))
                if level == "mastery_check"
                else assessments[min(index, len(assessments) - 1)]
            )
            prompt = (
                f"{label}｜{node.get('node_name') or node_id}\n"
                f"输入材料：{condition}\n"
                f"任务：{task_text}\n"
                f"限制条件：必须使用{_join_names(key_points[:2])}，写出依据、过程和结果检查。"
            )
            source_records = deepcopy(source_item.get("source_records") or []) if source_item else [{
                "source_type": "course_material",
                "course_id": str(course_data.get("course_id") or ""),
                "node_id": node_id,
                "rights_basis": "course_generated",
                "reuse_policy": "original_generation",
            }]
            item = {
                "schema_version": QUESTION_ITEM_SCHEMA,
                "course_id": str(course_data.get("course_id") or ""),
                "item_id": item_id,
                "parent_item_id": source_item.get("item_id") if source_item else None,
                "parent_revision_id": source_item.get("revision_id") if source_item else None,
                "node_id": node_id,
                "node_ids": [node_id],
                "prompt": prompt,
                "subquestions": assessments if level == "mastery_check" else [],
                "options": [],
                "answer_spec": {
                    "type": "rubric",
                    "criteria": _generated_criteria(node, level),
                    "expected_keywords": key_points[:6],
                    "max_score": 100,
                    "pass_score": 70,
                },
                "explanation": "",
                "score": 100,
                "estimated_minutes": 6 if level == "concept_check" else 15,
                "question_type": _question_type(course_data, level),
                "difficulty": _node_difficulty(course_data, node),
                "practice_levels": [level],
                "assessment_role": "practice",
                "course_objective_refs": [_objective_ref(course_data, node)],
                "course_knowledge_refs": _node_knowledge_refs(course_data, node),
                "course_skill_refs": _node_refs(node, "course_skill_refs"),
                "course_misconception_refs": _node_refs(node, "course_misconception_refs"),
                "course_mastery_refs": _node_refs(node, "course_mastery_refs"),
                "source_type": source_type,
                "source_records": source_records,
                "parse_confidence": "high",
                "risk_flags": [],
                "review_required": False,
                "lifecycle_status": "candidate",
                "review_status": "candidate",
                "review_history": [],
                "formal_task_revision_id": None,
                "deliverable": assessments[min(index, len(assessments) - 1)],
                "input_materials": [condition],
                "constraints": [f"必须使用{_join_names(key_points[:2])}", "必须写出可复核的结果检查"],
                "reference_concepts": key_points,
                "result_checks": ["覆盖指定知识点", "过程可执行", "结果与输入条件一致"],
                "created_at": _now(),
            }
            item["hint_contract"] = _hint_contract(item)
            item["quality_report"] = evaluate_question_item_quality(item)
            item["lifecycle_status"] = _initial_status(item)
            item["review_status"] = item["lifecycle_status"]
            item["revision_id"] = _item_revision_id(item)
            item["formal_task"] = _formal_task_from_item(item)
            item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
            result.append(item)
    return result


def _comprehensive_items(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    imported: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    purpose = str(
        course_data.get("course_purpose")
        or (course_data.get("generation_request") or {}).get("course_purpose")
        or "systematic"
    )
    preferences = (
        course_data.get("asset_preferences")
        or (course_data.get("generation_request") or {}).get("asset_preferences")
        or {}
    )
    if purpose == "material_organization" and not preferences.get("final_assessment"):
        return []
    assessment_nodes = _assessment_nodes(course_data, nodes, purpose)
    if not assessment_nodes:
        return []

    desired_count = max(3, min(8, len(assessment_nodes) + 1))
    selected = [
        assessment_nodes[index % len(assessment_nodes)]
        for index in range(desired_count - 1)
    ]
    items: list[dict[str, Any]] = []
    for index, node in enumerate(selected, start=1):
        node_id = str(node.get("node_id") or "")
        assessment = _assessment_items(node)[0]
        key_points = _node_key_points(node)
        input_material = _variant_condition(course_data, node, index + 3)
        prompt = (
            f"综合测评任务 {index}｜{node.get('node_name') or node_id}\n"
            f"输入材料：{input_material}\n"
            f"最终产物：{assessment}\n"
            f"限制条件：使用{_join_names(key_points[:2])}，展示依据与过程，并给出至少一项结果检查。"
        )
        items.append(_final_item(
            course_data,
            [node],
            index=index,
            role="coverage_task",
            prompt=prompt,
            deliverable=assessment,
            input_materials=[input_material],
            constraints=[f"使用{_join_names(key_points[:2])}", "展示依据和过程", "完成结果检查"],
        ))

    node_names = [
        str(node.get("node_name") or node.get("node_id") or "")
        for node in assessment_nodes
    ]
    objectives = [
        str(node.get("learning_objective") or "")
        for node in assessment_nodes
    ]
    cross_material = _cross_chapter_material(course_data, assessment_nodes)
    cross_prompt = (
        f"跨章节迁移任务｜连接{_join_names(node_names[:4])}\n"
        f"输入材料：{cross_material}\n"
        f"最终产物：提交一份完整解决方案，分别说明各章节概念如何参与，并对最终结论执行一致性检查。\n"
        f"限制条件：至少建立两处跨章节连接；不得省略关键假设；结论必须能够由给定材料复核。"
    )
    items.append(_final_item(
        course_data,
        assessment_nodes,
        index=desired_count,
        role="cross_chapter_transfer",
        prompt=cross_prompt,
        deliverable="一份包含跨章节连接、推理过程与结果验证的完整解决方案",
        input_materials=[cross_material, f"目标约束：{_join_names(objectives[:4])}"],
        constraints=["至少连接两个章节", "明确关键假设", "提供可执行的结果检查"],
    ))
    _apply_assessment_distribution(course_data, items, imported, purpose)
    return items


def _assessment_nodes(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    purpose: str,
) -> list[dict[str, Any]]:
    if purpose != "personalized_remedial":
        return nodes
    generation_request = course_data.get("generation_request") or {}
    weak_node_ids = {
        str(value)
        for value in (
            course_data.get("confirmed_weak_node_ids")
            or generation_request.get("confirmed_weak_node_ids")
            or []
        )
        if str(value).strip()
    }
    if not weak_node_ids:
        return nodes
    return [
        node for node in nodes
        if str(node.get("node_id") or "") in weak_node_ids
    ]


def _apply_assessment_distribution(
    course_data: dict[str, Any],
    items: list[dict[str, Any]],
    imported: list[dict[str, Any]],
    purpose: str,
) -> None:
    teacher_distribution = purpose == "exam_sprint" and bool(imported)
    for index, item in enumerate(items):
        matching = [
            candidate
            for candidate in imported
            if set(candidate.get("node_ids") or []) & set(item.get("node_ids") or [])
        ]
        sample = next(iter(matching), None)
        if sample is None and imported:
            sample = imported[index % len(imported)]
        if teacher_distribution and sample:
            item["question_type"] = sample.get("question_type") or item.get("question_type")
            item["difficulty"] = sample.get("difficulty") or item.get("difficulty")
            source_score = (
                sample.get("score")
                or (sample.get("answer_spec") or {}).get("max_score")
            )
            if source_score:
                item["score"] = source_score
                item["answer_spec"]["max_score"] = source_score
            item["assessment_distribution"] = {
                "basis": "teacher_question_bank",
                "inferred": False,
                "source_item_revision_id": sample.get("revision_id"),
            }
        else:
            item["assessment_distribution"] = {
                "basis": "systematic_rule",
                "inferred": purpose == "exam_sprint",
                "source_item_revision_id": None,
            }
        item["quality_report"] = evaluate_question_item_quality(item)
        item["revision_id"] = _item_revision_id(item)
        item["formal_task"] = _formal_task_from_item(item)
        item["formal_task_revision_id"] = item["formal_task"]["revision_id"]


def _assessment_blueprint(
    course_data: dict[str, Any],
    finals: list[dict[str, Any]],
    imported: list[dict[str, Any]],
) -> dict[str, Any]:
    purpose = str(
        course_data.get("course_purpose")
        or (course_data.get("generation_request") or {}).get("course_purpose")
        or "systematic"
    )
    teacher_distribution = purpose == "exam_sprint" and bool(imported)
    return {
        "purpose": purpose,
        "basis": "teacher_question_bank" if teacher_distribution else "systematic_rule",
        "distribution_inferred": purpose == "exam_sprint" and not teacher_distribution,
        "focus": (
            "confirmed_weak_objectives"
            if purpose == "personalized_remedial"
            else "all_required_objectives"
        ),
        "task_count": len(finals),
        "question_type_distribution": _distribution(finals, "question_type"),
        "difficulty_distribution": _distribution(finals, "difficulty"),
        "score_distribution": [
            item.get("score")
            for item in finals
            if item.get("score") is not None
        ],
    }


def _final_item(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    *,
    index: int,
    role: str,
    prompt: str,
    deliverable: str,
    input_materials: list[str],
    constraints: list[str],
) -> dict[str, Any]:
    course_id = str(course_data.get("course_id") or "")
    node_ids = [str(node.get("node_id") or "") for node in nodes]
    concepts = _unique(
        ref
        for node in nodes
        for ref in _node_knowledge_refs(course_data, node)
    )
    criteria = [
        deliverable,
        "正确使用指定章节概念并说明连接依据",
        "过程完整且关键假设明确",
        "执行结果检查并说明适用边界",
    ]
    item = {
        "schema_version": QUESTION_ITEM_SCHEMA,
        "course_id": course_id,
        "item_id": stable_hash(
            {"course": course_id, "role": role, "index": index, "nodes": node_ids},
            prefix="qbi_",
        ),
        "parent_item_id": None,
        "parent_revision_id": None,
        "node_id": node_ids[0] if len(node_ids) == 1 else "",
        "node_ids": node_ids,
        "prompt": prompt,
        "subquestions": [],
        "options": [],
        "answer_spec": {
            "type": "rubric",
            "criteria": criteria,
            "expected_keywords": _unique(
                point for node in nodes for point in _node_key_points(node)
            )[:12],
            "max_score": 100,
            "pass_score": 70,
        },
        "explanation": "",
        "score": 100,
        "estimated_minutes": 25 if role == "coverage_task" else 45,
        "question_type": _question_type(course_data, "final_assessment"),
        "difficulty": str(course_data.get("difficulty") or "intermediate"),
        "practice_levels": ["final_assessment"],
        "assessment_role": role,
        "course_objective_refs": [_objective_ref(course_data, node) for node in nodes],
        "course_knowledge_refs": concepts,
        "course_skill_refs": _unique(ref for node in nodes for ref in _node_refs(node, "course_skill_refs")),
        "course_misconception_refs": _unique(
            ref for node in nodes for ref in _node_refs(node, "course_misconception_refs")
        ),
        "course_mastery_refs": _unique(ref for node in nodes for ref in _node_refs(node, "course_mastery_refs")),
        "source_type": "generated",
        "source_records": [{
            "source_type": "course_knowledge_base",
            "course_id": course_id,
            "node_ids": node_ids,
            "rights_basis": "course_generated",
            "reuse_policy": "original_generation",
        }],
        "parse_confidence": "high",
        "risk_flags": ["comprehensive_task"],
        "review_required": True,
        "lifecycle_status": "needs_review",
        "review_status": "needs_review",
        "review_history": [],
        "formal_task_revision_id": None,
        "deliverable": deliverable,
        "input_materials": input_materials,
        "constraints": constraints,
        "reference_concepts": _unique(point for node in nodes for point in _node_key_points(node)),
        "result_checks": ["量规逐项可判定", "结果与输入材料一致", "跨章节连接有明确依据"],
        "created_at": _now(),
    }
    item["hint_contract"] = _hint_contract(item)
    item["quality_report"] = evaluate_question_item_quality(item)
    item["revision_id"] = _item_revision_id(item)
    item["formal_task"] = _formal_task_from_item(item)
    item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
    return item


def _legacy_item(course_data: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    item = {
        "schema_version": QUESTION_ITEM_SCHEMA,
        "course_id": str(course_data.get("course_id") or ""),
        "item_id": stable_hash(
            {"course": course_data.get("course_id"), "legacy": task.get("revision_id") or task},
            prefix="qbi_",
        ),
        "parent_item_id": None,
        "parent_revision_id": None,
        "node_id": str(task.get("node_id") or ""),
        "node_ids": [str(task.get("node_id") or "")] if task.get("node_id") else [],
        "prompt": str(task.get("prompt") or ""),
        "answer_spec": deepcopy(task.get("answer_spec") or {}),
        "question_type": str(task.get("question_type") or "short_answer"),
        "difficulty": str(course_data.get("difficulty") or "intermediate"),
        "practice_levels": [str(task.get("practice_level") or "objective_practice")],
        "assessment_role": "legacy",
        "course_objective_refs": [],
        "course_knowledge_refs": deepcopy(task.get("course_knowledge_refs") or task.get("concept_ids") or []),
        "course_skill_refs": deepcopy(task.get("course_skill_refs") or task.get("skill_unit_ids") or []),
        "course_misconception_refs": deepcopy(task.get("course_misconception_refs") or []),
        "course_mastery_refs": deepcopy(task.get("course_mastery_refs") or []),
        "source_type": "legacy_compiled",
        "source_records": [{
            "source_type": "legacy_compiled",
            "course_id": str(course_data.get("course_id") or ""),
            "formal_task_revision_id": task.get("revision_id"),
            "rights_basis": "legacy_course",
            "reuse_policy": "preserve_existing",
        }],
        "parse_confidence": "medium",
        "risk_flags": [],
        "review_required": False,
        "lifecycle_status": "approved",
        "review_status": "approved",
        "review_history": [],
        "formal_task_revision_id": task.get("revision_id"),
        "formal_task": deepcopy(task),
        "deliverable": str(task.get("prompt") or ""),
        "input_materials": [],
        "constraints": [],
        "reference_concepts": [],
        "result_checks": [],
        "created_at": _now(),
    }
    item["hint_contract"] = deepcopy(task.get("hint_contract") or _hint_contract(item))
    item["quality_report"] = evaluate_question_item_quality(item)
    item["revision_id"] = _item_revision_id(item)
    return item


def _coverage_report(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    items: list[dict[str, Any]],
    imported: list[dict[str, Any]],
) -> dict[str, Any]:
    required = {
        _objective_ref(course_data, node): {
            "node_id": str(node.get("node_id") or ""),
            "objective": str(node.get("learning_objective") or node.get("node_name") or ""),
            "knowledge_points": _node_key_points(node),
            "difficulty": _node_difficulty({}, node),
        }
        for node in nodes
    }
    covered = {
        objective
        for item in items
        if item.get("lifecycle_status") in {"approved", "needs_review"}
        and item.get("assessment_role") not in {"reference"}
        for objective in item.get("course_objective_refs") or []
    }
    imported_nodes = {
        str(item.get("node_id") or "")
        for item in imported
        if item.get("lifecycle_status") in {"approved", "needs_review"}
    }
    gaps = [
        {
            "node_id": str(node.get("node_id") or ""),
            "objective": str(node.get("learning_objective") or node.get("node_name") or ""),
            "knowledge_points": _node_key_points(node),
            "difficulty": _node_difficulty({}, node),
            "reason": "teacher_question_source_missing",
        }
        for node in nodes
        if str(node.get("node_id") or "") not in imported_nodes
    ]
    missing = [data for objective, data in required.items() if objective not in covered]
    count = len(required)
    return {
        "required_objective_count": count,
        "covered_objective_count": count - len(missing),
        "coverage_ratio": round((count - len(missing)) / max(1, count), 4),
        "missing_required_objectives": missing,
        "gaps": gaps,
        "status": "complete" if not missing else "blocked",
    }


def _deduplicate_imported_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_prompt: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _normalize_text(str(item.get("prompt") or ""))
        existing = by_prompt.get(key)
        if not existing:
            by_prompt[key] = item
            result.append(item)
            continue
        existing["source_records"] = [
            *existing.get("source_records", []),
            *item.get("source_records", []),
        ]
        existing_answer = (existing.get("answer_spec") or {}).get("correct_answer")
        candidate_answer = (item.get("answer_spec") or {}).get("correct_answer")
        if existing_answer is not None and candidate_answer is not None and existing_answer != candidate_answer:
            existing["risk_flags"] = _unique([*(existing.get("risk_flags") or []), "answer_conflict"])
            existing["review_required"] = True
            existing["lifecycle_status"] = "needs_review"
            existing["review_status"] = "needs_review"
        existing["quality_report"] = evaluate_question_item_quality(existing)
        existing["revision_id"] = _item_revision_id(existing)
        existing["formal_task"] = _formal_task_from_item(existing)
        existing["formal_task_revision_id"] = existing["formal_task"]["revision_id"]
    return result


def _mark_near_duplicate_risks(items: list[dict[str, Any]]) -> None:
    comparable = [
        item for item in items
        if item.get("assessment_role") not in FINAL_ASSESSMENT_ROLES
    ]
    for index, left in enumerate(comparable):
        left_text = _normalize_text(str(left.get("prompt") or ""))
        if not left_text:
            continue
        for right in comparable[index + 1:]:
            if left.get("node_id") != right.get("node_id"):
                continue
            right_text = _normalize_text(str(right.get("prompt") or ""))
            similarity = SequenceMatcher(None, left_text, right_text).ratio()
            if 0.9 <= similarity < 1:
                cluster_id = stable_hash(sorted([left_text, right_text]), prefix="qdc_")
                for item in (left, right):
                    item["near_duplicate_cluster_id"] = cluster_id
                    item["risk_flags"] = _unique([*(item.get("risk_flags") or []), "near_duplicate"])
                    item["review_required"] = True
                    item["lifecycle_status"] = "needs_review"
                    item["review_status"] = "needs_review"
                    item["quality_report"] = evaluate_question_item_quality(item)
                    item["revision_id"] = _item_revision_id(item)
                    item["formal_task"] = _formal_task_from_item(item)
                    item["formal_task_revision_id"] = item["formal_task"]["revision_id"]


def _teacher_source_record(
    evidence: dict[str, Any],
    binding: dict[str, Any],
) -> dict[str, Any]:
    locator = evidence.get("locator") or {}
    metadata = binding.get("source_metadata") or {}
    return {
        "source_type": "teacher_upload",
        "asset_id": str(evidence.get("asset_id") or ""),
        "document_id": str(evidence.get("document_id") or ""),
        "evidence_id": str(evidence.get("evidence_id") or ""),
        "page": locator.get("page"),
        "slide": locator.get("slide"),
        "section_path": deepcopy(locator.get("section_path") or []),
        "bbox": deepcopy(locator.get("bbox")),
        "year": metadata.get("year"),
        "term": metadata.get("term"),
        "exam_type": metadata.get("exam_type"),
        "source_label": str(binding.get("source_label") or ""),
        "content_hash": str(evidence.get("content_hash") or ""),
        "rights_basis": str(binding.get("rights_basis") or "teacher_asserted"),
        "reuse_policy": str(binding.get("reuse_policy") or "verbatim_allowed"),
    }


def _hint_contract(item: dict[str, Any]) -> dict[str, Any]:
    concepts = item.get("reference_concepts") or item.get("course_knowledge_refs") or []
    constraints = item.get("constraints") or []
    criteria = (item.get("answer_spec") or {}).get("criteria") or []
    levels = [
        {
            "level": 1,
            "kind": "orientation",
            "content": (
                f"先确认题目要求的最终产物，再回看相关概念：{_join_names(concepts[:3])}。"
                f"自检是否遗漏输入条件与边界。"
            ),
            "evidence_effect": "limited_mastery",
            "support_level": 1,
        },
        {
            "level": 2,
            "kind": "method_skeleton",
            "content": (
                f"按“整理输入—选择方法—执行关键步骤—检查结果”的骨架推进。"
                f"首个关键步骤是明确：{_join_names(constraints[:2])}。"
            ),
            "evidence_effect": "not_independent",
            "support_level": 2,
        },
        {
            "level": 3,
            "kind": "local_scaffold",
            "content": (
                f"用一个不同情境做局部对照：逐项核对{_join_names(criteria[:2])}，"
                "只补足当前卡住的环节，不代写最终结论。"
            ),
            "evidence_effect": "not_mastery",
            "support_level": 3,
        },
    ]
    prompt = _normalize_text(str(item.get("prompt") or ""))
    answer = _normalize_text(str((item.get("answer_spec") or {}).get("correct_answer") or ""))
    leakage = bool(answer and any(answer in _normalize_text(level["content"]) for level in levels))
    return {
        "levels": levels,
        "solution_policy": "after_submission_or_repeated_failure",
        "solution_effect": {
            "invalidate_current_evidence": True,
            "requires_unseen_equivalent_validation": True,
        },
        "frozen_with_item_revision": True,
        "leakage_check": {
            "passed": not leakage and all(_normalize_text(level["content"]) != prompt for level in levels),
            "checked_at_compile_time": True,
        },
    }


def _formal_task_from_item(item: dict[str, Any]) -> dict[str, Any]:
    task = {
        "asset_id": stable_hash(
            {"course": item.get("course_id"), "question_bank_item": item.get("item_id")},
            prefix="qbt_",
        ),
        "question_id": item.get("item_id"),
        "node_id": item.get("node_id"),
        "node_ids": deepcopy(item.get("node_ids") or []),
        "learning_objective": next(iter(item.get("course_objective_refs") or []), ""),
        "objective_id": next(iter(item.get("course_objective_refs") or []), ""),
        "course_objective_refs": deepcopy(item.get("course_objective_refs") or []),
        "concept_ids": deepcopy(item.get("course_knowledge_refs") or []),
        "skill_unit_ids": deepcopy(item.get("course_skill_refs") or []),
        "mistake_point_ids": deepcopy(item.get("course_misconception_refs") or []),
        "course_knowledge_refs": deepcopy(item.get("course_knowledge_refs") or []),
        "course_skill_refs": deepcopy(item.get("course_skill_refs") or []),
        "course_misconception_refs": deepcopy(item.get("course_misconception_refs") or []),
        "course_mastery_refs": deepcopy(item.get("course_mastery_refs") or []),
        "question_type": item.get("question_type"),
        "difficulty_contract": {"target_level": item.get("difficulty")},
        "prompt": item.get("prompt"),
        "subquestions": deepcopy(item.get("subquestions") or []),
        "options": deepcopy(item.get("options") or []),
        "answer_spec": deepcopy(item.get("answer_spec") or {}),
        "practice_level": next(iter(item.get("practice_levels") or []), "objective_practice"),
        "hint_contract": deepcopy(item.get("hint_contract") or {}),
        "input_contract": {
            "mode": "structured_text",
            "required": True,
            "supports_attachments": item.get("question_type") in {"implementation_task", "scenario_deliverable"},
        },
        "grading_policy": {
            "method": (
                "deterministic"
                if (item.get("answer_spec") or {}).get("correct_answer") is not None
                else "rubric_ai"
            ),
            "pass_score": int((item.get("answer_spec") or {}).get("pass_score") or 70),
            "confidence_threshold": 0.72,
            "near_threshold_review_margin": 3,
        },
        "validation_policy": {
            "mastery_eligible": next(iter(item.get("practice_levels") or []), "") in {
                "mastery_check",
                "final_assessment",
            },
            "max_support_level_for_mastery": 1,
            "requires_unseen_validation_after_solution": True,
        },
        "source_status": item.get("source_type"),
        "source_records": deepcopy(item.get("source_records") or []),
        "quality_status": (item.get("quality_report") or {}).get("status"),
        "quality_report": deepcopy(item.get("quality_report") or {}),
        "review_status": item.get("review_status"),
        "assessment_role": item.get("assessment_role"),
        "assessment_distribution": deepcopy(item.get("assessment_distribution") or {}),
        "deliverable": item.get("deliverable"),
        "input_materials": deepcopy(item.get("input_materials") or []),
        "constraints": deepcopy(item.get("constraints") or []),
        "result_checks": deepcopy(item.get("result_checks") or []),
        "question_bank_item_revision_id": item.get("revision_id"),
    }
    task["practice_contract_revision_id"] = stable_hash(
        {
            "input": task["input_contract"],
            "hint": task["hint_contract"],
            "grading": task["grading_policy"],
            "validation": task["validation_policy"],
        },
        prefix="pcr_",
    )
    task["revision_id"] = stable_hash(task, prefix="qr_")
    return task


def _initial_status(item: dict[str, Any]) -> str:
    if item.get("review_required"):
        return "needs_review"
    report = item.get("quality_report") or {}
    if not report.get("passed"):
        return "needs_review"
    if report.get("status") == "needs_review":
        return "needs_review"
    return "approved"


def _evidence_node_bindings(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        for evidence_id in (node.get("grounding_contract") or {}).get("question_evidence_ids") or []:
            result[str(evidence_id)] = node
    return result


def _best_node_for_evidence(
    evidence: dict[str, Any],
    nodes: list[dict[str, Any]],
    evidence_nodes: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    direct = evidence_nodes.get(str(evidence.get("evidence_id") or ""))
    if direct:
        return direct
    source = _normalize_text(str(evidence.get("source_text") or evidence.get("summary") or ""))
    scored: list[tuple[int, dict[str, Any]]] = []
    for node in nodes:
        terms = [
            str(node.get("node_name") or ""),
            str(node.get("learning_objective") or ""),
            *_node_key_points(node),
        ]
        score = sum(1 for term in terms if _normalize_text(term) and _normalize_text(term) in source)
        scored.append((score, node))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else (nodes[0] if nodes else None)


def _node_knowledge_refs(course_data: dict[str, Any], node: dict[str, Any]) -> list[str]:
    direct = _node_refs(node, "course_knowledge_refs") or _node_refs(node, "concept_ids")
    if direct:
        return direct
    course_id = str(course_data.get("course_id") or "")
    node_id = str(node.get("node_id") or "")
    return [
        stable_hash(
            {"course": course_id, "node": node_id, "knowledge": name},
            prefix="ck_",
        )
        for name in _node_key_points(node)
    ] or [stable_hash({"course": course_id, "node": node_id}, prefix="ck_")]


def _objective_ref(course_data: dict[str, Any], node: dict[str, Any]) -> str:
    return str(
        node.get("objective_id")
        or stable_hash(
            {
                "course": course_data.get("course_id"),
                "node": node.get("node_id"),
                "objective": node.get("learning_objective") or node.get("node_name"),
            },
            prefix="obj_",
        )
    )


def _question_type(course_data: dict[str, Any], level: str) -> str:
    if level == "concept_check":
        return "short_answer"
    mode = str((course_data.get("subject_pedagogy_profile") or {}).get("primary_mode") or "general")
    return {
        "math_formal": "worked_solution",
        "programming_engineering": "implementation_task",
        "natural_science": "evidence_analysis",
        "life_medical": "mechanism_explanation",
        "humanities_social": "source_argument",
        "language_learning": "language_production",
        "business_career": "scenario_deliverable",
    }.get(mode, "short_answer")


def _generated_criteria(node: dict[str, Any], level: str) -> list[str]:
    key_points = _node_key_points(node)
    if level == "concept_check":
        return [
            f"准确说明{next(iter(key_points), node.get('node_name') or '核心概念')}的含义",
            "指出成立条件或适用边界",
            "不混淆相近概念",
        ]
    if level == "objective_practice":
        return [
            "根据输入材料选择合适方法并说明依据",
            "给出可检查的执行或推理过程",
            "检查结果并说明条件或局限",
        ]
    return _assessment_items(node) + ["说明关键依据", "展示可复核过程", "执行结果检查"]


def _variant_condition(
    course_data: dict[str, Any],
    node: dict[str, Any],
    index: int,
) -> str:
    key_points = _node_key_points(node)
    seed = index + 2
    mode = str(
        (course_data.get("subject_pedagogy_profile") or {}).get("primary_mode")
        or "general"
    )
    joined = " ".join(key_points)
    if mode == "math_formal" or any(
        term in joined for term in ("矩阵", "行列式", "方程", "线性")
    ):
        variants = [
            f"数据对象 A=[[{seed},2],[1,{seed + 1}]]，向量 b=[{seed + 3},{seed + 5}]；边界条件为第二行不得整体约去",
            f"记录表含三组值 (1,{seed})、(2,{seed + 2})、(3,{seed + 5})，另有候选异常值 (3,{seed - 1})",
            f"对象甲用矩阵 [[{seed},1],[0,{seed + 1}]] 表示，对象乙用关系式 y={seed}x+1 表示；二者均须保留原始量纲",
        ]
    elif mode == "programming_engineering":
        variants = [
            f'输入 JSON={{"records":[{seed},{seed + 2},{seed + 2},null],"limit":{seed + 5}}}；null 必须单独处理',
            f"日志依次为 START、VALUE={seed}、VALUE={seed + 3}、RETRY、END；最多允许 1 次重试",
            f"接口样例包含状态码 200、409、503，请求预算为 {seed + 4} 次且结果必须可重放",
        ]
    elif mode in {"natural_science", "life_medical"}:
        variants = [
            f"对照组观测值为 {seed}、{seed + 1}、{seed + 2}，实验组为 {seed + 3}、{seed + 4}、{seed + 8}；第三次测量存在仪器漂移",
            f"样本甲在 0、10、20 分钟的读数为 {seed}、{seed + 2}、{seed + 5}，样本乙为 {seed}、{seed + 1}、{seed + 1}；环境温度恒定",
            f"案例记录包含基线值 {seed * 5}、干预后值 {seed * 4} 与复测值 {seed * 4 + 2}；不得据此推断未记录因素",
        ]
    elif mode in {"humanities_social", "language_learning"}:
        variants = [
            f"材料甲主张“{key_points[0]}是首要因素”，材料乙以编号 E{seed} 的反例提出限制；两份材料的时间背景相差 10 年",
            f"对话记录中发言者 A 陈述事实 F{seed}，发言者 B 提出结论 C{seed + 1}，但省略了连接二者的依据",
            f"短文包含观点 P{seed}、证据 E{seed} 与一个无关细节 N{seed}；结论不得超出证据范围",
        ]
    elif mode == "business_career":
        variants = [
            f"方案甲成本 {seed * 10} 万元、周期 {seed + 2} 周，方案乙成本 {seed * 12} 万元、周期 {seed} 周；预算上限 {seed * 11} 万元",
            f"三期数据为收入 {seed * 20}/{seed * 22}/{seed * 25} 万元，投诉率 2%/3%/5%；不得只按收入排序",
            f"客户 A 权重 0.5、客户 B 权重 0.3、客户 C 权重 0.2；候选方案评分分别为 {seed + 1}、{seed + 3}、{seed + 2}",
        ]
    else:
        variants = [
            f"案例 Q{seed} 含事实 F1={seed * 3}、F2={seed * 3 + 4}，约束 C1 为总量不得超过 {seed * 7}；另有无关记录 N={seed + 9}",
            f"对象甲满足条件“{key_points[0]}”，对象乙只满足“{key_points[-1]}”；记录编号分别为 A{seed} 与 B{seed + 1}",
            f"材料表列出基线值 {seed * 4}、调整值 {seed * 4 + 3} 和复核值 {seed * 4 + 2}；允许误差为 ±1",
        ]
    return variants[index % len(variants)]


def _cross_chapter_material(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> str:
    mode = str(
        (course_data.get("subject_pedagogy_profile") or {}).get("primary_mode")
        or "general"
    )
    labels = [
        str(node.get("node_name") or node.get("node_id") or "")
        for node in nodes[:3]
    ]
    if mode == "programming_engineering":
        return (
            f"项目 R7 收到 120 条记录，其中 8 条缺失、12 条重复；处理时限 2 秒，"
            f"失败后只允许重试 1 次。验收同时检查{_join_names(labels)}。"
        )
    if mode in {"natural_science", "life_medical"}:
        return (
            f"同一对象在 0、10、20 分钟的读数为 12、17、19，对照读数为 12、13、13；"
            f"第二次测量存在 ±1 误差，结论须联合解释{_join_names(labels)}。"
        )
    if mode == "business_career":
        return (
            f"方案 A 成本 80 万、周期 6 周、风险评分 3；方案 B 成本 65 万、周期 9 周、"
            f"风险评分 2；预算上限 75 万且必须联合运用{_join_names(labels)}。"
        )
    return (
        f"案例 Z9 的基线记录为 24、31、29，调整后记录为 27、30、34；总量上限 95，"
        f"其中记录 34 仍待复核。分析必须分别调用{_join_names(labels)}并说明连接依据。"
    )


def _assessment_items(node: dict[str, Any]) -> list[str]:
    values = [str(item).strip() for item in node.get("assessment") or [] if str(item).strip()]
    return values or [str(node.get("learning_objective") or f"完成{node.get('node_name') or '本节'}的应用任务")]


def _node_key_points(node: dict[str, Any]) -> list[str]:
    values = [str(item).strip() for item in node.get("key_points") or [] if str(item).strip()]
    if values:
        return values
    return [str(node.get("node_name") or "当前知识点")]


def _node_refs(node: dict[str, Any], field: str) -> list[str]:
    return _unique(str(value) for value in node.get(field) or [] if str(value).strip())


def _node_difficulty(course_data: dict[str, Any], node: dict[str, Any]) -> str:
    contract = node.get("difficulty_contract") or {}
    return str(
        contract.get("target_level")
        or (contract.get("challenge") or {}).get("level")
        or course_data.get("difficulty")
        or "intermediate"
    )


def _review_queue(items: list[dict[str, Any]]) -> dict[str, Any]:
    blocking = [
        {
            "item_id": item.get("item_id"),
            "revision_id": item.get("revision_id"),
            "node_id": item.get("node_id"),
            "assessment_role": item.get("assessment_role"),
            "risk_flags": deepcopy(item.get("risk_flags") or []),
            "quality_status": (item.get("quality_report") or {}).get("status"),
        }
        for item in items
        if item.get("lifecycle_status") == "needs_review"
    ]
    return {
        "blocking_count": len(blocking),
        "items": blocking,
    }


def _find_item(bundle: dict[str, Any], revision_id: str) -> dict[str, Any]:
    item = next(
        (
            value
            for value in bundle.get("items") or []
            if str(value.get("revision_id") or "") == str(revision_id or "")
        ),
        None,
    )
    if not item:
        raise KeyError(f"Unknown question bank item revision: {revision_id}")
    return item


def _item_revision_id(item: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in item.items()
        if key not in {
            "revision_id",
            "formal_task",
            "formal_task_revision_id",
            "review_history",
            "review_status",
            "lifecycle_status",
            "review_required",
            "edited_at",
            "edited_by",
            "created_at",
        }
    }
    return stable_hash(payload, prefix="qbir_")


def _without_volatile_timestamps(value: Any) -> Any:
    volatile_fields = {
        "compiled_at",
        "completed_at",
        "created_at",
        "edited_at",
        "retrieved_at",
        "reviewed_at",
    }
    if isinstance(value, dict):
        return {
            key: _without_volatile_timestamps(item)
            for key, item in value.items()
            if key not in volatile_fields
        }
    if isinstance(value, list):
        return [_without_volatile_timestamps(item) for item in value]
    return value


def _extract(pattern: re.Pattern[str], value: str) -> str:
    match = pattern.search(value)
    return _clean_text(match.group(1)) if match else ""


def _extract_score(value: str) -> int | None:
    match = _SCORE_RE.search(value)
    return int(match.group(1)) if match else None


def _clean_answer(value: str) -> str | None:
    cleaned = _clean_text(value).rstrip("。；;，, ")
    return cleaned or None


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split_options(value: str) -> tuple[str, list[dict[str, str]]]:
    matches = list(_OPTION_RE.finditer(value))
    if len(matches) < 2:
        return _clean_text(value), []
    options = [
        {
            "option_id": match.group(1).upper(),
            "text": _clean_text(match.group(2)),
        }
        for match in matches
    ]
    prompt = _clean_text(value[: matches[0].start()])
    return prompt or _clean_text(value), options


def _normalize_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()


def _storage_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if not _STORAGE_ID_RE.fullmatch(normalized) or normalized in {".", ".."}:
        raise ValueError("invalid question bank storage identifier")
    return normalized


def _estimated_minutes(prompt: str) -> int:
    return max(3, min(30, len(prompt) // 80 + 3))


def _join_names(values: Iterable[Any]) -> str:
    names = [str(value).strip() for value in values if str(value).strip()]
    return "、".join(names) if names else "相关概念"


def _unique(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _distribution(items: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        value = str(item.get(field) or "").strip()
        if value:
            result[value] = result.get(value, 0) + 1
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


question_bank_repository = QuestionBankRepository()


__all__ = [
    "FINAL_ASSESSMENT_ROLES",
    "QUESTION_BANK_SCHEMA",
    "QuestionBankRepository",
    "approved_formal_tasks",
    "build_question_bank",
    "evaluate_question_item_quality",
    "filter_question_bank_items",
    "formal_task_from_question_bank_item",
    "question_bank_repository",
    "reconcile_question_bank",
    "refresh_question_bank_bundle",
    "review_question_bank_item",
    "revise_question_bank_item",
]
