"""Evidence-driven course evolution endpoints with legacy route aliases."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from course_evolution import (
    course_evolution_repository,
    course_evolution_view,
    synchronize_and_evaluate_course_evolution,
)
from course_evolution.application import CourseEvolutionApplicationService
from dependencies import (
    get_course_document_repository,
    get_course_or_404,
    get_task_manager_optional,
    get_teacher_lesson_authoring_repository,
    require_task_manager,
)
from generation_streaming import structured_generation_stream
from learner_context import require_user_id
from course_generation.service import get_course_service
from question_bank import question_bank_repository
from jobs.manager import TaskManager
from teaching_representations import teaching_representation_repository
from course_evolution.teacher_planning import (
    context_view,
    TeacherCourseChangeSourceUnavailable,
)

router = APIRouter(prefix="/courses/{course_id}/evolution", tags=["course_evolution"])
personal_router = APIRouter(
    prefix="/courses/{course_id}/personal-adaptation",
    tags=["personal-adaptation"],
)


class AcceptCourseEvolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_scope: Literal["current", "current_and_next"]
    selected_operation_ids: list[str] | None = Field(default=None, max_length=500)
    retry_failed: bool = False


class RejectCourseEvolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=2000)


class GenerateCourseAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=5000)
    section_id: str = Field(min_length=1, max_length=240)
    scope_selection: Literal[
        "current_block",
        "current_section",
        "current_chapter",
        "whole_course",
    ] = "current_section"
    block_id: str = Field(default="", max_length=240)
    expected_document_revision: str = Field(default="", max_length=240)
    expected_block_revision: str = Field(default="", max_length=240)
    direction: Literal["simplify", "expand", "custom"] = "custom"
    anchor_role: Literal[
        "reasoning",
        "application",
        "example",
        "checkpoint",
        "concept",
    ] | None = None


class TeacherLiteralReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: str = Field(min_length=1, max_length=2000)
    after: str = Field(max_length=2000)


class GenerateTeacherCourseChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=5000)
    supersedes_plan_id: str = Field(default="", max_length=240)
    literal_replacement: TeacherLiteralReplacement | None = None
    asset_types: list[Literal["outline", "course_content", "lesson_plan", "script", "ppt", "question_bank"]] | None = None


class TeacherCourseOutlineReviewNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provisional_id: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=200)
    parent_ref: str = Field(default="root", max_length=240)
    source_node_ids: list[str] = Field(default_factory=list, max_length=200)
    learning_focus: str = Field(default="", max_length=500)


class ReviewTeacherCourseChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_migration_ids: list[str] = Field(max_length=2000)
    confirm_structure: bool = False
    migration_dispositions: dict[
        str,
        Literal["reuse_exact", "reuse_rebind", "rewrite_partial", "regenerate", "retire"],
    ] = Field(default_factory=dict)
    proposed_outline: list[TeacherCourseOutlineReviewNode] | None = Field(
        default=None,
        max_length=200,
    )


def _course_evolution_service(tm: TaskManager | None = None) -> CourseEvolutionApplicationService:
    return CourseEvolutionApplicationService(
        evolution_repository=course_evolution_repository,
        document_repository=get_course_document_repository(),
        authoring_repository=get_teacher_lesson_authoring_repository(),
        representation_repository=teaching_representation_repository,
        question_bank_repository=question_bank_repository,
        course_service=get_course_service(),
        task_manager=tm,
    )


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
async def get_course_evolution_progress(course_id: str, request: Request, tm: TaskManager | None = Depends(get_task_manager_optional)) -> dict:
    """Return persisted generation checkpoints without re-evaluating evidence."""
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    from course_evolution.jobs import reconcile_candidate_jobs
    state = await run_in_threadpool(reconcile_candidate_jobs, tm, course_evolution_repository, user_id, course_id) if tm is not None else await run_in_threadpool(course_evolution_repository.load, user_id, course_id)
    return course_evolution_view(state)


@personal_router.get("")
async def get_personal_adaptation(course_id: str, request: Request) -> dict:
    return await get_course_evolution(course_id, request)


@router.post("/evaluate")
async def evaluate_course_evolution(course_id: str, request: Request) -> dict:
    return await get_course_evolution(course_id, request)


@router.post("/plans")
async def create_course_adjustment_plan(
    course_id: str,
    body: GenerateCourseAdjustmentRequest,
    request: Request,
) -> dict:
    """Canonical entry for current-content, current-section and whole-course adjustments."""
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        state = await _course_evolution_service().create_course_adjustment(
            course_data=course,
            user_id=user_id,
            request_id=body.request_id,
            instruction=body.instruction,
            section_id=body.section_id,
            scope_selection=body.scope_selection,
            block_id=body.block_id,
            expected_document_revision=body.expected_document_revision,
            expected_block_revision=body.expected_block_revision,
            direction=body.direction,
            anchor_role=body.anchor_role or "",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_adjustment_generation_failed",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


@router.get("/course-context")
async def get_teacher_course_change_context(
    course_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
) -> dict:
    """Read-only cross-asset projection for the teacher change workbench."""
    await get_course_or_404(course_id)
    require_user_id(request.headers.get("X-User-Id"))
    context = await run_in_threadpool(_course_evolution_service(tm).teacher_context, course_id)
    return context_view(context)


@router.post("/course-plans")
async def create_teacher_course_plan(
    course_id: str,
    body: GenerateTeacherCourseChangeRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
) -> dict:
    """Analyze a teacher request against the whole course, never a fake section."""
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        state = await _course_evolution_service(tm).create_teacher_plan(
            course_id=course_id,
            user_id=user_id,
            request_id=body.request_id,
            instruction=body.instruction,
            supersedes_plan_id=body.supersedes_plan_id,
            literal_replacement=body.literal_replacement.model_dump() if body.literal_replacement else None,
            asset_types=body.asset_types,
        )
    except TeacherCourseChangeSourceUnavailable as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_change_source_unavailable",
            "message": str(exc),
        }) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "course_change_request_invalid",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


@router.post("/course-plans/{change_set_id}/review")
async def review_teacher_course_plan(
    course_id: str,
    change_set_id: str,
    body: ReviewTeacherCourseChangeRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
) -> dict:
    """Save the reviewed impact scope; this endpoint never writes course content."""
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        state = await run_in_threadpool(
            _course_evolution_service(tm).review_teacher_plan,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            selected_migration_ids=body.selected_migration_ids,
            confirm_structure=body.confirm_structure,
            migration_dispositions=body.migration_dispositions,
            proposed_outline=(
                [item.model_dump(mode="json") for item in body.proposed_outline]
                if body.proposed_outline is not None
                else None
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={
            "code": "course_change_plan_not_found",
            "message": "课程修改方案不存在",
        }) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "course_change_scope_invalid",
            "message": str(exc),
        }) from exc
    return course_evolution_view(state)


@router.post("/change-sets/{change_set_id}/generate")
@structured_generation_stream(
    stage="course_change_candidate",
    started_message="已收到修改要求，正在读取当前课程。",
    waiting_message="AI 正在生成可审阅的修改方案。",
)
async def generate_suggested_course_evolution_plan(
    course_id: str,
    change_set_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
) -> dict:
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        service = _course_evolution_service(tm)
        existing = service.evolution_repository.load(user_id, course_id)
        plan = next((p for p in existing.change_sets if p.change_set_id == change_set_id), None)
        if plan and plan.teacher_change_planning is not None:
            from course_evolution.jobs import enqueue_candidates
            state = await enqueue_candidates(manager=tm, service=service, user_id=user_id,
                                             course_id=course_id, plan_id=change_set_id)
        else:
            state = await service.generate_suggested(course_data=course, user_id=user_id,
                                                     change_set_id=change_set_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "course_change_plan_not_found",
                "message": "课程修改方案不存在",
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_adjustment_generation_failed",
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
    try:
        state = await run_in_threadpool(
            _course_evolution_service().accept,
            course_data=course,
            user_id=user_id,
            change_set_id=change_set_id,
            selected_scope=body.selected_scope,
            selected_operation_ids=body.selected_operation_ids,
            retry_failed=body.retry_failed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Course evolution change set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_evolution_conflict",
            "message": str(exc),
        }) from exc
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
            _course_evolution_service().reject,
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
    try:
        state = await run_in_threadpool(
            _course_evolution_service().undo,
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
    try:
        state = await run_in_threadpool(
            _course_evolution_service().adjust,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
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
