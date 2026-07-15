"""Learning-objective progress actions and deterministic projection API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from dependencies import get_course_or_404
from learner_context import require_user_id
from learning_events import load_learning_events, record_learning_event
from learning_progress import build_learning_progress, objective_for_node


router = APIRouter(prefix="/courses/{course_id}/learning-progress", tags=["learning_progress"])


class ProgressAction(BaseModel):
    action: Literal["start", "complete_reading"]


class LegacyCompletionMigration(BaseModel):
    node_ids: list[str] = Field(default_factory=list, max_length=500)


@router.get("")
async def get_learning_progress(course_id: str, request: Request):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    return build_learning_progress(course, user_id=user_id)


@router.post("/nodes/{node_id}")
async def update_node_learning_progress(
    course_id: str,
    node_id: str,
    payload: ProgressAction,
    request: Request,
):
    course = await get_course_or_404(course_id)
    objective = objective_for_node(course, node_id)
    if not objective:
        raise HTTPException(status_code=404, detail="Learning objective not found for node")
    user_id = require_user_id(request.headers.get("X-User-Id"))
    event_type = "node_learning_started" if payload.action == "start" else "node_learning_completed"
    current = load_learning_events(user_id=user_id, course_id=course_id, node_id=node_id)
    existing = next((
        event for event in current
        if event.get("event_type") == event_type
        and event.get("objective_revision_id") == objective["objective_revision_id"]
    ), None)
    event_id = existing.get("event_id") if existing else None
    if not existing:
        event = record_learning_event(
            event_type=event_type,
            actor="user",
            source="learning_progress.reading",
            user_id=user_id,
            course_id=course_id,
            course_version_id=course.get("current_course_version_id"),
            node_id=node_id,
            node_name=str(objective.get("node_name") or ""),
            objective_id=objective["objective_id"],
            objective_revision_id=objective["objective_revision_id"],
            evidence={"explicit_confirmation": payload.action == "complete_reading"},
            result={"reading_status": "in_progress" if payload.action == "start" else "learned"},
            operation_id=f"reading:{user_id}:{objective['objective_revision_id']}:{payload.action}",
            idempotency_key=f"{objective['objective_revision_id']}:{payload.action}",
            entity_type="learning_objective_progress",
            entity_id=objective["objective_id"],
            entity_revision=objective["objective_revision_id"],
        )
        event_id = event["event_id"]
    return {
        "status": "existing" if existing else "recorded",
        "event_id": event_id,
        "projection": build_learning_progress(course, user_id=user_id),
    }


@router.post("/migrate-legacy")
async def migrate_legacy_completion(
    course_id: str,
    payload: LegacyCompletionMigration,
    request: Request,
):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    existing = load_learning_events(user_id=user_id, course_id=course_id)
    migration_keys = {
        str((event.get("metadata") or {}).get("migration_key") or "")
        for event in existing
    }
    created = 0
    for node_id in dict.fromkeys(payload.node_ids):
        objective = objective_for_node(course, node_id)
        if not objective:
            continue
        key = f"legacy_completed_node:{course_id}:{node_id}:{objective['objective_revision_id']}"
        if key in migration_keys:
            continue
        record_learning_event(
            event_type="legacy_node_completion_imported",
            actor="migration",
            source="legacy.frontend.completedNodes",
            user_id=user_id,
            course_id=course_id,
            course_version_id=course.get("current_course_version_id"),
            node_id=node_id,
            node_name=str(objective.get("node_name") or ""),
            objective_id=objective["objective_id"],
            objective_revision_id=objective["objective_revision_id"],
            evidence={"legacy_signal": "completedNodes", "confidence": "low"},
            result={"reading_status": "in_progress", "read_only_source": True},
            metadata={"migration_key": key},
            operation_id=key,
            idempotency_key=key,
            entity_type="learning_objective_progress",
            entity_id=objective["objective_id"],
            entity_revision=objective["objective_revision_id"],
        )
        migration_keys.add(key)
        created += 1
    return {
        "status": "migrated",
        "created": created,
        "projection": build_learning_progress(course, user_id=user_id),
    }
