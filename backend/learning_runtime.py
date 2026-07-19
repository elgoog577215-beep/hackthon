"""Coherent read model spanning the six course-learning capabilities."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from content_blocks import resolve_content_anchor
from course_evolution import (
    course_evolution_repository,
    course_evolution_view,
    personal_course_overlay,
    project_applied_adaptive_blocks,
)
from course_learning_availability import project_course_learning_availability
from course_versioning import stable_hash
from diagnostic_service import workflow_view
from learning_continuation import build_learning_continuation
from learning_events import load_learning_events
from learner_model import build_learner_model, learner_model_summary
from learning_progress import build_learning_progress, project_learning_objective_bindings
from learning_records import learning_record_repository
from learning_snapshots import learning_snapshot_repository
from practice_attempts import practice_attempt_repository

SCHEMA_VERSION = "learning_runtime_v1"
ACTIVE_ATTEMPT_STATUSES = {"in_progress", "submitted", "grading"}


def build_learning_runtime(
    course_data: dict[str, Any],
    *,
    user_id: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Build all coordination projections from one immutable source batch."""
    course = project_learning_objective_bindings(course_data)
    course_id = str(course.get("course_id") or "")
    events = load_learning_events(user_id=user_id, course_id=course_id)
    snapshot = learning_snapshot_repository.load(user_id, course_id)
    records = learning_record_repository.list(user_id, course_id)
    attempts = practice_attempt_repository.list(user_id, course_id)
    workflow = workflow_view(user_id, course_id)
    progress = build_learning_progress(
        course,
        user_id=user_id,
        events=events,
        attempts=attempts,
    )
    continuation = build_learning_continuation(
        course,
        user_id=user_id,
        node_id=node_id,
        progress=progress,
        snapshot=snapshot,
        attempts=attempts,
        workflow=workflow,
        records=records,
        events=events,
    )
    resolution = resolve_content_anchor(
        course,
        node_id=(snapshot or {}).get("node_id"),
        anchor=(snapshot or {}).get("content_anchor"),
    ) if snapshot else None
    current_objective = continuation.get("current_objective") or {}
    context = {
        "course_id": course_id,
        "course_version_id": str(course.get("current_course_version_id") or ""),
        "chapter_id": str((continuation.get("chapter") or {}).get("chapter_id") or ""),
        "node_id": str(current_objective.get("node_id") or (snapshot or {}).get("node_id") or node_id or ""),
        "objective_id": str(current_objective.get("objective_id") or ""),
        "objective_revision_id": str(current_objective.get("objective_revision_id") or ""),
    }
    revision_vector = build_runtime_revision_vector(
        course=course,
        events=events,
        snapshot=snapshot,
        records=records,
        attempts=attempts,
        workflow=workflow,
        continuation=continuation,
    )
    learner_model = build_learner_model(
        course,
        user_id=user_id,
        events=events,
        snapshot=snapshot,
        records=records,
        attempts=attempts,
        workflow=workflow,
        progress=progress,
        source_revision_vector=revision_vector,
    )
    revision_vector["learner_model_revision_id"] = learner_model["model_revision_id"]
    evolution_state = course_evolution_repository.load(user_id, course_id)
    personal_overlay = personal_course_overlay(evolution_state)
    personal_adaptive_blocks = project_applied_adaptive_blocks(
        evolution_state,
        node_id=node_id,
    )
    for block in personal_adaptive_blocks:
        feedback = _adaptive_feedback(events, str(block.get("adaptive_block_id") or ""))
        block["feedback"]["value"] = feedback or "unrated"
    personal_adaptive_blocks = [
        block for block in personal_adaptive_blocks
        if (block.get("feedback") or {}).get("value") != "dismissed"
    ]
    temporary_adaptive_blocks = _adaptive_blocks(
        course,
        attempts=attempts,
        workflow=workflow,
        events=events,
        requested_node_id=node_id,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "course_id": course_id,
        "user_id": user_id,
        "context": context,
        "revision_vector": revision_vector,
        "runtime_revision_id": stable_hash(revision_vector, prefix="lrr_"),
        "course_availability": project_course_learning_availability(course),
        "snapshot": {
            "current": deepcopy(snapshot) if snapshot else None,
            "resolution": resolution,
        },
        "progress": progress,
        "records": _record_summary(records),
        "practice": _practice_summary(attempts),
        "diagnostic": _diagnostic_summary(workflow),
        "learner_model": learner_model_summary(
            learner_model,
            node_id=str(current_objective.get("node_id") or node_id or "") or None,
        ),
        "course_evolution": course_evolution_view(evolution_state),
        "personal_course_overlay": personal_overlay.model_dump(mode="json"),
        "adaptive_blocks": personal_adaptive_blocks + temporary_adaptive_blocks,
        "active_task": deepcopy((continuation.get("primary_action") or {}).get("task_ref")),
        "continuation": continuation,
    }


