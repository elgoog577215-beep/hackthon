# =============================================================================
# 课程管理路由
# 课程 CRUD、课程生成、节点级操作、大纲编辑、生成配置
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import CourseGenerationRequest, LocateNodeRequest, NodeGenerationConfig
from course_type_contracts import ENABLED_COURSE_TYPES
from storage import storage
from course_service import get_course_service
from learning_progress import project_learning_objective_bindings
from dependencies import (
    get_course_document_repository,
    get_course_or_404,
    require_task_manager,
    get_node_or_404,
)
from course_repository import CourseMigrationConflict
from storage_utils import save_course_compat
from task_manager import TaskManager
from learner_context import resolve_user_id
from learning_snapshots import learning_snapshot_repository

router = APIRouter(tags=["courses"])


# =============================================================================
# Request models for new endpoints
# =============================================================================

class CustomInstructionRequest(BaseModel):
    """Request body for setting a custom instruction on a node."""
    instruction: str


class NodeConfigUpdateRequest(BaseModel):
    """Request body for updating a node's generation config."""
    difficulty: Optional[str] = None
    style: Optional[str] = None
    target_word_range: Optional[tuple] = None
    include_code_examples: Optional[bool] = None
    include_exercises: Optional[bool] = None
    custom_instruction: Optional[str] = None


class CourseDocumentMigrationRequest(BaseModel):
    source_checksum: str
    confirm: bool = False


# =============================================================================
# Core course endpoints
# =============================================================================


def _resume_summary(snapshot: dict | None) -> dict | None:
    if not snapshot or not str(snapshot.get("node_id") or "").strip():
        return None
    task = snapshot.get("task_state") if isinstance(snapshot.get("task_state"), dict) else {}
    return {
        "kind": str(task.get("kind") or "reading"),
        "status": str(task.get("status") or "active"),
        "node_id": str(snapshot.get("node_id") or ""),
        "node_name": str(snapshot.get("node_name") or ""),
        "activity_at": str(snapshot.get("activity_at") or snapshot.get("updated_at") or ""),
    }


def _list_courses_with_resume(user_id: str, known_task_ids: set[str]) -> list[dict]:
    courses = [
        course for course in storage.list_courses()
        if course.get("is_published")
        or not course.get("generation_job_id")
        or str(course.get("generation_job_id")) in known_task_ids
    ]
    for course in courses:
        course_id = str(course.get("course_id") or "")
        summary = _resume_summary(learning_snapshot_repository.load(user_id, course_id))
        if summary:
            course["resume"] = summary
    return courses


@router.get("/courses")
async def list_courses(
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    user_id = resolve_user_id(request.headers.get("X-User-Id"))
    known_task_ids = {str(task_id) for task_id in tm.tasks}
    return await run_in_threadpool(_list_courses_with_resume, user_id, known_task_ids)


@router.get("/courses/{course_id}")
async def get_course(course_id: str):
    return project_learning_objective_bindings(await get_course_or_404(course_id))


@router.get("/courses/{course_id}/document")
async def get_course_document(course_id: str):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    repository = get_course_document_repository()
    return await run_in_threadpool(
        lambda: repository.document_envelope(
            course_id,
            prepared_legacy_course=course,
        )
    )


@router.post("/courses/{course_id}/document/migrate")
async def migrate_course_document(course_id: str, body: CourseDocumentMigrationRequest):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Explicit migration confirmation is required")
    repository = get_course_document_repository()
    try:
        return await repository.migrate_legacy_course(
            course_id,
            expected_source_checksum=body.source_checksum,
        )
    except CourseMigrationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    removed_tasks = await tm.delete_course(course_id)
    return {"status": "success", "removed_tasks": removed_tasks}


@router.post("/course-generation/generate", status_code=202)
async def create_course_generation_job(
    req: CourseGenerationRequest,
    tm: TaskManager = Depends(require_task_manager),
):
    """Create the sole persisted generation job and return immediately."""
    if req.course_type not in ENABLED_COURSE_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "course_type_not_enabled",
                "course_type": req.course_type,
                "enabled_course_types": sorted(ENABLED_COURSE_TYPES),
            },
        )
    request_snapshot = req.model_dump(mode="json")
    return await tm.create_generation_job(request_snapshot)


@router.post("/courses/{course_id}/locate")
async def locate_node(course_id: str, req: LocateNodeRequest):
    tree_data = await get_course_or_404(course_id)
    if "nodes" not in tree_data:
        return {}
    return get_course_service().locate_node(req.keyword, tree_data["nodes"])


# =============================================================================
# Node-level operations (HTTP fallback for WebSocket commands)
# Requirements: 7.1, 7.2, 7.3, 7.4
# =============================================================================


@router.post("/courses/{course_id}/nodes/{node_id}/skip")
async def skip_node(
    course_id: str,
    node_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    """Skip a node during generation."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm.skip_node(task_id, node_id)
    return {"status": "skipped"}


@router.post("/courses/{course_id}/nodes/{node_id}/retry")
async def retry_node(
    course_id: str,
    node_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    """Retry a failed or completed node."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm.retry_node(task_id, node_id)
    return {"status": "retry_scheduled"}


@router.post("/courses/{course_id}/nodes/{node_id}/stop")
async def stop_node(
    course_id: str,
    node_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    """Stop generating a node, keeping already-generated content."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm.stop_node(task_id, node_id)
    return {"status": "stopped"}


@router.post("/courses/{course_id}/nodes/{node_id}/instruction")
async def set_custom_instruction(
    course_id: str,
    node_id: str,
    body: CustomInstructionRequest,
    tm: TaskManager = Depends(require_task_manager),
):
    """Set a custom generation instruction for a node."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm._set_custom_instruction(task_id, node_id, body.instruction)
    return {"status": "instruction_set"}


@router.post("/courses/{course_id}/retry_all_failed")
async def retry_all_failed(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    """Retry all failed nodes for a course."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm.retry_all_failed(task_id)
    return {"status": "retry_all_scheduled"}


# =============================================================================
# Generation config
# Requirements: 14.4
# =============================================================================


@router.put("/courses/{course_id}/nodes/{node_id}/config")
async def update_node_config(
    course_id: str,
    node_id: str,
    body: NodeConfigUpdateRequest,
):
    """Update generation config for a specific node."""
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)

    config = node.get("generation_config") or {}
    update_data = body.model_dump(exclude_none=True)
    config.update(update_data)
    node["generation_config"] = config

    await save_course_compat(storage, course_id, tree_data)
    return {"status": "config_updated", "config": config}
