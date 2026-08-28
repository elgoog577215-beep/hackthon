"""Connect durable learning events to the existing course-evolution service."""

from __future__ import annotations

from typing import Any

from course_evolution import synchronize_and_evaluate_course_evolution
from learner_context import DEFAULT_USER_ID
from learning_events import LearningEventStorage, register_evidence_evaluator


def evaluate_learning_event(
    event: dict[str, Any],
    event_storage: LearningEventStorage,
) -> None:
    course_id = str(event.get("course_id") or "")
    if not course_id:
        return
    course = event_storage.load_course(course_id)
    if not course:
        return
    synchronize_and_evaluate_course_evolution(
        course,
        user_id=str(event.get("user_id") or DEFAULT_USER_ID),
    )


def configure_learning_event_evolution() -> None:
    register_evidence_evaluator(evaluate_learning_event)


__all__ = ["configure_learning_event_evolution", "evaluate_learning_event"]