def _adaptive_blocks(
    course: dict[str, Any],
    *,
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any],
    events: list[dict[str, Any]],
    requested_node_id: str | None,
) -> list[dict[str, Any]]:
    """Project at most one low-risk support block for the current semantic anchor."""
    case = workflow.get("case") or {}
    session = workflow.get("session") or {}
    task = workflow.get("current_task") or {}
    phase = str(workflow.get("phase") or "practice")
    node_id = str(case.get("node_id") or task.get("node_id") or requested_node_id or "")
    objective_revision_id = str(
        case.get("objective_revision_id")
        or session.get("objective_revision_id")
        or task.get("objective_revision_id")
        or ""
    )

    evidence_refs: list[str] = []
    if phase in {"diagnostic", "remediation", "validation", "needs_support"} and case:
        evidence_refs.extend(str(item) for item in case.get("trigger_attempt_ids") or [] if item)
        evidence_refs.extend(filter(None, [
            str(case.get("diagnostic_case_id") or ""),
            str(session.get("remediation_session_id") or ""),
            str(task.get("task_revision_id") or task.get("question_revision_id") or ""),
        ]))
    else:
        failures = [
            item for item in attempts
            if item.get("status") == "graded"
            and (item.get("result") or {}).get("passed") is False
            and float((item.get("result") or {}).get("grading_confidence") or 0) >= 0.72
            and int((item.get("result") or {}).get("support_level") or 0) <= 1
            and (not requested_node_id or str(item.get("node_id") or "") == requested_node_id)
        ]
        if not failures:
            return []
        latest = failures[-1]
        node_id = str(latest.get("node_id") or requested_node_id or "")
        objective_revision_id = str(latest.get("objective_revision_id") or "")
        matching = [
            item for item in failures
            if item.get("objective_revision_id") == objective_revision_id
            and item.get("course_version_id") == latest.get("course_version_id")
        ]
        if len(matching) < 2:
            return []
        evidence_refs = [str(item.get("attempt_id") or "") for item in matching[-3:] if item.get("attempt_id")]
        phase = "practice_gap"

    if not node_id or (requested_node_id and requested_node_id != node_id):
        return []

    units = [
        item for item in (course.get("learning_assets") or {}).get("remediation_units") or []
        if not objective_revision_id or str(item.get("objective_revision_id") or "") == objective_revision_id
    ]
    unit = deepcopy(session.get("unit") or (units[0] if units else {}))
    hypotheses = list(case.get("hypotheses") or [])
    confirmed_id = str(case.get("confirmed_hypothesis_id") or "")
    hypothesis = next((item for item in hypotheses if str(item.get("hypothesis_id") or "") == confirmed_id), None)
    if not hypothesis:
        hypothesis = next((item for item in hypotheses if item.get("status") == "confirmed"), None)
    if not hypothesis and hypotheses:
        hypothesis = hypotheses[0]

    kind_by_phase = {
        "diagnostic": "understanding_check",
        "remediation": "counterexample",
        "validation": "transition",
        "needs_support": "explanation",
        "practice_gap": "explanation",
    }
    kind = kind_by_phase.get(phase, "explanation")
    reason_code = {
        "diagnostic": "repeated_failure_under_diagnosis",
        "remediation": "confirmed_gap_under_remediation",
        "validation": "remediation_ready_for_independent_validation",
        "needs_support": "diagnosis_requires_additional_support",
        "practice_gap": "repeated_independent_practice_failure",
    }.get(phase, "strong_learning_evidence")
    body = str(
        unit.get("micro_explanation")
        or unit.get("remediation_objective")
        or (hypothesis or {}).get("claim")
        or "回到当前概念的定义、必要条件和适用边界，先完成一次最小澄清。"
    )
    contrast = str(unit.get("worked_contrast") or "")
    prompt = str((hypothesis or {}).get("claim") or unit.get("remediation_objective") or "")
    content_block_id = str(next(iter(unit.get("content_block_ids") or []), ""))
    block_id = stable_hash({
        "course_id": course.get("course_id"),
        "course_version_id": course.get("current_course_version_id"),
        "node_id": node_id,
        "phase": phase,
        "evidence_refs": evidence_refs,
        "unit_revision_id": unit.get("revision_id"),
    }, prefix="ab_")
    feedback = _adaptive_feedback(events, block_id)
    if feedback == "dismissed":
        return []
    return [{
        "adaptive_block_id": block_id,
        "anchor": {
            "node_id": node_id,
            "content_block_id": content_block_id,
            "placement": "after_block" if content_block_id else "after_node",
        },
        "kind": kind,
        "role": "low_risk_support",
        "payload": {
            "body": body,
            "contrast": contrast,
            "prompt": prompt if kind == "understanding_check" else "",
            "objective": str(unit.get("remediation_objective") or ""),
        },
        "reason_code": reason_code,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "status": "active",
        "expires_at": _adaptive_expiry([case, session, task, *attempts[-3:]]),
        "feedback": {
            "value": feedback or "unrated",
            "options": ["helpful", "not_helpful", "dismissed"],
        },
    }]


