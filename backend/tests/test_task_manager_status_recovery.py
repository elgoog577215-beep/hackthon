from copy import deepcopy

import pytest


class MemoryStorage:
    def __init__(self, root) -> None:
        self._data_dir = root
        self.course = {"course_id": "course-status-recovery"}

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


@pytest.mark.asyncio
async def test_successful_retry_clears_stale_failure_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    import task_manager as task_manager_module
    from task_manager import TaskManager

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "jobs.json")
    manager = TaskManager(
        MemoryStorage(tmp_path),
        course_service=None,
        ws_service=None,
    )
    task_id = await manager.create_task(
        "course-status-recovery",
        "teacher_outline_generation",
        enqueue=False,
    )
    await manager._update_task_status(
        task_id,
        "failed",
        error="provider unavailable",
        error_detail={"code": "provider_unavailable", "retryable": True},
    )
    manager.tasks[task_id]["error_code"] = "provider_unavailable"
    manager.tasks[task_id]["error_user_message"] = "生成暂停"

    await manager._update_task_status(task_id, "running", message="正在恢复")
    running = manager.get_task(task_id)
    assert running["error"] is None
    assert running["error_detail"] is None
    assert running["error_code"] is None
    assert running["error_user_message"] is None

    await manager._update_task_status(task_id, "completed", message="生成完成")
    completed = manager.get_task(task_id)
    assert completed["status"] == "completed"
    assert completed["error_code"] is None
