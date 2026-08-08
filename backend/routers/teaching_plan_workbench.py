"""HTTP boundary for structured teaching-plan drafts and revisions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from course_repository import CourseDocumentConflict, CourseDocumentNotFound
from dependencies import get_course_document_repository
from learner_context import resolve_user_id
from teaching_plan_workbench import (
    TeachingPlanWorkbenchError,
    TeachingPlanWorkbenchService,
)


router = APIRouter(
    prefix="/courses/{course_id}/teaching-plan",
    tags=["teaching_plan_workbench"],
)


class DraftRequest(BaseModel):
    base_plan_revision_id: str = Field(default="", max_length=200)
    base_course_document_revision: str = Field(default="", max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class PatchDraftRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    value: Any
    expected_value_hash: str = Field(default="", max_length=200)
    base_plan_revision_id: str = Field(default="", max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ChangeSetRequest(BaseModel):
    draft_id: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class CommandRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=200)


class InitializeBaselineRequest(CommandRequest):
    base_course_document_revision: str = Field(default="", max_length=200)


class AICandidateRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=96)
    instruction: str = Field(min_length=1, max_length=3000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class CandidateCommandRequest(CommandRequest):
    operation_ids: list[str] = Field(default_factory=list, max_length=96)


def _service(repository=Depends(get_course_document_repository)) -> TeachingPlanWorkbenchService:
    return TeachingPlanWorkbenchService(repository)


def _actor(request: Request) -> str:
    return resolve_user_id(request.headers.get("X-User-Id"))


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, TeachingPlanWorkbenchError):
        status_code = 409 if exc.code.endswith("conflict") or exc.code.endswith("blocked") else 400
        if exc.code.endswith("not_found") or exc.code == "teaching_plan_missing":
            status_code = 404
        return HTTPException(status_code=status_code, detail={
            "code": exc.code,
            "message": str(exc),
            **exc.details,
        })
    if isinstance(exc, CourseDocumentNotFound):
        return HTTPException(status_code=404, detail={"code": "course_not_found", "message": "课程不存在。"})
    if isinstance(exc, CourseDocumentConflict):
        return HTTPException(status_code=409, detail={"code": "course_document_conflict", "message": str(exc)})
    return HTTPException(status_code=500, detail={"code": "teaching_plan_workbench_error", "message": str(exc)})


@router.get("/workbench")
async def get_workbench(
    course_id: str,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {"status": "success", "workbench": service.view(course_id, actor=_actor(request))}
    except Exception as exc:  # Convert domain conflicts into a stable API contract.
        raise _error(exc) from exc


@router.post("/baseline")
async def initialize_baseline(
    course_id: str,
    body: InitializeBaselineRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "initialized",
            **await service.initialize_baseline(
                course_id,
                actor=_actor(request),
                **body.model_dump(),
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/drafts")
async def create_draft(
    course_id: str,
    body: DraftRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "success",
            "workbench": await service.create_draft(
                course_id,
                actor=_actor(request),
                **body.model_dump(),
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.patch("/drafts/{draft_id}")
async def patch_draft(
    course_id: str,
    draft_id: str,
    body: PatchDraftRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "success",
            "workbench": await service.patch_draft(
                course_id,
                actor=_actor(request),
                draft_id=draft_id,
                **body.model_dump(),
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.delete("/drafts/{draft_id}")
async def discard_draft(
    course_id: str,
    draft_id: str,
    body: CommandRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "discarded",
            "workbench": await service.discard_draft(
                course_id,
                actor=_actor(request),
                draft_id=draft_id,
                idempotency_key=body.idempotency_key,
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/drafts/{draft_id}/ai-candidates")
async def create_ai_candidate(
    course_id: str,
    draft_id: str,
    body: AICandidateRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "success",
            "workbench": await service.create_ai_candidate(
                course_id,
                actor=_actor(request),
                draft_id=draft_id,
                **body.model_dump(),
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/ai-candidates/{candidate_id}/accept")
async def accept_ai_candidate(
    course_id: str,
    candidate_id: str,
    body: CandidateCommandRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "accepted",
            "workbench": await service.accept_ai_candidate(
                course_id,
                actor=_actor(request),
                candidate_id=candidate_id,
                **body.model_dump(),
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/ai-candidates/{candidate_id}/reject")
async def reject_ai_candidate(
    course_id: str,
    candidate_id: str,
    body: CommandRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "rejected",
            "workbench": await service.reject_ai_candidate(
                course_id,
                actor=_actor(request),
                candidate_id=candidate_id,
                **body.model_dump(),
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/validate")
async def validate_draft(
    course_id: str,
    body: ChangeSetRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "success",
            "review": service.review_draft(course_id, actor=_actor(request), draft_id=body.draft_id),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/change-sets")
async def create_change_set(
    course_id: str,
    body: ChangeSetRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "success",
            "workbench": await service.create_change_set(
                course_id,
                actor=_actor(request),
                **body.model_dump(),
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/change-sets/{change_set_id}/apply")
async def apply_change_set(
    course_id: str,
    change_set_id: str,
    body: CommandRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "applied",
            **await service.apply_change_set(
                course_id,
                actor=_actor(request),
                change_set_id=change_set_id,
                idempotency_key=body.idempotency_key,
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/change-sets/{change_set_id}/reject")
async def reject_change_set(
    course_id: str,
    change_set_id: str,
    body: CommandRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "rejected",
            "workbench": await service.reject_change_set(
                course_id,
                actor=_actor(request),
                change_set_id=change_set_id,
                idempotency_key=body.idempotency_key,
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/revisions")
async def list_revisions(
    course_id: str,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {"status": "success", "revisions": service.view(course_id, actor=_actor(request))["revisions"]}
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/revisions/{revision_id}/diff")
async def revision_diff(
    course_id: str,
    revision_id: str,
    against: str,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {"status": "success", **service.revision_diff(course_id, left=against, right=revision_id)}
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/revisions/{revision_id}/restore")
async def restore_revision(
    course_id: str,
    revision_id: str,
    body: CommandRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "restored",
            **await service.restore_revision(
                course_id,
                actor=_actor(request),
                revision_id=revision_id,
                idempotency_key=body.idempotency_key,
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc


class RebuildRequest(CommandRequest):
    # 定向重建：不传就按整份下游状态里所有 rebuild_required 的对象来。
    only_types: list[str] = Field(default_factory=list, max_length=16)
    only_ids: list[str] = Field(default_factory=list, max_length=256)
    # 默认生成候选等教师确认，而不是直接覆盖正式产物。
    candidate_only: bool = True


@router.post("/downstream/rebuild")
async def rebuild_downstream(
    course_id: str,
    body: RebuildRequest,
    request: Request,
    service: TeachingPlanWorkbenchService = Depends(_service),
) -> dict[str, Any]:
    try:
        return {
            "status": "rebuilt",
            **await service.rebuild_downstream(
                course_id,
                actor=_actor(request),
                idempotency_key=body.idempotency_key,
                only_types=body.only_types or None,
                only_ids=body.only_ids or None,
                candidate_only=body.candidate_only,
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc
