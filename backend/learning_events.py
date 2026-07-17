"""Unified lightweight learning event ledger.

The ledger records learning evidence that later learner-state and teaching
decision layers can consume. It intentionally uses the existing file storage
instead of introducing a database.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from learner_context import DEFAULT_USER_ID
from storage import storage

LEARNING_EVENTS_FILE = "learning_events.json"
SCHEMA_VERSION = 8
_event_lock = threading.RLock()


@dataclass
class LearningEvent:
    event_id: str
    event_type: str
    user_id: str = DEFAULT_USER_ID
    actor: str = "system"
    source: str = ""
    course_id: str | None = None
    course_version_id: str | None = None
    node_id: str | None = None
    node_name: str = ""
    objective_id: str | None = None
    objective_revision_id: str | None = None
    concept_ids: list[str] = field(default_factory=list)
    skill_unit_ids: list[str] = field(default_factory=list)
    mistake_point_ids: list[str] = field(default_factory=list)
    improvement_point_ids: list[str] = field(default_factory=list)
    question_revision_id: str | None = None
    task_revision_id: str | None = None
    task_purpose: str | None = None
    criterion_id: str | None = None
    criterion_revision_id: str | None = None
    record_id: str | None = None
    record_type: str | None = None
    attempt_id: str | None = None
    diagnostic_case_id: str | None = None
    remediation_session_id: str | None = None
    operation_id: str | None = None
    idempotency_key: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    entity_revision: str | int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_learning_event(
    *,
    event_type: str,
    actor: str = "system",
    source: str = "",
    user_id: str = DEFAULT_USER_ID,
    course_id: str | None = None,
    course_version_id: str | None = None,
    node_id: str | None = None,
    node_name: str = "",
    objective_id: str | None = None,
    objective_revision_id: str | None = None,
    concept_ids: list[str] | None = None,
    skill_unit_ids: list[str] | None = None,
    mistake_point_ids: list[str] | None = None,
    improvement_point_ids: list[str] | None = None,
    question_revision_id: str | None = None,
    task_revision_id: str | None = None,
    task_purpose: str | None = None,
    criterion_id: str | None = None,
    criterion_revision_id: str | None = None,
    record_id: str | None = None,
    record_type: str | None = None,
    attempt_id: str | None = None,
    diagnostic_case_id: str | None = None,
    remediation_session_id: str | None = None,
    operation_id: str | None = None,
    idempotency_key: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    entity_revision: str | int | None = None,
    evidence: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one structured learning event and return the saved dict.

    When ``idempotency_key`` is supplied, the tuple of learner, course, source
    and key identifies one semantic fact. Retries return the original event.
    """
    normalized_key = str(idempotency_key or "").strip() or None
    event_id = f"evt_{uuid.uuid4().hex}"
    event = LearningEvent(
        event_id=event_id,
        event_type=event_type,
        user_id=user_id,
        actor=actor,
        source=source,
        course_id=course_id,
        course_version_id=course_version_id,
        node_id=node_id,
        node_name=node_name,
        objective_id=objective_id,
        objective_revision_id=objective_revision_id,
        concept_ids=concept_ids or [],
        skill_unit_ids=skill_unit_ids or [],
        mistake_point_ids=mistake_point_ids or [],
        improvement_point_ids=improvement_point_ids or [],
        question_revision_id=question_revision_id,
        task_revision_id=task_revision_id,
        task_purpose=task_purpose,
        criterion_id=criterion_id,
        criterion_revision_id=criterion_revision_id,
        record_id=record_id,
        record_type=record_type,
        attempt_id=attempt_id,
        diagnostic_case_id=diagnostic_case_id,
        remediation_session_id=remediation_session_id,
        operation_id=str(operation_id or normalized_key or event_id),
        idempotency_key=normalized_key,
        entity_type=str(entity_type or "") or None,
        entity_id=str(entity_id or "") or None,
        entity_revision=entity_revision,
        evidence=_sanitize_dict(evidence or {}),
        result=_sanitize_dict(result or {}),
        metadata=_sanitize_dict(metadata or {}),
    ).to_dict()

    with _event_lock:
        stored = storage.load_data(LEARNING_EVENTS_FILE) or []
        events = list(stored) if isinstance(stored, list) else []
        if normalized_key:
            existing = next((
                item for item in events
                if item.get("user_id") == user_id
                and item.get("course_id") == course_id
                and item.get("source") == source
                and item.get("idempotency_key") == normalized_key
            ), None)
            if existing:
                return dict(existing)
        events.append(event)
        storage.save_data(LEARNING_EVENTS_FILE, events)
    _maybe_trigger_evidence_evaluation(event)
    return event


