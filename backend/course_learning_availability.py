"""Read-only capability projection for standard and degraded courses."""

from __future__ import annotations

from typing import Any, Literal


SCHEMA_VERSION = "course_learning_availability_v1"
LearningMode = Literal["standard", "reading_only", "compatibility"]


def project_course_learning_availability(course: dict[str, Any]) -> dict[str, Any]:
    """Explain usable learning capabilities without repairing or mutating a course."""
    mode = resolve_learning_mode(course)
    assets = course.get("learning_assets") or {}
    questions = list(assets.get("questions") or [])
    mastery_questions = [
        item for item in questions
        if item.get("practice_level") == "mastery_check"
    ]
    criteria = list(assets.get("mastery_criteria") or [])
    diagnostics = list(assets.get("diagnostic_templates") or [])
    remediation = list(assets.get("remediation_units") or [])
    validations = list(assets.get("validation_questions") or [])

    if mode == "reading_only":
        reason_code = "declared_reading_only"
        practice = _capability("unavailable", reason_code)
        mastery = _capability("unavailable", reason_code)
        remediation_capability = _capability("unavailable", reason_code)
    elif mode == "compatibility":
        reason_code = "legacy_reading_compatible"
        practice = _capability("degraded", reason_code)
        mastery = _capability("unavailable", reason_code)
        remediation_capability = _capability("unavailable", reason_code)
    else:
        reason_code = "full_learning_chain"
        practice = _capability(
            "available" if questions else "blocked",
            "formal_practice_available" if questions else "required_practice_missing",
        )
        mastery_ready = bool(mastery_questions and criteria)
        mastery = _capability(
            "available" if mastery_ready else "blocked",
            "formal_mastery_available" if mastery_ready else "required_mastery_assets_missing",
        )
        remediation_ready = bool(diagnostics and remediation and validations)
        remediation_capability = _capability(
            "available" if remediation_ready else "blocked",
            "formal_remediation_available" if remediation_ready else "required_remediation_assets_missing",
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "reason_code": reason_code,
        "capabilities": {
            "reading": _capability("available", "course_content_available"),
            "practice": practice,
            "mastery_evidence": mastery,
            "remediation": remediation_capability,
        },
    }


def project_practice_availability(
    course: dict[str, Any],
    *,
    scope: Literal["node", "final", "all"],
    node_id: str | None,
    scoped_question_count: int,
) -> dict[str, Any]:
    """Explain why a concrete practice scope is available or empty."""
    learning = project_course_learning_availability(course)
    if scoped_question_count:
        return {
            "status": "available",
            "reason_code": "formal_practice_available",
            "scope": scope,
            "node_id": node_id,
        }

    mode = learning["mode"]
    if mode == "reading_only":
        status, reason_code = "unavailable", "declared_reading_only"
    elif mode == "compatibility":
        status, reason_code = "degraded", "legacy_reading_compatible"
    elif _scope_requires_missing_assets(course, scope):
        status, reason_code = "blocked", "required_practice_missing"
    else:
        status, reason_code = "empty", "no_questions_in_scope"
    return {
        "status": status,
        "reason_code": reason_code,
        "scope": scope,
        "node_id": node_id,
    }


def resolve_learning_mode(course: dict[str, Any]) -> LearningMode:
    """Classify by declared generation contract, never by missing question count."""
    plan = course.get("learning_asset_plan") or {}
    if plan.get("reading_only_degraded") is True:
        return "reading_only"

    assets = course.get("learning_assets") or {}
    has_formal_asset_structure = any(
        assets.get(asset_type)
        for asset_type in (
            "questions",
            "mastery_criteria",
            "chapter_progression_contracts",
            "diagnostic_templates",
            "remediation_units",
        )
    )
    modern_markers = (
        course.get("generation_schema_version"),
        course.get("prompt_contract_version"),
        course.get("learning_asset_bundle_revision_id"),
        plan.get("schema_version"),
        (course.get("generation_request") or {}).get("course_purpose"),
        has_formal_asset_structure,
    )
    return "standard" if any(modern_markers) else "compatibility"


def has_mastery_task(course: dict[str, Any], node_id: str) -> bool:
    return any(
        str(item.get("node_id") or "") == node_id
        and item.get("practice_level") == "mastery_check"
        and (item.get("task_revision_id") or item.get("revision_id"))
        for item in (course.get("learning_assets") or {}).get("questions") or []
    )


def _scope_requires_missing_assets(course: dict[str, Any], scope: str) -> bool:
    assets = course.get("learning_assets") or {}
    if scope in {"node", "all"}:
        return not bool(assets.get("questions"))
    plan = course.get("learning_asset_plan") or {}
    final_contract = next((
        item for item in plan.get("contracts") or []
        if item.get("asset_type") == "final_assessment"
    ), None)
    return bool(final_contract and final_contract.get("enabled") and final_contract.get("required"))


def _capability(status: str, reason_code: str) -> dict[str, str]:
    return {"status": status, "reason_code": reason_code}


__all__ = [
    "SCHEMA_VERSION",
    "has_mastery_task",
    "project_course_learning_availability",
    "project_practice_availability",
    "resolve_learning_mode",
]
