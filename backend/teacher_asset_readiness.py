from __future__ import annotations

from typing import Any


def _readiness(ready: bool, unavailable_reason: str = "") -> dict[str, Any]:
    return {
        "ready": ready,
        "unavailable_reason": "" if ready else unavailable_reason,
    }


def _revision(items: object, revision_id: str) -> dict[str, Any] | None:
    return next(
        (
            item for item in items or []
            if isinstance(item, dict)
            and str(item.get("revision_id") or "") == revision_id
        ),
        None,
    )


def teacher_lesson_plan_revision_has_content(revision: object) -> bool:
    if not isinstance(revision, dict):
        return False
    if str(revision.get("generation_source") or "") == "deterministic_local_fallback":
        return False
    quality_report = revision.get("quality_report")
    if isinstance(quality_report, dict) and quality_report.get("passed") is False:
        return False
    plan = revision.get("plan") or {}
    if str(plan.get("schema_version") or "") != "course_teaching_plan_v3":
        return False
    sections = [item for item in plan.get("sections") or [] if isinstance(item, dict)]
    return bool(sections) and all(
        str(section.get("node_id") or "").strip()
        and any(
            isinstance(module, dict)
            and str(module.get("module_id") or module.get("block_id") or "").strip()
            for module in section.get("teaching_modules") or []
        )
        for section in sections
    )


def teacher_lesson_script_revision_has_content(revision: object) -> bool:
    if not isinstance(revision, dict):
        return False
    if (
        str(revision.get("generation_source") or "")
        == "model_block_pipeline_with_recovery_preview"
    ):
        return False
    quality_report = revision.get("quality_report")
    if isinstance(quality_report, dict) and quality_report.get("passed") is False:
        return False
    if revision.get("publication_eligible") is False:
        return False
    sections = [
        item for item in revision.get("sections") or []
        if isinstance(item, dict)
    ]
    return bool(sections) and all(
        str(item.get("section_node_id") or "").strip()
        and str(item.get("content") or "").strip()
        and list(item.get("blocks") or [])
        for item in sections
    )


def teacher_lesson_plan_readiness(lesson: object) -> dict[str, Any]:
    if not isinstance(lesson, dict):
        return _readiness(False, "asset_missing")
    revision_id = str(lesson.get("working_revision_id") or "")
    if not revision_id:
        return _readiness(False, "revision_missing")
    if str(lesson.get("source_state") or "current") != "current":
        return _readiness(False, "source_stale")
    revision = _revision(lesson.get("revisions"), revision_id)
    if not isinstance(revision, dict):
        return _readiness(False, "revision_not_found")
    if not teacher_lesson_plan_revision_has_content(revision):
        return _readiness(False, "content_incomplete")
    return _readiness(True)


def teacher_lesson_script_readiness(
    lesson: object,
    *,
    plan_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(lesson, dict):
        return _readiness(False, "asset_missing")
    plan_state = plan_readiness or teacher_lesson_plan_readiness(lesson)
    if not plan_state.get("ready"):
        return _readiness(False, "upstream_plan_not_ready")
    revision_id = str(lesson.get("working_script_revision_id") or "")
    if not revision_id:
        return _readiness(False, "revision_missing")
    revision = _revision(lesson.get("script_revisions"), revision_id)
    if not isinstance(revision, dict):
        return _readiness(False, "revision_not_found")
    if (
        str(revision.get("source_lesson_plan_revision_id") or "")
        != str(lesson.get("working_revision_id") or "")
    ):
        return _readiness(False, "upstream_plan_mismatch")
    if not teacher_lesson_script_revision_has_content(revision):
        return _readiness(False, "content_incomplete")
    return _readiness(True)


def teacher_lesson_ppt_asset_readiness(
    lesson: object,
    asset: object,
    *,
    plan_readiness: dict[str, Any] | None = None,
    script_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(lesson, dict) or not isinstance(asset, dict):
        return _readiness(False, "asset_missing")
    plan_state = plan_readiness or teacher_lesson_plan_readiness(lesson)
    if not plan_state.get("ready"):
        return _readiness(False, "upstream_plan_not_ready")
    script_state = script_readiness or teacher_lesson_script_readiness(
        lesson,
        plan_readiness=plan_state,
    )
    if not script_state.get("ready"):
        return _readiness(False, "upstream_script_not_ready")
    if str(asset.get("source_state") or "current") != "current":
        return _readiness(False, "source_stale")
    if (
        str(asset.get("source_lesson_plan_revision_id") or "")
        != str(lesson.get("working_revision_id") or "")
    ):
        return _readiness(False, "upstream_plan_mismatch")
    if (
        str(asset.get("source_script_revision_id") or "")
        != str(lesson.get("working_script_revision_id") or "")
    ):
        return _readiness(False, "upstream_script_mismatch")
    if not any(
        str(asset.get(field) or "")
        for field in (
            "working_representation_id",
            "working_v6_revision_id",
            "working_revision_id",
        )
    ):
        return _readiness(False, "revision_missing")
    return _readiness(True)
