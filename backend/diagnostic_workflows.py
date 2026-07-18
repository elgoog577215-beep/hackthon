"""Atomic diagnostic cases and remediation sessions with deterministic decisions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Callable
import uuid

from assessment_tasks import project_assessment_task
from course_versioning import stable_hash
from storage import storage


SCHEMA_VERSION = 1
CASE_ACTIVE = {"testing", "confirmed", "remediating", "reopened", "unresolved"}
SESSION_ACTIVE = {"active", "awaiting_validation", "reopened"}


class WorkflowConflict(Exception):
    def __init__(self, current: dict[str, Any]):
        super().__init__("diagnostic workflow revision conflict")
        self.current = current


class DiagnosticWorkflowRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def load(self, user_id: str, course_id: str) -> dict[str, Any]:
        key = self._key(user_id, course_id)
        with self._lock(key):
            return deepcopy(self._read(self._path(key)))

    def list_cases(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        return self.load(user_id, course_id)["cases"]

    def list_sessions(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        return self.load(user_id, course_id)["sessions"]

    def get_case(self, user_id: str, course_id: str, case_id: str) -> dict[str, Any]:
        item = next((x for x in self.list_cases(user_id, course_id) if x.get("diagnostic_case_id") == case_id), None)
        if not item:
            raise KeyError(case_id)
        return item

    def get_session(self, user_id: str, course_id: str, session_id: str) -> dict[str, Any]:
        item = next((x for x in self.list_sessions(user_id, course_id) if x.get("remediation_session_id") == session_id), None)
        if not item:
            raise KeyError(session_id)
        return item

    def create_case_once(
        self,
        user_id: str,
        course_id: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            data = self._read(path)
            objective_revision_id = str(payload.get("objective_revision_id") or "")
            existing = next((
                item for item in reversed(data["cases"])
                if item.get("objective_revision_id") == objective_revision_id
                and item.get("status") in CASE_ACTIVE
            ), None)
            if existing:
                return deepcopy(existing), False
            now = _now()
            item = _clean(payload)
            case_id = str(payload.get("diagnostic_case_id") or f"dc_{uuid.uuid4().hex}")
            for task in item.get("diagnostic_tasks") or []:
                task["diagnostic_case_id"] = case_id
                task["course_version_id"] = item.get("course_version_id")
            item.update({
                "diagnostic_case_id": case_id,
                "user_id": user_id,
                "course_id": course_id,
                "status": "testing",
                "revision": 1,
                "schema_version": SCHEMA_VERSION,
                "created_at": now,
                "updated_at": now,
            })
            data["cases"].append(item)
            self._write(path, data)
            return deepcopy(item), True

    def update_case(
        self,
        user_id: str,
        course_id: str,
        case_id: str,
        *,
        expected_revision: int,
        mutate: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        return self._update_entity(
            user_id, course_id, "cases", "diagnostic_case_id", case_id,
            expected_revision=expected_revision, mutate=mutate,
        )

    def create_session_once(
        self,
        user_id: str,
        course_id: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            data = self._read(path)
            case_id = str(payload.get("diagnostic_case_id") or "")
            existing = next((item for item in reversed(data["sessions"]) if item.get("diagnostic_case_id") == case_id), None)
            if existing:
                return deepcopy(existing), False
            now = _now()
            item = _clean(payload)
            session_id = str(payload.get("remediation_session_id") or f"rs_{uuid.uuid4().hex}")
            for task in item.get("tasks") or []:
                task["diagnostic_case_id"] = case_id
                task["remediation_session_id"] = session_id
                task["course_version_id"] = item.get("course_version_id")
            item.update({
                "remediation_session_id": session_id,
                "user_id": user_id,
                "course_id": course_id,
                "status": "active",
                "failure_count": 0,
                "validation_attempts": [],
                "revision": 1,
                "schema_version": SCHEMA_VERSION,
                "created_at": now,
                "updated_at": now,
            })
            data["sessions"].append(item)
            self._write(path, data)
            return deepcopy(item), True

    def update_session(
        self,
        user_id: str,
        course_id: str,
        session_id: str,
        *,
        expected_revision: int,
        mutate: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        return self._update_entity(
            user_id, course_id, "sessions", "remediation_session_id", session_id,
            expected_revision=expected_revision, mutate=mutate,
        )

    def all_tasks(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        data = self.load(user_id, course_id)
        tasks: list[dict[str, Any]] = []
        for case in data["cases"]:
            tasks.extend(case.get("diagnostic_tasks") or [])
        for session in data["sessions"]:
            tasks.extend(session.get("tasks") or [])
        return tasks

    def active(self, user_id: str, course_id: str, *, node_id: str | None = None) -> dict[str, Any]:
        data = self.load(user_id, course_id)
        cases = [item for item in data["cases"] if item.get("status") in CASE_ACTIVE]
        if node_id:
            cases = [item for item in cases if item.get("node_id") == node_id]
        case = cases[-1] if cases else None
        session = next((
            item for item in reversed(data["sessions"])
            if case and item.get("diagnostic_case_id") == case.get("diagnostic_case_id")
            and item.get("status") in SESSION_ACTIVE
        ), None)
        return {"case": deepcopy(case), "session": deepcopy(session)}

    def _update_entity(
        self,
        user_id: str,
        course_id: str,
        collection: str,
        id_field: str,
        entity_id: str,
        *,
        expected_revision: int,
        mutate: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            data = self._read(path)
            item = next((x for x in data[collection] if x.get(id_field) == entity_id), None)
            if not item:
                raise KeyError(entity_id)
            if int(item.get("revision") or 0) != int(expected_revision):
                raise WorkflowConflict(deepcopy(item))
            mutate(item)
            item["revision"] = int(item.get("revision") or 0) + 1
            item["updated_at"] = _now()
            self._write(path, data)
            return deepcopy(item)

    @staticmethod
    def _key(user_id: str, course_id: str) -> str:
        return hashlib.sha256(f"{user_id}\0{course_id}".encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def _lock(self, key: str) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(key, threading.RLock())

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"schema_version": SCHEMA_VERSION, "cases": [], "sessions": []}
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return {
                "schema_version": SCHEMA_VERSION,
                "cases": list(data.get("cases") or []),
                "sessions": list(data.get("sessions") or []),
            }
        except (OSError, json.JSONDecodeError):
            corrupt = path.with_suffix(f".corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            try:
                os.replace(path, corrupt)
            except OSError:
                pass
            return {"schema_version": SCHEMA_VERSION, "cases": [], "sessions": []}

    @staticmethod
    def _write(path: Path, data: dict[str, Any]) -> None:
        temp = path.with_suffix(f".{threading.get_ident()}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


def diagnostic_hypotheses(course: dict[str, Any], task: dict[str, Any], attempt: dict[str, Any]) -> list[dict[str, Any]]:
    result = attempt.get("result") or {}
    answer_diagnosis = result.get("answer_diagnosis") or {}
    diagnosis = answer_diagnosis.get("diagnosis") or {}
    diagnosed_claims = []
    if answer_diagnosis.get("status") == "completed":
        for issue in diagnosis.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            claim = str(
                issue.get("what_happened")
                or issue.get("title")
                or ""
            ).strip()
            if not claim:
                continue
            diagnosed_claims.append({
                "claim": claim,
                "concept_ids": list(issue.get("knowledge_ids") or []),
                "skill_unit_ids": list(issue.get("skill_ids") or []),
                "candidate_mistake_point_ids": list(
                    issue.get("misconception_ids") or []
                ),
                "confidence": float(issue.get("confidence") or 0.0),
                "source": "answer_diagnosis",
            })
    failed = [
        str(item.get("criterion") or "").strip()
        for item in result.get("rubric_results") or []
        if item.get("met") is False and str(item.get("criterion") or "").strip()
    ]
    level = str(task.get("practice_level") or "mastery_check")
    default_category = {
        "concept_check": "concept_gap",
        "objective_practice": "transfer_gap",
        "mastery_check": "process_error",
    }.get(level, "process_error")
    claims = diagnosed_claims[:2] or (
        [
            {"claim": claim, "candidate_mistake_point_ids": []}
            for claim in failed[:2]
        ] or [{
            "claim": f"尚未稳定达到：{task.get('learning_objective') or task.get('prompt')}",
            "candidate_mistake_point_ids": list(task.get("mistake_point_ids") or []),
        }]
    )
    misconceptions = [
        item for item in (course.get("learning_assets") or {}).get("misconceptions") or []
        if item.get("objective_revision_id") == task.get("objective_revision_id")
    ]
    if misconceptions and not diagnosed_claims:
        matched_id = str(misconceptions[0].get("mistake_point_id") or "")
        claims.append({
            "claim": f"可能混淆：{misconceptions[0].get('error_pattern')}",
            "candidate_mistake_point_ids": [matched_id] if matched_id else [],
        })
    hypotheses = []
    for index, claim_entry in enumerate(claims[:3]):
        claim = str(claim_entry.get("claim") or "")
        category = "boundary_confusion" if index >= len(failed) and misconceptions else default_category
        hypothesis_id = stable_hash({
            "objective": task.get("objective_revision_id"), "category": category, "claim": claim,
        }, prefix="dh_")
        hypotheses.append({
            "hypothesis_id": hypothesis_id,
            "category": category,
            "claim": claim,
            "status": "testing",
            "confidence_level": (
                "medium"
                if float(claim_entry.get("confidence") or 0.0) >= 0.7
                else "low"
            ),
            "concept_ids": list(
                claim_entry.get("concept_ids")
                or task.get("concept_ids")
                or attempt.get("concept_ids")
                or []
            ),
            "skill_unit_ids": list(
                claim_entry.get("skill_unit_ids")
                or task.get("skill_unit_ids")
                or attempt.get("skill_unit_ids")
                or []
            ),
            "candidate_mistake_point_ids": list(claim_entry.get("candidate_mistake_point_ids") or []),
            "confirmed_mistake_point_ids": [],
            "evidence_for": [{
                "attempt_id": attempt.get("attempt_id"),
                "kind": (
                    "answer_diagnosis"
                    if claim_entry.get("source") == "answer_diagnosis"
                    else "formal_failure"
                ),
            }],
            "evidence_against": [],
        })
    return hypotheses


def diagnostic_tasks(course: dict[str, Any], task: dict[str, Any], hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    templates = [
        item for item in (course.get("learning_assets") or {}).get("diagnostic_templates") or []
        if item.get("objective_revision_id") == task.get("objective_revision_id")
    ]
    results = []
    for index, hypothesis in enumerate(hypotheses[:3]):
        base = deepcopy(templates[index]) if index < len(templates) else {
            "question_type": "short_answer",
            "learning_objective": task.get("learning_objective"),
            "objective_id": task.get("objective_id"),
            "objective_revision_id": task.get("objective_revision_id"),
            "node_id": task.get("node_id"),
            "prompt": f"只针对下面这一点作答，不展开其他内容：{hypothesis['claim']}。说明你的判断、必要条件和一个最小例子。",
            "answer_spec": {
                "type": "rubric",
                "expected_keywords": (task.get("answer_spec") or {}).get("expected_keywords") or [task.get("learning_objective")],
                "criteria": [hypothesis["claim"], "说明必要条件或边界", "给出可检查的最小例子"],
                "pass_score": 70,
            },
            "practice_level": "diagnostic_probe",
        }
        base["target_hypothesis_ids"] = [hypothesis["hypothesis_id"]]
        base["concept_ids"] = list(base.get("concept_ids") or hypothesis.get("concept_ids") or [])
        base["skill_unit_ids"] = list(base.get("skill_unit_ids") or hypothesis.get("skill_unit_ids") or [])
        base["mistake_point_ids"] = list(
            base.get("mistake_point_ids")
            or hypothesis.get("candidate_mistake_point_ids")
            or []
        )
        base["outcome_matrix"] = {
            "independent_pass": "evidence_against",
            "independent_fail": "evidence_for",
            "supported_or_pending": "inconclusive",
        }
        base["revision_id"] = stable_hash({
            "base": base, "hypothesis": hypothesis["hypothesis_id"],
        }, prefix="dtr_")
        results.append(project_assessment_task(base, purpose="diagnostic_probe", source="diagnostic_workflow"))
    return results


def remediation_payload(
    course: dict[str, Any],
    case: dict[str, Any],
    hypothesis: dict[str, Any],
) -> dict[str, Any]:
    assets = course.get("learning_assets") or {}
    units = [
        item for item in assets.get("remediation_units") or []
        if item.get("objective_revision_id") == case.get("objective_revision_id")
        and (not item.get("category") or item.get("category") == hypothesis.get("category"))
    ]
    unit = deepcopy(units[0]) if units else {
        "revision_id": stable_hash({"case": case.get("diagnostic_case_id"), "claim": hypothesis.get("claim")}, prefix="rur_"),
        "category": hypothesis.get("category"),
        "remediation_objective": f"只修复：{hypothesis.get('claim')}",
        "micro_explanation": f"回到必要条件和边界，重新检查“{hypothesis.get('claim')}”。",
        "worked_contrast": "比较一个满足条件的例子和一个只改变关键条件的反例。",
        "content_block_ids": [],
    }
    guided = unit.get("guided_task") or {
        "question_type": "short_answer",
        "learning_objective": case.get("learning_objective"),
        "objective_id": case.get("objective_id"),
        "objective_revision_id": case.get("objective_revision_id"),
        "node_id": case.get("node_id"),
        "prompt": f"完成一次局部修复练习：{hypothesis.get('claim')}。先写条件，再完成关键步骤，最后检查结果。",
        "answer_spec": {
            "type": "rubric",
            "expected_keywords": [hypothesis.get("claim")],
            "criteria": ["写出必要条件", "完成关键步骤", "检查结果"],
            "pass_score": 70,
        },
        "practice_level": "remediation_guided",
    }
    guided["revision_id"] = str(guided.get("revision_id") or stable_hash({"unit": unit.get("revision_id"), "guided": guided}, prefix="rgtr_"))
    guided_task = project_assessment_task(guided, purpose="remediation_guided", source="remediation_workflow")
    validations = [
        project_assessment_task(item, purpose="remediation_validation", source="course_asset_reserve")
        for item in assets.get("validation_questions") or []
        if item.get("objective_revision_id") == case.get("objective_revision_id")
    ][:2]
    if not validations:
        fallback = deepcopy(guided)
        fallback["prompt"] = f"在一个未展示的新情境中独立证明你已经能够：{case.get('learning_objective')}。说明依据、过程和检查。"
        fallback["practice_level"] = "remediation_validation"
        fallback["revision_id"] = stable_hash({"case": case.get("diagnostic_case_id"), "validation": fallback}, prefix="rvtr_")
        fallback["quality_status"] = "runtime_fallback"
        validations = [project_assessment_task(fallback, purpose="remediation_validation", source="runtime_fallback")]
    return {
        "diagnostic_case_id": case.get("diagnostic_case_id"),
        "confirmed_hypothesis_id": hypothesis.get("hypothesis_id"),
        "course_version_id": case.get("course_version_id"),
        "objective_id": case.get("objective_id"),
        "objective_revision_id": case.get("objective_revision_id"),
        "criterion_revision_id": case.get("criterion_revision_id"),
        "node_id": case.get("node_id"),
        "node_name": case.get("node_name"),
        "concept_ids": list(case.get("concept_ids") or []),
        "skill_unit_ids": list(case.get("skill_unit_ids") or []),
        "confirmed_mistake_point_ids": list(hypothesis.get("confirmed_mistake_point_ids") or []),
        "improvement_point_ids": list(case.get("improvement_point_ids") or []),
        "unit": unit,
        "tasks": [guided_task, *validations],
        "current_task_revision_id": guided_task.get("task_revision_id"),
        "validation_task_revision_ids": [item.get("task_revision_id") for item in validations],
        "return_anchor": case.get("return_anchor") or {"node_id": case.get("node_id")},
    }


def _clean(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


diagnostic_workflow_repository = DiagnosticWorkflowRepository(Path(storage._data_dir) / "diagnostic_workflows")


__all__ = [
    "CASE_ACTIVE",
    "DiagnosticWorkflowRepository",
    "WorkflowConflict",
    "diagnostic_hypotheses",
    "diagnostic_tasks",
    "diagnostic_workflow_repository",
    "remediation_payload",
]
