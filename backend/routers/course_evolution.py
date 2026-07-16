"""Learner-isolated evidence, hypothesis, and course-growth endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from course_evolution import (
    accept_change_set,
    course_evolution_view,
    reject_change_set,
    synchronize_and_evaluate_course_evolution,
    undo_change_set,
)
from dependencies import get_course_or_404
from learner_context import require_user_id

router = APIRouter(prefix="/courses/{course_id}/evolution", tags=["course_evolution"])


class AcceptCourseEvolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_scope: Literal["current", "current_and_next"]


class RejectCourseEvolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=2000)


@router.get("")
async def get_course_evolution(course_id: str, request: Request) -> dict:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    state = await run_in_threadpool(
        synchronize_and_evaluate_course_evolution,
        course,
        user_id=user_id,
    )
    return course_evolution_view(state)


@router.post("/evaluate")
async def evaluate_course_evolution(course_id: str, request: Request) -> dict:
    return await get_course_evolution(course_id, request)


@router.post("/change-sets/{change_set_id}/accept")
async def accept_course_evolution_change_set(
    course_id: str,
    change_set_id: str,
    body: AcceptCourseEvolutionRequest,
    request: Request,
) -> dict:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        state = await run_in_threadpool(
            accept_change_set,
            course,
            user_id=user_id,
            change_set_id=change_set_id,
            selected_scope=body.selected_scope,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_evolution_conflict",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


@router.post("/change-sets/{change_set_id}/reject")
async def reject_course_evolution_change_set(
    course_id: str,
    change_set_id: str,
    body: RejectCourseEvolutionRequest,
    request: Request,
) -> dict:
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        state = await run_in_threadpool(
            reject_change_set,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_evolution_conflict",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


@router.post("/change-sets/{change_set_id}/undo")
async def undo_course_evolution_change_set(
    course_id: str,
    change_set_id: str,
    request: Request,
) -> dict:
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        state = await run_in_threadpool(
            undo_change_set,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_evolution_conflict",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


__all__ = ["router"]
