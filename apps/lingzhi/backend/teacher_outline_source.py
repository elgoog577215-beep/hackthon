from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_document import course_view_from_document


def has_teaching_structure(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    if source.get("outline_framework_only") is True:
        return False
    if str(source.get("generation_status") or "") in {
        "outline_framework_ready",
        "outline_detail_generation",
        "outline_detail_failed",
    }:
        return False
    outline_stage = (source.get("generation_stage_artifacts") or {}).get("outline") or {}
    if str(outline_stage.get("strategy") or "") in {
        "teacher_framework_then_detail_batches",
        "teacher_framework_then_lecture_tasks",
    } and str(outline_stage.get("status") or "") not in {
        "completed",
        "completed_with_warnings",
    }:
        return False
    if any(isinstance(item, dict) for item in source.get("nodes") or []):
        return True
    document = source.get("course_document")
    if not isinstance(document, dict):
        return False
    return bool(document.get("sections") or document.get("blocks"))


def matches_course_shell(source: Any, course_id: str) -> bool:
    if not isinstance(source, dict):
        return False
    if str(source.get("course_id") or "") == course_id:
        return True
    document = source.get("course_document")
    return isinstance(document, dict) and str(document.get("course_id") or "") == course_id


def read_teacher_outline_source(
    course: dict[str, Any],
    task_manager: Any | None,
) -> dict[str, Any]:
    """Read the current usable teacher outline without persisting or repairing it.

    The same selection serves content, generation and production status. A
    completed workspace (or its last usable result) precedes the course shell;
    incomplete framework/detail previews never grant generation permission.
    """
    course_id = str(course.get("course_id") or "")
    getter = getattr(task_manager, "get_generation_workspace_course_for_task", None)
    selected = (
        getter(
            course_id,
            task_type="teacher_outline_generation",
            require_confirmed_outline=False,
            require_usable_outline=True,
        )
        if callable(getter)
        else None
    )
    if not (matches_course_shell(selected, course_id) and has_teaching_structure(selected)):
        selected = course if has_teaching_structure(course) else None
    if selected is None:
        for name in ("get_generation_workspace_course", "get_generation_preview"):
            getter = getattr(task_manager, name, None)
            candidate = getter(course_id) if callable(getter) else None
            if matches_course_shell(candidate, course_id) and has_teaching_structure(candidate):
                selected = candidate
                break
    source = deepcopy({**course, **selected}) if selected is not None else deepcopy(course)
    if not source.get("nodes") and isinstance(source.get("course_document"), dict):
        source = course_view_from_document(source, source["course_document"])
    plan = source.get("course_plan") or source.get("course_outline")
    if has_teaching_structure(source) and isinstance(plan, dict) and plan.get("chapters"):
        from course_generation.outline import _QUALITY_RULE_VERSION, review_course_outline_document

        if (source.get("course_outline_quality_report") or {}).get("rule_version") != _QUALITY_RULE_VERSION:
            source["course_outline_quality_report"] = review_course_outline_document(plan, course_context=source)
    return source
