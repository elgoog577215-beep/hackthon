"""Coherent learning-runtime projection API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from dependencies import get_course_or_404
from learner_context import require_user_id
from learning_events import record_learning_event
from learning_runtime import build_learning_runtime

router = APIRouter(prefix="/courses/{course_id}/learning-runtime", tags=["learning_runtime"])


class AdaptiveBlockFeedbackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adaptive_block_id: str = Field(..., min_length=1, max_length=160)
    node_id: str = Field(..., min_length=1, max_length=240)
    feedback: str = Field(..., pattern="^(helpful|not_helpful|dismissed)$")


class AdaptiveBlockInteractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adaptive_block_id: str = Field(..., min_length=1, max_length=160)
    node_id: str = Field(..., min_length=1, max_length=240)
    interaction: str = Field(..., pattern="^(animation_played|validation_started)$")


@router.get("")
async def get_learning_runtime(
    course_id: str,
    request: Request,
    node_id: str | None = None,
) -> dict[str, Any]:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    return await run_in_threadpool(
        build_learning_runtime,
        course,
        user_id=user_id,
        node_id=node_id,
    )


@router.post("/adaptive-blocks/feedback")
async def record_adaptive_block_feedback(
    course_id: str,
    payload: AdaptiveBlockFeedbackPayload,
    request: Request,
) -> dict[str, Any]:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    runtime = await run_in_threadpool(
        build_learning_runtime,
        course,
        user_id=user_id,
        node_id=payload.node_id,
    )
    block = next((
        item for item in runtime.get("adaptive_blocks") or []
        if item.get("adaptive_block_id") == payload.adaptive_block_id
    ), None)
    if not block:
        raise HTTPException(status_code=404, detail="Adaptive block not found or expired")
    event = await run_in_threadpool(
        record_learning_event,
        event_type="adaptive_block_feedback",
        actor="user",
        source="learning_runtime.adaptive_block",
        user_id=user_id,
        course_id=course_id,
        course_version_id=course.get("current_course_version_id"),
        node_id=payload.node_id,
        evidence={"evidence_refs": block.get("evidence_refs") or []},
        result={"feedback": payload.feedback},
        operation_id=f"adaptive-feedback:{payload.adaptive_block_id}:{payload.feedback}",
        idempotency_key=f"{payload.adaptive_block_id}:{payload.feedback}",
        entity_type="adaptive_learning_block",
        entity_id=payload.adaptive_block_id,
        entity_revision=runtime.get("runtime_revision_id"),
        metadata={
            "adaptive_block_id": payload.adaptive_block_id,
            "kind": block.get("kind"),
            "reason_code": block.get("reason_code"),
        },
    )
    return {"status": "recorded", "event_id": event["event_id"], "feedback": payload.feedback}


@router.post("/adaptive-blocks/interactions")
async def record_adaptive_block_interaction(
    course_id: str,
    payload: AdaptiveBlockInteractionPayload,
    request: Request,
) -> dict[str, Any]:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    runtime = await run_in_threadpool(
        build_learning_runtime,
        course,
        user_id=user_id,
        node_id=payload.node_id,
    )
    block = next((
        item for item in runtime.get("adaptive_blocks") or []
        if item.get("adaptive_block_id") == payload.adaptive_block_id
    ), None)
    if not block:
        raise HTTPException(status_code=404, detail="Adaptive block not found or expired")
    event = await run_in_threadpool(
        record_learning_event,
        event_type="adaptive_block_interaction",
        actor="user",
        source="learning_runtime.adaptive_block",
        user_id=user_id,
        course_id=course_id,
        course_version_id=course.get("current_course_version_id"),
        node_id=payload.node_id,
        evidence={"evidence_refs": block.get("evidence_refs") or []},
        result={"interaction": payload.interaction},
        operation_id=f"adaptive-interaction:{payload.adaptive_block_id}:{payload.interaction}",
        idempotency_key=f"{payload.adaptive_block_id}:{payload.interaction}",
        entity_type="adaptive_learning_block",
        entity_id=payload.adaptive_block_id,
        entity_revision=runtime.get("runtime_revision_id"),
        metadata={
            "adaptive_block_id": payload.adaptive_block_id,
            "kind": block.get("kind"),
            "reason_code": block.get("reason_code"),
        },
    )
    return {
        "status": "recorded",
        "event_id": event["event_id"],
        "interaction": payload.interaction,
    }


__all__ = ["router"]
