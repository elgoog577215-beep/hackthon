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

from assessment_blueprint import (
    compile_course_assessment_blueprint,
    slot_for,
)
from assessment_compiler import (
    compile_formal_task_contract,
    normalize_public_options,
)
from assessment_contracts import (
    compile_assessment_objectives,
    compile_course_assessment_profile,
)
from assessment_diversity import (
    build_diversity_signature,
    compare_diversity_signatures,
)
from assessment_generation import generate_universal_question_contract
from course_versioning import stable_hash
from practice_contracts import (
    project_default_single_choice,
)
from question_generation import (
    generate_cross_chapter_contract,
    generate_question_contract,
    validate_question_spec,
)
from storage import DATA_DIR

QUESTION_BANK_SCHEMA = "question_bank_bundle_v1"
QUESTION_ITEM_SCHEMA = "question_bank_item_v1"
QUESTION_SOURCE_TYPES = {"imported", "web_reference", "generated", "variant", "legacy_compiled"}
QUESTION_LIFECYCLE_STATES = {"candidate", "needs_review", "approved", "rejected", "retired"}
QUESTION_REVIEW_DECISIONS = {"approved", "rejected"}
FINAL_ASSESSMENT_ROLES = {"coverage_task", "cross_chapter_transfer"}
QUESTION_REVIEW_TIERS = {
    "auto_publish",
    "sample_review",
    "mandatory_review",
}
QUESTION_REVIEW_POLICY_SCHEMA = "exception_driven_question_quality_v1"
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

    assessment_profile = compile_course_assessment_profile(course_data)
    assessment_objectives = compile_assessment_objectives(
        course_data,
        assessment_profile,
    )
    assessment_blueprint = deepcopy(
        course_data.get("_course_assessment_blueprint") or {}
    )
    if assessment_blueprint.get("schema_version") != (
        "course_assessment_blueprint_v2"
    ):
        assessment_blueprint = compile_course_assessment_blueprint(
            course_data,
            profile=assessment_profile,
            objectives=assessment_objectives,
        )
    generated, solution_envelopes = _generated_course_items(
        course_data,
        nodes,
        imported,
        profile=assessment_profile,
        objectives=assessment_objectives,
        blueprint=assessment_blueprint,
    )
    finals, final_solutions = _comprehensive_items(
        course_data,
        nodes,
        imported,
        profile=assessment_profile,
        objectives=assessment_objectives,
    )
    legacy_blueprint_summary = _assessment_blueprint(
        course_data,
        finals,
        imported,
    )
    for key in (
        "purpose",
        "basis",
        "distribution_inferred",
        "focus",
        "task_count",
        "question_type_distribution",
        "difficulty_distribution",
        "score_distribution",
    ):
        if key in legacy_blueprint_summary:
            assessment_blueprint.setdefault(
                key,
                deepcopy(legacy_blueprint_summary[key]),
            )
    solution_envelopes.update(final_solutions)
    legacy = [_legacy_item(course_data, item) for item in legacy_tasks]
    items = [*imported, *generated, *finals, *legacy]
    _mark_near_duplicate_risks(items)
    _apply_tiered_review_policy(items, assessment_profile)

    coverage = _coverage_report(course_data, nodes, items, imported)
    reference_package = deepcopy(
        course_data.get("_question_reference_package") or {}
    )
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
        "assessment_profile": assessment_profile,
        "assessment_objectives": assessment_objectives,
        "solution_envelopes": solution_envelopes,
        "items": items,
        "coverage": coverage,
        "assessment_blueprint": assessment_blueprint,
        "reference_package": _public_reference_package_summary(
            reference_package
        ),
        "generation_audit": deepcopy(
            course_data.get("_assessment_generation_audit") or {}
        ),
        "review_policy": deepcopy(
            assessment_profile.get("review_policy") or {}
        ),
        "review_queue": _review_queue(items),
        "web_enrichment": {
            "enabled": (
                (
                    reference_package.get("retrieval_mode")
                    != "off"
                )
                if reference_package
                else bool(
                    (
                        assessment_profile.get("source_policy")
                        or {}
                    ).get("web_enabled")
                )
            ),
            "mode": (
                reference_package.get("retrieval_mode")
                or (
                    "auto_on_gap"
                    if (
                        (
                            assessment_profile.get(
                                "source_policy"
                            )
                            or {}
                        ).get("web_enabled")
                    )
                    else "off"
                )
            ),
            "status": (
                (reference_package.get("web") or {}).get("status")
                or "not_started"
            ),
            "query_count": int(
                (reference_package.get("web") or {}).get(
                    "query_count"
                )
                or 0
            ),
            "source_count": int(
                (reference_package.get("web") or {}).get(
                    "source_count"
                )
                or 0
            ),
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
    if decision == "approved" and not (
        item.get("quality_report") or {}
    ).get("passed"):
        raise ValueError(
            "question with failed quality must be revised before approval"
        )
    item["lifecycle_status"] = decision
    item["review_status"] = decision
    item["review_required"] = False
    if decision == "approved":
        item["generation_status"] = "published"
    else:
        item["generation_status"] = "rework_requested"
        item["rework_requested_at"] = _now()
        item["rework_requested_by"] = str(reviewer_id)[:200]
        item["rework_reason"] = str(note or "")[:2000]
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
    if (
        "answer_spec" in patch
        and (item.get("question_spec") or {}).get("schema_version")
        == "question_spec_v2"
    ):
        raise ValueError(
            "V2 question answers must be revised through the private solution contract"
        )
    solution_revision_id = str(
        item.get("solution_revision_id") or ""
    )
    if solution_revision_id:
        solution = (
            result.get("solution_envelopes") or {}
        ).get(solution_revision_id)
        if solution:
            item["_solution_envelope"] = deepcopy(solution)
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
    _apply_compiled_contract_quality(
        item,
        item.get("_solution_envelope") or None,
    )
    item["revision_id"] = _item_revision_id(item)
    item["formal_task"] = _stored_formal_task_from_item(item)
    item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
    item.pop("_solution_envelope", None)
    result["review_queue"] = _review_queue(result.get("items") or [])
    return refresh_question_bank_bundle(result)


def filter_question_bank_items(
    bundle: dict[str, Any],
    *,
    node_id: str | None = None,
    source_type: str | None = None,
    lifecycle_status: str | None = None,
    risk: str | None = None,
    archetype_id: str | None = None,
    validation_mode: str | None = None,
    risk_level: str | None = None,
    objective_id: str | None = None,
    generation_status: str | None = None,
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
    if archetype_id:
        items = [
            item
            for item in items
            if item.get("archetype_id") == archetype_id
        ]
    if validation_mode:
        items = [
            item
            for item in items
            if item.get("validation_mode") == validation_mode
        ]
    if risk_level:
        items = [
            item
            for item in items
            if item.get("risk_level") == risk_level
        ]
    if objective_id:
        items = [
            item
            for item in items
            if item.get("objective_id") == objective_id
        ]
    if generation_status:
        items = [
            item
            for item in items
            if item.get("generation_status") == generation_status
        ]
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
        if not (item.get("quality_report") or {}).get("passed"):
            continue
        if assessment_role and item.get("assessment_role") != assessment_role:
            continue
        hydrated = deepcopy(item)
        solution_revision_id = str(
            item.get("solution_revision_id") or ""
        )
        solution = (
            bundle.get("solution_envelopes") or {}
        ).get(solution_revision_id)
        if solution:
            hydrated["_solution_envelope"] = deepcopy(solution)
        projected = _formal_task_from_item(hydrated)
        if (
            (item.get("question_spec") or {}).get(
                "schema_version"
            )
            == "question_spec_v2"
            and not (
                projected.get(
                    "compiled_contract_validation"
                )
                or {}
            ).get("passed")
        ):
            continue
        projected["review_status"] = "approved"
        projected["source_type"] = item.get("source_type")
        projected["question_bank_item_revision_id"] = item.get(
            "revision_id"
        )
        tasks.append(projected)
    return tasks


def formal_task_from_question_bank_item(item: dict[str, Any]) -> dict[str, Any]:
    return _formal_task_from_item(item)


def finalize_v2_question_bank_item(
    item: dict[str, Any],
    solution_envelope: dict[str, Any],
) -> dict[str, Any]:
    """Freeze one V2 item while keeping its solution outside the item."""
    result = deepcopy(item)
    result["_solution_envelope"] = deepcopy(solution_envelope)
    result["solution_revision_id"] = solution_envelope.get(
        "solution_revision_id"
    )
    result["hint_contract"] = _hint_contract(result)
    result["quality_report"] = evaluate_question_item_quality(result)
    _apply_compiled_contract_quality(result, solution_envelope)
    result["lifecycle_status"] = _initial_status(result)
    result["review_status"] = result["lifecycle_status"]
    result["revision_id"] = _item_revision_id(result)
    result["formal_task"] = _stored_formal_task_from_item(result)
    result["formal_task_revision_id"] = result["formal_task"][
        "revision_id"
    ]
    result.pop("_solution_envelope", None)
    return result


def refresh_question_bank_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(bundle)
    result["review_queue"] = _review_queue(result.get("items") or [])
    payload = {
        "schema_version": result.get("schema_version"),
        "course_id": result.get("course_id"),
        "items": result.get("items") or [],
        "coverage": result.get("coverage") or {},
        "assessment_blueprint": result.get("assessment_blueprint") or {},
        "reference_package": result.get("reference_package") or {},
        "generation_audit": result.get("generation_audit") or {},
        "web_enrichment": result.get("web_enrichment") or {},
        "assessment_profile": result.get("assessment_profile") or {},
        "assessment_objectives": (
            result.get("assessment_objectives") or []
        ),
        "solution_envelopes": result.get("solution_envelopes") or {},
        "review_policy": result.get("review_policy") or {},
    }
    result["bundle_revision_id"] = stable_hash(
        _without_volatile_timestamps(payload),
        prefix="qbb_",
    )
    return result


def migrate_question_bank_review_policy(
    course_data: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """Idempotently upgrade an active bank to exception-driven moderation."""
    profile = compile_course_assessment_profile(course_data)
    current_policy = bundle.get("review_policy") or {}
    desired_policy = profile.get("review_policy") or {}
    if (
        current_policy.get("schema_version")
        == QUESTION_REVIEW_POLICY_SCHEMA
        and current_policy == desired_policy
    ):
        return deepcopy(bundle)
    result = deepcopy(bundle)
    result["assessment_profile"] = profile
    result["review_policy"] = deepcopy(desired_policy)
    for item in result.get("items") or []:
        validation = (
            item.get("solution_validation")
            or item.get("domain_validation")
            or {}
        )
        legacy_blanket_review = bool(
            not item.get("review_history")
            and item.get("assessment_role")
            not in FINAL_ASSESSMENT_ROLES
            and not (item.get("risk_flags") or [])
            and (item.get("quality_report") or {}).get("passed")
            and (
                not validation
                or validation.get("passed")
            )
        )
        if legacy_blanket_review:
            item["review_required"] = False
    _apply_tiered_review_policy(
        result.get("items") or [],
        profile,
    )
    result["policy_migration"] = {
        "schema_version": QUESTION_REVIEW_POLICY_SCHEMA,
        "migrated_at": _now(),
    }
    return recalculate_question_bank_coverage(
        course_data,
        result,
    )


def load_active_question_bank(
    course_data: dict[str, Any],
    *,
    repository: QuestionBankRepository | None = None,
) -> dict[str, Any] | None:
    """Load the active bank through the current review policy.

    Every student and teacher consumer must use this boundary instead of
    reading the repository directly.  Legacy policy migration is idempotent
    and activates one immutable migrated revision before returning it.
    """
    course_id = str(course_data.get("course_id") or "").strip()
    if not course_id:
        raise ValueError(
            "course_id is required to load an active question bank"
        )
    active_repository = repository or question_bank_repository
    bundle = active_repository.load_bundle(course_id)
    if not bundle:
        return None
    migrated = migrate_question_bank_review_policy(
        course_data,
        bundle,
    )
    if (
        migrated.get("bundle_revision_id")
        == bundle.get("bundle_revision_id")
    ):
        return bundle
    save_bundle = getattr(active_repository, "save_bundle", None)
    if callable(save_bundle):
        return save_bundle(
            course_id,
            migrated,
        )
    return migrated


def reconcile_question_bank(
    previous: dict[str, Any] | None,
    rebuilt: dict[str, Any],
    *,
    preserve_reviewed: bool = True,
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
        if (
            preserve_reviewed
            and old_item
            and _should_preserve_reviewed_item(old_item)
        ):
            merged.append(deepcopy(old_item))
        else:
            merged.append(deepcopy(fresh_item))
    active_node_ids = {
        str(objective.get("node_id") or "")
        for objective in rebuilt.get("assessment_objectives") or []
        if objective.get("node_id")
    }
    for item_id, old_item in old_by_item.items():
        if item_id in present_ids:
            continue
        old_node_ids = {
            str(value)
            for value in (
                old_item.get("node_ids")
                or [old_item.get("node_id")]
            )
            if value
        }
        if (
            preserve_reviewed
            and _should_preserve_reviewed_item(old_item)
            and bool(old_node_ids & active_node_ids)
        ):
            merged.append(deepcopy(old_item))
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
    previous_solutions = previous.get("solution_envelopes") or {}
    rebuilt_solutions = rebuilt.get("solution_envelopes") or {}
    referenced_solution_ids = {
        str(item.get("solution_revision_id") or "")
        for item in merged
        if item.get("solution_revision_id")
    }
    result["solution_envelopes"] = {
        solution_id: deepcopy(
            rebuilt_solutions.get(solution_id)
            or previous_solutions.get(solution_id)
        )
        for solution_id in referenced_solution_ids
        if (
            rebuilt_solutions.get(solution_id)
            or previous_solutions.get(solution_id)
        )
    }
    return refresh_question_bank_bundle(result)


def reconcile_scoped_question_bank(
    previous: dict[str, Any] | None,
    rebuilt: dict[str, Any],
    *,
    node_ids: Iterable[str],
    preserve_reviewed: bool = True,
    preserve_global_assessments: bool = False,
    practice_levels_by_node: dict[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Replace only selected nodes while preserving other active revisions."""
    if not previous:
        return refresh_question_bank_bundle(rebuilt)
    if str(previous.get("course_id") or "") != str(
        rebuilt.get("course_id") or ""
    ):
        raise ValueError(
            "cannot reconcile question banks from different course scopes"
        )
    selected = {
        str(node_id).strip()
        for node_id in node_ids
        if str(node_id).strip()
    }
    if not selected:
        raise ValueError("node_ids are required for scoped reconciliation")
    selected_levels = {
        str(node_id): {
            str(level)
            for level in levels
            if str(level).strip()
        }
        for node_id, levels in (practice_levels_by_node or {}).items()
    }

    def in_scope(item: dict[str, Any]) -> bool:
        if (
            preserve_global_assessments
            and str(item.get("assessment_role") or "")
            in FINAL_ASSESSMENT_ROLES
        ):
            return False
        item_nodes = {
            str(value)
            for value in (
                item.get("node_ids")
                or [item.get("node_id")]
            )
            if value
        }
        matched_nodes = item_nodes & selected
        if not matched_nodes:
            return False
        if not selected_levels:
            return True
        practice_level = str(item.get("practice_level") or "")
        return any(
            not selected_levels.get(node_id)
            or practice_level in selected_levels[node_id]
            for node_id in matched_nodes
        )

    previous_items = list(previous.get("items") or [])
    rebuilt_items = list(rebuilt.get("items") or [])
    previous_slice = {
        **deepcopy(previous),
        "items": [
            deepcopy(item)
            for item in previous_items
            if in_scope(item)
        ],
    }
    rebuilt_slice = {
        **deepcopy(rebuilt),
        "items": [
            deepcopy(item)
            for item in rebuilt_items
            if in_scope(item)
        ],
    }
    reconciled_slice = reconcile_question_bank(
        previous_slice,
        rebuilt_slice,
        preserve_reviewed=preserve_reviewed,
    )
    merged_items = [
        *deepcopy(reconciled_slice.get("items") or []),
        *[
            deepcopy(item)
            for item in previous_items
            if not in_scope(item)
        ],
    ]

    old_objectives = list(
        previous.get("assessment_objectives") or []
    )
    fresh_objectives = list(
        rebuilt.get("assessment_objectives") or []
    )
    merged_objectives = [
        deepcopy(objective)
        for objective in fresh_objectives
        if str(objective.get("node_id") or "") in selected
    ]
    merged_objectives.extend(
        deepcopy(objective)
        for objective in old_objectives
        if str(objective.get("node_id") or "") not in selected
    )

    previous_solutions = previous.get("solution_envelopes") or {}
    rebuilt_solutions = rebuilt.get("solution_envelopes") or {}
    referenced_solution_ids = {
        str(item.get("solution_revision_id") or "")
        for item in merged_items
        if item.get("solution_revision_id")
    }
    result = {
        **deepcopy(rebuilt),
        "items": merged_items,
        "assessment_objectives": merged_objectives,
        "assessment_blueprint": _merge_scoped_assessment_blueprint(
            previous.get("assessment_blueprint") or {},
            rebuilt.get("assessment_blueprint") or {},
            selected,
        ),
        "reference_package": _merge_scoped_reference_package(
            previous.get("reference_package") or {},
            rebuilt.get("reference_package") or {},
            selected,
        ),
        "solution_envelopes": {
            solution_id: deepcopy(
                rebuilt_solutions.get(solution_id)
                or previous_solutions.get(solution_id)
            )
            for solution_id in referenced_solution_ids
            if (
                rebuilt_solutions.get(solution_id)
                or previous_solutions.get(solution_id)
            )
        },
    }
    return refresh_question_bank_bundle(result)


def _should_preserve_reviewed_item(
    item: dict[str, Any],
) -> bool:
    """Keep human decisions and teacher sources, not auto-published output."""
    return bool(
        item.get("review_history")
        or item.get("edited_by")
        or item.get("lifecycle_status") == "rejected"
        or item.get("source_type") == "imported"
    )


def _merge_scoped_assessment_blueprint(
    previous: dict[str, Any],
    rebuilt: dict[str, Any],
    selected_node_ids: set[str],
) -> dict[str, Any]:
    """Keep each untouched chapter bound to the blueprint that made its items."""
    if (
        rebuilt.get("schema_version")
        != "course_assessment_blueprint_v2"
    ):
        return deepcopy(rebuilt or previous)
    if (
        previous.get("schema_version")
        != "course_assessment_blueprint_v2"
    ):
        return deepcopy(rebuilt)
    fresh_nodes = {
        str(node.get("node_id") or ""): deepcopy(node)
        for node in rebuilt.get("nodes") or []
        if node.get("node_id")
    }
    old_nodes = {
        str(node.get("node_id") or ""): deepcopy(node)
        for node in previous.get("nodes") or []
        if node.get("node_id")
    }
    node_order = [
        *[
            str(node.get("node_id") or "")
            for node in rebuilt.get("nodes") or []
            if node.get("node_id")
        ],
        *[
            str(node.get("node_id") or "")
            for node in previous.get("nodes") or []
            if (
                node.get("node_id")
                and str(node.get("node_id")) not in fresh_nodes
            )
        ],
    ]
    merged_nodes = [
        deepcopy(
            fresh_nodes.get(node_id)
            if node_id in selected_node_ids
            else old_nodes.get(node_id)
            or fresh_nodes.get(node_id)
        )
        for node_id in node_order
        if (
            (
                fresh_nodes.get(node_id)
                if node_id in selected_node_ids
                else old_nodes.get(node_id)
                or fresh_nodes.get(node_id)
            )
            is not None
        )
    ]
    if merged_nodes == list(rebuilt.get("nodes") or []):
        return deepcopy(rebuilt)
    result = {
        **deepcopy(rebuilt),
        "nodes": merged_nodes,
    }
    result["blueprint_revision_id"] = stable_hash(
        {
            key: value
            for key, value in result.items()
            if key != "blueprint_revision_id"
        },
        prefix="abp_",
    )
    return result


def _merge_scoped_reference_package(
    previous: dict[str, Any],
    rebuilt: dict[str, Any],
    selected_node_ids: set[str],
) -> dict[str, Any]:
    """Merge node-scoped RAG coverage without erasing untouched chapters."""
    if (
        rebuilt.get("schema_version")
        != "question_reference_package_v2"
    ):
        return deepcopy(rebuilt or previous)
    if (
        previous.get("schema_version")
        != "question_reference_package_v2"
    ):
        return deepcopy(rebuilt)

    result = deepcopy(rebuilt)
    coverage_keys = {
        "content_coverage": lambda item: (
            str(item.get("objective_id") or ""),
        ),
        "method_coverage": lambda item: (
            str(item.get("objective_id") or ""),
            str(item.get("question_type") or ""),
        ),
        "objective_coverage": lambda item: (
            str(item.get("objective_id") or ""),
        ),
    }
    for field, identity in coverage_keys.items():
        old_values = [
            deepcopy(item)
            for item in previous.get(field) or []
            if isinstance(item, dict)
        ]
        fresh_values = [
            deepcopy(item)
            for item in rebuilt.get(field) or []
            if isinstance(item, dict)
        ]
        fresh_by_key = {
            identity(item): item
            for item in fresh_values
        }
        old_by_key = {
            identity(item): item
            for item in old_values
        }
        order = list(dict.fromkeys([
            *[identity(item) for item in fresh_values],
            *[identity(item) for item in old_values],
        ]))
        merged: list[dict[str, Any]] = []
        for key in order:
            fresh = fresh_by_key.get(key)
            old = old_by_key.get(key)
            node_id = str(
                (fresh or old or {}).get("node_id") or ""
            )
            value = (
                fresh
                if node_id in selected_node_ids
                else old or fresh
            )
            if value is not None:
                merged.append(deepcopy(value))
        result[field] = merged

    result["content_reference_count"] = max(
        int(previous.get("content_reference_count") or 0),
        int(rebuilt.get("content_reference_count") or 0),
    )
    result["authoring_pattern_count"] = max(
        int(previous.get("authoring_pattern_count") or 0),
        int(rebuilt.get("authoring_pattern_count") or 0),
    )
    old_distribution = previous.get("source_distribution") or {}
    fresh_distribution = rebuilt.get("source_distribution") or {}
    result["source_distribution"] = {
        source_type: max(
            int(old_distribution.get(source_type) or 0),
            int(fresh_distribution.get(source_type) or 0),
        )
        for source_type in {
            *old_distribution,
            *fresh_distribution,
        }
    }
    result["source_count"] = max(
        int(previous.get("source_count") or 0),
        int(rebuilt.get("source_count") or 0),
        sum(result["source_distribution"].values()),
    )
    result.pop("package_revision_id", None)
    result["package_revision_id"] = stable_hash(
        result,
        prefix="qrp_",
    )
    return result


def reconcile_item_question_bank(
    previous: dict[str, Any] | None,
    rebuilt: dict[str, Any],
    *,
    revision_ids: Iterable[str],
) -> dict[str, Any]:
    """Replace only explicitly rejected item revisions with fresh revisions."""
    if not previous:
        return refresh_question_bank_bundle(rebuilt)
    if str(previous.get("course_id") or "") != str(
        rebuilt.get("course_id") or ""
    ):
        raise ValueError(
            "cannot reconcile question banks from different course scopes"
        )
    selected_revisions = {
        str(revision_id).strip()
        for revision_id in revision_ids
        if str(revision_id).strip()
    }
    if not selected_revisions:
        raise ValueError(
            "revision_ids are required for item reconciliation"
        )
    previous_items = list(previous.get("items") or [])
    selected_items = [
        item
        for item in previous_items
        if str(item.get("revision_id") or "") in selected_revisions
    ]
    if len(selected_items) != len(selected_revisions):
        known = {
            str(item.get("revision_id") or "")
            for item in selected_items
        }
        raise ValueError(
            "unknown question revisions: "
            f"{sorted(selected_revisions - known)}"
        )

    selected_item_ids = {
        str(item.get("item_id") or "")
        for item in selected_items
        if item.get("item_id")
    }
    fresh_by_item_id = {
        str(item.get("item_id") or ""): deepcopy(item)
        for item in rebuilt.get("items") or []
        if str(item.get("item_id") or "") in selected_item_ids
    }
    missing_replacements = sorted(
        selected_item_ids - set(fresh_by_item_id)
    )
    if missing_replacements:
        raise ValueError(
            "rebuilt bank did not produce replacements for items: "
            f"{missing_replacements}"
        )

    merged_items = [
        deepcopy(item)
        for item in previous_items
        if str(item.get("item_id") or "") not in selected_item_ids
    ]
    merged_items.extend(
        fresh_by_item_id[item_id]
        for item_id in sorted(selected_item_ids)
    )
    previous_solutions = previous.get("solution_envelopes") or {}
    rebuilt_solutions = rebuilt.get("solution_envelopes") or {}
    referenced_solution_ids = {
        str(item.get("solution_revision_id") or "")
        for item in merged_items
        if item.get("solution_revision_id")
    }
    result = {
        **deepcopy(previous),
        "assessment_profile": deepcopy(
            rebuilt.get("assessment_profile")
            or previous.get("assessment_profile")
            or {}
        ),
        "review_policy": deepcopy(
            rebuilt.get("review_policy")
            or previous.get("review_policy")
            or {}
        ),
        "items": merged_items,
        "solution_envelopes": {
            solution_id: deepcopy(
                rebuilt_solutions.get(solution_id)
                or previous_solutions.get(solution_id)
            )
            for solution_id in referenced_solution_ids
            if (
                rebuilt_solutions.get(solution_id)
                or previous_solutions.get(solution_id)
            )
        },
    }
    return refresh_question_bank_bundle(result)


def recalculate_question_bank_coverage(
    course_data: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """Refresh coverage and review state after scoped reconciliation."""
    result = deepcopy(bundle)
    nodes = [
        deepcopy(node)
        for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    ]
    items = list(result.get("items") or [])
    imported = [
        item
        for item in items
        if item.get("source_type") in {
            "imported",
            "legacy_compiled",
        }
    ]
    result["coverage"] = _coverage_report(
        course_data,
        nodes,
        items,
        imported,
    )
    result["review_queue"] = _review_queue(items)
    return refresh_question_bank_bundle(result)


def evaluate_question_item_quality(item: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    prompt = str(item.get("prompt") or "").strip()
    answer_spec = item.get("answer_spec") or {}
    private_solution = item.get("_solution_envelope") or {}
    is_v2 = (
        (item.get("question_spec") or {}).get("schema_version")
        == "question_spec_v2"
    )
    criteria = [str(value).strip() for value in answer_spec.get("criteria") or [] if str(value).strip()]
    if is_v2:
        criteria = [
            str(value).strip()
            for value in private_solution.get("rubric") or []
            if str(value).strip()
        ]
    source_type = str(item.get("source_type") or "")
    requires_structured_spec = source_type in {"generated", "variant"}
    domain_validation: dict[str, Any] = {
        "passed": True,
        "status": "passed",
        "issues": [],
        "checks": {},
    }
    if requires_structured_spec:
        question_spec = item.get("question_spec")
        if not isinstance(question_spec, dict):
            issues.append({
                "code": "question:structured_spec_missing",
                "severity": "critical",
            })
            domain_validation = {
                "passed": False,
                "status": "failed",
                "issues": [{
                    "code": "question:structured_spec_missing",
                    "severity": "critical",
                }],
                "checks": {},
            }
        elif is_v2:
            domain_validation = deepcopy(
                item.get("solution_validation") or {}
            )
            issues.extend(
                deepcopy(domain_validation.get("issues") or [])
            )
        else:
            domain_validation = validate_question_spec(question_spec)
            issues.extend(deepcopy(domain_validation.get("issues") or []))
    if len(prompt) < 12:
        issues.append({"code": "question:prompt_too_short", "severity": "critical"})
    if (
        item.get("source_type") in {"generated", "variant"}
        and is_generic_generated_prompt(prompt)
    ):
        issues.append({"code": "question:generic_prompt", "severity": "critical"})
    has_executable_solution = bool(
        criteria
        or answer_spec.get("correct_answer") is not None
        or answer_spec.get("correct_option_id") is not None
        or (
            is_v2
            and (
                private_solution.get("canonical_answer") is not None
                or private_solution.get("rubric")
            )
        )
    )
    if not has_executable_solution:
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
    if "semantic_near_duplicate" in (item.get("risk_flags") or []):
        issues.append({
            "code": "question:semantic_near_duplicate",
            "severity": "critical",
        })
    if "answer_conflict" in (item.get("risk_flags") or []):
        issues.append({"code": "question:answer_conflict", "severity": "critical"})
    has_reasoning_steps = bool(
        (
            (item.get("question_spec") or {}).get("reasoning_path")
            or {}
        ).get("steps")
        or (
            private_solution.get("solution_graph") or {}
        ).get("steps")
    )
    if requires_structured_spec and not has_reasoning_steps:
        issues.append({
            "code": "question:reasoning_path_missing",
            "severity": "critical",
        })
    if requires_structured_spec and not _has_actionable_reasoning_hints(item):
        issues.append({
            "code": "question:hint_not_actionable",
            "severity": "critical",
        })

    issues = _deduplicate_quality_issues(issues)
    critical = [issue for issue in issues if issue["severity"] == "critical"]
    status = "failed" if critical else ("needs_review" if issues else "passed")
    return {
        "schema_version": "question_item_quality_v1",
        "passed": not critical,
        "status": status,
        "issues": issues,
        "checks": {
            "structure": not any(
                issue["code"] in {
                    "question:prompt_too_short",
                    "question:generic_prompt",
                }
                for issue in issues
            ),
            "knowledge_and_difficulty": bool(item.get("course_knowledge_refs")) and bool(item.get("difficulty")),
            "source_and_rights": bool(item.get("source_records")),
            "answer_and_rubric": not any("answer" in issue["code"] for issue in critical),
            "domain_validation": bool(domain_validation.get("passed"))
            and domain_validation.get("status") == "passed",
            "semantic_alignment": (
                len(prompt) >= 12
                and not (
                    item.get("source_type") in {"generated", "variant"}
                    and is_generic_generated_prompt(prompt)
                )
                and bool(
                    has_executable_solution
                )
                and bool(domain_validation.get("passed"))
            ),
            "hint_safety": bool((item.get("hint_contract") or {}).get("leakage_check", {}).get("passed", True)),
            "hint_actionability": not any(
                issue["code"] in {
                    "question:reasoning_path_missing",
                    "question:hint_not_actionable",
                    "question:hint_not_path_derived",
                    "question:reasoning_path_schema_invalid",
                    "question:reasoning_operator_missing",
                    "question:reasoning_inputs_missing",
                    "question:reasoning_steps_incomplete",
                    "question:semantic_archetype_unavailable",
                    "question:solution_path_missing",
                }
                for issue in issues
            ),
        },
    }


def _apply_compiled_contract_quality(
    item: dict[str, Any],
    solution_envelope: dict[str, Any] | None,
) -> None:
    """Bind quality approval to the exact student-visible contract."""
    if (
        (item.get("question_spec") or {}).get("schema_version")
        != "question_spec_v2"
    ):
        return
    compiled = compile_formal_task_contract(
        item,
        solution_envelope,
    )
    validation = deepcopy(compiled["contract_validation"])
    item["compiled_contract_hash"] = compiled[
        "compiled_contract_hash"
    ]
    item["compiled_contract_validation"] = validation
    report = deepcopy(item.get("quality_report") or {})
    report.setdefault("hard_gates", {})
    report["hard_gates"]["final_contract"] = bool(
        validation.get("passed")
    )
    report["compiled_contract_hash"] = compiled[
        "compiled_contract_hash"
    ]
    if not validation.get("passed"):
        report["passed"] = False
        report["status"] = "failed"
        report["decision"] = "discard"
        report["issues"] = _deduplicate_quality_issues([
            *deepcopy(report.get("issues") or []),
            *deepcopy(validation.get("issues") or []),
        ])
    item["quality_report"] = report


def is_generic_generated_prompt(prompt: str) -> bool:
    """Identify legacy placeholders that name a topic but provide no task input."""
    normalized = " ".join(str(prompt or "").split())
    if not normalized:
        return True
    generic_markers = (
        "用自己的话说明",
        "成立或适用的关键条件",
        "在一个不同于正文示例的新情境中",
        "综合运用全部章节完成最终任务",
        "比较案例值",
        "边界值",
    )
    return any(marker in normalized for marker in generic_markers)


def _has_actionable_reasoning_hints(item: dict[str, Any]) -> bool:
    spec = item.get("question_spec") or {}
    path = spec.get("reasoning_path") or {}
    contract = item.get("hint_contract") or {}
    levels = contract.get("levels") or []
    if spec.get("schema_version") == "question_spec_v2":
        private_solution = item.get("_solution_envelope") or {}
        graph = private_solution.get("solution_graph") or {}
        return bool(
            graph.get("schema_version") == "solution_graph_v1"
            and graph.get("steps")
            and contract.get("generator") == "solution_graph_v1"
            and (
                contract.get("grounding") or {}
            ).get("solution_revision_id")
            == item.get("solution_revision_id")
            and {
                int(level.get("level") or 0)
                for level in levels
            } == {1, 2, 3}
            and all(
                len(str(level.get("content") or "").strip()) >= 12
                and level.get("step_refs")
                for level in levels
            )
            and (
                contract.get("leakage_check") or {}
            ).get("passed") is True
        )
    generic_markers = (
        "先确认题目要求的最终产物",
        "整理输入—选择方法—执行关键步骤—检查结果",
        "用一个不同情境做局部对照",
    )
    return bool(
        path.get("schema_version") == "reasoning_path_v1"
        and path.get("input_anchors")
        and path.get("steps")
        and contract.get("generator") == "reasoning_path_v1"
        and (contract.get("grounding") or {}).get("reasoning_path_schema")
        == "reasoning_path_v1"
        and {int(level.get("level") or 0) for level in levels} == {1, 2, 3}
        and all(
            len(str(level.get("content") or "").strip()) >= 12
            and level.get("step_refs")
            and not any(
                marker in str(level.get("content") or "")
                for marker in generic_markers
            )
            for level in levels
        )
        and (contract.get("leakage_check") or {}).get("passed") is True
    )


def _deduplicate_quality_issues(
    issues: list[dict[str, str]],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (str(issue.get("code") or ""), str(issue.get("severity") or ""))
        if not all(key) or key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


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
    item["formal_task"] = _stored_formal_task_from_item(item)
    item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
    return item


def _generated_course_items(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    imported: list[dict[str, Any]],
    *,
    profile: dict[str, Any],
    objectives: list[dict[str, Any]],
    blueprint: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    result: list[dict[str, Any]] = []
    solutions: dict[str, dict[str, Any]] = {}
    objective_by_node = {
        str(item.get("node_id") or ""): item
        for item in objectives
        if item.get("node_id")
    }
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
        source_item = imported_by_node.get(node_id)
        objective = objective_by_node.get(node_id)
        if not objective:
            continue
        for index, (level, label) in enumerate(level_specs):
            assessment_slot = slot_for(
                blueprint,
                node_id=node_id,
                practice_level=level,
            )
            if not assessment_slot:
                continue
            prepared_contract = (
                (
                    course_data.get(
                        "_assessment_generated_contracts"
                    )
                    or {}
                ).get(node_id)
                or {}
            ).get(level)
            if prepared_contract:
                generated_contract = deepcopy(prepared_contract)
                if generated_contract.get(
                    "generation_status"
                ) == "discarded":
                    continue
            else:
                universal_contract = generate_universal_question_contract(
                    course_data,
                    node,
                    profile=profile,
                    objective=objective,
                    practice_level=level,
                    variant_index=index,
                    slot=assessment_slot,
                )
                validation_plugin_contract = generate_question_contract(
                    course_data,
                    node,
                    level,
                    index,
                )
                generated_contract = _apply_validation_plugin(
                    universal_contract,
                    validation_plugin_contract,
                )
            generated_contract = _align_generated_contract_to_slot(
                generated_contract,
                assessment_slot,
                misconception_labels=[
                    str(value)
                    for value in objective.get("misconceptions") or []
                    if str(value).strip()
                ],
                variant_index=index,
            )
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
            prompt = generated_contract["prompt"]
            source_records = (
                deepcopy(source_item.get("source_records") or [])
                if source_item
                else [{
                    "source_type": "course_material",
                    "course_id": str(course_data.get("course_id") or ""),
                    "node_id": node_id,
                    "rights_basis": "course_generated",
                    "reuse_policy": "original_generation",
                }]
            )
            source_records.extend(
                deepcopy(generated_contract.get("source_records") or [])
            )
            item = {
                "schema_version": QUESTION_ITEM_SCHEMA,
                "course_id": str(course_data.get("course_id") or ""),
                "item_id": item_id,
                "parent_item_id": source_item.get("item_id") if source_item else None,
                "parent_revision_id": source_item.get("revision_id") if source_item else None,
                "node_id": node_id,
                "node_ids": [node_id],
                "prompt": prompt,
                "subquestions": (
                    [generated_contract["deliverable"]]
                    if level == "mastery_check"
                    else []
                ),
                "options": deepcopy(
                    (
                        generated_contract.get("question_spec")
                        or {}
                    ).get("options")
                    or generated_contract.get("options")
                    or []
                ),
                "explanation": "",
                "score": 100,
                "estimated_minutes": generated_contract["estimated_minutes"],
                "question_type": generated_contract["question_type"],
                "difficulty": _node_difficulty(course_data, node),
                "practice_levels": [level],
                "assessment_role": "practice",
                "course_objective_refs": [_objective_ref(course_data, node)],
                "learning_objective": str(
                    objective.get("objective")
                    or node.get("learning_objective")
                    or node.get("node_name")
                    or ""
                ),
                "objective_id": objective.get("objective_id"),
                "course_knowledge_refs": _node_knowledge_refs(course_data, node),
                "course_skill_refs": _node_refs(node, "course_skill_refs"),
                "course_misconception_refs": _node_refs(node, "course_misconception_refs"),
                "course_mastery_refs": _node_refs(node, "course_mastery_refs"),
                "source_type": source_type,
                "source_records": source_records,
                "parse_confidence": "high",
                "risk_flags": deepcopy(generated_contract["risk_flags"]),
                "review_required": bool(
                    generated_contract["review_required"]
                ),
                "lifecycle_status": "candidate",
                "review_status": "candidate",
                "review_history": [],
                "formal_task_revision_id": None,
                "assessment_slot": deepcopy(assessment_slot),
                "deliverable": generated_contract["deliverable"],
                "input_materials": deepcopy(
                    generated_contract["input_materials"]
                ),
                "constraints": deepcopy(generated_contract["constraints"]),
                "reference_concepts": key_points,
                "result_checks": deepcopy(
                    generated_contract["result_checks"]
                ),
                "question_spec": deepcopy(
                    generated_contract["question_spec"]
                ),
                "input_contract": deepcopy(
                    generated_contract.get("input_contract")
                    or (
                        generated_contract.get("question_spec")
                        or {}
                    ).get("input_contract")
                    or {}
                ),
                "solution_revision_id": (
                    generated_contract["solution_envelope"][
                        "solution_revision_id"
                    ]
                ),
                "solution_validation": deepcopy(
                    generated_contract["solution_validation"]
                ),
                "archetype_id": (
                    generated_contract["question_spec"][
                        "archetype_id"
                    ]
                ),
                "validation_mode": (
                    generated_contract["solution_envelope"][
                        "validation_mode"
                    ]
                ),
                "risk_level": (
                    generated_contract["question_spec"][
                        "risk_contract"
                    ]["risk_level"]
                ),
                "generation_status": (
                    generated_contract.get("generation_status")
                    or "generated"
                ),
                "design_brief_summary": _public_design_brief_summary(
                    generated_contract.get("design_brief") or {}
                ),
                "question_type_semantics": {
                    "registry_id": (
                        (
                            generated_contract.get("design_brief")
                            or {}
                        ).get("question_type_semantics")
                        or {}
                    ).get("registry_id"),
                    "passed": bool(
                        (
                            generated_contract.get(
                                "semantic_preflight"
                            )
                            or {}
                        ).get("passed")
                    ),
                },
                "semantic_preflight": deepcopy(
                    generated_contract.get("semantic_preflight")
                    or {}
                ),
                "semantic_reviewer_trigger": bool(
                    generated_contract.get(
                        "semantic_reviewer_trigger"
                    )
                ),
                "material_bindings": deepcopy(
                    generated_contract.get("material_bindings")
                    or []
                ),
                "retrieval_summary": deepcopy(
                    generated_contract.get("retrieval_summary")
                    or {}
                ),
                "generation_audit_summary": deepcopy(
                    generated_contract.get(
                        "generation_audit_summary"
                    )
                    or {}
                ),
                "diversity_signature": deepcopy(
                    generated_contract.get("diversity_signature")
                    or {}
                ),
                "diversity_report": deepcopy(
                    generated_contract.get("diversity_report")
                    or (
                        generated_contract.get("quality_report")
                        or {}
                    ).get("diversity_report")
                    or {}
                ),
                "domain_validation": deepcopy(
                    generated_contract["solution_validation"]
                ),
                "created_at": _now(),
            }
            solution_envelope = deepcopy(
                generated_contract["solution_envelope"]
            )
            item["_solution_envelope"] = solution_envelope
            item["hint_contract"] = _hint_contract(item)
            item_quality = evaluate_question_item_quality(item)
            generated_quality = generated_contract.get(
                "quality_report"
            )
            if (
                isinstance(generated_quality, dict)
                and generated_quality.get("schema_version")
                == "question_quality_report_v2"
            ):
                item["quality_report"] = {
                    **deepcopy(generated_quality),
                    "item_checks": item_quality,
                    "passed": bool(generated_quality.get("passed"))
                    and bool(item_quality.get("passed")),
                }
                if not item["quality_report"]["passed"]:
                    item["quality_report"]["status"] = "failed"
            else:
                item["quality_report"] = item_quality
            _apply_compiled_contract_quality(
                item,
                solution_envelope,
            )
            item["lifecycle_status"] = _initial_status(item)
            item["review_status"] = item["lifecycle_status"]
            item["generation_status"] = (
                "published"
                if item["lifecycle_status"] == "approved"
                else (
                    "waiting_review"
                    if item["quality_report"].get("passed")
                    else "validation_failed"
                )
            )
            item["revision_id"] = _item_revision_id(item)
            item["formal_task"] = _stored_formal_task_from_item(item)
            item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
            item.pop("_solution_envelope", None)
            solutions[solution_envelope["solution_revision_id"]] = (
                solution_envelope
            )
            result.append(item)
    return result, solutions


def _align_generated_contract_to_slot(
    contract: dict[str, Any],
    assessment_slot: dict[str, Any],
    *,
    misconception_labels: list[str],
    variant_index: int,
) -> dict[str, Any]:
    """Preserve the blueprint contract and only synthesize missing choice data."""
    result = deepcopy(contract)
    slot_input = deepcopy(
        assessment_slot.get("input_contract") or {}
    )
    input_mode = str(
        assessment_slot.get("input_mode")
        or slot_input.get("mode")
        or ""
    )
    question_spec = result.setdefault("question_spec", {})
    solution = result.setdefault("solution_envelope", {})
    original_minutes = int(result.get("estimated_minutes") or 1)
    public_options = normalize_public_options(
        question_spec.get("options")
        if isinstance(question_spec.get("options"), list)
        else result.get("options")
    )
    if not public_options:
        public_options = normalize_public_options(
            result.get("options")
        )

    if input_mode == "choice":
        option_ids = {
            str(option.get("id") or "")
            for option in public_options
            if str(option.get("id") or "")
        }
        canonical = solution.get("canonical_answer")
        canonical_option_id = (
            str(
                canonical.get("selected_option_id")
                or canonical.get("option_id")
                or ""
            ).strip()
            if isinstance(canonical, dict)
            else str(canonical or "").strip()
        )
        legacy_correct = str(
            (
                solution.get("choice_answer_spec")
                or solution.get("legacy_answer_spec")
                or {}
            ).get("correct_option_id")
            or ""
        ).strip()
        correct_option_id = legacy_correct or canonical_option_id
        if (
            len(public_options) < 2
            or not correct_option_id
            or correct_option_id not in option_ids
        ):
            result = project_default_single_choice(
                result,
                misconception_labels=misconception_labels,
                variant_index=variant_index,
            )
            question_spec = result.setdefault(
                "question_spec",
                {},
            )
            solution = result.setdefault(
                "solution_envelope",
                {},
            )
            public_options = normalize_public_options(
                result.get("options")
            )
        question_spec["options"] = deepcopy(public_options)
        question_spec["presentation_contract"] = {
            "mode": "single_choice",
            "option_count": len(public_options),
            "selection_limit": 1,
        }
        question_spec["response_contract"] = {
            "format": "single_choice",
            "required_parts": ["selected_option_id"],
            "option_count": len(public_options),
            "selection_limit": 1,
        }
        choice_answer = solution.get("choice_answer_spec")
        if isinstance(choice_answer, dict):
            choice_answer["options"] = deepcopy(public_options)
        result["options"] = deepcopy(public_options)
    else:
        result["options"] = []
        question_spec.pop("options", None)
        question_spec.pop("presentation_contract", None)
        solution.pop("choice_answer_spec", None)

    result["question_type"] = str(
        assessment_slot.get("question_type")
        or result.get("question_type")
        or ""
    )
    result["input_contract"] = slot_input
    result["estimated_minutes"] = original_minutes
    question_spec["input_contract"] = deepcopy(slot_input)
    question_spec["assessment_slot_id"] = assessment_slot.get(
        "slot_id"
    )
    validation_mode = str(
        assessment_slot.get("validation_mode")
        or solution.get("validation_mode")
        or ""
    )
    solution["validation_mode"] = validation_mode
    if isinstance(result.get("solution_validation"), dict):
        result["solution_validation"]["validation_mode"] = (
            validation_mode
        )
    return result


def _apply_validation_plugin(
    universal_contract: dict[str, Any],
    plugin_contract: dict[str, Any],
) -> dict[str, Any]:
    """Use a legacy deterministic adapter only as a V2 validation plugin."""
    result = deepcopy(universal_contract)
    plugin_spec = plugin_contract.get("question_spec") or {}
    adapter_id = str(plugin_spec.get("adapter_id") or "")
    if adapter_id == "fallback.teacher_review":
        return result

    validation_mode = _plugin_validation_mode(adapter_id)
    plugin_validation = plugin_contract.get("domain_validation") or {}
    plugin_answer = deepcopy(plugin_contract.get("answer_spec") or {})
    canonical = (
        plugin_answer.get("correct_answer")
        if plugin_answer.get("correct_answer") is not None
        else plugin_answer.get("canonical_answer")
    )
    if canonical is None:
        canonical = deepcopy(
            (plugin_answer.get("solution_spec") or {}).get(
                "final_answer"
            )
        )
    rubric = [
        str(value)
        for value in plugin_answer.get("criteria") or []
        if str(value).strip()
    ]
    deterministic = validation_mode in {
        "exact_validator",
        "numeric_unit_validator",
        "symbolic_validator",
        "code_validator",
        "state_trace_validator",
    }
    plugin_requires_review = bool(
        plugin_contract.get("review_required")
        or not plugin_validation.get("passed")
        or not deterministic
    )
    objective_risk = str(
        (
            result.get("question_spec", {}).get("risk_contract")
            or {}
        ).get("risk_level")
        or "teacher_review"
    )
    requires_review = plugin_requires_review or (
        objective_risk != "low"
    )

    public_spec = result["question_spec"]
    for field in (
        "stimulus",
        "task",
        "constraints",
        "response_contract",
        "provenance",
    ):
        if field in plugin_spec:
            public_spec[field] = deepcopy(plugin_spec[field])
    public_spec["validation_plugin"] = {
        "adapter_id": adapter_id,
        "capability_id": plugin_spec.get("capability_id"),
        "archetype_id": plugin_spec.get("archetype_id"),
        "subject_family": plugin_spec.get("subject_family"),
        "mode": validation_mode,
    }
    public_spec["subject_family"] = plugin_spec.get("subject_family")
    public_spec["target"] = {
        **deepcopy(public_spec.get("target") or {}),
        "knowledge_points": deepcopy(
            (plugin_spec.get("target") or {}).get(
                "knowledge_points"
            )
            or []
        ),
        "assessment_actions": deepcopy(
            (plugin_spec.get("target") or {}).get(
                "assessment_actions"
            )
            or []
        ),
    }
    public_spec["risk_contract"] = {
        **deepcopy(public_spec.get("risk_contract") or {}),
        "requires_teacher_review": requires_review,
    }

    solution = result["solution_envelope"]
    solution["validation_mode"] = validation_mode
    solution["canonical_answer"] = canonical
    solution["rubric"] = rubric or deepcopy(solution.get("rubric") or [])
    solution["legacy_answer_spec"] = plugin_answer
    solution["validator_config"] = {
        **deepcopy(solution.get("validator_config") or {}),
        "adapter_id": adapter_id,
        "capability_id": plugin_spec.get("capability_id"),
    }
    reasoning_path = plugin_spec.get("reasoning_path") or {}
    if reasoning_path.get("steps"):
        solution["solution_graph"] = {
            "schema_version": "solution_graph_v1",
            "steps": [
                {
                    "step_id": (
                        step.get("step_id")
                        or f"step-{position}"
                    ),
                    "action": (
                        step.get("instruction")
                        or step.get("action")
                        or step.get("operation")
                        or "执行当前步骤"
                    ),
                    "check": (
                        step.get("check")
                        or step.get("expected_state")
                        or step.get("result_check")
                        or "核对当前中间结果"
                    ),
                }
                for position, step in enumerate(
                    reasoning_path.get("steps") or [],
                    start=1,
                )
            ],
        }

    validation_issues = deepcopy(
        plugin_validation.get("issues") or []
    )
    if not deterministic:
        validation_issues.append({
            "code": "independent_solution_required",
            "severity": "major",
        })
    passed = bool(plugin_validation.get("passed"))
    auto_publish = passed and not requires_review
    result["solution_validation"] = {
        "schema_version": "solution_validation_report_v1",
        "passed": passed,
        "status": (
            "passed"
            if auto_publish
            else (
                "needs_review"
                if passed
                else "failed"
            )
        ),
        "validation_mode": validation_mode,
        "deterministic": deterministic,
        "auto_publish_eligible": auto_publish,
        "issues": validation_issues,
        "checks": {
            "schema": True,
            "solution_revision": True,
            "answer_executable": bool(
                canonical is not None or solution.get("rubric")
            ),
            "independent_agreement": (
                deterministic and passed
            ),
        },
        "plugin_report": deepcopy(plugin_validation),
    }
    result["domain_validation"] = deepcopy(
        result["solution_validation"]
    )
    result["review_required"] = requires_review
    result["risk_flags"] = _unique([
        *result.get("risk_flags", []),
        *plugin_contract.get("risk_flags", []),
        *[
            str(issue.get("code") or "")
            for issue in validation_issues
            if issue.get("code")
        ],
    ])
    for field in (
        "prompt",
        "deliverable",
        "input_materials",
        "constraints",
        "result_checks",
        "question_type",
        "estimated_minutes",
    ):
        if field in plugin_contract:
            result[field] = deepcopy(plugin_contract[field])
    return result


def _plugin_validation_mode(adapter_id: str) -> str:
    if adapter_id in {
        "math.quantitative_reasoning",
        "math.calculus",
        "physics.thermodynamics",
    }:
        return "exact_validator"
    if adapter_id in {
        "computer_science.graph_traversal",
        "computer_science.hashing",
        "computer_science.heap",
        "computer_science.avl_tree",
    }:
        return "state_trace_validator"
    if adapter_id.startswith("programming."):
        return "code_validator"
    if adapter_id == "humanities.evidence_argument":
        return "evidence_validator"
    if adapter_id == "language.contextual_production":
        return "language_rubric_validator"
    return "expert_rubric_validator"


def _comprehensive_items(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    imported: list[dict[str, Any]],
    *,
    profile: dict[str, Any],
    objectives: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    purpose = str(
        course_data.get("course_purpose")
        or (course_data.get("generation_request") or {}).get(
            "course_purpose"
        )
        or "systematic"
    )
    preferences = (
        course_data.get("asset_preferences")
        or (course_data.get("generation_request") or {}).get(
            "asset_preferences"
        )
        or {}
    )
    if (
        purpose == "material_organization"
        and not preferences.get("final_assessment")
    ):
        return [], {}
    assessment_nodes = _assessment_nodes(course_data, nodes, purpose)
    if not assessment_nodes:
        return [], {}
    objective_by_node = {
        str(item.get("node_id") or ""): item
        for item in objectives
        if item.get("node_id")
    }
    desired_count = max(3, min(8, len(assessment_nodes) + 1))
    selected = [
        assessment_nodes[index % len(assessment_nodes)]
        for index in range(desired_count - 1)
    ]
    items: list[dict[str, Any]] = []
    solutions: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(selected, start=1):
        objective = objective_by_node.get(
            str(node.get("node_id") or "")
        )
        if not objective:
            continue
        universal = generate_universal_question_contract(
            course_data,
            node,
            profile=profile,
            objective=objective,
            practice_level="final_assessment",
            variant_index=index + 3,
        )
        plugin = generate_question_contract(
            course_data,
            node,
            "final_assessment",
            index + 3,
        )
        contract = _force_comprehensive_review(
            _apply_validation_plugin(universal, plugin)
        )
        item, solution = _v2_final_item(
            course_data,
            [node],
            index=index,
            role="coverage_task",
            objective=objective,
            contract=contract,
        )
        items.append(item)
        solutions[solution["solution_revision_id"]] = solution

    cross_objective = _cross_chapter_objective(
        course_data,
        assessment_nodes,
        objective_by_node,
    )
    cross_node = {
        "node_id": str(
            assessment_nodes[0].get("node_id") or "cross-chapter"
        ),
        "node_level": 2,
        "node_name": "跨章节综合任务",
        "node_content": cross_objective.get("source_excerpt"),
        "learning_objective": cross_objective.get("objective"),
        "key_points": deepcopy(
            cross_objective.get("knowledge") or []
        ),
        "assessment": deepcopy(
            cross_objective.get("skills") or []
        ),
    }
    cross_universal = generate_universal_question_contract(
        course_data,
        cross_node,
        profile=profile,
        objective=cross_objective,
        practice_level="final_assessment",
        variant_index=desired_count,
    )
    if len(assessment_nodes) >= 2:
        cross_plugin = generate_cross_chapter_contract(
            course_data,
            assessment_nodes,
        )
        cross_contract = _apply_validation_plugin(
            cross_universal,
            cross_plugin,
        )
    else:
        # A one-node course cannot truthfully claim cross-chapter
        # deterministic validation. Keep the integrated task on the
        # universal rubric path and require teacher review.
        cross_contract = cross_universal
    cross_contract = _force_comprehensive_review(cross_contract)
    cross_item, cross_solution = _v2_final_item(
        course_data,
        assessment_nodes,
        index=desired_count,
        role="cross_chapter_transfer",
        objective=cross_objective,
        contract=cross_contract,
    )
    items.append(cross_item)
    solutions[
        cross_solution["solution_revision_id"]
    ] = cross_solution
    _apply_assessment_distribution(
        course_data,
        items,
        imported,
        purpose,
        solutions,
    )
    return items, solutions


def _force_comprehensive_review(
    contract: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(contract)
    risk_contract = result["question_spec"].setdefault(
        "risk_contract",
        {},
    )
    risk_contract["risk_level"] = "teacher_review"
    risk_contract["requires_teacher_review"] = True
    result["review_required"] = True
    result["risk_flags"] = _unique([
        *result.get("risk_flags", []),
        "comprehensive_assessment_teacher_review",
    ])
    result["solution_validation"] = {
        **deepcopy(result.get("solution_validation") or {}),
        "status": "needs_review",
        "auto_publish_eligible": False,
    }
    result["domain_validation"] = deepcopy(
        result["solution_validation"]
    )
    return result


def _cross_chapter_objective(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    objective_by_node: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected = [
        objective_by_node.get(str(node.get("node_id") or ""))
        for node in nodes
    ]
    selected = [item for item in selected if item]
    knowledge = _unique([
        value
        for item in selected
        for value in item.get("knowledge") or []
    ])
    skills = _unique([
        value
        for item in selected
        for value in item.get("skills") or []
    ])
    source_excerpt = "\n".join(
        str(item.get("source_excerpt") or "").strip()
        for item in selected
        if str(item.get("source_excerpt") or "").strip()
    )[:8000]
    objective = "综合运用多个章节知识完成迁移任务并验证结果"
    return {
        "schema_version": "assessment_objective_v1",
        "course_id": str(course_data.get("course_id") or ""),
        "node_id": str(nodes[0].get("node_id") or "") if nodes else "",
        "objective_id": stable_hash(
            {
                "course_id": course_data.get("course_id"),
                "node_ids": [
                    str(node.get("node_id") or "")
                    for node in nodes
                ],
                "role": "cross_chapter_transfer",
            },
            prefix="aobj_",
        ),
        "objective": objective,
        "knowledge": knowledge,
        "skills": skills or [objective],
        "misconceptions": _unique([
            value
            for item in selected
            for value in item.get("misconceptions") or []
        ]),
        "observable_evidence": _unique([
            value
            for item in selected
            for value in item.get("observable_evidence") or []
        ]),
        "source_refs": [
            deepcopy(source)
            for item in selected
            for source in item.get("source_refs") or []
        ],
        "source_excerpt": source_excerpt,
        "source_sufficiency": (
            "sufficient" if len(source_excerpt) >= 80 else "insufficient"
        ),
        "answer_modalities": ["integrated_deliverable"],
        "preferred_archetype_ids": ["integrated_performance"],
        "difficulty_contract": {
            "target_level": str(
                course_data.get("difficulty") or "intermediate"
            ),
            "transfer_distance": "cross_chapter",
            "minimum_steps": 3,
        },
        "confidence": "medium" if source_excerpt else "low",
        "risk_level": "teacher_review",
        "generation_status": "candidate_only",
    }


def _v2_final_item(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    *,
    index: int,
    role: str,
    objective: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    node_ids = _unique([
        str(node.get("node_id") or "")
        for node in nodes
        if node.get("node_id")
    ])
    solution = deepcopy(contract["solution_envelope"])
    item = {
        "schema_version": QUESTION_ITEM_SCHEMA,
        "course_id": str(course_data.get("course_id") or ""),
        "item_id": stable_hash(
            {
                "course_id": course_data.get("course_id"),
                "node_ids": node_ids,
                "role": role,
                "index": index,
                "objective_id": objective.get("objective_id"),
            },
            prefix="qbi_",
        ),
        "parent_item_id": None,
        "parent_revision_id": None,
        "node_id": node_ids[0] if node_ids else None,
        "node_ids": node_ids,
        "prompt": contract["prompt"],
        "subquestions": [contract["deliverable"]],
        "options": [],
        "explanation": "",
        "score": max(20, round(100 / max(1, len(nodes)))),
        "estimated_minutes": max(
            25,
            int(contract.get("estimated_minutes") or 25),
        ),
        "question_type": contract["question_type"],
        "difficulty": str(
            course_data.get("difficulty") or "intermediate"
        ),
        "practice_levels": ["final_assessment"],
        "assessment_role": role,
        "course_objective_refs": _unique([
            _objective_ref(course_data, node)
            for node in nodes
        ]),
        "objective_id": objective.get("objective_id"),
        "assessment_objective_id": objective.get("objective_id"),
        "course_knowledge_refs": _unique([
            ref
            for node in nodes
            for ref in _node_knowledge_refs(course_data, node)
        ]),
        "course_skill_refs": _unique([
            ref
            for node in nodes
            for ref in _node_refs(node, "course_skill_refs")
        ]),
        "course_misconception_refs": _unique([
            ref
            for node in nodes
            for ref in _node_refs(
                node,
                "course_misconception_refs",
            )
        ]),
        "course_mastery_refs": _unique([
            ref
            for node in nodes
            for ref in _node_refs(node, "course_mastery_refs")
        ]),
        "source_type": "generated",
        "source_records": [
            {
                "source_type": "course_material",
                "course_id": str(course_data.get("course_id") or ""),
                "node_id": node_id,
                "rights_basis": "course_generated",
                "reuse_policy": "original_generation",
            }
            for node_id in node_ids
        ],
        "parse_confidence": "high",
        "risk_flags": _unique([
            *contract.get("risk_flags", []),
            "comprehensive_assessment_teacher_review",
        ]),
        "review_required": True,
        "lifecycle_status": "needs_review",
        "review_status": "needs_review",
        "review_history": [],
        "formal_task_revision_id": None,
        "deliverable": contract["deliverable"],
        "input_materials": deepcopy(
            contract.get("input_materials") or []
        ),
        "constraints": deepcopy(
            contract.get("constraints") or []
        ),
        "reference_concepts": deepcopy(
            objective.get("knowledge") or []
        ),
        "result_checks": deepcopy(
            contract.get("result_checks") or []
        ),
        "question_spec": deepcopy(contract["question_spec"]),
        "solution_revision_id": solution["solution_revision_id"],
        "solution_validation": deepcopy(
            contract["solution_validation"]
        ),
        "archetype_id": contract["question_spec"]["archetype_id"],
        "validation_mode": solution["validation_mode"],
        "risk_level": "teacher_review",
        "generation_status": "waiting_review",
        "domain_validation": deepcopy(
            contract["solution_validation"]
        ),
        "created_at": _now(),
        "_solution_envelope": solution,
    }
    item["hint_contract"] = _hint_contract(item)
    item["quality_report"] = evaluate_question_item_quality(item)
    item["revision_id"] = _item_revision_id(item)
    item["formal_task"] = _stored_formal_task_from_item(item)
    item["formal_task_revision_id"] = item["formal_task"][
        "revision_id"
    ]
    item.pop("_solution_envelope", None)
    return item, solution


def _legacy_comprehensive_items(
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
        generated_contract = generate_question_contract(
            course_data,
            node,
            "final_assessment",
            index + 3,
        )
        items.append(_final_item(
            course_data,
            [node],
            index=index,
            role="coverage_task",
            prompt=generated_contract["prompt"].replace(
                "综合测评｜",
                f"综合测评任务 {index}｜",
                1,
            ),
            deliverable=generated_contract["deliverable"],
            input_materials=generated_contract["input_materials"],
            constraints=generated_contract["constraints"],
            generated_contract=generated_contract,
        ))

    integration_nodes = assessment_nodes
    if len(integration_nodes) == 1:
        source_node = integration_nodes[0]
        integration_targets = _unique([
            *_node_key_points(source_node),
            *_assessment_items(source_node),
        ])[:2]
        if len(integration_targets) < 2:
            integration_targets = [
                str(source_node.get("learning_objective") or "理解课程概念"),
                f"验证{source_node.get('node_name') or '课程任务'}的应用边界",
            ]
        integration_nodes = []
        for target in integration_targets:
            component = deepcopy(source_node)
            component["learning_objective"] = target
            component["key_points"] = [target]
            component["assessment"] = [f"围绕{target}形成可检查结果"]
            integration_nodes.append(component)
    cross_contract = generate_cross_chapter_contract(
        course_data,
        integration_nodes,
    )
    items.append(_final_item(
        course_data,
        integration_nodes,
        index=desired_count,
        role="cross_chapter_transfer",
        prompt=cross_contract["prompt"],
        deliverable=cross_contract["deliverable"],
        input_materials=cross_contract["input_materials"],
        constraints=cross_contract["constraints"],
        generated_contract=cross_contract,
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
    solution_envelopes: dict[str, dict[str, Any]] | None = None,
) -> None:
    teacher_distribution = purpose == "exam_sprint" and bool(imported)
    for index, item in enumerate(items):
        solution = (
            solution_envelopes or {}
        ).get(str(item.get("solution_revision_id") or ""))
        if solution:
            item["_solution_envelope"] = deepcopy(solution)
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
            item["assessment_distribution"] = {
                "basis": "teacher_question_bank",
                "inferred": False,
                "source_item_revision_id": sample.get("revision_id"),
                "source_score": source_score,
            }
        else:
            item["assessment_distribution"] = {
                "basis": "systematic_rule",
                "inferred": purpose == "exam_sprint",
                "source_item_revision_id": None,
                "source_score": None,
            }
        item["quality_report"] = evaluate_question_item_quality(item)
        item["revision_id"] = _item_revision_id(item)
        item["formal_task"] = _stored_formal_task_from_item(item)
        item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
        item.pop("_solution_envelope", None)


def _assessment_blueprint(
    course_data: dict[str, Any],
    finals: list[dict[str, Any]],
    imported: list[dict[str, Any]],
) -> dict[str, Any]:
    compiled = course_data.get("_course_assessment_blueprint")
    if isinstance(compiled, dict) and compiled.get(
        "schema_version"
    ) == "course_assessment_blueprint_v2":
        return deepcopy(compiled)
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
    generated_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    course_id = str(course_data.get("course_id") or "")
    node_ids = [str(node.get("node_id") or "") for node in nodes]
    concepts = _unique(
        ref
        for node in nodes
        for ref in _node_knowledge_refs(course_data, node)
    )
    criteria = (
        list((generated_contract or {}).get("answer_spec", {}).get("criteria") or [])
        or [
            deliverable,
            "正确使用指定章节概念并说明连接依据",
            "过程完整且关键假设明确",
            "执行结果检查并说明适用边界",
        ]
    )
    answer_spec = deepcopy(
        (generated_contract or {}).get("answer_spec")
        or {
            "type": "rubric",
            "criteria": criteria,
            "expected_keywords": _unique(
                point for node in nodes for point in _node_key_points(node)
            )[:12],
            "max_score": 100,
            "pass_score": 70,
        }
    )
    answer_spec["criteria"] = criteria
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
        "answer_spec": answer_spec,
        "explanation": "",
        "score": 100,
        "estimated_minutes": int(
            (generated_contract or {}).get("estimated_minutes")
            or (25 if role == "coverage_task" else 45)
        ),
        "question_type": (
            (generated_contract or {}).get("question_type")
            or _question_type(course_data, "final_assessment")
        ),
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
        }, *deepcopy((generated_contract or {}).get("source_records") or [])],
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
        "question_spec": deepcopy(
            (generated_contract or {}).get("question_spec") or {}
        ),
        "domain_validation": deepcopy(
            (generated_contract or {}).get("domain_validation") or {}
        ),
        "created_at": _now(),
    }
    item["hint_contract"] = _hint_contract(item)
    item["quality_report"] = evaluate_question_item_quality(item)
    item["revision_id"] = _item_revision_id(item)
    item["formal_task"] = _stored_formal_task_from_item(item)
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
        if item.get("lifecycle_status") == "approved"
        and (item.get("quality_report") or {}).get("passed")
        and item.get("assessment_role") in {
            "practice",
            "imported_practice",
            "web_enriched_practice",
        }
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
        existing["formal_task"] = _stored_formal_task_from_item(existing)
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
        left_signature = build_diversity_signature(left)
        left["diversity_signature"] = deepcopy(left_signature)
        for right in comparable[index + 1:]:
            if left.get("node_id") != right.get("node_id"):
                continue
            right_text = _normalize_text(str(right.get("prompt") or ""))
            lexical_similarity = SequenceMatcher(
                None,
                left_text,
                right_text,
            ).ratio()
            right_signature = build_diversity_signature(right)
            right["diversity_signature"] = deepcopy(
                right_signature
            )
            semantic = compare_diversity_signatures(
                left_signature,
                right_signature,
            )
            semantic_signals = semantic.get("signals") or {}
            lexical_duplicate = bool(
                lexical_similarity >= 0.9
                and (
                    float(
                        semantic_signals.get("task_similarity")
                        or 0
                    ) >= 0.9
                    or semantic_signals.get(
                        "same_cognitive_action"
                    )
                    or semantic_signals.get(
                        "same_reasoning_route"
                    )
                )
            )
            if lexical_duplicate or semantic.get("duplicate"):
                cluster_id = stable_hash(
                    sorted([
                        str(left_signature.get("signature_id") or ""),
                        str(right_signature.get("signature_id") or ""),
                    ]),
                    prefix="qdc_",
                )
                for item in (left, right):
                    item["near_duplicate_cluster_id"] = cluster_id
                    item["risk_flags"] = _unique([
                        *(item.get("risk_flags") or []),
                        "near_duplicate",
                        "semantic_near_duplicate",
                    ])
                    item["diversity_report"] = {
                        "schema_version": (
                            "question_diversity_report_v1"
                        ),
                        "passed": False,
                        "max_similarity": max(
                            lexical_similarity,
                            float(
                                semantic.get(
                                    "overall_similarity"
                                )
                                or 0
                            ),
                        ),
                        "closest_question_id": (
                            right.get("item_id")
                            if item is left
                            else left.get("item_id")
                        ),
                        "reasons": _unique([
                            *semantic.get("reasons", []),
                            *(
                                ["lexical_threshold"]
                                if lexical_duplicate
                                else []
                            ),
                        ]),
                        "signals": deepcopy(
                            semantic.get("signals") or {}
                        ),
                        "threshold": semantic.get("threshold"),
                    }
                    item["review_required"] = True
                    item["lifecycle_status"] = "needs_review"
                    item["review_status"] = "needs_review"
                    _mark_quality_as_semantic_duplicate(item)
                    item["revision_id"] = _item_revision_id(item)
                    item["formal_task"] = _stored_formal_task_from_item(item)
                    item["formal_task_revision_id"] = item["formal_task"]["revision_id"]


def _mark_quality_as_semantic_duplicate(
    item: dict[str, Any],
) -> None:
    """Preserve prior private-solution checks after the envelope is stored."""
    quality = deepcopy(item.get("quality_report") or {})
    issues = list(quality.get("issues") or [])
    issues.extend([
        {
            "code": "question:near_duplicate",
            "severity": "major",
        },
        {
            "code": "question:semantic_near_duplicate",
            "severity": "critical",
        },
    ])
    quality.update({
        "schema_version": (
            quality.get("schema_version")
            or "question_item_quality_v1"
        ),
        "passed": False,
        "status": "failed",
        "decision": "regenerate",
        "issues": _deduplicate_quality_issues(issues),
    })
    item_checks = quality.get("item_checks")
    if isinstance(item_checks, dict):
        item_check_issues = list(item_checks.get("issues") or [])
        item_check_issues.extend([
            {
                "code": "question:near_duplicate",
                "severity": "major",
            },
            {
                "code": "question:semantic_near_duplicate",
                "severity": "critical",
            },
        ])
        quality["item_checks"] = {
            **item_checks,
            "passed": False,
            "status": "failed",
            "issues": _deduplicate_quality_issues(
                item_check_issues
            ),
        }
    item["quality_report"] = quality


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
    private_solution = item.get("_solution_envelope") or {}
    if (
        (item.get("question_spec") or {}).get("schema_version")
        == "question_spec_v2"
        and private_solution
    ):
        return _solution_graph_hint_contract(
            item,
            private_solution,
        )
    concepts = item.get("reference_concepts") or item.get("course_knowledge_refs") or []
    constraints = item.get("constraints") or []
    criteria = (item.get("answer_spec") or {}).get("criteria") or []
    adapter_contract = deepcopy(
        (item.get("question_spec") or {}).get("hint_contract") or {}
    )
    levels = adapter_contract.get("levels") or [
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
    evidence_effects = {
        1: ("limited_mastery", 1),
        2: ("not_independent", 2),
        3: ("not_mastery", 3),
    }
    for level in levels:
        level_number = int(level.get("level") or 0)
        effect, support = evidence_effects.get(
            level_number,
            ("not_mastery", max(1, level_number)),
        )
        level.setdefault("evidence_effect", effect)
        level.setdefault("support_level", support)
    prompt = _normalize_text(str(item.get("prompt") or ""))
    answer_spec = item.get("answer_spec") or {}
    answer_fragments = _answer_fragments({
        "correct_answer": answer_spec.get("correct_answer"),
        "canonical_answer": answer_spec.get("canonical_answer"),
        # Procedural steps and checks intentionally overlap with progressive
        # hints because both are derived from one reasoning path.  Only the
        # frozen final answer is forbidden in pre-submission hints.
        "solution_final_answer": (
            answer_spec.get("solution_spec") or {}
        ).get("final_answer"),
    })
    leakage = any(
        fragment in _normalize_text(str(level.get("content") or ""))
        for fragment in answer_fragments
        for level in levels
    )
    return {
        "generator": str(
            adapter_contract.get("generator")
            or "legacy_hint_contract"
        ),
        "grounding": deepcopy(adapter_contract.get("grounding") or {}),
        "levels": levels,
        "solution_policy": "after_submission_or_repeated_failure",
        "solution_effect": {
            "invalidate_current_evidence": True,
            "requires_unseen_equivalent_validation": True,
        },
        "frozen_with_item_revision": True,
        "leakage_check": {
            "passed": not leakage and all(
                _normalize_text(str(level.get("content") or "")) != prompt
                for level in levels
            ),
            "checked_at_compile_time": True,
        },
    }


def _solution_graph_hint_contract(
    item: dict[str, Any],
    solution_envelope: dict[str, Any],
) -> dict[str, Any]:
    raw_graph = solution_envelope.get("solution_graph") or {}
    if isinstance(raw_graph, list):
        graph = {
            "schema_version": "solution_graph_v1",
            "steps": raw_graph,
        }
    elif isinstance(raw_graph, dict):
        graph = raw_graph
    else:
        graph = {}
    steps = [
        step
        if isinstance(step, dict)
        else {
            "step_id": f"step-{index + 1}",
            "action": str(step),
        }
        for index, step in enumerate(graph.get("steps") or [])
    ]
    while len(steps) < 3:
        steps.append({
            "step_id": f"support-{len(steps) + 1}",
            "action": "核对题面输入、限制条件与当前中间结果",
            "check": "确认当前步骤没有引入题面之外的假设",
        })

    def action(position: int) -> str:
        step = steps[position]
        return str(
            step.get("action")
            or step.get("instruction")
            or step.get("description")
            or "完成当前步骤"
        ).strip()

    def check(position: int) -> str:
        step = steps[position]
        return str(
            step.get("check")
            or step.get("result_check")
            or "核对当前中间结果"
        ).strip()

    source_text = str(
        (
            (item.get("question_spec") or {}).get("stimulus")
            or {}
        ).get("rendered_text")
        or next(iter(item.get("input_materials") or []), "")
    ).strip()
    source_anchor = source_text[:80] or "题面给定材料"
    levels = [
        {
            "level": 1,
            "kind": "orientation",
            "content": (
                f"先在“{source_anchor}”中定位任务需要的输入与边界。"
                f"自检方向：{check(0)}。"
            ),
            "step_refs": [
                str(steps[0].get("step_id") or "step-1")
            ],
            "evidence_effect": "limited_mastery",
            "support_level": 1,
        },
        {
            "level": 2,
            "kind": "method_skeleton",
            "content": (
                f"方法骨架：{action(0)}；然后{action(1)}。"
                f"先完成第一步，并检查：{check(0)}。"
            ),
            "step_refs": [
                str(steps[0].get("step_id") or "step-1"),
                str(steps[1].get("step_id") or "step-2"),
            ],
            "evidence_effect": "not_independent",
            "support_level": 2,
        },
        {
            "level": 3,
            "kind": "local_scaffold",
            "content": (
                f"只示范当前卡点的检查方式：先{action(1)}，"
                f"再用不同数据核对“{check(1)}”。"
                "不要直接抄写最终结论。"
            ),
            "step_refs": [
                str(steps[1].get("step_id") or "step-2"),
                str(steps[2].get("step_id") or "step-3"),
            ],
            "evidence_effect": "not_mastery",
            "support_level": 3,
        },
    ]
    prompt = _normalize_text(str(item.get("prompt") or ""))
    final_answer = (
        solution_envelope.get("legacy_answer_spec") or {}
    ).get("correct_answer")
    fragments = (
        _answer_fragments({"correct_answer": final_answer})
        if final_answer is not None
        else []
    )
    leakage = any(
        fragment
        and fragment in _normalize_text(level["content"])
        for fragment in fragments
        for level in levels
    )
    return {
        "generator": "solution_graph_v1",
        "grounding": {
            "solution_revision_id": solution_envelope.get(
                "solution_revision_id"
            ),
            "solution_graph_schema": graph.get(
                "schema_version",
                "solution_graph_v1",
            ),
        },
        "levels": levels,
        "solution_policy": "after_submission_or_repeated_failure",
        "solution_effect": {
            "invalidate_current_evidence": True,
            "requires_unseen_equivalent_validation": True,
        },
        "frozen_with_item_revision": True,
        "leakage_check": {
            "passed": not leakage and all(
                _normalize_text(level["content"]) != prompt
                for level in levels
            ),
            "checked_at_compile_time": True,
        },
    }


def _formal_task_from_item(item: dict[str, Any]) -> dict[str, Any]:
    private_solution = item.get("_solution_envelope") or {}
    compiled = compile_formal_task_contract(
        item,
        private_solution,
    )
    answer_spec = deepcopy(compiled["answer_spec"])
    input_contract = deepcopy(compiled["input_contract"])
    task = {
        "asset_id": stable_hash(
            {"course": item.get("course_id"), "question_bank_item": item.get("item_id")},
            prefix="qbt_",
        ),
        "question_id": item.get("item_id"),
        "node_id": item.get("node_id"),
        "node_ids": deepcopy(item.get("node_ids") or []),
        "learning_objective": (
            item.get("learning_objective")
            or next(
                iter(item.get("course_objective_refs") or []),
                "",
            )
        ),
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
        "options": deepcopy(compiled["options"]),
        "answer_spec": answer_spec,
        "solution_revision_id": (
            item.get("solution_revision_id")
            or private_solution.get("solution_revision_id")
        ),
        "practice_level": compiled["practice_level"],
        "hint_contract": deepcopy(item.get("hint_contract") or {}),
        "input_contract": input_contract,
        "grading_policy": deepcopy(compiled["grading_policy"]),
        "validation_policy": deepcopy(
            compiled["validation_policy"]
        ),
        "source_status": item.get("source_type"),
        "source_records": deepcopy(item.get("source_records") or []),
        "quality_status": (item.get("quality_report") or {}).get("status"),
        "quality_report": deepcopy(item.get("quality_report") or {}),
        "diversity_signature": deepcopy(
            item.get("diversity_signature") or {}
        ),
        "diversity_report": deepcopy(
            item.get("diversity_report")
            or (item.get("quality_report") or {}).get(
                "diversity_report"
            )
            or {}
        ),
        "review_status": item.get("review_status"),
        "assessment_role": item.get("assessment_role"),
        "assessment_distribution": deepcopy(item.get("assessment_distribution") or {}),
        "deliverable": item.get("deliverable"),
        "input_materials": deepcopy(item.get("input_materials") or []),
        "constraints": deepcopy(item.get("constraints") or []),
        "result_checks": deepcopy(item.get("result_checks") or []),
        "question_spec": deepcopy(item.get("question_spec") or {}),
        "domain_validation": deepcopy(item.get("domain_validation") or {}),
        "validation_mode": item.get("validation_mode"),
        "compiled_contract_hash": compiled[
            "compiled_contract_hash"
        ],
        "compiled_contract_validation": deepcopy(
            compiled["contract_validation"]
        ),
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


def _stored_formal_task_from_item(
    item: dict[str, Any],
) -> dict[str, Any]:
    """Persist a task shell without duplicating the private V2 solution."""
    task = _formal_task_from_item(item)
    if (
        (item.get("question_spec") or {}).get("schema_version")
        == "question_spec_v2"
    ):
        task["answer_spec"] = {}
    return task


def _answer_spec_from_solution(
    solution_envelope: dict[str, Any],
) -> dict[str, Any]:
    choice = deepcopy(
        solution_envelope.get("choice_answer_spec") or {}
    )
    if choice:
        return choice
    legacy = deepcopy(
        solution_envelope.get("legacy_answer_spec") or {}
    )
    if legacy:
        return legacy
    canonical = deepcopy(
        solution_envelope.get("canonical_answer")
    )
    return {
        "validation_mode": solution_envelope.get(
            "validation_mode"
        ),
        "canonical_answer": canonical,
        "criteria": deepcopy(
            solution_envelope.get("rubric") or []
        ),
        "pass_score": int(
            (
                solution_envelope.get("validator_config") or {}
            ).get("pass_score")
            or 70
        ),
        "validator_config": deepcopy(
            solution_envelope.get("validator_config") or {}
        ),
        "solution_spec": {
            "schema_version": "solution_spec_v1",
            "final_answer": canonical,
            "steps": deepcopy(
                (
                    solution_envelope.get("solution_graph") or {}
                ).get("steps")
                or []
            ),
        },
    }


def _initial_status(item: dict[str, Any]) -> str:
    if item.get("review_required"):
        return "needs_review"
    report = item.get("quality_report") or {}
    if not report.get("passed"):
        return "needs_review"
    if report.get("status") == "needs_review":
        return "needs_review"
    return "approved"


def _apply_tiered_review_policy(
    items: list[dict[str, Any]],
    profile: dict[str, Any],
) -> None:
    """Publish validated questions by default and quarantine hard blockers."""
    high_stakes = bool(
        (profile.get("discipline") or {}).get("high_stakes")
    )
    for item in items:
        mandatory_reason = _mandatory_review_reason(
            item,
            high_stakes,
        )
        latest_decision = next(
            (
                str(entry.get("decision") or "")
                for entry in reversed(
                    item.get("review_history") or []
                )
                if entry.get("decision")
            ),
            "",
        )
        if latest_decision == "rejected":
            item["review_tier"] = (
                "mandatory_review"
                if mandatory_reason
                else "auto_publish"
            )
            item["review_policy_reason"] = "teacher_requested_rework"
            item["review_required"] = False
            item["lifecycle_status"] = "rejected"
            item["review_status"] = "rejected"
            item["generation_status"] = "rework_requested"
        elif latest_decision == "approved":
            _set_review_tier(
                item,
                (
                    "mandatory_review"
                    if mandatory_reason
                    else "auto_publish"
                ),
                "teacher_approved",
            )
            item["review_required"] = False
            item["lifecycle_status"] = "approved"
            item["review_status"] = "approved"
            item["generation_status"] = "published"
        elif mandatory_reason:
            _set_review_tier(
                item,
                "mandatory_review",
                mandatory_reason,
            )
        else:
            _set_review_tier(
                item,
                "auto_publish",
                "quality_and_validation_passed",
            )
        item["revision_id"] = _item_revision_id(item)
        item["formal_task"] = _stored_formal_task_from_item(item)
        item["formal_task_revision_id"] = item["formal_task"][
            "revision_id"
        ]


def _mandatory_review_reason(
    item: dict[str, Any],
    high_stakes: bool,
) -> str:
    if high_stakes:
        return "high_stakes_course"
    if item.get("assessment_role") in FINAL_ASSESSMENT_ROLES:
        return "comprehensive_assessment"
    quality = item.get("quality_report") or {}
    if not quality.get("passed"):
        return "quality_validation_failed"
    validation = (
        item.get("solution_validation")
        or item.get("domain_validation")
        or {}
    )
    if validation and not validation.get("passed"):
        return "solution_validation_failed"
    if item.get("review_required"):
        risk_flags = [
            str(value)
            for value in item.get("risk_flags") or []
            if str(value).strip()
        ]
        return (
            f"risk:{risk_flags[0]}"
            if risk_flags
            else "existing_review_gate"
        )
    return ""


def _set_review_tier(
    item: dict[str, Any],
    tier: str,
    reason: str,
) -> None:
    if tier not in QUESTION_REVIEW_TIERS:
        raise ValueError(f"unsupported review tier: {tier}")
    requires_review = tier == "mandatory_review"
    sample_pending = tier == "sample_review"
    item["review_tier"] = tier
    item["review_policy_reason"] = reason
    item["review_required"] = requires_review
    item["lifecycle_status"] = (
        "needs_review" if requires_review else "approved"
    )
    item["review_status"] = (
        "needs_review"
        if requires_review or sample_pending
        else "approved"
    )
    quality = item.get("quality_report") or {}
    item["generation_status"] = (
        "validation_failed"
        if requires_review and not quality.get("passed")
        else (
            "waiting_review"
            if requires_review
            else "published"
        )
    )

    risk_contract = (
        item.get("question_spec") or {}
    ).get("risk_contract")
    if isinstance(risk_contract, dict):
        risk_contract["review_tier"] = tier
        risk_contract["requires_teacher_review"] = requires_review
    validation = item.get("solution_validation")
    if isinstance(validation, dict):
        validation["auto_publish_eligible"] = not requires_review
        if validation.get("passed"):
            validation["status"] = (
                "needs_review"
                if requires_review
                else "passed"
            )


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
    if _topic_family(node) == "hashing":
        if level == "concept_check":
            return [
                "正确计算每个键的初始哈希地址",
                "准确标出发生冲突的键并说明原因",
                "所有地址均满足 0≤h(k)<m",
            ]
        if level == "objective_practice":
            return [
                "按给定顺序和线性探测规则逐键插入",
                "写出完整最终槽位并记录各键探测次数",
                "复核每个键都能按同一规则查回",
            ]
        return [
            "按给定哈希函数与链地址法完成实现",
            "给出各桶内容和两次查询路径",
            "正确计算负载因子并用测试结果验证实现",
        ]
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


def _generated_task_text(
    node: dict[str, Any],
    level: str,
    assessments: list[str],
    index: int,
) -> str:
    if _topic_family(node) == "hashing":
        return {
            "concept_check": (
                "计算每个键的初始哈希地址，标出发生冲突的键，"
                "并说明冲突产生的原因"
            ),
            "objective_practice": (
                "按线性探测规则完成全部插入，写出最终槽位，"
                "并记录每个键的探测次数"
            ),
            "mastery_check": (
                "实现给定哈希表，给出各桶内容、两次查询路径和负载因子，"
                "再用测试结果验证实现"
            ),
        }[level]
    if level == "mastery_check":
        return "；".join(
            f"（{task_index}）{task}"
            for task_index, task in enumerate(assessments, start=1)
        )
    return assessments[min(index, len(assessments) - 1)]


def _topic_family(node: dict[str, Any]) -> str:
    topic = " ".join([
        str(node.get("node_name") or ""),
        str(node.get("learning_objective") or ""),
        *_node_key_points(node),
    ])
    if any(marker in topic for marker in ("哈希", "散列表", "散列")):
        return "hashing"
    return "general"


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
    if _topic_family(node) == "hashing":
        variants = [
            (
                "散列表容量 m=11，哈希函数 h(k)=k mod 11，"
                "依次处理键 22、41、53、46、30；若地址重复只标记冲突，暂不插入"
            ),
            (
                "散列表容量 m=10，哈希函数 h(k)=(3k+1) mod 10，"
                "依次插入键 12、22、32、7；冲突采用线性探测（步长为 1），表初始为空"
            ),
            (
                "散列表容量 m=13，哈希函数 h(k)=k mod 13，"
                "依次插入键 18、41、22、44、59、32、31；冲突采用链地址法，"
                "插入后依次查询键 44 和 35"
            ),
        ]
    elif mode == "math_formal" or any(
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
            "review_tier": item.get("review_tier"),
            "review_policy_reason": item.get(
                "review_policy_reason"
            ),
            "risk_flags": deepcopy(item.get("risk_flags") or []),
            "quality_status": (item.get("quality_report") or {}).get("status"),
        }
        for item in items
        if item.get("lifecycle_status") == "needs_review"
    ]
    sampling = [
        {
            "item_id": item.get("item_id"),
            "revision_id": item.get("revision_id"),
            "node_id": item.get("node_id"),
            "assessment_role": item.get("assessment_role"),
            "review_tier": item.get("review_tier"),
            "review_policy_reason": item.get(
                "review_policy_reason"
            ),
            "risk_flags": deepcopy(item.get("risk_flags") or []),
            "quality_status": (
                item.get("quality_report") or {}
            ).get("status"),
        }
        for item in items
        if (
            item.get("review_tier") == "sample_review"
            and item.get("review_status") == "needs_review"
        )
    ]
    tier_counts = {
        tier: sum(
            1
            for item in items
            if item.get("review_tier") == tier
        )
        for tier in sorted(QUESTION_REVIEW_TIERS)
    }
    return {
        "schema_version": QUESTION_REVIEW_POLICY_SCHEMA,
        "blocking_count": len(blocking),
        "sample_count": len(sampling),
        "tier_counts": tier_counts,
        "items": blocking,
        "sample_items": sampling,
    }


def _public_reference_package_summary(
    package: dict[str, Any],
) -> dict[str, Any]:
    if not package:
        return {}
    references = (
        package.get("authoring_patterns")
        or package.get("references")
        or []
    )
    content_evidence = package.get("content_evidence") or []
    source_distribution: dict[str, int] = {}
    for reference in references:
        source_type = str(
            reference.get("source_type") or "unknown"
        )
        source_distribution[source_type] = (
            source_distribution.get(source_type, 0) + 1
        )
    return {
        "schema_version": package.get("schema_version"),
        "package_revision_id": package.get("package_revision_id"),
        "retrieval_mode": package.get("retrieval_mode"),
        "source_priority": deepcopy(
            package.get("source_priority") or []
        ),
        "source_count": len(references),
        "content_reference_count": len(content_evidence),
        "authoring_pattern_count": len(references),
        "source_distribution": source_distribution,
        "content_coverage": deepcopy(
            package.get("content_coverage") or []
        ),
        "method_coverage": deepcopy(
            package.get("method_coverage") or []
        ),
        "objective_coverage": deepcopy(
            package.get("objective_coverage") or []
        ),
        "web": deepcopy(package.get("web") or {}),
    }


def _public_design_brief_summary(
    brief: dict[str, Any],
) -> dict[str, Any]:
    if not brief:
        return {}
    semantics = brief.get("question_type_semantics") or {}
    retrieval = brief.get("retrieval_contract") or {}
    return {
        "schema_version": brief.get("schema_version"),
        "design_brief_revision_id": brief.get(
            "design_brief_revision_id"
        ),
        "question_type": brief.get("question_type"),
        "semantics_registry_id": semantics.get("registry_id"),
        "primary_knowledge": brief.get("primary_knowledge"),
        "primary_skill": brief.get("primary_skill"),
        "primary_misconception": brief.get(
            "primary_misconception"
        ),
        "diversity_plan": deepcopy(
            brief.get("diversity_plan") or {}
        ),
        "content_coverage": bool(
            retrieval.get("content_coverage")
        ),
        "method_coverage": bool(
            retrieval.get("method_coverage")
        ),
        "content_reference_count": int(
            retrieval.get("content_reference_count") or 0
        ),
        "authoring_pattern_count": int(
            retrieval.get("authoring_pattern_count") or 0
        ),
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


def _answer_fragments(value: Any) -> list[str]:
    fragments: list[str] = []

    def visit(current: Any) -> None:
        if isinstance(current, dict):
            for nested in current.values():
                visit(nested)
            serialized = json.dumps(current, ensure_ascii=False, sort_keys=True)
            normalized = _normalize_text(serialized)
            if len(normalized) >= 8:
                fragments.append(normalized)
            return
        if isinstance(current, list):
            for nested in current:
                visit(nested)
            serialized = json.dumps(current, ensure_ascii=False)
            normalized = _normalize_text(serialized)
            if len(normalized) >= 8:
                fragments.append(normalized)
            return
        if isinstance(current, str):
            normalized = _normalize_text(current)
            if len(normalized) >= 8:
                fragments.append(normalized)

    visit(value)
    return _unique(fragments)


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
    "finalize_v2_question_bank_item",
    "formal_task_from_question_bank_item",
    "is_generic_generated_prompt",
    "load_active_question_bank",
    "migrate_question_bank_review_policy",
    "question_bank_repository",
    "reconcile_item_question_bank",
    "reconcile_question_bank",
    "refresh_question_bank_bundle",
    "review_question_bank_item",
    "revise_question_bank_item",
]
