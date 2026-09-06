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
    import jobs.manager as task_manager_module
    from jobs.manager import TaskManager

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

    await manager._update_task_status(
        task_id,
        "running",
        message="正在恢复",
        allow_reactivation=True,
    )
    running = manager.get_task(task_id)
    assert running["error"] is None
    assert running["error_detail"] is None
    assert running["error_code"] is None
    assert running["error_user_message"] is None

    await manager._update_task_status(task_id, "completed", message="生成完成")
    completed = manager.get_task(task_id)
    assert completed["status"] == "completed"
    assert completed["error_code"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen_status",
    [
        "paused",
        "cancelled",
        "waiting_for_input",
        "waiting_for_review",
        "completed",
        "completed_with_warnings",
        "failed",
        "conflict",
        "error",
    ],
)
async def test_late_background_updates_cannot_overwrite_frozen_task_states(
    tmp_path,
    monkeypatch,
    frozen_status,
) -> None:
    import jobs.manager as task_manager_module
    from jobs.manager import TaskManager

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
    task = manager.tasks[task_id]
    task.update({
        "status": frozen_status,
        "phase": "frozen_phase",
        "current_phase": "frozen_phase",
        "progress": 40,
        "message": "用户或终态已确立",
        "current_nodes": [{"node_id": "node-1", "generated_chars": 12}],
        "event_history": [],
    })

    for late_status in ("running", "completed", "failed"):
        changed = await manager._update_task_status(
            task_id,
            late_status,
            message="迟到后台更新",
            error="late worker failure",
        )
        assert changed is False
    phase_changed = await manager._update_phase(
        task_id,
        "late_phase",
        95,
        "迟到进度",
    )
    await manager._mark_node_streaming(task_id, "node-1", 999)
    await manager._record_representation_event(task_id, {
        "event": "build_complete",
        "progress": 100,
        "stage": "complete",
    })

    assert phase_changed is False
    assert task["status"] == frozen_status
    assert task["phase"] == "frozen_phase"
    assert task["progress"] == 40
    assert task["message"] == "用户或终态已确立"
    assert task["current_nodes"][0]["generated_chars"] == 12
    assert task["event_history"] == []


@pytest.mark.asyncio
async def test_complete_task_preserves_pause_that_wins_final_status_race(
    tmp_path,
    monkeypatch,
) -> None:
    import jobs.manager as task_manager_module
    from jobs.manager import TaskManager

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "jobs.json")
    manager = TaskManager(
        MemoryStorage(tmp_path),
        course_service=None,
        ws_service=None,
    )
    task_id = await manager.create_task(
        "course-status-recovery",
        "course_generation",
        enqueue=False,
    )
    task = manager.tasks[task_id]
    task.update({
        "status": "running",
        "phase": "generating",
        "current_phase": "generating",
        "progress": 80,
        "message": "正在生成",
        "request_snapshot": {},
    })
    course = {"course_id": "course-status-recovery", "nodes": []}

    async def prepare_candidate(_task_id, _course):
        return course, {"final_status": "quality_failed"}, [], False, False

    async def pause_during_finalization(_task_id, _course):
        task.update({
            "status": "paused",
            "phase": "paused_by_user",
            "current_phase": "paused_by_user",
            "progress": 82,
            "message": "用户已暂停",
        })
        return {}

    monkeypatch.setattr(manager, "_prepare_content_candidate", prepare_candidate)
    monkeypatch.setattr(
        manager,
        "_publish_course_artifacts_to_space",
        pause_during_finalization,
    )

    await manager._complete_task(task_id, course)

    assert task["status"] == "paused"
    assert task["phase"] == "paused_by_user"
    assert task["current_phase"] == "paused_by_user"
    assert task["progress"] == 82
    assert task["message"] == "用户已暂停"
