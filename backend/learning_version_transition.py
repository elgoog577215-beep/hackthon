"""Version-transition planning and coordinated learning-state confirmation."""

from __future__ import annotations

from copy import deepcopy
import threading
from typing import Any

from content_blocks import resolve_content_anchor
from diagnostic_service import invalidate_stale_workflows
from learning_events import load_learning_events, record_learning_event
from learning_progress import project_learning_objective_bindings
from learning_records import learning_record_repository, project_record
from learning_snapshots import learning_snapshot_repository
from practice_attempts import practice_attempt_repository


ACTIVE_ATTEMPT_STATUSES = {"in_progress", "submitted", "grading"}
ACTIVE_CASE_STATUSES = {"testing", "confirmed", "remediating", "reopened", "unresolved"}
ACTIVE_SESSION_STATUSES = {"active", "awaiting_validation", "reopened"}
SAFE_ANCHOR_STATUSES = {"exact", "updated_block", "fingerprint_remap", "node_fallback"}
UNSAFE_ANCHOR_STATUSES = {"course_fallback", "unavailable"}


class VersionTransitionConflict(Exception):
    def __init__(self, current: dict[str, Any]):
        super().__init__("learning version transition revision conflict")
        self.current = current


class VersionTransitionTargetRequired(ValueError):
    def __init__(self, plan: dict[str, Any]):
        super().__init__("version transition requires an explicit target node")
        self.plan = plan


class NoPendingVersionTransition(ValueError):
    pass


