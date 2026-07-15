"""Load one formal evidence batch and project the current learner model."""

from __future__ import annotations

from typing import Any

from diagnostic_service import workflow_view
from learner_context import DEFAULT_USER_ID
from learner_model import build_learner_model
from learning_continuation import build_learning_continuation
from learning_events import load_learning_events
from learning_progress import build_learning_progress, project_learning_objective_bindings
from learning_records import learning_record_repository
from learning_runtime import build_runtime_revision_vector
from learning_snapshots import learning_snapshot_repository
from practice_attempts import practice_attempt_repository
from storage import storage


def build_current_learner_model(course_data: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    """Build a model from one immutable source batch without persisting it."""
    course = project_learning_objective_bindings(course_data)
    course_id = str(course.get("course_id") or "")
    has_stable_identity = bool(user_id and user_id != DEFAULT_USER_ID)

    if has_stable_identity:
        events = load_learning_events(user_id=user_id, course_id=course_id)
        snapshot = learning_snapshot_repository.load(user_id, course_id)
        records = learning_record_repository.list(user_id, course_id)
        attempts = practice_attempt_repository.list(user_id, course_id)
        workflow = workflow_view(user_id, course_id)
    else:
        events = []
        snapshot = None
        records = []
        attempts = []
        workflow = {}

    progress = build_learning_progress(
        course,
        user_id=user_id,
        events=events,
        attempts=attempts,
    )
    continuation = build_learning_continuation(
        course,
        user_id=user_id,
        progress=progress,
        snapshot=snapshot,
        attempts=attempts,
        workflow=workflow,
        records=records,
        events=events,
    )
    source_revision_vector = build_runtime_revision_vector(
        course=course,
        events=events,
        snapshot=snapshot,
        records=records,
        attempts=attempts,
        workflow=workflow,
        continuation=continuation,
    )
    return build_learner_model(
        course,
        user_id=user_id,
        events=events,
        snapshot=snapshot,
        records=records,
        attempts=attempts,
        workflow=workflow,
        progress=progress,
        source_revision_vector=source_revision_vector,
    )


def build_current_learner_model_for_course(
    course_id: str | None,
    *,
    user_id: str,
) -> dict[str, Any] | None:
    """Load a course and return its model; missing courses have no model."""
    if not course_id:
        return None
    course = storage.load_course(course_id)
    if not course:
        return None
    return build_current_learner_model(course, user_id=user_id)


__all__ = ["build_current_learner_model", "build_current_learner_model_for_course"]
