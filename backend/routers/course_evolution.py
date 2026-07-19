"""Evidence-driven course evolution endpoints with legacy route aliases."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from course_evolution import (
    accept_change_set,
    course_evolution_repository,
    course_evolution_view,
    create_adjustment_plan,
    reject_change_set,
    synchronize_and_evaluate_course_evolution,
    undo_change_set,
)
from dependencies import get_course_document_repository, get_course_or_404
from learner_context import require_user_id
from section_evolution import generate_section_evolution_plan

router = APIRouter(prefix="/courses/{course_id}/evolution", tags=["course_evolution"])
personal_router = APIRouter(
    prefix="/courses/{course_id}/personal-adaptation",
    tags=["personal-adaptation"],
)


class AcceptCourseEvolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_scope: Literal["current", "current_and_next"]
    selected_operation_ids: list[str] | None = Field(default=None, max_length=500)


class RejectCourseEvolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=2000)


class GenerateSectionEvolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=5000)
    scope_selection: Literal["current_section", "whole_course"] = "current_section"
    anchor_role: Literal[
        "reasoning",
        "application",
        "example",
        "checkpoint",
        "concept",
    ] | None = None


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


@router.get("/progress")
async def get_course_evolution_progress(course_id: str, request: Request) -> dict:
    """Return persisted generation checkpoints without re-evaluating evidence."""
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    state = await run_in_threadpool(
        course_evolution_repository.load,
        user_id,
        course_id,
    )
    return course_evolution_view(state)


@personal_router.get("")
async def get_personal_adaptation(course_id: str, request: Request) -> dict:
    return await get_course_evolution(course_id, request)


@router.post("/evaluate")
async def evaluate_course_evolution(course_id: str, request: Request) -> dict:
    return await get_course_evolution(course_id, request)


@router.post("/sections/{section_id}/plans")
async def create_section_evolution_plan(
    course_id: str,
    section_id: str,
    body: GenerateSectionEvolutionRequest,
    request: Request,
) -> dict:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        state = await generate_section_evolution_plan(
            course,
            user_id=user_id,
            section_id=section_id,
            instruction=body.instruction,
            scope_selection=body.scope_selection,
            anchor_role=body.anchor_role,
            request_id=body.request_id,
            repository=course_evolution_repository,
            document_repository=get_course_document_repository(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "section_evolution_generation_failed",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


@router.post("/change-sets/{change_set_id}/generate")
async def generate_suggested_course_evolution_plan(
    course_id: str,
    change_set_id: str,
    request: Request,
) -> dict:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    state = course_evolution_repository.load(user_id, course_id)
    plan = next(
        (item for item in state.change_sets if item.change_set_id == change_set_id),
        None,
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Course evolution change set not found")
    try:
        state = await generate_section_evolution_plan(
            course,
            user_id=user_id,
            section_id=plan.target_section_id,
            instruction=plan.request_text,
            scope_selection=plan.scope_selection,
            request_id=plan.change_set_id,
            repository=course_evolution_repository,
            document_repository=get_course_document_repository(),
            existing_change_set_id=plan.change_set_id,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail={
            "code": "section_evolution_generation_failed",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


@personal_router.post("/evaluate")
async def evaluate_personal_adaptation(course_id: str, request: Request) -> dict:
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
    document_repository = get_course_document_repository()
    try:
        state = await run_in_threadpool(
            accept_change_set,
            course,
            user_id=user_id,
            change_set_id=change_set_id,
            selected_scope=body.selected_scope,
            selected_operation_ids=body.selected_operation_ids,
            document_repository=document_repository,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_evolution_conflict",
            "message": str(exc),
        }) from exc
    from routers.change_proposals import synchronize_teaching_representations

    representation_sync = await run_in_threadpool(
        synchronize_teaching_representations,
        course_id,
    )
    plan = next(
        item for item in state.change_sets
        if item.change_set_id == change_set_id
    )
    plan.application_receipt["representation_sync"] = representation_sync
    state = course_evolution_repository.save(state)
    return course_evolution_view(state)


@personal_router.post("/plans/{change_set_id}/accept")
async def accept_personal_adaptation_plan(
    course_id: str,
    change_set_id: str,
    body: AcceptCourseEvolutionRequest,
    request: Request,
) -> dict:
    return await accept_course_evolution_change_set(
        course_id,
        change_set_id,
        body,
        request,
    )


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


@personal_router.post("/plans/{change_set_id}/reject")
async def reject_personal_adaptation_plan(
    course_id: str,
    change_set_id: str,
    body: RejectCourseEvolutionRequest,
    request: Request,
) -> dict:
    return await reject_course_evolution_change_set(
        course_id,
        change_set_id,
        body,
        request,
    )


@router.post("/change-sets/{change_set_id}/undo")
async def undo_course_evolution_change_set(
    course_id: str,
    change_set_id: str,
    request: Request,
) -> dict:
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    document_repository = get_course_document_repository()
    try:
        state = await run_in_threadpool(
            undo_change_set,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            document_repository=document_repository,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_evolution_conflict",
            "message": str(exc),
        }) from exc
    from routers.change_proposals import synchronize_teaching_representations

    representation_sync = await run_in_threadpool(
        synchronize_teaching_representations,
        course_id,
    )
    plan = next(
        item for item in state.change_sets
        if item.change_set_id == change_set_id
    )
    plan.undo_receipt["representation_sync"] = representation_sync
    state = course_evolution_repository.save(state)
    return course_evolution_view(state)


@personal_router.post("/plans/{change_set_id}/undo")
async def undo_personal_adaptation_plan(
    course_id: str,
    change_set_id: str,
    request: Request,
) -> dict:
    return await undo_course_evolution_change_set(course_id, change_set_id, request)


@router.post("/change-sets/{change_set_id}/adjust")
async def adjust_course_evolution_change_set(
    course_id: str,
    change_set_id: str,
    request: Request,
) -> dict:
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    document_repository = get_course_document_repository()
    try:
        state = await run_in_threadpool(
            create_adjustment_plan,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            document_repository=document_repository,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_evolution_adjustment_conflict",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


@personal_router.post("/plans/{change_set_id}/adjust")
async def adjust_personal_adaptation_plan(
    course_id: str,
    change_set_id: str,
    request: Request,
) -> dict:
    return await adjust_course_evolution_change_set(course_id, change_set_id, request)


__all__ = ["personal_router", "router"]
