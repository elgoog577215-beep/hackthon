# =============================================================================
# 任务管理路由
# 后台任务创建、暂停、恢复、删除、查询
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Literal
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from jobs.manager import TaskManager, TaskRecoveryConflict, TaskStateConflict
from dependencies import (
    get_course_document_repository,
    get_teacher_lesson_authoring_repository,
    require_task_manager,
)
from course_repository import CourseDocumentRepository, CourseDocumentNotFound
from learner_context import resolve_actor_id
from teacher_lesson_authoring import project_current_teacher_scripts

router = APIRouter(tags=["tasks"])


def _task_owner_id(task: dict | None) -> str:
    if not task:
        return ""
    return str(
        task.get("owner_id")
        or (task.get("request_snapshot") or {}).get("_retrieval_actor_id")
        or ""
    ).strip()


def _task_is_visible_to(task: dict | None, actor_id: str) -> bool:
    owner_id = _task_owner_id(task)
    return not owner_id or owner_id == actor_id


def _require_task_access(tm: TaskManager, task_id: str, request: Request) -> dict:
    task = tm.tasks.get(task_id)
    actor_id = resolve_actor_id(request.headers.get("X-User-Id"))
    if not task or not _task_is_visible_to(task, actor_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _require_latest_course_task_access(
    tm: TaskManager,
    course_id: str,
    request: Request,
    *,
    task_types: set[str] | None = None,
) -> None:
    candidates = [
        task for task in tm.tasks.values()
        if task.get("course_id") == course_id
        and (task_types is None or str(task.get("type") or "") in task_types)
    ]
    if not candidates:
        return
    latest = max(candidates, key=lambda item: str(item.get("updated_at") or ""))
    actor_id = resolve_actor_id(request.headers.get("X-User-Id"))
    if not _task_is_visible_to(latest, actor_id):
        raise HTTPException(status_code=404, detail="Task not found")


@router.get("/courses/{course_id}/task")
def get_course_task(
    course_id: str,
    request: Request,
    task_type: str | None = None,
    tm: TaskManager = Depends(require_task_manager),
    course_repository: CourseDocumentRepository = Depends(
        get_course_document_repository
    ),
):
    try:
        _require_latest_course_task_access(
            tm,
            course_id,
            request,
            task_types={task_type} if task_type else None,
        )
    except HTTPException as access_error:
        try:
            raw = course_repository.load_raw(course_id)
        except CourseDocumentNotFound:
            raise access_error
        if raw.get("is_published") or raw.get("course_document_publication"):
            return {"status": "none"}
        raise access_error
    task = tm.get_latest_task_by_course(course_id, task_type=task_type)
    if task is None:
        return {"status": "none"}
    return task


@router.get("/courses/{course_id}/generation-preview")
def get_course_generation_preview(
    course_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    _require_latest_course_task_access(
        tm,
        course_id,
        request,
        task_types={"course_generation", "course_import"},
    )
    preview = tm.get_generation_preview(
        course_id,
        task_types={"course_generation", "course_import"},
    )
    if preview is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "generation_preview_unavailable",
                "message": "当前课程没有可读取的生成工作区",
            },
        )
    return preview


@router.get("/teacher/courses/{course_id}/generation-preview")
def get_teacher_course_generation_preview(
    course_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    teacher_repository=Depends(get_teacher_lesson_authoring_repository),
):
    _require_latest_course_task_access(
        tm,
        course_id,
        request,
        task_types={"teacher_outline_generation"},
    )
    preview = tm.get_generation_preview(
        course_id,
        task_types={"teacher_outline_generation"},
    )
    if preview is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "teacher_generation_preview_unavailable",
                "message": "当前教师课程没有可读取的大纲工作区",
            },
        )
    return project_current_teacher_scripts(
        preview,
        teacher_repository.view(course_id),
    )


@router.get("/tasks")
def list_tasks(
    request: Request,
    limit: int = 100,
    tm: TaskManager = Depends(require_task_manager),
):
    actor_id = resolve_actor_id(request.headers.get("X-User-Id"))
    summaries = tm.get_all_tasks(max(limit, len(tm.tasks)))
    return [
        summary for summary in summaries
        if _task_is_visible_to(tm.tasks.get(str(summary.get("id") or "")), actor_id)
    ][:limit]


@router.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    _require_task_access(tm, task_id, request)
    task = tm.get_task_summary(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    _require_task_access(tm, task_id, request)
    try:
        await tm.pause_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except TaskStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_state_conflict",
                "message": str(exc),
                "status": exc.status,
            },
        ) from exc
    return {"status": "paused"}


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    _require_task_access(tm, task_id, request)
    try:
        return await tm.resume_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except TaskRecoveryConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_recovery_unavailable",
                "message": str(exc),
                "recovery": exc.recovery,
            },
        ) from exc


@router.get("/tasks/{task_id}/recovery")
def get_task_recovery(
    task_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    _require_task_access(tm, task_id, request)
    try:
        return tm.describe_task_recovery(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@router.delete("/tasks/failed")
async def clear_failed_tasks(
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    actor_id = resolve_actor_id(request.headers.get("X-User-Id"))
    removed_count = await tm.clear_failed_tasks(owner_id=actor_id)
    return {"status": "success", "removed": removed_count}


@router.delete("/tasks")
async def clear_task_records(
    request: Request,
    scope: Literal["invalid", "completed"],
    course_id: str | None = None,
    tm: TaskManager = Depends(require_task_manager),
):
    actor_id = resolve_actor_id(request.headers.get("X-User-Id"))
    task_ids = await tm.clear_task_records(
        scope,
        course_id=course_id,
        owner_id=actor_id,
    )
    return {
        "status": "success",
        "removed": len(task_ids),
        "task_ids": task_ids,
    }


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    _require_task_access(tm, task_id, request)
    try:
        await tm.delete_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    return {"status": "deleted"}