def _adaptive_feedback(events: list[dict[str, Any]], block_id: str) -> str:
    for event in reversed(events):
        if event.get("event_type") != "adaptive_block_feedback":
            continue
        metadata = event.get("metadata") or {}
        if str(metadata.get("adaptive_block_id") or "") == block_id:
            return str((event.get("result") or {}).get("feedback") or "")
    return ""


def _adaptive_expiry(sources: list[dict[str, Any]]) -> str:
    timestamps = [
        str(source.get(key) or "")
        for source in sources
        for key in ("updated_at", "graded_at", "created_at")
        if source.get(key)
    ]
    base = datetime.now(timezone.utc)
    for value in reversed(timestamps):
        try:
            base = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    return (max(base, datetime.now(timezone.utc)) + timedelta(days=7)).isoformat()


def _record_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    active = [item for item in records if item.get("status") != "archived"]
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for item in active:
        record_type = str(item.get("record_type") or "unknown")
        status = str(item.get("status") or "unknown")
        by_type[record_type] = by_type.get(record_type, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "total": len(active),
        "by_type": by_type,
        "by_status": by_status,
        "open_issue_ids": [
            str(item.get("record_id") or "")
            for item in active
            if item.get("record_type") == "issue" and item.get("status") not in {"resolved", "archived"}
        ],
    }


def _practice_summary(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    active = [item for item in attempts if item.get("status") in ACTIVE_ATTEMPT_STATUSES]
    return {
        "total": len(attempts),
        "active": [
            {
                "attempt_id": item.get("attempt_id"),
                "task_revision_id": item.get("task_revision_id") or item.get("question_revision_id"),
                "task_purpose": item.get("task_purpose") or "course_practice",
                "status": item.get("status"),
                "revision": item.get("revision"),
                "course_version_id": item.get("course_version_id"),
                "node_id": item.get("node_id"),
                "objective_revision_id": item.get("objective_revision_id"),
                "has_draft": bool(item.get("answer_payload")),
            }
            for item in active
        ],
        "pending_review_count": sum(item.get("status") == "grading" for item in attempts),
        "needs_review_count": sum(
            item.get("status") == "grading" or (item.get("result") or {}).get("passed") is False
            for item in attempts
        ),
    }


def _diagnostic_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    case = workflow.get("case") or None
    session = workflow.get("session") or None
    task = workflow.get("current_task") or None
    return {
        "phase": str(workflow.get("phase") or "practice"),
        "case": {
            "diagnostic_case_id": case.get("diagnostic_case_id"),
            "status": case.get("status"),
            "revision": case.get("revision"),
            "node_id": case.get("node_id"),
            "objective_revision_id": case.get("objective_revision_id"),
        } if case else None,
        "session": {
            "remediation_session_id": session.get("remediation_session_id"),
            "status": session.get("status"),
            "revision": session.get("revision"),
            "course_version_id": session.get("course_version_id"),
        } if session else None,
        "current_task": {
            "task_revision_id": task.get("task_revision_id") or task.get("question_revision_id"),
            "task_purpose": task.get("task_purpose"),
            "node_id": task.get("node_id"),
        } if task else None,
    }


def build_runtime_revision_vector(
    *,
    course: dict[str, Any],
    events: list[dict[str, Any]],
    snapshot: dict[str, Any] | None,
    records: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any],
    continuation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "course_version_id": str(course.get("current_course_version_id") or ""),
        "events_revision": stable_hash(
            [(item.get("event_id"), item.get("schema_version")) for item in events], prefix="levr_",
        ),
        "snapshot_revision": int((snapshot or {}).get("revision") or 0),
        "records_revision": stable_hash(
            [(item.get("record_id"), item.get("revision"), item.get("status")) for item in records], prefix="lrevr_",
        ),
        "attempts_revision": stable_hash(
            [(item.get("attempt_id"), item.get("revision"), item.get("status")) for item in attempts], prefix="larev_",
        ),
        "diagnostic_revision": stable_hash([
            ((workflow.get("case") or {}).get("diagnostic_case_id"), (workflow.get("case") or {}).get("revision"), (workflow.get("case") or {}).get("status")),
            ((workflow.get("session") or {}).get("remediation_session_id"), (workflow.get("session") or {}).get("revision"), (workflow.get("session") or {}).get("status")),
        ], prefix="ldrev_"),
        "continuation_revision_id": str(continuation.get("projection_revision_id") or ""),
    }


__all__ = ["SCHEMA_VERSION", "build_learning_runtime", "build_runtime_revision_vector"]
