"""Course blueprint drafts, impact reports, and product version history."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

from ai_base import AIProviderRequestError, AIProviderUnavailable
from course_outline_adjustments import (
    OutlineAdjustmentError,
    apply_outline_operations,
    compile_outline_draft,
)

from course_versioning import (
    analyze_blueprint_impact,
    blueprint_draft_revision_id,
    blueprint_revision_id,
    build_blueprint_draft,
    outline_adjustment_proposal_id,
)
from course_versions import CourseVersionConflict, CourseVersionRepository, course_version_repository
from dependencies import get_course_document_repository, get_course_or_404, get_task_manager_optional, require_task_manager
from storage import storage
from storage_utils import save_course_compat
from task_manager import TaskManager, TaskStateConflict


router = APIRouter(prefix="/courses/{course_id}", tags=["course_versions"])
logger = logging.getLogger(__name__)


class BlueprintDraftRequest(BaseModel):
    base_blueprint_revision_id: str | None = None
    expected_draft_revision_id: str | None = None
    adjustment_proposal_id: str | None = Field(default=None, max_length=120)
    adjustment_operations: list[dict[str, Any]] | None = None
    course_name: str | None = Field(default=None, max_length=300)
    course_purpose: Literal["systematic", "exam_sprint", "material_organization", "personalized_remedial"] | None = None
    course_type: str | None = Field(default=None, max_length=100)
    course_intent: dict[str, Any] | None = None
    learner_starting_profile: dict[str, Any] | None = None
    course_blueprint: dict[str, Any] | None = None
    nodes: list[dict[str, Any]] | None = None
    learning_asset_plan: dict[str, Any] | None = None
    blueprint_locks: dict[str, dict[str, bool]] | None = None


class BlueprintAdjustmentPreviewRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)
    base_blueprint_revision_id: str = Field(min_length=1, max_length=120)
    expected_draft_revision_id: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=3000)

    @field_validator("request_id", "base_blueprint_revision_id", "expected_draft_revision_id", "instruction")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class BlueprintAdjustmentCancelRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)

    @field_validator("request_id")
    @classmethod
    def request_id_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class RestoreVersionRequest(BaseModel):
    reason: str = Field(default="恢复历史课程版本", max_length=500)


class RegenerateCourseRequest(BaseModel):
    reason: str = Field(default="更新受影响内容", max_length=500)
    regenerate_all: bool = False


GenerationStep = Literal[
    "outline",
    "knowledge",
    "teaching",
    "content",
    "release",
]


@router.get("/blueprint")
async def get_blueprint(course_id: str):
    course = await _course_for_blueprint(course_id)
    draft = await run_in_threadpool(course_version_repository.load_draft, course_id)
    current = build_blueprint_draft(course)
    if isinstance(draft, dict):
        draft["draft_revision_id"] = blueprint_draft_revision_id(draft)
    return {
        "status": "success",
        "current": current,
        "draft": draft,
        "current_blueprint_revision_id": blueprint_revision_id(course),
        "has_unconfirmed_draft": bool(draft),
        "retrieval": deepcopy(
            (course.get("generation_stage_artifacts") or {}).get(
                "web_retrieval"
            )
            or {}
        ),
    }


@router.put("/blueprint/draft")
async def save_blueprint_draft(course_id: str, request: BlueprintDraftRequest):
    course = await _course_for_blueprint(course_id)
    current_revision = blueprint_revision_id(course)
    if request.base_blueprint_revision_id and request.base_blueprint_revision_id != current_revision:
        raise HTTPException(status_code=409, detail={
            "code": "blueprint_base_conflict",
            "message": "课程蓝图已更新，请重新载入后再编辑",
            "current_blueprint_revision_id": current_revision,
        })
    existing_draft = await run_in_threadpool(course_version_repository.load_draft, course_id)
    authoritative_draft = existing_draft or build_blueprint_draft(course)
    authoritative_revision = blueprint_draft_revision_id(authoritative_draft)
    if (
        request.expected_draft_revision_id
        and request.expected_draft_revision_id != authoritative_revision
    ):
        raise HTTPException(status_code=409, detail={
            "code": "draft_revision_conflict",
            "message": "目录草稿已被其他页面修改，请重新载入后再操作",
            "current_draft_revision_id": authoritative_revision,
        })
    if request.adjustment_proposal_id:
        operations = request.adjustment_operations
        if not isinstance(operations, list):
            raise HTTPException(status_code=422, detail={
                "code": "adjustment_operations_missing",
                "message": "应用调整方案时必须提供预览中的原子操作",
            })
        expected_proposal_id = outline_adjustment_proposal_id(
            authoritative_revision,
            operations,
        )
        if request.adjustment_proposal_id != expected_proposal_id:
            raise HTTPException(status_code=409, detail={
                "code": "adjustment_proposal_mismatch",
                "message": "调整方案与预览内容不一致，请重新生成方案",
            })
        try:
            draft = apply_outline_operations(
                authoritative_draft,
                operations,
            )["draft"]
        except OutlineAdjustmentError as exc:
            raise HTTPException(status_code=422, detail=exc.as_issue()) from exc
    else:
        draft = build_blueprint_draft(course)
        for field, value in request.model_dump(exclude_none=True).items():
            if field not in {
                "base_blueprint_revision_id",
                "expected_draft_revision_id",
                "adjustment_proposal_id",
                "adjustment_operations",
            }:
                draft[field] = deepcopy(value)
        if any(int(node.get("node_level") or 0) == 1 for node in draft.get("nodes") or []):
            try:
                draft = compile_outline_draft(draft)
            except OutlineAdjustmentError as exc:
                raise HTTPException(status_code=422, detail=exc.as_issue()) from exc
        else:
            _validate_blueprint_draft(draft)
    draft["base_blueprint_revision_id"] = current_revision
    draft["draft_revision_id"] = blueprint_draft_revision_id(draft)
    impact = analyze_blueprint_impact(course, draft)
    draft["impact_report"] = impact
    saved = await run_in_threadpool(course_version_repository.save_draft, course_id, draft)
    if request.adjustment_proposal_id:
        logger.info(
            "outline_adjustment_applied proposal_id=%s draft_revision_id=%s",
            request.adjustment_proposal_id,
            draft["draft_revision_id"],
        )
    return {"status": "success", "draft": saved, "impact_report": impact}


@router.post("/blueprint/adjustments/preview")
async def preview_blueprint_adjustment(
    course_id: str,
    request: BlueprintAdjustmentPreviewRequest,
    tm: TaskManager = Depends(require_task_manager),
):
    try:
        return await tm.preview_outline_adjustment(
            course_id,
            request.model_dump(),
        )
    except CourseVersionConflict as exc:
        raise HTTPException(status_code=409, detail={
            "code": "outline_adjustment_revision_conflict",
            "message": str(exc),
        }) from exc
    except TaskStateConflict as exc:
        raise HTTPException(status_code=409, detail={
            "code": "outline_adjustment_lifecycle_conflict",
            "message": str(exc),
            "status": exc.status,
        }) from exc
    except OutlineAdjustmentError as exc:
        raise HTTPException(status_code=422, detail=exc.as_issue()) from exc
    except (AIProviderUnavailable, AIProviderRequestError) as exc:
        raise HTTPException(status_code=503, detail={
            "code": "outline_adjustment_model_unavailable",
            "message": "AI 调整服务暂时不可用，请稍后重试",
        }) from exc


@router.post("/blueprint/adjustments/{proposal_id}/cancel")
async def cancel_blueprint_adjustment(
    course_id: str,
    request: BlueprintAdjustmentCancelRequest,
    proposal_id: str = Path(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$"),
):
    logger.info(
        "outline_adjustment_cancelled course_id=%s request_id=%s proposal_id=%s",
        course_id,
        request.request_id,
        proposal_id,
    )
    return {"status": "cancelled", "proposal_id": proposal_id}


@router.post("/blueprint/impact")
async def preview_blueprint_impact(course_id: str, request: BlueprintDraftRequest):
    course = await _course_for_blueprint(course_id)
    draft = build_blueprint_draft(course)
    for field, value in request.model_dump(exclude_none=True).items():
        if field != "base_blueprint_revision_id":
            draft[field] = deepcopy(value)
    _validate_blueprint_draft(draft)
    return analyze_blueprint_impact(course, draft)


@router.delete("/blueprint/draft")
async def discard_blueprint_draft(course_id: str):
    await get_course_or_404(course_id)
    await run_in_threadpool(course_version_repository.delete_draft, course_id)
    return {"status": "discarded"}


@router.get("/blueprint/revisions/{revision_id}")
async def get_blueprint_revision(course_id: str, revision_id: str):
    await get_course_or_404(course_id)
    try:
        return await run_in_threadpool(
            course_version_repository.get_blueprint_revision,
            course_id,
            revision_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/versions")
async def list_course_versions(course_id: str):
    course = await get_course_or_404(course_id)
    entry = await _ensure_initial_version(course_id, course, course_version_repository)
    versions = await run_in_threadpool(course_version_repository.list_versions, course_id)
    return {
        "status": "success",
        "current_version_id": course_version_repository.current_version_id(course_id),
        "versions": versions,
    }


@router.get("/versions/compare")
async def compare_course_versions(course_id: str, left: str, right: str):
    await get_course_or_404(course_id)
    try:
        return await run_in_threadpool(course_version_repository.compare_versions, course_id, left, right)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/versions/{version_id}")
async def get_course_version(course_id: str, version_id: str):
    await get_course_or_404(course_id)
    try:
        entry = await run_in_threadpool(course_version_repository.get_version_entry, course_id, version_id)
        snapshot = await run_in_threadpool(course_version_repository.get_version_snapshot, course_id, version_id)
        return {"status": "success", "version": entry, "course": snapshot}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/versions/{version_id}/restore")
async def restore_course_version(course_id: str, version_id: str, request: RestoreVersionRequest):
    await get_course_or_404(course_id)
    try:
        restored, entry = await run_in_threadpool(
            course_version_repository.restore_version,
            course_id,
            version_id,
            reason=request.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await save_course_compat(storage, course_id, restored)
    return {"status": "restored", "version": entry, "course": restored}


@router.post("/blueprint/confirm", status_code=202)
async def confirm_course_blueprint(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    await get_course_or_404(course_id)
    try:
        return await tm.confirm_blueprint(course_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TaskStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_state_conflict",
                "message": str(exc),
                "status": exc.status,
            },
        ) from exc


@router.get("/generation/review")
async def get_generation_review(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    await get_course_or_404(course_id)
    review = tm.get_generation_review(course_id)
    if not review:
        raise HTTPException(
            status_code=404,
            detail="No guided generation workflow was found for this course",
        )
    return review


@router.post("/generation/steps/{step}/confirm", status_code=202)
async def confirm_generation_step(
    course_id: str,
    step: GenerationStep,
    tm: TaskManager = Depends(require_task_manager),
):
    await get_course_or_404(course_id)
    try:
        return await tm.confirm_generation_step(course_id, step)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TaskStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_state_conflict",
                "message": str(exc),
                "status": exc.status,
            },
        ) from exc


@router.post("/generation/steps/{step}/reopen", status_code=202)
async def reopen_generation_step(
    course_id: str,
    step: GenerationStep,
    tm: TaskManager = Depends(require_task_manager),
):
    await get_course_or_404(course_id)
    try:
        return await tm.reopen_generation_step(course_id, step)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TaskStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_state_conflict",
                "message": str(exc),
                "status": exc.status,
            },
        ) from exc


@router.post("/regenerate", status_code=202)
async def regenerate_course(
    course_id: str,
    request: RegenerateCourseRequest,
    tm: TaskManager = Depends(require_task_manager),
):
    await get_course_or_404(course_id)
    repository = get_course_document_repository()
    raw_course = await run_in_threadpool(repository.load_raw, course_id)
    if repository.is_canonical(raw_course):
        raise HTTPException(status_code=409, detail={
            "code": "canonical_block_regeneration_required",
            "message": "Canonical courses must use block regeneration candidates",
            "endpoint_template": f"/api/courses/{course_id}/blocks/{{block_id}}/regeneration-candidates",
        })
    try:
        return await tm.create_regeneration_job(
            course_id,
            reason=request.reason,
            regenerate_all=request.regenerate_all,
        )
    except CourseVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TaskStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_state_conflict",
                "message": str(exc),
                "status": exc.status,
            },
        ) from exc


@router.get("/version-candidates")
async def list_version_candidates(course_id: str):
    await get_course_or_404(course_id)
    candidates = await run_in_threadpool(course_version_repository.list_candidates, course_id)
    return {"status": "success", "candidates": candidates}


async def _course_for_blueprint(course_id: str) -> dict[str, Any]:
    """Read an unpublished generation blueprint from its isolated workspace."""
    course = await get_course_or_404(course_id)
    task_manager = get_task_manager_optional()
    if task_manager is None:
        return course
    workspace_course = task_manager.get_generation_workspace_course(course_id)
    return workspace_course or course


async def _ensure_initial_version(
    course_id: str,
    course: dict[str, Any],
    repository: CourseVersionRepository,
) -> dict[str, Any]:
    entry = await run_in_threadpool(repository.ensure_initial_version, course_id, course)
    if course.get("current_course_version_id") != entry.get("version_id"):
        course["current_course_version_id"] = entry.get("version_id")
        course["blueprint_revision_id"] = entry.get("blueprint_revision_id")
        await save_course_compat(storage, course_id, course)
    return entry


def _validate_blueprint_draft(draft: dict[str, Any]) -> None:
    nodes = draft.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise HTTPException(status_code=422, detail="课程蓝图必须至少包含一个节点")
    node_ids = [str(node.get("node_id") or "") for node in nodes]
    if any(not node_id for node_id in node_ids) or len(set(node_ids)) != len(node_ids):
        raise HTTPException(status_code=422, detail="课程蓝图节点 ID 缺失或重复")
    known = set(node_ids)
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        parent = str(node.get("parent_node_id") or "")
        if parent and parent != "root" and parent not in known:
            raise HTTPException(status_code=422, detail=f"节点 {node_id} 的父节点不存在")
        for dependency in node.get("prerequisite_node_ids") or []:
            if dependency not in known:
                raise HTTPException(status_code=422, detail=f"节点 {node_id} 的前置节点 {dependency} 不存在")
            if dependency == node_id:
                raise HTTPException(status_code=422, detail=f"节点 {node_id} 不能依赖自身")
    _ensure_acyclic(nodes)


def _ensure_acyclic(nodes: list[dict[str, Any]]) -> None:
    dependencies = {
        str(node.get("node_id") or ""): {str(item) for item in node.get("prerequisite_node_ids") or []}
        for node in nodes
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise HTTPException(status_code=422, detail="课程蓝图的前置依赖形成循环")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dependency in dependencies.get(node_id, set()):
            visit(dependency)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in dependencies:
        visit(node_id)


__all__ = ["router"]