def _maybe_trigger_evidence_evaluation(event: dict[str, Any]) -> None:
    """Best-effort projection into the learner-isolated course-evolution chain.

    The event write remains the durable fact. Evolution evaluation only stores
    evidence references, hypotheses, and pending course-evolution plans; it
    never writes ``CourseDocument`` from this hook.
    """
    if event.get("event_type") not in {
        "learner_self_reported",
        "assistant_question_submitted",
        "assistant_answer_feedback_submitted",
        "practice_attempt_graded",
        "learning_record_created",
        "learning_record_updated",
        "adaptive_block_feedback",
        "adaptive_block_interaction",
    }:
        return
    course_id = event.get("course_id")
    if not course_id:
        return
    try:
        from course_evolution import synchronize_and_evaluate_course_evolution

        course = storage.load_course(str(course_id))
        if not course:
            return
        synchronize_and_evaluate_course_evolution(
            course,
            user_id=str(event.get("user_id") or DEFAULT_USER_ID),
        )
    except Exception:
        pass


def load_learning_events(
    *,
    user_id: str | None = None,
    course_id: str | None = None,
    node_id: str | None = None,
    event_type: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load events with optional filters. Results are ordered oldest to newest."""
    events = storage.load_data(LEARNING_EVENTS_FILE) or []
    if not isinstance(events, list):
        return []

    filtered = [
        event for event in events
        if _matches(event, user_id=user_id, course_id=course_id, node_id=node_id, event_type=event_type)
    ]
    if limit is not None and limit >= 0:
        filtered = filtered[-limit:]
    return [dict(event) for event in filtered]


def summarize_text(text: str, limit: int = 240) -> str:
    """Create a compact evidence summary suitable for event payloads."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def migrate_legacy_learning_state(course_data: dict[str, Any]) -> int:
    """Import legacy quiz/review fields once without treating them as live truth."""
    course_id = str(course_data.get("course_id") or "")
    if not course_id:
        return 0
    existing_keys = {
        str((event.get("metadata") or {}).get("migration_key") or "")
        for event in load_learning_events(course_id=course_id)
    }
    created = 0
    version_id = course_data.get("current_course_version_id")
    for node in course_data.get("nodes") or []:
        node_id = str(node.get("node_id") or "")
        score = node.get("quiz_score")
        key = f"legacy_quiz:{course_id}:{node_id}:{score}"
        if isinstance(score, (int, float)) and key not in existing_keys:
            record_learning_event(
                event_type="legacy_quiz_imported",
                actor="migration",
                source="legacy.node.quiz_score",
                course_id=course_id,
                course_version_id=version_id,
                node_id=node_id,
                node_name=str(node.get("node_name") or ""),
                result={"score": score, "passed": score >= 60},
                metadata={"migration_key": key, "read_only_source": True},
            )
            created += 1
    for node_id, review in (course_data.get("review_history") or {}).items():
        key = f"legacy_review:{course_id}:{node_id}:{review.get('last_reviewed')}:{review.get('review_count')}"
        if key in existing_keys:
            continue
        record_learning_event(
            event_type="legacy_review_imported",
            actor="migration",
            source="legacy.course.review_history",
            course_id=course_id,
            course_version_id=version_id,
            node_id=str(node_id),
            evidence={"legacy_review": review},
            metadata={"migration_key": key, "read_only_source": True},
        )
        created += 1
    return created


def _matches(
    event: dict[str, Any],
    *,
    user_id: str | None,
    course_id: str | None,
    node_id: str | None,
    event_type: str | None,
) -> bool:
    if user_id is not None and event.get("user_id") != user_id:
        return False
    if course_id is not None and event.get("course_id") != course_id:
        return False
    if node_id is not None and event.get("node_id") != node_id:
        return False
    if event_type is not None and event.get("event_type") != event_type:
        return False
    return True


def _sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Keep event payloads JSON-friendly and bounded."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        result[str(key)] = _sanitize_value(value)
    return result


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return summarize_text(value, limit=1000)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key): _sanitize_value(val) for key, val in list(value.items())[:30] if val is not None}
    return str(value)
