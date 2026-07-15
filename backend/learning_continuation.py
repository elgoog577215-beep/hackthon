"""Deterministic chapter entry, result, and next-action projection."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from course_versioning import stable_hash
from course_learning_availability import (
    has_mastery_task,
    project_course_learning_availability,
)
from diagnostic_service import workflow_view
from learning_contracts import task_ref_for_action
from learning_events import load_learning_events
from learning_progress import build_learning_progress, project_learning_objective_bindings
from learning_records import learning_record_repository
from learning_snapshots import learning_snapshot_repository
from learning_version_transition import build_version_transition_plan
from practice_attempts import practice_attempt_repository

SCHEMA_VERSION = "learning_continuation_v1"
ACTIVE_ATTEMPT_STATUSES = {"in_progress", "submitted", "grading"}
ACTIVE_CASE_STATUSES = {"testing", "confirmed", "remediating", "reopened", "unresolved"}
ACTIVE_SESSION_STATUSES = {"active", "awaiting_validation", "reopened"}


def build_learning_continuation(
    course_data: dict[str, Any],
    *,
    user_id: str,
    node_id: str | None = None,
    progress: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    attempts: list[dict[str, Any]] | None = None,
    workflow: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Project current learning continuity without writing another state store."""
    course = project_learning_objective_bindings(course_data)
    course_id = str(course.get("course_id") or "")
    course_version_id = str(course.get("current_course_version_id") or "")
    source_attempts = attempts if attempts is not None else practice_attempt_repository.list(user_id, course_id)
    source_events = events if events is not None else load_learning_events(user_id=user_id, course_id=course_id)
    source_progress = progress if progress is not None else build_learning_progress(
        course,
        user_id=user_id,
        events=source_events,
        attempts=source_attempts,
    )
    source_snapshot = snapshot if snapshot is not None else learning_snapshot_repository.load(user_id, course_id)
    source_workflow = workflow if workflow is not None else workflow_view(user_id, course_id)
    source_records = records if records is not None else learning_record_repository.list(user_id, course_id)
    timestamp = now or datetime.now(timezone.utc)

    chapters = _chapters(course, source_progress)
    chapter = _select_chapter(chapters, node_id or str((source_snapshot or {}).get("node_id") or ""))
    objective = _select_objective(chapter, node_id, source_snapshot)
    chapter_ids = {str(item.get("node_id") or "") for item in chapter.get("objectives") or []}
    contract = _progression_contract(course, chapter)
    course_availability = project_course_learning_availability(course)
    version_conflicts = _version_conflicts(
        course_version_id,
        source_snapshot,
        source_attempts,
        source_workflow,
    )
    version_transition = build_version_transition_plan(
        course,
        user_id=user_id,
        snapshot=source_snapshot,
        attempts=source_attempts,
        workflow=source_workflow,
        records=source_records,
    )
    risks = _entry_risks(
        course,
        chapter,
        source_progress,
        contract,
        source_events,
        timestamp,
    )
    workflow_state = _active_workflow(source_workflow)
    workflow_node_id = str(((workflow_state or {}).get("case") or {}).get("node_id") or "")
    active_workflow = workflow_state if workflow_state and (not workflow_node_id or workflow_node_id in chapter_ids) else None
    other_workflow = workflow_state if workflow_state and not active_workflow else None
    active_attempts = [item for item in source_attempts if item.get("status") in ACTIVE_ATTEMPT_STATUSES]
    current_attempts = [item for item in active_attempts if str(item.get("node_id") or "") in chapter_ids]
    other_attempts = [item for item in active_attempts if str(item.get("node_id") or "") not in chapter_ids]
    blockers = _blocking_issues(source_records, chapter_ids)
    open_issues = _open_issues(source_records, chapter_ids)
    due_reviews = _due_reviews(source_records, chapter_ids, timestamp)
    chapter_result = _chapter_result(chapter, contract, source_records, active_workflow, version_conflicts)
    primary_action = _select_primary_action(
        course=course,
        requested_node_id=node_id,
        chapter=chapter,
        objective=objective,
        chapters=chapters,
        snapshot=source_snapshot,
        active_attempts=current_attempts,
        active_workflow=active_workflow,
        blockers=blockers,
        open_issues=open_issues,
        risks=risks,
        due_reviews=due_reviews,
        contract=contract,
        chapter_result=chapter_result,
        version_conflicts=version_conflicts,
        course_availability=course_availability,
    )
    action_objective = next((
        item for item in chapter.get("objectives") or []
        if str(item.get("node_id") or "") == str(primary_action.get("node_id") or "")
    ), None)
    primary_action["task_ref"] = task_ref_for_action(
        primary_action,
        course=course,
        chapter_id=str(chapter.get("chapter_id") or ""),
        objective=action_objective or objective,
        snapshot=source_snapshot,
        attempts=source_attempts,
        workflow=active_workflow or source_workflow,
    )
    secondary_notices = _secondary_notices(
        primary_action,
        risks=risks,
        due_reviews=due_reviews,
        blockers=blockers,
        open_issues=open_issues,
        active_attempts=current_attempts,
        other_attempts=other_attempts,
        other_workflow=other_workflow,
    )
    task_continuity = _task_continuity(
        version_conflicts=version_conflicts,
        active_workflow=active_workflow,
        active_attempts=current_attempts,
        blockers=blockers,
        risks=risks,
    )
    projection_revision_id = _projection_revision(
        course_version_id=course_version_id,
        progress=source_progress,
        snapshot=source_snapshot,
        attempts=source_attempts,
        workflow=source_workflow,
        records=source_records,
        events=source_events,
        selected_chapter_id=str(chapter.get("chapter_id") or ""),
        temporal_state={
            "due_review_ids": [str(item.get("record_id") or "") for item in due_reviews],
            "deferred_risk_ids": [str(item.get("risk_id") or "") for item in risks if item.get("deferred")],
        },
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "course_id": course_id,
        "course_version_id": course_version_id,
        "user_id": user_id,
        "projection_revision_id": projection_revision_id,
        "chapter": {
            "chapter_id": chapter.get("chapter_id"),
            "chapter_name": chapter.get("chapter_name"),
            "chapter_index": chapter.get("chapter_index"),
            "chapter_count": len(chapters),
            "objective_count": len(chapter.get("objectives") or []),
        },
        "current_objective": deepcopy(action_objective or objective) if (action_objective or objective) else None,
        "progress": {
            "learning": _chapter_learning_status(chapter),
            "mastery": _chapter_mastery_status(chapter),
            "task_continuity": task_continuity,
        },
        "entry_mode": _entry_mode(primary_action, chapter_result),
        "course_availability": course_availability,
        "progression_contract": contract,
        "risks": risks,
        "chapter_result": chapter_result,
        "primary_action": primary_action,
        "secondary_notices": secondary_notices,
        "version_conflicts": version_conflicts,
        "version_transition": version_transition,
    }


