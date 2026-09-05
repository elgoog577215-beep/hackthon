"""Deterministic orchestration for diagnosis, remediation, and validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from diagnostic_workflows import (
    CASE_ACTIVE,
    SESSION_ACTIVE,
    WorkflowConflict,
    diagnostic_hypotheses,
    diagnostic_tasks,
    diagnostic_workflow_repository,
    remediation_payload,
)
from learning_events import record_learning_event
from practice_attempts import practice_attempt_repository

MIN_GRADING_CONFIDENCE = 0.72


def consider_course_failure(
    course: dict[str, Any],
    *,
    user_id: str,
    attempt: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any] | None:
    if str(attempt.get("task_purpose") or "course_practice") != "course_practice":
        return None
    result = attempt.get("result") or {}
    if result.get("passed") is not False or attempt.get("status") != "graded":
        return None
    if float(result.get("grading_confidence") or 0) < MIN_GRADING_CONFIDENCE:
        return None
    if int(result.get("support_level") or 0) > 1:
        return None
    all_attempts = practice_attempt_repository.list(user_id, str(attempt.get("course_id") or ""))
    failures = [
        item for item in all_attempts
        if item.get("objective_revision_id") == attempt.get("objective_revision_id")
        and item.get("course_version_id") == attempt.get("course_version_id")
        and str(item.get("task_purpose") or "course_practice") == "course_practice"
        and item.get("status") == "graded"
        and (item.get("result") or {}).get("passed") is False
        and float((item.get("result") or {}).get("grading_confidence") or 0) >= MIN_GRADING_CONFIDENCE
    ]
    if len(failures) < 2:
        return None
    hypotheses = diagnostic_hypotheses(course, task, attempt)
    tasks = diagnostic_tasks(course, task, hypotheses)
    payload = {
        "trigger_attempt_ids": [str(item.get("attempt_id")) for item in failures[-3:]],
        "course_version_id": attempt.get("course_version_id"),
        "node_id": attempt.get("node_id"),
        "node_name": attempt.get("node_name"),
        "learning_objective": task.get("learning_objective"),
        "objective_id": attempt.get("objective_id"),
        "objective_revision_id": attempt.get("objective_revision_id"),
        "criterion_id": attempt.get("criterion_id"),
        "criterion_revision_id": attempt.get("criterion_revision_id"),
        "concept_ids": list(attempt.get("concept_ids") or task.get("concept_ids") or []),
        "skill_unit_ids": list(attempt.get("skill_unit_ids") or task.get("skill_unit_ids") or []),
        "candidate_mistake_point_ids": list(attempt.get("mistake_point_ids") or task.get("mistake_point_ids") or []),
        "improvement_point_ids": list(attempt.get("improvement_point_ids") or task.get("improvement_point_ids") or []),
        "hypotheses": hypotheses,
        "diagnostic_tasks": tasks,
        "current_task_revision_id": (tasks[0] if tasks else {}).get("task_revision_id"),
        "decision_rule_version": "diagnostic_policy_v1",
        "return_anchor": {"node_id": attempt.get("node_id"), "attempt_id": attempt.get("attempt_id")},
    }
    case, created = diagnostic_workflow_repository.create_case_once(
        user_id, str(attempt.get("course_id") or ""), payload,
    )
    if created:
        _event("diagnostic_case_opened", user_id, attempt, {
            "diagnostic_case_id": case.get("diagnostic_case_id"),
            "trigger_attempt_ids": case.get("trigger_attempt_ids"),
        })
    return case


def advance_workflow_after_grade(
    course: dict[str, Any],
    *,
    user_id: str,
    attempt: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    purpose = str(attempt.get("task_purpose") or task.get("task_purpose") or "course_practice")
    if purpose == "course_practice":
        consider_course_failure(course, user_id=user_id, attempt=attempt, task=task)
        return workflow_view(
            user_id,
            str(attempt.get("course_id") or ""),
            node_id=str(attempt.get("node_id") or "") or None,
        )
    if purpose == "diagnostic_probe":
        return _advance_diagnostic(course, user_id=user_id, attempt=attempt, task=task)
    if purpose == "remediation_guided":
        return _advance_guided(user_id=user_id, attempt=attempt)
    if purpose == "remediation_validation":
        return _advance_validation(user_id=user_id, attempt=attempt, task=task)
    return {"case": None, "session": None}


def workflow_view(user_id: str, course_id: str, *, node_id: str | None = None) -> dict[str, Any]:
    active = diagnostic_workflow_repository.active(user_id, course_id, node_id=node_id)
    return {
        **active,
        "current_task": _current_task(active.get("case"), active.get("session")),
        "phase": _phase(active.get("case"), active.get("session")),
    }


def invalidate_stale_workflows(course: dict[str, Any], *, user_id: str) -> int:
    course_id = str(course.get("course_id") or "")
    current_version = str(course.get("current_course_version_id") or "")
    objective_revisions = {
        str(item.get("objective_revision_id") or "")
        for collection in (
            (course.get("learning_assets") or {}).get("questions") or [],
            (course.get("learning_assets") or {}).get("mastery_criteria") or [],
        )
        for item in collection
        if item.get("objective_revision_id")
    }
    changed = 0
    data = diagnostic_workflow_repository.load(user_id, course_id)
    for case in data.get("cases") or []:
        stale = (
            case.get("status") in CASE_ACTIVE
            and (
                str(case.get("course_version_id") or "") != current_version
                or str(case.get("objective_revision_id") or "") not in objective_revisions
            )
        )
        if not stale:
            continue
        try:
            diagnostic_workflow_repository.update_case(
                user_id, course_id, str(case.get("diagnostic_case_id") or ""),
                expected_revision=int(case.get("revision") or 0),
                mutate=lambda current: current.update({"status": "stale", "current_task_revision_id": None}),
            )
            changed += 1
        except WorkflowConflict:
            pass
    for session in data.get("sessions") or []:
        if session.get("status") not in SESSION_ACTIVE or str(session.get("course_version_id") or "") == current_version:
            continue
        try:
            diagnostic_workflow_repository.update_session(
                user_id, course_id, str(session.get("remediation_session_id") or ""),
                expected_revision=int(session.get("revision") or 0),
                mutate=lambda current: current.update({"status": "stale", "current_task_revision_id": None}),
            )
            changed += 1
        except WorkflowConflict:
            pass
    return changed


def _advance_diagnostic(
    course: dict[str, Any],
    *,
    user_id: str,
    attempt: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    course_id = str(attempt.get("course_id") or "")
    case_id = str(attempt.get("diagnostic_case_id") or "")
    case = diagnostic_workflow_repository.get_case(user_id, course_id, case_id)
    result = attempt.get("result") or {}
    support = int(result.get("support_level") or 0)
    target_ids = list(task.get("target_hypothesis_ids") or [])
    target_id = str(target_ids[0] if target_ids else "")
    hypotheses = deepcopy(case.get("hypotheses") or [])
    target = next((item for item in hypotheses if item.get("hypothesis_id") == target_id), None)
    if not target:
        return {"case": case, "session": None}
    evidence = {"attempt_id": attempt.get("attempt_id"), "task_revision_id": task.get("task_revision_id")}
    conclusive = attempt.get("status") == "graded" and result.get("passed") in {True, False} and support == 0
    if conclusive and result.get("passed") is True:
        target["evidence_against"] = [*(target.get("evidence_against") or []), {**evidence, "kind": "independent_probe_pass"}]
        target["status"] = "rejected"
        target["confidence_level"] = "high"
    elif conclusive:
        target["evidence_for"] = [*(target.get("evidence_for") or []), {**evidence, "kind": "independent_probe_fail"}]
        if len(target["evidence_for"]) >= 2:
            target["status"] = "confirmed"
            target["confidence_level"] = "high"
            target["confirmed_mistake_point_ids"] = list(target.get("candidate_mistake_point_ids") or [])
    else:
        target["confidence_level"] = "low"

    confirmed = next((item for item in hypotheses if item.get("status") == "confirmed"), None)
    remaining = [item for item in hypotheses if item.get("status") == "testing"]
    next_task = next((
        item for item in case.get("diagnostic_tasks") or []
        if any(h.get("hypothesis_id") in (item.get("target_hypothesis_ids") or []) for h in remaining)
    ), None)
    status = "confirmed" if confirmed else "testing" if remaining else "unresolved"
    updated = diagnostic_workflow_repository.update_case(
        user_id, course_id, case_id, expected_revision=int(case.get("revision") or 0),
        mutate=lambda current: current.update({
            "hypotheses": hypotheses,
            "status": status,
            "confirmed_hypothesis_id": (confirmed or {}).get("hypothesis_id"),
            "current_task_revision_id": (next_task or {}).get("task_revision_id"),
        }),
    )
    _event("diagnostic_probe_evaluated", user_id, attempt, {
        "diagnostic_case_id": case_id, "hypothesis_id": target_id, "decision": target.get("status"),
    })
    session = None
    if confirmed:
        session_payload = remediation_payload(course, updated, confirmed)
        session, _ = diagnostic_workflow_repository.create_session_once(user_id, course_id, session_payload)
        updated = diagnostic_workflow_repository.update_case(
            user_id, course_id, case_id, expected_revision=int(updated.get("revision") or 0),
            mutate=lambda current: current.update({
                "status": "remediating",
                "remediation_session_id": session.get("remediation_session_id"),
            }),
        )
        _event("remediation_session_started", user_id, attempt, {
            "diagnostic_case_id": case_id,
            "remediation_session_id": session.get("remediation_session_id"),
        })
    return {"case": updated, "session": session, "current_task": _current_task(updated, session), "phase": _phase(updated, session)}


def _advance_guided(*, user_id: str, attempt: dict[str, Any]) -> dict[str, Any]:
    course_id = str(attempt.get("course_id") or "")
    session_id = str(attempt.get("remediation_session_id") or "")
    session = diagnostic_workflow_repository.get_session(user_id, course_id, session_id)
    result = attempt.get("result") or {}
    if attempt.get("status") == "graded" and result.get("passed") is True:
        next_id = next(iter(session.get("validation_task_revision_ids") or []), None)
        session = diagnostic_workflow_repository.update_session(
            user_id, course_id, session_id, expected_revision=int(session.get("revision") or 0),
            mutate=lambda current: current.update({
                "status": "awaiting_validation",
                "guided_attempt_id": attempt.get("attempt_id"),
                "current_task_revision_id": next_id,
            }),
        )
        _event("remediation_unit_completed", user_id, attempt, {"remediation_session_id": session_id})
    case = diagnostic_workflow_repository.get_case(user_id, course_id, str(session.get("diagnostic_case_id") or ""))
    return {"case": case, "session": session, "current_task": _current_task(case, session), "phase": _phase(case, session)}


def _advance_validation(
    *,
    user_id: str,
    attempt: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    course_id = str(attempt.get("course_id") or "")
    session_id = str(attempt.get("remediation_session_id") or "")
    session = diagnostic_workflow_repository.get_session(user_id, course_id, session_id)
    case_id = str(session.get("diagnostic_case_id") or "")
    case = diagnostic_workflow_repository.get_case(user_id, course_id, case_id)
    result = attempt.get("result") or {}
    independent = int(result.get("support_level") or 0) == 0
    quality_ok = task.get("quality_status") == "passed"
    conclusive = attempt.get("status") == "graded" and result.get("passed") in {True, False}
    if conclusive and result.get("passed") is True and independent and quality_ok:
        session = diagnostic_workflow_repository.update_session(
            user_id, course_id, session_id, expected_revision=int(session.get("revision") or 0),
            mutate=lambda current: current.update({
                "status": "resolved", "validation_attempt_id": attempt.get("attempt_id"),
                "outcome": "resolved", "current_task_revision_id": None,
                "validation_attempts": [
                    *(current.get("validation_attempts") or []),
                    {"attempt_id": attempt.get("attempt_id"), "task_revision_id": attempt.get("task_revision_id"), "outcome": "passed"},
                ],
            }),
        )
        case = diagnostic_workflow_repository.update_case(
            user_id, course_id, case_id, expected_revision=int(case.get("revision") or 0),
            mutate=lambda current: current.update({"status": "resolved", "resolved_by_attempt_id": attempt.get("attempt_id")}),
        )
        _event("remediation_validation_passed", user_id, attempt, {"diagnostic_case_id": case_id, "remediation_session_id": session_id})
    elif conclusive and result.get("passed") is False and independent:
        failures = int(session.get("failure_count") or 0) + 1
        escalated = failures >= 2
        session = diagnostic_workflow_repository.update_session(
            user_id, course_id, session_id, expected_revision=int(session.get("revision") or 0),
            mutate=lambda current: current.update({
                "failure_count": failures,
                "status": "escalated" if escalated else "reopened",
                "outcome": "escalated" if escalated else "reopened",
                "current_task_revision_id": None if escalated else (current.get("tasks") or [{}])[0].get("task_revision_id"),
                "validation_attempts": [
                    *(current.get("validation_attempts") or []),
                    {"attempt_id": attempt.get("attempt_id"), "task_revision_id": attempt.get("task_revision_id"), "outcome": "failed"},
                ],
            }),
        )
        case = diagnostic_workflow_repository.update_case(
            user_id, course_id, case_id, expected_revision=int(case.get("revision") or 0),
            mutate=lambda current: current.update({"status": "unresolved" if escalated else "reopened"}),
        )
        _event("remediation_validation_failed", user_id, attempt, {"diagnostic_case_id": case_id, "failure_count": failures})
    else:
        used = {
            str(item.get("task_revision_id") or "")
            for item in session.get("validation_attempts") or []
        } | {str(attempt.get("task_revision_id") or "")}
        next_id = next((item for item in session.get("validation_task_revision_ids") or [] if item not in used), None)
        session = diagnostic_workflow_repository.update_session(
            user_id, course_id, session_id, expected_revision=int(session.get("revision") or 0),
            mutate=lambda current: current.update({
                "status": "awaiting_validation",
                "outcome": "awaiting_review" if not next_id else "inconclusive",
                "current_task_revision_id": next_id,
                "validation_attempts": [
                    *(current.get("validation_attempts") or []),
                    {"attempt_id": attempt.get("attempt_id"), "task_revision_id": attempt.get("task_revision_id"), "outcome": "inconclusive"},
                ],
            }),
        )
        _event("remediation_validation_inconclusive", user_id, attempt, {"diagnostic_case_id": case_id})
    return {"case": case, "session": session, "current_task": _current_task(case, session), "phase": _phase(case, session)}


def _current_task(case: dict[str, Any] | None, session: dict[str, Any] | None) -> dict[str, Any] | None:
    if (case or {}).get("status") in {"resolved", "unresolved", "stale"}:
        return None
    if (session or {}).get("status") in {"resolved", "escalated", "stale"}:
        return None
    if session and session.get("current_task_revision_id"):
        return next((item for item in session.get("tasks") or [] if item.get("task_revision_id") == session.get("current_task_revision_id")), None)
    if case and case.get("current_task_revision_id"):
        return next((item for item in case.get("diagnostic_tasks") or [] if item.get("task_revision_id") == case.get("current_task_revision_id")), None)
    return None


def _phase(case: dict[str, Any] | None, session: dict[str, Any] | None) -> str:
    if not case:
        return "practice"
    if case.get("status") == "resolved":
        return "resolved"
    if case.get("status") == "unresolved":
        return "needs_support"
    if session:
        if session.get("status") == "awaiting_validation":
            return "validation"
        if session.get("status") in {"active", "reopened"}:
            return "remediation"
        if session.get("status") == "resolved":
            return "resolved"
    return "diagnostic"


def _event(event_type: str, user_id: str, attempt: dict[str, Any], metadata: dict[str, Any]) -> None:
    record_learning_event(
        event_type=event_type,
        actor="system",
        source="diagnostic.remediation",
        user_id=user_id,
        course_id=attempt.get("course_id"),
        course_version_id=attempt.get("course_version_id"),
        node_id=attempt.get("node_id"),
        node_name=str(attempt.get("node_name") or ""),
        objective_id=attempt.get("objective_id"),
        objective_revision_id=attempt.get("objective_revision_id"),
        concept_ids=attempt.get("concept_ids") or [],
        skill_unit_ids=attempt.get("skill_unit_ids") or [],
        mistake_point_ids=attempt.get("mistake_point_ids") or [],
        improvement_point_ids=attempt.get("improvement_point_ids") or [],
        task_revision_id=attempt.get("task_revision_id") or attempt.get("question_revision_id"),
        task_purpose=attempt.get("task_purpose"),
        criterion_id=attempt.get("criterion_id"),
        criterion_revision_id=attempt.get("criterion_revision_id"),
        attempt_id=attempt.get("attempt_id"),
        diagnostic_case_id=attempt.get("diagnostic_case_id") or metadata.get("diagnostic_case_id"),
        remediation_session_id=attempt.get("remediation_session_id") or metadata.get("remediation_session_id"),
        evidence={"task_revision_id": attempt.get("task_revision_id"), "task_purpose": attempt.get("task_purpose")},
        result={},
        metadata=metadata,
    )


__all__ = [
    "advance_workflow_after_grade",
    "consider_course_failure",
    "invalidate_stale_workflows",
    "workflow_view",
]
