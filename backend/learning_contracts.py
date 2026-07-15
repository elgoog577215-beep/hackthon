"""Shared identity and task-reference contracts for the learning runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

TASK_KINDS = {"reading", "practice", "diagnostic", "remediation", "validation", "record", "review"}


def task_revision_id(value: dict[str, Any] | None) -> str:
    """Return the canonical task revision while reading legacy question IDs."""
    item = value or {}
    return str(
        item.get("task_revision_id")
        or item.get("question_revision_id")
        or (item.get("metadata") or {}).get("task_revision_id")
        or ""
    )


def learning_context_ref(
    course: dict[str, Any],
    *,
    chapter_id: str = "",
    node_id: str = "",
    objective: dict[str, Any] | None = None,
    content_anchor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = objective or {}
    return {
        "course_id": str(course.get("course_id") or ""),
        "course_version_id": str(course.get("current_course_version_id") or ""),
        "chapter_id": str(chapter_id or ""),
        "node_id": str(node_id or current.get("node_id") or ""),
        "objective_id": str(current.get("objective_id") or ""),
        "objective_revision_id": str(current.get("objective_revision_id") or ""),
        "content_anchor": deepcopy(content_anchor) if content_anchor else None,
    }


def learning_task_ref(
    *,
    kind: str,
    object_id: str,
    revision_id: str = "",
    status: str = "active",
    context: dict[str, Any] | None = None,
    return_node_id: str = "",
) -> dict[str, Any]:
    normalized_kind = kind if kind in TASK_KINDS else "reading"
    return {
        "kind": normalized_kind,
        "object_id": str(object_id or ""),
        "task_revision_id": str(revision_id or ""),
        "status": str(status or "active"),
        "context": deepcopy(context or {}),
        "return_node_id": str(return_node_id or (context or {}).get("node_id") or ""),
    }


def task_ref_for_action(
    action: dict[str, Any],
    *,
    course: dict[str, Any],
    chapter_id: str,
    objective: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any] | None,
) -> dict[str, Any]:
    action_type = str(action.get("action_type") or "")
    node_id = str(action.get("node_id") or (objective or {}).get("node_id") or "")
    context = learning_context_ref(
        course,
        chapter_id=chapter_id,
        node_id=node_id,
        objective=objective if (objective or {}).get("node_id") == node_id else None,
        content_anchor=(snapshot or {}).get("content_anchor") if (snapshot or {}).get("node_id") == node_id else None,
    )

    if action_type == "start_mastery_check":
        questions = ((course.get("learning_assets") or {}).get("questions") or [])
        mastery_task = next((
            item for item in questions
            if str(item.get("node_id") or "") == node_id
            and str(item.get("practice_level") or "") == "mastery_check"
            and str(item.get("status") or "active") == "active"
        ), None) or {}
        if mastery_task:
            return learning_task_ref(
                kind="practice",
                object_id="",
                revision_id=str(mastery_task.get("task_revision_id") or mastery_task.get("revision_id") or ""),
                status="active",
                context={
                    **context,
                    "objective_id": str(mastery_task.get("objective_id") or context.get("objective_id") or ""),
                    "objective_revision_id": str(
                        mastery_task.get("objective_revision_id")
                        or context.get("objective_revision_id")
                        or ""
                    ),
                },
                return_node_id=node_id,
            )

    if action.get("scope") == "practice_attempt":
        attempt = next((item for item in attempts if item.get("attempt_id") == action.get("target_id")), None) or {}
        return learning_task_ref(
            kind="practice",
            object_id=str(attempt.get("attempt_id") or action.get("target_id") or ""),
            revision_id=task_revision_id(attempt),
            status=str(attempt.get("status") or "active"),
            context={
                **context,
                "node_id": str(attempt.get("node_id") or node_id),
                "objective_id": str(attempt.get("objective_id") or context.get("objective_id") or ""),
                "objective_revision_id": str(attempt.get("objective_revision_id") or context.get("objective_revision_id") or ""),
            },
            return_node_id=str(attempt.get("node_id") or node_id),
        )

    if action.get("scope") == "diagnostic_workflow":
        current_workflow = workflow or {}
        task = current_workflow.get("current_task") or {}
        case = current_workflow.get("case") or {}
        session = current_workflow.get("session") or {}
        kind = "validation" if "validation" in action_type else "remediation" if "remediation" in action_type else "diagnostic"
        object_id = (
            session.get("remediation_session_id")
            if kind in {"remediation", "validation"}
            else case.get("diagnostic_case_id")
        )
        return learning_task_ref(
            kind=kind,
            object_id=str(object_id or action.get("target_id") or ""),
            revision_id=task_revision_id(task) or str(action.get("target_revision_id") or action.get("target_id") or ""),
            status="active",
            context={
                **context,
                "node_id": str(case.get("node_id") or node_id),
                "objective_id": str(case.get("objective_id") or context.get("objective_id") or ""),
                "objective_revision_id": str(case.get("objective_revision_id") or context.get("objective_revision_id") or ""),
            },
            return_node_id=str((case.get("return_anchor") or {}).get("node_id") or case.get("node_id") or node_id),
        )

    if action.get("scope") == "learning_record":
        return learning_task_ref(
            kind="review" if action_type == "start_due_review" else "record",
            object_id=str(action.get("target_id") or ""),
            status="active",
            context=context,
            return_node_id=node_id,
        )

    return learning_task_ref(
        kind="reading",
        object_id=str(action.get("target_id") or node_id),
        revision_id=str(action.get("target_revision_id") or ""),
        status="stale" if action_type == "confirm_version_change" else "active",
        context=context,
        return_node_id=node_id,
    )


__all__ = [
    "TASK_KINDS",
    "learning_context_ref",
    "learning_task_ref",
    "task_ref_for_action",
    "task_revision_id",
]
