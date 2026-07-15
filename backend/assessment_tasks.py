"""Unified immutable task revisions for practice, diagnosis, and remediation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from course_knowledge_map import project_learning_assets_to_knowledge
from course_versioning import stable_hash
from practice_contracts import enrich_question_contract


TASK_PURPOSES = {
    "course_practice",
    "diagnostic_probe",
    "remediation_guided",
    "remediation_validation",
}


def project_assessment_task(
    raw: dict[str, Any],
    *,
    purpose: str,
    source: str,
) -> dict[str, Any]:
    if purpose not in TASK_PURPOSES:
        raise ValueError(f"Unsupported assessment task purpose: {purpose}")
    base = deepcopy(raw)
    if purpose != "course_practice":
        mastery_eligible = (
            purpose == "remediation_validation"
            and source != "runtime_fallback"
            and base.get("quality_status") == "passed"
        )
        base["validation_policy"] = {
            **(base.get("validation_policy") or {}),
            "mastery_eligible": mastery_eligible,
            "max_support_level_for_mastery": 0 if purpose == "remediation_validation" else -1,
        }
    item = enrich_question_contract(base, practice_level=base.get("practice_level"))
    revision_id = str(item.get("task_revision_id") or item.get("revision_id") or "")
    if not revision_id:
        revision_id = stable_hash({"purpose": purpose, "source": source, "task": item}, prefix="atr_")
    item.update({
        "task_revision_id": revision_id,
        "task_id": str(item.get("task_id") or item.get("question_id") or item.get("asset_id") or revision_id),
        "task_purpose": purpose,
        "task_source": source,
    })
    item["assessment_contract_revision_id"] = stable_hash({
        "task_revision_id": revision_id,
        "purpose": purpose,
        "input": item.get("input_contract"),
        "grading": item.get("grading_policy"),
        "validation": item.get("validation_policy"),
    }, prefix="acr_")
    return item


def course_assessment_tasks(course: dict[str, Any]) -> list[dict[str, Any]]:
    assets = project_learning_assets_to_knowledge(
        course,
        course.get("learning_assets") or {},
    )
    tasks: list[dict[str, Any]] = []
    for item in [*(assets.get("questions") or []), *(assets.get("final_assessment") or [])]:
        tasks.append(project_assessment_task(item, purpose="course_practice", source="course_asset"))
    for item in assets.get("diagnostic_templates") or []:
        tasks.append(project_assessment_task(item, purpose="diagnostic_probe", source="course_asset"))
    for item in assets.get("validation_questions") or []:
        tasks.append(project_assessment_task(item, purpose="remediation_validation", source="course_asset_reserve"))
    for unit in assets.get("remediation_units") or []:
        guided = unit.get("guided_task")
        if isinstance(guided, dict):
            task = project_assessment_task(guided, purpose="remediation_guided", source="course_asset")
            task["remediation_unit_revision_id"] = unit.get("revision_id")
            tasks.append(task)
    return _unique_tasks(tasks)


def resolve_assessment_task(
    course: dict[str, Any],
    revision_id: str,
    *,
    extra_tasks: Iterable[dict[str, Any]] = (),
) -> dict[str, Any] | None:
    target = str(revision_id or "")
    for task in [*[deepcopy(item) for item in extra_tasks], *course_assessment_tasks(course)]:
        projected = task if task.get("task_revision_id") else project_assessment_task(
            task,
            purpose=str(task.get("task_purpose") or "diagnostic_probe"),
            source=str(task.get("task_source") or "diagnostic_workflow"),
        )
        if str(projected.get("task_revision_id") or "") == target:
            return projected
    return None


def _unique_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in tasks:
        revision_id = str(item.get("task_revision_id") or "")
        if revision_id and revision_id not in seen:
            seen.add(revision_id)
            result.append(item)
    return result


__all__ = [
    "TASK_PURPOSES",
    "course_assessment_tasks",
    "project_assessment_task",
    "resolve_assessment_task",
]
