# =============================================================================
# 任务管理路由
# 后台任务创建、暂停、恢复、删除、查询
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from task_manager import TaskManager, TaskRecoveryConflict, TaskStateConflict
from dependencies import require_task_manager

router = APIRouter(tags=["tasks"])


@router.get("/courses/{course_id}/task")
def get_course_task(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    tasks = tm.get_tasks_by_course(course_id)
    if not tasks:
        return {"status": "none"}
    tasks.sort(key=lambda x: x["updated_at"], reverse=True)
    return tasks[0]


@router.get("/tasks")
def list_tasks(
    limit: int = 100,
    tm: TaskManager = Depends(require_task_manager),
):
    return tm.get_all_tasks(limit)


@router.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    task = tm.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
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
    tm: TaskManager = Depends(require_task_manager),
):
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
    tm: TaskManager = Depends(require_task_manager),
):
    try:
        return tm.describe_task_recovery(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@router.delete("/tasks/failed")
async def clear_failed_tasks(
    tm: TaskManager = Depends(require_task_manager),
):
    removed_count = await tm.clear_failed_tasks()
    return {"status": "success", "removed": removed_count}


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    try:
        await tm.delete_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    return {"status": "deleted"}
