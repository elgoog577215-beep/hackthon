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
from teaching_representations import teaching_representation_repository


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


class AICandidateRequest(BaseModel):
    # 上限按「一个小节的全部可编辑字段」定，不是按人手勾选的字段数定：
    # 需求 5 的分小节优化会把整节路径一次性发出，最小课程的小节已有 17 条
    # （目标、要点、时长、7 条课堂执行列表、5 条模块字段、知识 2 条），
    # 模块或知识点多几个就更高。领域层仍逐条校验白名单与只读。
    paths: list[str] = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=3000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class CandidateCommandRequest(CommandRequest):
    # 逐项接受 AI 候选时同样可能覆盖整节，与 paths 对齐。
    operation_ids: list[str] = Field(default_factory=list, max_length=64)


def _service(repository=Depends(get_course_document_repository)) -> TeachingPlanWorkbenchService:
    # 表达注册表只读接入：影响分析据此把 needs_regeneration 收窄到真实引用的
    # 下游对象；拿不到注册表时分析自动退回按小节的保守答案，不阻断工作台。
    return TeachingPlanWorkbenchService(
        repository,
        representation_repository=teaching_representation_repository,
    )


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