def _chapters(course: dict[str, Any], progress: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = course.get("nodes") or []
    node_by_id = {str(item.get("node_id") or ""): item for item in nodes}
    l1_nodes = [item for item in nodes if int(item.get("node_level") or 1) == 1]
    objective_progress = {
        str(item.get("node_id") or ""): deepcopy(item)
        for item in progress.get("nodes") or []
    }
    chapters: list[dict[str, Any]] = []
    assigned: set[str] = set()

    for chapter_index, chapter_node in enumerate(l1_nodes):
        chapter_id = str(chapter_node.get("node_id") or "")
        child_ids = [
            str(item.get("node_id") or "")
            for item in nodes
            if str(item.get("parent_node_id") or "") == chapter_id
            and str(item.get("node_id") or "") in objective_progress
        ]
        if chapter_id in objective_progress and not child_ids:
            child_ids = [chapter_id]
        if not child_ids:
            continue
        assigned.update(child_ids)
        chapters.append({
            "chapter_id": chapter_id,
            "chapter_name": str(chapter_node.get("node_name") or ""),
            "chapter_index": chapter_index,
            "objectives": [objective_progress[item] for item in child_ids],
        })

    for node_id, objective in objective_progress.items():
        if node_id in assigned:
            continue
        node = node_by_id.get(node_id) or {}
        chapters.append({
            "chapter_id": node_id,
            "chapter_name": str(node.get("node_name") or objective.get("node_name") or ""),
            "chapter_index": len(chapters),
            "objectives": [objective],
        })

    if chapters:
        for chapter_index, chapter in enumerate(chapters):
            chapter["chapter_index"] = chapter_index
        return chapters
    return [{
        "chapter_id": "",
        "chapter_name": str(course.get("course_name") or ""),
        "chapter_index": 0,
        "objectives": [],
    }]


def _select_chapter(chapters: list[dict[str, Any]], target_node_id: str) -> dict[str, Any]:
    for chapter in chapters:
        if target_node_id == chapter.get("chapter_id"):
            return chapter
        if any(item.get("node_id") == target_node_id for item in chapter.get("objectives") or []):
            return chapter
    for chapter in chapters:
        if any(item.get("reading_status") != "learned" for item in chapter.get("objectives") or []):
            return chapter
    return chapters[-1]


def _select_objective(
    chapter: dict[str, Any],
    requested_node_id: str | None,
    snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    objectives = chapter.get("objectives") or []
    candidates = [requested_node_id, str((snapshot or {}).get("node_id") or "")]
    has_unfinished = any(item.get("reading_status") != "learned" for item in objectives)
    for candidate in candidates:
        if not candidate:
            continue
        found = next((item for item in objectives if item.get("node_id") == candidate), None)
        if found and (found.get("reading_status") != "learned" or not has_unfinished):
            return found
    return next((item for item in objectives if item.get("reading_status") != "learned"), None) or next(
        (item for item in objectives if item.get("mastery_status") != "mastered"),
        objectives[0] if objectives else None,
    )


def _progression_contract(course: dict[str, Any], chapter: dict[str, Any]) -> dict[str, Any]:
    assets = course.get("learning_assets") or {}
    contracts = assets.get("chapter_progression_contracts") or []
    if isinstance(contracts, dict):
        contracts = list(contracts.values())
    found = next((item for item in contracts if item.get("chapter_id") == chapter.get("chapter_id")), None) or {}
    objective_ids = [str(item.get("objective_id") or "") for item in chapter.get("objectives") or []]
    return {
        "chapter_id": chapter.get("chapter_id"),
        "required_objective_ids": list(found.get("required_objective_ids") or objective_ids),
        "mastery_required": bool(found.get("mastery_required", False)),
        "prerequisite_policy": str(found.get("prerequisite_policy") or "advisory"),
        "completion_policy": str(found.get("completion_policy") or "reading_covered"),
        "source": "course_asset" if found else "legacy_compatible_default",
    }


def _version_conflicts(
    current_version_id: str,
    snapshot: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any],
) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    snapshot_version = str((snapshot or {}).get("course_version_id") or "")
    if snapshot and snapshot_version and snapshot_version != current_version_id:
        conflicts.append({"kind": "snapshot", "object_id": str(snapshot.get("snapshot_id") or ""), "version_id": snapshot_version})
    for attempt in attempts:
        version_id = str(attempt.get("course_version_id") or "")
        if attempt.get("status") == "in_progress" and version_id and version_id != current_version_id:
            conflicts.append({"kind": "practice_attempt", "object_id": str(attempt.get("attempt_id") or ""), "version_id": version_id})
    for kind, item in (("diagnostic_case", workflow.get("case")), ("remediation_session", workflow.get("session"))):
        if not item:
            continue
        active = item.get("status") in (ACTIVE_CASE_STATUSES if kind == "diagnostic_case" else ACTIVE_SESSION_STATUSES)
        version_id = str(item.get("course_version_id") or "")
        if active and version_id and version_id != current_version_id:
            object_field = "diagnostic_case_id" if kind == "diagnostic_case" else "remediation_session_id"
            conflicts.append({"kind": kind, "object_id": str(item.get(object_field) or ""), "version_id": version_id})
    return conflicts


def _entry_risks(
    course: dict[str, Any],
    chapter: dict[str, Any],
    progress: dict[str, Any],
    contract: dict[str, Any],
    events: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    nodes = {str(item.get("node_id") or ""): item for item in course.get("nodes") or []}
    progress_by_node = {str(item.get("node_id") or ""): item for item in progress.get("nodes") or []}
    prerequisite_ids: list[str] = []
    chapter_node_ids = {str(item.get("node_id") or "") for item in chapter.get("objectives") or []}
    for objective in chapter.get("objectives") or []:
        node = nodes.get(str(objective.get("node_id") or "")) or {}
        prerequisite_ids.extend(str(item) for item in node.get("prerequisite_node_ids") or [])
    prerequisite_ids = list(dict.fromkeys(
        item for item in prerequisite_ids if item and item not in chapter_node_ids
    ))
    deferred = _deferred_risks(events, now)
    risks: list[dict[str, Any]] = []
    for prerequisite_id in prerequisite_ids:
        prerequisite = progress_by_node.get(prerequisite_id)
        if prerequisite_id not in nodes and not prerequisite:
            continue
        if prerequisite and prerequisite.get("mastery_status") == "mastered":
            continue
        reliable_gap = bool(prerequisite and prerequisite.get("mastery_status") == "needs_review")
        required = contract.get("prerequisite_policy") == "required" and reliable_gap
        level = "action_required" if required else "action_recommended" if reliable_gap else "notice"
        risk_id = stable_hash({
            "chapter_id": chapter.get("chapter_id"),
            "prerequisite_node_id": prerequisite_id,
            "objective_revision_id": (prerequisite or {}).get("objective_revision_id"),
        }, prefix="lrisk_")
        risks.append({
            "risk_id": risk_id,
            "risk_type": "prerequisite_gap" if reliable_gap else "prerequisite_unverified",
            "level": level,
            "node_id": prerequisite_id,
            "node_name": str((nodes.get(prerequisite_id) or {}).get("node_name") or (prerequisite or {}).get("node_name") or ""),
            "reason_code": "required_prerequisite_needs_attention" if required else "prerequisite_needs_attention" if reliable_gap else "prerequisite_not_verified",
            "evidence_refs": list((prerequisite or {}).get("practice_attempt_ids") or []),
            "deferred": level != "action_required" and risk_id in deferred,
            "deferred_until": deferred.get(risk_id),
        })
    return risks


def _deferred_risks(events: list[dict[str, Any]], now: datetime) -> dict[str, str]:
    deferred: dict[str, str] = {}
    for event in events:
        if event.get("event_type") != "entry_risk_deferred":
            continue
        risk_id = str((event.get("metadata") or {}).get("risk_id") or "")
        until = str((event.get("result") or {}).get("deferred_until") or "")
        parsed = _parse_datetime(until)
        if risk_id and parsed and parsed > now:
            deferred[risk_id] = until
    return deferred


def _active_workflow(workflow: dict[str, Any]) -> dict[str, Any] | None:
    case = workflow.get("case")
    session = workflow.get("session")
    if not case or case.get("status") not in ACTIVE_CASE_STATUSES:
        return None
    phase = str(workflow.get("phase") or "diagnostic")
    return {
        "phase": phase,
        "case": case,
        "session": session,
        "current_task": workflow.get("current_task"),
    }


def _blocking_issues(records: list[dict[str, Any]], chapter_node_ids: set[str]) -> list[dict[str, Any]]:
    return [
        item for item in records
        if item.get("record_type") == "issue"
        and item.get("status") in {"open", "explaining", "awaiting_verification", "reopened"}
        and str(item.get("node_id") or "") in chapter_node_ids
        and (
            (item.get("metadata") or {}).get("blocking") is True
            or item.get("category") == "blocking"
        )
    ]


def _open_issues(records: list[dict[str, Any]], chapter_node_ids: set[str]) -> list[dict[str, Any]]:
    return [
        item for item in records
        if item.get("record_type") == "issue"
        and item.get("status") in {"open", "explaining", "awaiting_verification", "reopened"}
        and str(item.get("node_id") or "") in chapter_node_ids
        and item not in _blocking_issues(records, chapter_node_ids)
    ]


def _due_reviews(
    records: list[dict[str, Any]],
    chapter_node_ids: set[str],
    now: datetime,
) -> list[dict[str, Any]]:
    due: list[dict[str, Any]] = []
    for item in records:
        if item.get("record_type") != "review_task" or item.get("status") not in {"pending", "due"}:
            continue
        due_at = _parse_datetime(str(item.get("due_at") or ""))
        if item.get("status") == "due" or (due_at and due_at <= now):
            copied = deepcopy(item)
            copied["in_current_chapter"] = str(item.get("node_id") or "") in chapter_node_ids
            due.append(copied)
    return sorted(due, key=lambda item: (not item.get("in_current_chapter"), str(item.get("due_at") or "")))


def _chapter_result(
    chapter: dict[str, Any],
    contract: dict[str, Any],
    records: list[dict[str, Any]],
    active_workflow: dict[str, Any] | None,
    version_conflicts: list[dict[str, str]],
) -> dict[str, Any]:
    objectives = chapter.get("objectives") or []
    required_objectives = _required_objectives(chapter, contract)
    required_ids = {str(item.get("objective_id") or "") for item in required_objectives}
    chapter_node_ids = {str(item.get("node_id") or "") for item in objectives}
    objective_results = []
    for objective in objectives:
        node_id = str(objective.get("node_id") or "")
        related = [item for item in records if str(item.get("node_id") or "") == node_id]
        objective_results.append({
            "objective_id": objective.get("objective_id"),
            "objective_revision_id": objective.get("objective_revision_id"),
            "node_id": node_id,
            "node_name": objective.get("node_name"),
            "statement": objective.get("statement"),
            "reading_status": objective.get("reading_status"),
            "mastery_status": _mastery_label(str(objective.get("mastery_status") or "")),
            "evidence_strength": _evidence_strength(objective),
            "active_diagnostic": bool(active_workflow and (active_workflow.get("case") or {}).get("node_id") == node_id),
            "open_issue_count": sum(item.get("record_type") == "issue" and item.get("status") not in {"resolved", "archived"} for item in related),
            "due_review_count": sum(item.get("record_type") == "review_task" and item.get("status") == "due" for item in related),
            "stale": bool(version_conflicts),
            "required": str(objective.get("objective_id") or "") in required_ids,
        })
    state = "stale" if version_conflicts else _chapter_result_state(required_objectives)
    return {
        "state": state,
        "chapter_id": chapter.get("chapter_id"),
        "objectives": objective_results,
        "residuals": {
            "open_issues": sum(
                item.get("record_type") == "issue"
                and item.get("status") not in {"resolved", "archived"}
                and str(item.get("node_id") or "") in chapter_node_ids
                for item in records
            ),
            "due_reviews": sum(
                item.get("record_type") == "review_task"
                and item.get("status") == "due"
                and str(item.get("node_id") or "") in chapter_node_ids
                for item in records
            ),
            "active_diagnostic": bool(active_workflow),
        },
    }


def _select_primary_action(
    *,
    course: dict[str, Any],
    requested_node_id: str | None,
    chapter: dict[str, Any],
    objective: dict[str, Any] | None,
    chapters: list[dict[str, Any]],
    snapshot: dict[str, Any] | None,
    active_attempts: list[dict[str, Any]],
    active_workflow: dict[str, Any] | None,
    blockers: list[dict[str, Any]],
    open_issues: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    due_reviews: list[dict[str, Any]],
    contract: dict[str, Any],
    chapter_result: dict[str, Any],
    version_conflicts: list[dict[str, str]],
    course_availability: dict[str, Any],
) -> dict[str, Any]:
    if version_conflicts:
        return _action("confirm_version_change", "course", str(course.get("course_id") or ""), "course_version_changed", [item["object_id"] for item in version_conflicts], blocking=True, confirmation=True)

    if active_workflow:
        phase = active_workflow.get("phase") or "diagnostic"
        task = active_workflow.get("current_task") or {}
        case = active_workflow.get("case") or {}
        action_type = {
            "remediation": "resume_remediation",
            "validation": "resume_validation",
            "needs_support": "resolve_diagnostic_support",
        }.get(str(phase), "resume_diagnostic")
        return _action(
            action_type,
            "diagnostic_workflow",
            str(task.get("task_revision_id") or case.get("diagnostic_case_id") or ""),
            f"active_{phase}",
            [str(case.get("diagnostic_case_id") or "")],
            node_id=str(case.get("node_id") or ""),
        )

    ranked_attempts = _rank_attempts(active_attempts, chapter, snapshot)
    if ranked_attempts:
        attempt = ranked_attempts[0]
        return _action(
            "resume_practice_attempt",
            "practice_attempt",
            str(attempt.get("attempt_id") or ""),
            "unfinished_practice_attempt",
            [str(attempt.get("attempt_id") or "")],
            node_id=str(attempt.get("node_id") or ""),
        )

    if blockers:
        blocker = blockers[0]
        return _action("resolve_blocking_issue", "learning_record", str(blocker.get("record_id") or ""), "user_marked_blocker", [str(blocker.get("record_id") or "")], node_id=str(blocker.get("node_id") or ""), blocking=True)

    required_risk = next((item for item in risks if item.get("level") == "action_required"), None)
    if required_risk:
        return _action("resolve_prerequisite_gap", "learning_objective", str(required_risk.get("node_id") or ""), str(required_risk.get("reason_code") or ""), list(required_risk.get("evidence_refs") or []), node_id=str(required_risk.get("node_id") or ""), blocking=True)

    required_objectives = _required_objectives(chapter, contract)
    action_objectives = required_objectives
    if (
        objective
        and objective not in required_objectives
        and objective.get("reading_status") != "learned"
        and objective.get("node_id") == requested_node_id
    ):
        action_objectives = [objective, *required_objectives]
    unfinished = next((item for item in action_objectives if item.get("reading_status") != "learned"), None)
    if unfinished:
        action_type = "start_objective" if unfinished.get("reading_status") == "not_started" else "complete_reading"
        return _action(action_type, "learning_objective", str(unfinished.get("objective_revision_id") or ""), f"reading_{unfinished.get('reading_status')}", list(unfinished.get("evidence_event_ids") or []), node_id=str(unfinished.get("node_id") or ""))

    needs_check = next((item for item in required_objectives if item.get("mastery_status") != "mastered"), None)
    if needs_check and (contract.get("mastery_required") or needs_check.get("mastery_status") == "needs_review"):
        if course_availability.get("mode") != "standard":
            needs_check = None
        elif not has_mastery_task(course, str(needs_check.get("node_id") or "")):
            return _action(
                "repair_course_assets",
                "course",
                str(course.get("course_id") or ""),
                "required_practice_missing",
                [],
                node_id=str(needs_check.get("node_id") or ""),
                blocking=True,
                availability="unavailable",
            )
    if needs_check and (contract.get("mastery_required") or needs_check.get("mastery_status") == "needs_review"):
        return _action("start_mastery_check", "learning_objective", str(needs_check.get("objective_revision_id") or ""), f"mastery_{needs_check.get('mastery_status')}", list(needs_check.get("practice_attempt_ids") or []), node_id=str(needs_check.get("node_id") or ""))

    if open_issues:
        issue = open_issues[0]
        return _action("resolve_open_issue", "learning_record", str(issue.get("record_id") or ""), "chapter_issue_remaining", [str(issue.get("record_id") or "")], node_id=str(issue.get("node_id") or ""))

    current_chapter_review = next((item for item in due_reviews if item.get("in_current_chapter")), None)
    if current_chapter_review:
        return _action("start_due_review", "learning_record", str(current_chapter_review.get("record_id") or ""), "current_chapter_review_due", [str(current_chapter_review.get("record_id") or "")], node_id=str(current_chapter_review.get("node_id") or ""))

    chapter_index = int(chapter.get("chapter_index") or 0)
    next_chapter = chapters[chapter_index + 1] if chapter_index + 1 < len(chapters) else None
    if next_chapter:
        target = (next_chapter.get("objectives") or [{}])[0]
        return _action("start_next_chapter", "chapter", str(next_chapter.get("chapter_id") or ""), "chapter_ready_to_advance", [str(chapter_result.get("state") or "")], node_id=str(target.get("node_id") or next_chapter.get("chapter_id") or ""))
    return _action("view_chapter_result", "chapter", str(chapter.get("chapter_id") or ""), "course_learning_path_complete", [str(chapter_result.get("state") or "")], node_id=str((objective or {}).get("node_id") or ""))


def _rank_attempts(
    attempts: list[dict[str, Any]],
    chapter: dict[str, Any],
    snapshot: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    attempts = [item for item in attempts if item.get("status") == "in_progress"]
    chapter_node_ids = {str(item.get("node_id") or "") for item in chapter.get("objectives") or []}
    snapshot_object_id = str(((snapshot or {}).get("task_state") or {}).get("object_id") or "")
    return sorted(attempts, key=lambda item: (
        str(item.get("node_id") or "") not in chapter_node_ids,
        str(item.get("attempt_id") or "") != snapshot_object_id,
        not bool(item.get("answer_payload")),
        str(item.get("created_at") or ""),
        str(item.get("attempt_id") or ""),
    ))


def _secondary_notices(
    primary_action: dict[str, Any],
    *,
    risks: list[dict[str, Any]],
    due_reviews: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    open_issues: list[dict[str, Any]],
    active_attempts: list[dict[str, Any]],
    other_attempts: list[dict[str, Any]],
    other_workflow: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    notices: list[dict[str, Any]] = []
    if other_workflow:
        case = other_workflow.get("case") or {}
        notices.append({
            "notice_type": "other_chapter_workflow",
            "level": "action_recommended",
            "reason_code": "other_chapter_workflow_active",
            "target_id": str(case.get("diagnostic_case_id") or ""),
            "node_id": str(case.get("node_id") or ""),
            "deferrable": False,
        })
    unfinished_elsewhere = [item for item in other_attempts if item.get("status") == "in_progress"]
    if unfinished_elsewhere:
        notices.append({
            "notice_type": "other_chapter_attempt",
            "level": "notice",
            "reason_code": "other_chapter_attempt_active",
            "target_id": str(unfinished_elsewhere[0].get("attempt_id") or ""),
            "node_id": str(unfinished_elsewhere[0].get("node_id") or ""),
            "count": len(unfinished_elsewhere),
            "deferrable": False,
        })
    for risk in risks:
        if risk.get("deferred") or risk.get("level") == "action_required":
            continue
        notices.append({
            "notice_type": "entry_risk",
            "level": risk.get("level"),
            "reason_code": risk.get("reason_code"),
            "target_id": risk.get("risk_id"),
            "node_id": risk.get("node_id"),
            "deferrable": True,
        })
    if due_reviews and primary_action.get("action_type") != "start_due_review":
        notices.append({
            "notice_type": "due_review",
            "level": "notice",
            "reason_code": "review_tasks_due",
            "target_id": str(due_reviews[0].get("record_id") or ""),
            "count": len(due_reviews),
            "deferrable": False,
        })
    if blockers and primary_action.get("action_type") != "resolve_blocking_issue":
        notices.append({
            "notice_type": "blocking_issue",
            "level": "action_recommended",
            "reason_code": "other_blocking_issue_open",
            "target_id": str(blockers[0].get("record_id") or ""),
            "count": len(blockers),
            "deferrable": False,
        })
    if open_issues and primary_action.get("action_type") != "resolve_open_issue":
        notices.append({
            "notice_type": "open_issue",
            "level": "notice",
            "reason_code": "open_issues_remaining",
            "target_id": str(open_issues[0].get("record_id") or ""),
            "count": len(open_issues),
            "deferrable": False,
        })
    pending_review = [item for item in active_attempts if item.get("status") == "grading"]
    if pending_review:
        notices.append({
            "notice_type": "pending_review",
            "level": "notice",
            "reason_code": "practice_waiting_for_review",
            "target_id": str(pending_review[0].get("attempt_id") or ""),
            "count": len(pending_review),
            "deferrable": False,
        })
    return notices[:2]


def _action(
    action_type: str,
    scope: str,
    target_id: str,
    reason_code: str,
    evidence_refs: list[str],
    *,
    node_id: str = "",
    blocking: bool = False,
    confirmation: bool = False,
    availability: str = "available",
) -> dict[str, Any]:
    clean_refs = [str(item) for item in evidence_refs if item]
    return {
        "action_id": stable_hash({"type": action_type, "scope": scope, "target": target_id, "reason": reason_code}, prefix="la_"),
        "action_type": action_type,
        "scope": scope,
        "target_id": target_id,
        "target_revision_id": target_id if scope in {"learning_objective", "diagnostic_workflow"} else "",
        "node_id": node_id,
        "reason_code": reason_code,
        "evidence_refs": clean_refs,
        "blocking": blocking,
        "requires_confirmation": confirmation,
        "availability": availability,
    }


def _task_continuity(
    *,
    version_conflicts: list[dict[str, str]],
    active_workflow: dict[str, Any] | None,
    active_attempts: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> str:
    if version_conflicts:
        return "stale"
    if blockers or any(item.get("level") == "action_required" for item in risks):
        return "blocked"
    if active_workflow or any(item.get("status") == "in_progress" for item in active_attempts):
        return "resumable"
    return "none"


def _entry_mode(action: dict[str, Any], chapter_result: dict[str, Any]) -> str:
    action_type = str(action.get("action_type") or "")
    if action_type == "confirm_version_change":
        return "version_change"
    if action_type.startswith("resume_"):
        return "resume_task" if action_type != "resume_reading" else "continue_learning"
    if action_type in {"resolve_blocking_issue", "resolve_prerequisite_gap", "repair_course_assets"}:
        return "risk_handling"
    if action_type == "start_mastery_check":
        return "awaiting_validation"
    if action_type in {"start_next_chapter", "view_chapter_result"} or chapter_result.get("state") in {"verified", "covered_unverified"}:
        return "chapter_closeout"
    has_started = any(
        item.get("reading_status") != "not_started"
        for item in chapter_result.get("objectives") or []
    )
    if action_type == "start_objective" and chapter_result.get("state") == "in_progress" and not has_started:
        return "first_entry"
    return "continue_learning"


def _chapter_learning_status(chapter: dict[str, Any]) -> str:
    statuses = [item.get("reading_status") for item in chapter.get("objectives") or []]
    if statuses and all(item == "learned" for item in statuses):
        return "covered"
    if statuses and all(item == "not_started" for item in statuses):
        return "not_started"
    return "in_progress"


def _chapter_mastery_status(chapter: dict[str, Any]) -> str:
    statuses = [str(item.get("mastery_status") or "") for item in chapter.get("objectives") or []]
    if any(item == "needs_review" for item in statuses):
        return "needs_attention"
    if statuses and all(item == "mastered" for item in statuses):
        return "verified"
    if any(item == "mastered" for item in statuses):
        return "partial"
    if any(item == "evidence_insufficient" for item in statuses):
        return "evidence_insufficient"
    return "not_checked"


def _chapter_result_state(objectives: list[dict[str, Any]]) -> str:
    if any(item.get("mastery_status") == "needs_review" for item in objectives):
        return "needs_attention"
    if objectives and all(item.get("mastery_status") == "mastered" for item in objectives):
        return "verified"
    if any(item.get("mastery_status") == "mastered" for item in objectives):
        return "partially_verified"
    if objectives and all(item.get("reading_status") == "learned" for item in objectives):
        return "covered_unverified"
    return "in_progress"


def _required_objectives(chapter: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    objectives = chapter.get("objectives") or []
    required_ids = {str(item) for item in contract.get("required_objective_ids") or [] if item}
    required = [item for item in objectives if str(item.get("objective_id") or "") in required_ids]
    return required or objectives


def _mastery_label(status: str) -> str:
    return {
        "mastered": "verified",
        "needs_review": "needs_attention",
    }.get(status, status)


def _evidence_strength(objective: dict[str, Any]) -> str:
    if objective.get("mastery_status") == "mastered":
        return "strong"
    if objective.get("practice_attempt_ids"):
        return "moderate"
    if objective.get("evidence_event_ids"):
        return "limited"
    return "none"


def _projection_revision(
    *,
    course_version_id: str,
    progress: dict[str, Any],
    snapshot: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any],
    records: list[dict[str, Any]],
    events: list[dict[str, Any]],
    selected_chapter_id: str,
    temporal_state: dict[str, Any],
) -> str:
    payload = {
        "course_version_id": course_version_id,
        "selected_chapter_id": selected_chapter_id,
        "temporal_state": temporal_state,
        "progress": [
            (item.get("objective_revision_id"), item.get("reading_status"), item.get("mastery_status"), item.get("evidence_event_ids"), item.get("practice_attempt_ids"))
            for item in progress.get("nodes") or []
        ],
        "snapshot": {
            "revision": (snapshot or {}).get("revision"),
            "course_version_id": (snapshot or {}).get("course_version_id"),
            "node_id": (snapshot or {}).get("node_id"),
            "task_state": (snapshot or {}).get("task_state"),
        },
        "attempts": [(item.get("attempt_id"), item.get("revision"), item.get("status")) for item in attempts],
        "workflow": [
            ((workflow.get("case") or {}).get("diagnostic_case_id"), (workflow.get("case") or {}).get("revision"), (workflow.get("case") or {}).get("status")),
            ((workflow.get("session") or {}).get("remediation_session_id"), (workflow.get("session") or {}).get("revision"), (workflow.get("session") or {}).get("status")),
        ],
        "records": [(item.get("record_id"), item.get("revision"), item.get("status"), item.get("due_at")) for item in records],
        "deferrals": [(item.get("event_id"), (item.get("metadata") or {}).get("risk_id"), (item.get("result") or {}).get("deferred_until")) for item in events if item.get("event_type") == "entry_risk_deferred"],
    }
    return stable_hash(payload, prefix="lcr_")


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


__all__ = ["SCHEMA_VERSION", "build_learning_continuation"]