_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def build_version_transition_plan(
    course_data: dict[str, Any],
    *,
    user_id: str,
    snapshot: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Describe how historical learning objects relate to the current course."""
    course = project_learning_objective_bindings(course_data)
    current_version_id = str(course.get("current_course_version_id") or "")
    source_versions: set[str] = set()

    snapshot_plan = _snapshot_plan(course, snapshot)
    if snapshot_plan and snapshot_plan["action"] != "none":
        source_versions.add(str(snapshot_plan.get("source_version_id") or ""))

    attempt_plans = []
    for attempt in attempts:
        source_version = str(attempt.get("course_version_id") or "")
        if attempt.get("status") not in ACTIVE_ATTEMPT_STATUSES or not source_version or source_version == current_version_id:
            continue
        source_versions.add(source_version)
        attempt_plans.append({
            "attempt_id": str(attempt.get("attempt_id") or ""),
            "source_version_id": source_version,
            "status": str(attempt.get("status") or ""),
            "node_id": str(attempt.get("node_id") or ""),
            "task_revision_id": str(attempt.get("task_revision_id") or attempt.get("question_revision_id") or ""),
            "has_draft": bool(attempt.get("answer_payload")),
            "action": "invalidate",
        })

    workflow_plans = _workflow_plans(workflow, current_version_id)
    source_versions.update(item["source_version_id"] for item in workflow_plans)

    if not source_versions:
        return None

    projected_records = [project_record(item, course) for item in records]
    record_statuses: dict[str, int] = {}
    for item in projected_records:
        status = str(item.get("migration_status") or "orphaned")
        record_statuses[status] = record_statuses.get(status, 0) + 1

    requires_target = bool(snapshot_plan and snapshot_plan.get("requires_target_node"))
    return {
        "schema_version": "learning_version_transition_v1",
        "current_version_id": current_version_id,
        "source_version_ids": sorted(item for item in source_versions if item),
        "snapshot": snapshot_plan,
        "attempts": attempt_plans,
        "workflows": workflow_plans,
        "records": {
            "total": len(projected_records),
            "by_migration_status": record_statuses,
            "needs_confirmation_ids": [
                str(item.get("record_id") or "")
                for item in projected_records
                if item.get("migration_status") in {"needs_confirmation", "orphaned"}
            ],
        },
        "requires_target_node": requires_target,
        "can_confirm": not requires_target,
        "summary": {
            "migrated_snapshot": bool(snapshot_plan and snapshot_plan.get("action") == "migrate"),
            "invalidated_attempts": len(attempt_plans),
            "stale_workflows": len(workflow_plans),
            "preserved_records": len(projected_records),
        },
    }


def confirm_version_transition(
    course_data: dict[str, Any],
    *,
    user_id: str,
    expected_projection_revision_id: str,
    request_id: str,
    node_id: str | None = None,
    target_node_id: str | None = None,
) -> dict[str, Any]:
    """Apply a version plan while preserving all historical evidence objects."""
    course = project_learning_objective_bindings(course_data)
    course_id = str(course.get("course_id") or "")
    current_version_id = str(course.get("current_course_version_id") or "")
    with _lock(user_id, course_id):
        existing = _confirmation_event(user_id, course_id, request_id)
        if existing:
            return _result(course, user_id, node_id, existing, already_confirmed=True)

        from learning_continuation import build_learning_continuation

        projection = build_learning_continuation(course, user_id=user_id, node_id=node_id)
        plan = projection.get("version_transition")
        if not plan:
            recovered = _recover_confirmation_event(course, user_id=user_id, request_id=request_id)
            if recovered:
                return _result(course, user_id, node_id, recovered, already_confirmed=True)
            raise NoPendingVersionTransition("no pending version transition")
        if projection.get("projection_revision_id") != expected_projection_revision_id:
            raise VersionTransitionConflict(projection)
        if plan.get("requires_target_node") and not _valid_target_node(course, target_node_id):
            raise VersionTransitionTargetRequired(plan)

        migrated_snapshot = _migrate_snapshot(
            course,
            user_id=user_id,
            snapshot=learning_snapshot_repository.load(user_id, course_id),
            target_node_id=target_node_id,
            request_id=request_id,
            plan=plan,
        )
        invalidated_attempt_ids: list[str] = []
        for item in plan.get("attempts") or []:
            attempt_id = str(item.get("attempt_id") or "")
            if not attempt_id:
                continue
            _, changed = practice_attempt_repository.invalidate(
                user_id,
                course_id,
                attempt_id,
                reason=f"course_version_changed:{item.get('source_version_id')}->{current_version_id}",
            )
            if changed:
                invalidated_attempt_ids.append(attempt_id)
        stale_workflow_count = invalidate_stale_workflows(course, user_id=user_id)

        event = record_learning_event(
            event_type="course_version_transition_confirmed",
            actor="user",
            source="learning_continuation.version_change",
            user_id=user_id,
            course_id=course_id,
            course_version_id=current_version_id,
            node_id=str((migrated_snapshot or {}).get("node_id") or target_node_id or node_id or ""),
            evidence={
                "source_version_ids": plan.get("source_version_ids") or [],
                "snapshot_resolution": ((plan.get("snapshot") or {}).get("resolution_status")),
            },
            result={
                "snapshot_revision": int((migrated_snapshot or {}).get("revision") or 0),
                "invalidated_attempt_ids": invalidated_attempt_ids,
                "stale_workflow_count": stale_workflow_count,
                "preserved_record_count": int((plan.get("records") or {}).get("total") or 0),
            },
            metadata={"request_id": request_id, "transition_schema": "learning_version_transition_v1"},
        )
        return _result(course, user_id, node_id, event, already_confirmed=False)


def _snapshot_plan(course: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    current_version_id = str(course.get("current_course_version_id") or "")
    source_version_id = str(snapshot.get("course_version_id") or "")
    if not source_version_id or source_version_id == current_version_id:
        return {
            "snapshot_id": str(snapshot.get("snapshot_id") or ""),
            "source_version_id": source_version_id,
            "resolution_status": "exact",
            "target_node_id": str(snapshot.get("node_id") or ""),
            "action": "none",
            "requires_target_node": False,
        }
    resolution = resolve_content_anchor(
        course,
        node_id=snapshot.get("node_id"),
        anchor=snapshot.get("content_anchor"),
    )
    status = str(resolution.get("status") or "unavailable")
    resolved_anchor = resolution.get("resolved_anchor") or {}
    return {
        "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        "source_version_id": source_version_id,
        "resolution_status": status,
        "content_changed": bool(resolution.get("content_changed")),
        "target_node_id": str(resolved_anchor.get("node_id") or ""),
        "previous_task_kind": str((snapshot.get("task_state") or {}).get("kind") or "reading"),
        "previous_task_id": str((snapshot.get("task_state") or {}).get("object_id") or ""),
        "action": "migrate" if status in SAFE_ANCHOR_STATUSES else "select_target",
        "requires_target_node": status in UNSAFE_ANCHOR_STATUSES,
    }


def _workflow_plans(workflow: dict[str, Any], current_version_id: str) -> list[dict[str, Any]]:
    result = []
    for kind, item, active_statuses, id_field in (
        ("diagnostic_case", workflow.get("case") or {}, ACTIVE_CASE_STATUSES, "diagnostic_case_id"),
        ("remediation_session", workflow.get("session") or {}, ACTIVE_SESSION_STATUSES, "remediation_session_id"),
    ):
        source_version = str(item.get("course_version_id") or "")
        if not item or item.get("status") not in active_statuses or not source_version or source_version == current_version_id:
            continue
        result.append({
            "kind": kind,
            "object_id": str(item.get(id_field) or ""),
            "source_version_id": source_version,
            "status": str(item.get("status") or ""),
            "action": "mark_stale",
        })
    return result


def _migrate_snapshot(
    course: dict[str, Any],
    *,
    user_id: str,
    snapshot: dict[str, Any] | None,
    target_node_id: str | None,
    request_id: str,
    plan: dict[str, Any],
) -> dict[str, Any] | None:
    if not snapshot:
        return None
    current_version_id = str(course.get("current_course_version_id") or "")
    if str(snapshot.get("course_version_id") or "") == current_version_id:
        return snapshot
    resolution = resolve_content_anchor(
        course,
        node_id=snapshot.get("node_id"),
        anchor=snapshot.get("content_anchor"),
    )
    if str(resolution.get("status") or "") in UNSAFE_ANCHOR_STATUSES:
        resolution = resolve_content_anchor(course, node_id=target_node_id, anchor={})
    anchor = deepcopy(resolution.get("resolved_anchor") or {})
    node_id = str(anchor.get("node_id") or target_node_id or snapshot.get("node_id") or "")
    node = next((item for item in course.get("nodes") or [] if str(item.get("node_id") or "") == node_id), {})
    previous_task = snapshot.get("task_state") or {}
    payload = deepcopy(snapshot)
    payload.update({
        "course_version_id": current_version_id,
        "node_id": node_id,
        "node_name": str(node.get("node_name") or snapshot.get("node_name") or ""),
        "content_anchor": anchor or None,
        "task_state": {
            "kind": "reading",
            "object_id": node_id,
            "task_revision_id": "",
            "status": "active",
            "context": {
                "course_id": str(course.get("course_id") or ""),
                "course_version_id": current_version_id,
                "node_id": node_id,
                "content_anchor": anchor or None,
            },
            "return_node_id": node_id,
            "draft_revision": 0,
            "metadata": {
                "transitioned_from_version": str(snapshot.get("course_version_id") or ""),
                "transition_request_id": request_id,
                "planned_invalidated_attempts": len(plan.get("attempts") or []),
                "planned_stale_workflows": len(plan.get("workflows") or []),
                "preserved_record_count": int((plan.get("records") or {}).get("total") or 0),
                "invalidated_task_kind": str(previous_task.get("kind") or "reading"),
                "invalidated_task_id": str(previous_task.get("object_id") or ""),
            },
        },
        "interaction_state": {
            **deepcopy(snapshot.get("interaction_state") or {}),
            "remediation_session_id": "",
        },
        "source": "live",
    })
    return learning_snapshot_repository.save(
        user_id,
        str(course.get("course_id") or ""),
        expected_revision=int(snapshot.get("revision") or 0),
        payload=payload,
    )


def _valid_target_node(course: dict[str, Any], target_node_id: str | None) -> bool:
    if not target_node_id:
        return False
    return any(
        str(item.get("node_id") or "") == target_node_id and str(item.get("node_content") or "").strip()
        for item in course.get("nodes") or []
    )


def _confirmation_event(user_id: str, course_id: str, request_id: str) -> dict[str, Any] | None:
    return next((
        item for item in reversed(load_learning_events(
            user_id=user_id,
            course_id=course_id,
            event_type="course_version_transition_confirmed",
        ))
        if str((item.get("metadata") or {}).get("request_id") or "") == request_id
    ), None)


def _recover_confirmation_event(
    course: dict[str, Any],
    *,
    user_id: str,
    request_id: str,
) -> dict[str, Any] | None:
    course_id = str(course.get("course_id") or "")
    snapshot = learning_snapshot_repository.load(user_id, course_id)
    metadata = ((snapshot or {}).get("task_state") or {}).get("metadata") or {}
    current_version_id = str(course.get("current_course_version_id") or "")
    if (
        str(metadata.get("transition_request_id") or "") != request_id
        or str((snapshot or {}).get("course_version_id") or "") != current_version_id
    ):
        return None
    return record_learning_event(
        event_type="course_version_transition_confirmed",
        actor="system",
        source="learning_continuation.version_change.recovery",
        user_id=user_id,
        course_id=course_id,
        course_version_id=current_version_id,
        node_id=str((snapshot or {}).get("node_id") or ""),
        evidence={
            "source_version_ids": [str(metadata.get("transitioned_from_version") or "")],
            "recovered_after_interruption": True,
        },
        result={
            "snapshot_revision": int((snapshot or {}).get("revision") or 0),
            "invalidated_attempt_count": int(metadata.get("planned_invalidated_attempts") or 0),
            "stale_workflow_count": int(metadata.get("planned_stale_workflows") or 0),
            "preserved_record_count": int(metadata.get("preserved_record_count") or 0),
        },
        metadata={"request_id": request_id, "transition_schema": "learning_version_transition_v1"},
    )


def _result(
    course: dict[str, Any],
    user_id: str,
    node_id: str | None,
    event: dict[str, Any],
    *,
    already_confirmed: bool,
) -> dict[str, Any]:
    from learning_runtime import build_learning_runtime

    runtime = build_learning_runtime(course, user_id=user_id, node_id=node_id)
    return {
        "status": "already_confirmed" if already_confirmed else "confirmed",
        "event_id": event.get("event_id"),
        "result": deepcopy(event.get("result") or {}),
        "runtime": runtime,
    }


def _lock(user_id: str, course_id: str) -> threading.RLock:
    key = f"{user_id}\0{course_id}"
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


__all__ = [
    "NoPendingVersionTransition",
    "VersionTransitionConflict",
    "VersionTransitionTargetRequired",
    "build_version_transition_plan",
    "confirm_version_transition",
]
