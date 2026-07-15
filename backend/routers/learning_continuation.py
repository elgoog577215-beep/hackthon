"""Unified chapter entry, result, and next-action API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from dependencies import get_course_or_404
from learner_context import require_user_id
from learning_continuation import build_learning_continuation
from learning_events import record_learning_event
from learning_version_transition import (
    NoPendingVersionTransition,
    VersionTransitionConflict,
    VersionTransitionTargetRequired,
    confirm_version_transition,
)

router = APIRouter(prefix="/courses/{course_id}/learning-continuation", tags=["learning_continuation"])


class RiskDeferral(BaseModel):
    expected_projection_revision_id: str = Field(..., min_length=1, max_length=160)
    defer_hours: int = Field(default=24, ge=1, le=168)
    reason: str = Field(default="", max_length=500)
    node_id: str | None = Field(default=None, max_length=240)


class VersionTransitionConfirmation(BaseModel):
    expected_projection_revision_id: str = Field(..., min_length=1, max_length=160)
    request_id: str = Field(..., min_length=1, max_length=200)
    node_id: str | None = Field(default=None, max_length=240)
    target_node_id: str | None = Field(default=None, max_length=240)


@router.get("")
async def get_learning_continuation(
    course_id: str,
    request: Request,
    node_id: str | None = None,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    return await run_in_threadpool(
        build_learning_continuation,
        course,
        user_id=user_id,
        node_id=node_id or chapter_id,
    )


@router.post("/risks/{risk_id}/defer")
async def defer_entry_risk(
    course_id: str,
    risk_id: str,
    payload: RiskDeferral,
    request: Request,
) -> dict[str, Any]:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    projection = await run_in_threadpool(
        build_learning_continuation,
        course,
        user_id=user_id,
        node_id=payload.node_id,
    )
    if projection.get("projection_revision_id") != payload.expected_projection_revision_id:
        raise HTTPException(status_code=409, detail={
            "code": "learning_continuation_revision_conflict",
            "current": projection,
        })
    risk = next((item for item in projection.get("risks") or [] if item.get("risk_id") == risk_id), None)
    if not risk:
        raise HTTPException(status_code=404, detail="Entry risk not found")
    if risk.get("level") == "action_required":
        raise HTTPException(status_code=422, detail="Required entry risk cannot be deferred")
    deferred_until = datetime.now(timezone.utc) + timedelta(hours=payload.defer_hours)
    record_learning_event(
        event_type="entry_risk_deferred",
        actor="user",
        source="learning_continuation.risk",
        user_id=user_id,
        course_id=course_id,
        course_version_id=course.get("current_course_version_id"),
        node_id=risk.get("node_id"),
        evidence={"reason": payload.reason, "risk_level": risk.get("level")},
        result={"deferred_until": deferred_until.isoformat()},
        metadata={"risk_id": risk_id, "reason_code": risk.get("reason_code")},
    )
    updated = await run_in_threadpool(
        build_learning_continuation,
        course,
        user_id=user_id,
        node_id=payload.node_id,
    )
    return {"status": "deferred", "projection": updated}


@router.post("/version-change/confirm")
async def confirm_course_version_change(
    course_id: str,
    payload: VersionTransitionConfirmation,
    request: Request,
) -> dict[str, Any]:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        return await run_in_threadpool(
            confirm_version_transition,
            course,
            user_id=user_id,
            expected_projection_revision_id=payload.expected_projection_revision_id,
            request_id=payload.request_id,
            node_id=payload.node_id,
            target_node_id=payload.target_node_id,
        )
    except VersionTransitionConflict as conflict:
        raise HTTPException(status_code=409, detail={
            "code": "learning_version_transition_revision_conflict",
            "current": conflict.current,
        }) from conflict
    except VersionTransitionTargetRequired as exc:
        raise HTTPException(status_code=422, detail={
            "code": "learning_version_transition_target_required",
            "plan": exc.plan,
        }) from exc
    except NoPendingVersionTransition as exc:
        raise HTTPException(status_code=409, detail={
            "code": "learning_version_transition_not_pending",
        }) from exc


__all__ = ["router"]
