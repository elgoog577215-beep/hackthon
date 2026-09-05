"""Deterministic learning-objective bindings and progress projection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from content_blocks import project_course_content_blocks
from course_versioning import stable_hash
from learning_events import load_learning_events
from practice_attempts import practice_attempt_repository
from practice_contracts import project_practice_contracts

PROJECTION_SCHEMA = "learning_progress_v1"


def learning_objective_identity(course_id: str, node: dict[str, Any]) -> dict[str, str]:
    node_id = str(node.get("node_id") or "")
    statement = str(
        node.get("learning_objective")
        or f"能够解释并应用 {node.get('node_name') or node_id or '本节内容'}"
    ).strip()
    objective_id = stable_hash({"course_id": course_id, "node_id": node_id}, prefix="lo_")
    revision_id = stable_hash(
        {"objective_id": objective_id, "statement": " ".join(statement.split())},
        prefix="lor_",
    )
    return {
        "objective_id": objective_id,
        "objective_revision_id": revision_id,
        "statement": statement,
    }


def project_learning_objective_bindings(course_data: dict[str, Any]) -> dict[str, Any]:
    """Project objective identities onto old and new courses without mutating storage."""
    course = project_course_content_blocks(course_data)
    course_id = str(course.get("course_id") or "")
    assets = project_practice_contracts(course.get("learning_assets") or {})
    questions = assets.get("questions") or []
    criteria = assets.get("mastery_criteria") or []
    misconceptions = assets.get("misconceptions") or []
    checklist = assets.get("checklist") or []
    objectives: list[dict[str, Any]] = []

    for node in _learning_nodes(course):
        identity = learning_objective_identity(course_id, node)
        node_id = str(node.get("node_id") or "")
        node["learning_objective"] = identity["statement"]
        node["objective_id"] = identity["objective_id"]
        node["objective_revision_id"] = identity["objective_revision_id"]

        node_questions = [item for item in questions if item.get("node_id") == node_id]
        node_criteria = [item for item in criteria if item.get("node_id") == node_id]
        node_misconceptions = [item for item in misconceptions if item.get("node_id") == node_id]
        for item in [*node_questions, *node_criteria, *node_misconceptions]:
            item["objective_id"] = identity["objective_id"]
            item["objective_revision_id"] = identity["objective_revision_id"]
        for item in checklist:
            if item.get("node_id") == node_id:
                item["objective_id"] = identity["objective_id"]
                item["objective_revision_id"] = identity["objective_revision_id"]

        content_blocks = node.get("content_blocks") or []
        content_block_ids = [str(item.get("block_id")) for item in content_blocks if item.get("block_id")]
        question_revision_ids = [str(item.get("revision_id")) for item in node_questions if item.get("revision_id")]
        criterion_revision_ids = [str(item.get("revision_id")) for item in node_criteria if item.get("revision_id")]
        misconception_revision_ids = [
            str(item.get("revision_id")) for item in node_misconceptions if item.get("revision_id")
        ]
        objectives.append({
            **identity,
            "node_id": node_id,
            "node_name": str(node.get("node_name") or ""),
            "content_block_ids": content_block_ids,
            "content_block_revision_ids": [
                str(item.get("block_revision_id"))
                for item in content_blocks
                if item.get("block_revision_id")
            ],
            "question_revision_ids": question_revision_ids,
            "criterion_revision_ids": criterion_revision_ids,
            "misconception_revision_ids": misconception_revision_ids,
            "remediation_entry": {
                "kind": "reading_and_formal_practice",
                "node_id": node_id,
                "content_block_ids": content_block_ids,
                "question_revision_ids": question_revision_ids,
            },
        })

    assets["questions"] = questions
    assets["mastery_criteria"] = criteria
    assets["misconceptions"] = misconceptions
    assets["checklist"] = checklist
    assets["learning_objectives"] = deepcopy(objectives)
    course["learning_assets"] = assets
    course["learning_objectives"] = objectives
    return course


def _learning_nodes(course: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = course.get("nodes") or []
    level_two = [node for node in nodes if int(node.get("node_level") or 1) == 2]
    if level_two:
        return level_two
    return [
        node for node in nodes
        if str(node.get("node_content") or "").strip()
        and str(node.get("node_id") or "") not in {"", "root"}
    ]


def build_learning_progress(
    course_data: dict[str, Any],
    *,
    user_id: str,
    events: list[dict[str, Any]] | None = None,
    attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    course = project_learning_objective_bindings(course_data)
    course_id = str(course.get("course_id") or "")
    current_version_id = str(course.get("current_course_version_id") or "")
    loaded_events = events if events is not None else load_learning_events(
        user_id=user_id,
        course_id=course_id,
    )
    source_events = [
        event for event in loaded_events
        if event.get("user_id") == user_id and event.get("course_id") == course_id
    ]
    loaded_attempts = attempts if attempts is not None else practice_attempt_repository.list(user_id, course_id)
    source_attempts = [
        attempt for attempt in loaded_attempts
        if attempt.get("user_id") == user_id and attempt.get("course_id") == course_id
    ]
    objectives = course.get("learning_objectives") or []
    criteria = (course.get("learning_assets") or {}).get("mastery_criteria") or []
    nodes: list[dict[str, Any]] = []

    for objective in objectives:
        node_id = str(objective.get("node_id") or "")
        objective_id = str(objective.get("objective_id") or "")
        objective_revision_id = str(objective.get("objective_revision_id") or "")
        criterion_revision_ids = set(objective.get("criterion_revision_ids") or [])
        question_revision_ids = set(objective.get("question_revision_ids") or [])
        current_events = [
            event for event in source_events
            if _event_matches_current_objective(
                event,
                node_id=node_id,
                objective_revision_id=objective_revision_id,
                criterion_revision_ids=criterion_revision_ids,
                question_revision_ids=question_revision_ids,
            )
        ]
        historical_events = [
            event for event in source_events
            if event.get("objective_id") == objective_id
            and event not in current_events
            and (
                event.get("objective_revision_id")
                or event.get("criterion_revision_id")
                or event.get("question_revision_id")
            )
        ]
        current_attempts = [
            attempt for attempt in source_attempts
            if attempt.get("objective_revision_id") == objective_revision_id
            and (
                attempt.get("question_revision_id") in question_revision_ids
                or attempt.get("task_purpose") == "remediation_validation"
            )
        ]
        historical_attempts = [
            attempt for attempt in source_attempts
            if attempt.get("objective_id") == objective_id
            and attempt not in current_attempts
            and (
                attempt.get("objective_revision_id")
                or attempt.get("criterion_revision_id")
                or attempt.get("question_revision_id")
            )
        ]
        reading_status = _reading_status(current_events)
        criterion_states = [
            _project_criterion(criterion, current_events, current_attempts)
            for criterion in criteria
            if criterion.get("revision_id") in criterion_revision_ids
        ]
        mastery_status = _mastery_status(reading_status, criterion_states)
        nodes.append({
            **deepcopy(objective),
            "course_version_id": current_version_id,
            "reading_status": reading_status,
            "mastery_status": mastery_status,
            "criterion_states": criterion_states,
            "evidence_event_ids": [
                str(event.get("event_id")) for event in current_events if event.get("event_id")
            ],
            "practice_attempt_ids": [
                str(attempt.get("attempt_id")) for attempt in current_attempts if attempt.get("attempt_id")
            ],
            "has_historical_evidence": bool(historical_events or historical_attempts),
            "historical_evidence_count": len(historical_events) + len(historical_attempts),
        })

    total = len(nodes)
    learned = sum(item["reading_status"] == "learned" for item in nodes)
    in_progress = sum(item["reading_status"] == "in_progress" for item in nodes)
    mastered = sum(item["mastery_status"] == "mastered" for item in nodes)
    needs_review = sum(item["mastery_status"] == "needs_review" for item in nodes)
    return {
        "schema_version": PROJECTION_SCHEMA,
        "course_id": course_id,
        "course_version_id": current_version_id,
        "user_id": user_id,
        "summary": {
            "total_nodes": total,
            "not_started_nodes": total - learned - in_progress,
            "in_progress_nodes": in_progress,
            "learned_nodes": learned,
            "mastered_nodes": mastered,
            "needs_review_nodes": needs_review,
            "completion_percentage": round(learned / total * 100, 1) if total else 0.0,
            "mastery_percentage": round(mastered / total * 100, 1) if total else 0.0,
        },
        "nodes": nodes,
    }


def objective_for_node(course_data: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    course = project_learning_objective_bindings(course_data)
    return next(
        (item for item in course.get("learning_objectives") or [] if item.get("node_id") == node_id),
        None,
    )


def _event_matches_current_objective(
    event: dict[str, Any],
    *,
    node_id: str,
    objective_revision_id: str,
    criterion_revision_ids: set[str],
    question_revision_ids: set[str],
) -> bool:
    event_revision = str(event.get("objective_revision_id") or "")
    criterion_revision = str(event.get("criterion_revision_id") or "")
    question_revision = str(event.get("question_revision_id") or "")
    if criterion_revision or question_revision:
        objective_matches = not event_revision or event_revision == objective_revision_id
        return objective_matches and (
            criterion_revision in criterion_revision_ids
            or question_revision in question_revision_ids
        )
    if event_revision:
        return event_revision == objective_revision_id
    return (
        event.get("node_id") == node_id
        and event.get("event_type") == "legacy_node_completion_imported"
    )


def _reading_status(events: list[dict[str, Any]]) -> str:
    if any(event.get("event_type") == "node_learning_completed" for event in events):
        return "learned"
    if events:
        return "in_progress"
    return "not_started"


def _project_criterion(
    criterion: dict[str, Any],
    events: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    revision_id = str(criterion.get("revision_id") or "")
    relevant = [event for event in events if event.get("criterion_revision_id") == revision_id]
    formal = [event for event in relevant if event.get("event_type") == "formal_question_answered"]
    confirmations = [event for event in relevant if event.get("event_type") == "mastery_self_confirmed"]
    practice = [
        attempt for attempt in attempts
        if attempt.get("criterion_revision_id") == revision_id
        and attempt.get("status") in {"graded", "grading"}
    ]
    has_assessment = bool(criterion.get("assessment_bindings"))
    status = "not_started" if has_assessment else "unverified"
    latest_score = None
    evidence_event_id = None
    if practice:
        latest = practice[-1]
        result = latest.get("result") or {}
        latest_score = result.get("score")
        evidence_event_id = latest.get("attempt_id")
        if latest.get("status") == "grading" or result.get("status") == "pending_review":
            status = "evidence_insufficient"
        elif result.get("passed") is True and result.get("mastery_eligible") is True:
            status = "system_verified"
        elif result.get("passed") is True:
            status = "self_confirmed"
        else:
            status = "needs_review"
    elif formal:
        latest = formal[-1]
        latest_score = (latest.get("result") or {}).get("score")
        evidence_event_id = latest.get("event_id")
        status = "system_verified" if (latest.get("result") or {}).get("passed") is True else "needs_review"
    elif confirmations:
        latest = confirmations[-1]
        evidence_event_id = latest.get("event_id")
        status = (latest.get("result") or {}).get("status") or "self_confirmed"
    return {
        "criterion_id": criterion.get("criterion_id"),
        "criterion_revision_id": revision_id,
        "observable_performance": criterion.get("observable_performance"),
        "status": status,
        "latest_score": latest_score,
        "evidence_event_id": evidence_event_id,
    }


def _mastery_status(reading_status: str, criterion_states: list[dict[str, Any]]) -> str:
    if any(item["status"] == "needs_review" for item in criterion_states):
        return "needs_review"
    verifiable = [item for item in criterion_states if item["status"] != "unverified"]
    if verifiable and all(item["status"] == "system_verified" for item in verifiable):
        return "mastered"
    if any(item["status"] == "system_verified" for item in criterion_states):
        return "partial"
    if any(item["status"] == "self_confirmed" for item in criterion_states):
        return "evidence_insufficient"
    if any(item["status"] == "evidence_insufficient" for item in criterion_states):
        return "evidence_insufficient"
    if reading_status == "learned":
        return "evidence_insufficient"
    return "not_checked"


__all__ = [
    "build_learning_progress",
    "learning_objective_identity",
    "objective_for_node",
    "project_learning_objective_bindings",
]
