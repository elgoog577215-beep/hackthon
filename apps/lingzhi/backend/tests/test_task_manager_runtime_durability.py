from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

import jobs.manager as task_manager_module
from jobs.manager import (
    TaskLeaderConflictError,
    TaskManager,
)


class RuntimeStorage:
    def __init__(self, root) -> None:
        self._data_dir = root


def build_manager(tmp_path, monkeypatch, *, runtime_mode: str = "isolated_test") -> TaskManager:
    data_dir = tmp_path / "data"
    monkeypatch.setattr(
        task_manager_module,
        "TASKS_FILE",
        data_dir / "generation_jobs.json",
    )
    return TaskManager(
        storage=RuntimeStorage(data_dir),
        course_service=None,
        ws_service=None,
        runtime_mode=runtime_mode,
    )


def fail_atomic_write(*_args, **_kwargs) -> None:
    raise OSError("disk unavailable")


@pytest.mark.asyncio
async def test_lifecycle_write_failure_keeps_previous_memory_state(
    tmp_path,
    monkeypatch,
) -> None:
    manager = build_manager(tmp_path, monkeypatch)
    task_id = await manager.create_task("course-1", enqueue=False)
    manager.tasks[task_id].update({
        "status": "running",
        "phase": "content_generation",
        "current_phase": "content_generation",
        "progress": 40,
    })
    manager.save_tasks(strict=True)
    previous = deepcopy(manager.tasks[task_id])
    monkeypatch.setattr(manager, "_write_task_index_atomic", fail_atomic_write)

    with pytest.raises(OSError, match="disk unavailable"):
        await manager._update_task_status(
            task_id,
            "completed",
            message="已完成",
        )

    assert manager.tasks[task_id] == previous

    changed = await manager._update_phase(
        task_id,
        "content_generation",
        45,
        "正在生成",
    )
    assert changed is True
    assert manager.tasks[task_id]["status"] == "running"
    assert manager.tasks[task_id]["progress"] == 45


@pytest.mark.asyncio
async def test_create_pause_resume_and_cancel_do_not_publish_failed_writes(
    tmp_path,
    monkeypatch,
) -> None:
    manager = build_manager(tmp_path, monkeypatch)
    running_id = await manager.create_task("course-running", enqueue=False)
    manager.tasks[running_id]["status"] = "running"
    failed_id = await manager.create_task(
        "course-import",
        task_type="course_import",
        enqueue=False,
    )
    manager.tasks[failed_id]["status"] = "failed"
    manager.save_tasks(strict=True)
    running_before = deepcopy(manager.tasks[running_id])
    failed_before = deepcopy(manager.tasks[failed_id])
    manager._cancel_runtime_tasks = AsyncMock()
    manager.describe_task_recovery = lambda _task_id: {
        "can_resume": True,
        "checkpoint": {"parsed_ready": False},
    }
    monkeypatch.setattr(manager, "_write_task_index_atomic", fail_atomic_write)

    with pytest.raises(OSError, match="disk unavailable"):
        await manager.create_task("course-new", task_id="new-task", enqueue=False)
    assert "new-task" not in manager.tasks

    with pytest.raises(OSError, match="disk unavailable"):
        await manager.pause_task(running_id)
    assert manager.tasks[running_id] == running_before
    manager._cancel_runtime_tasks.assert_not_awaited()

    with pytest.raises(OSError, match="disk unavailable"):
        await manager.resume_task(failed_id)
    assert manager.tasks[failed_id] == failed_before
    assert manager._task_queue.empty()

    with pytest.raises(OSError, match="disk unavailable"):
        await manager.delete_task(running_id)
    assert manager.tasks[running_id] == running_before
    manager._cancel_runtime_tasks.assert_not_awaited()


def test_confirmation_draft_is_not_published_when_persistence_fails(
    tmp_path,
    monkeypatch,
) -> None:
    manager = build_manager(tmp_path, monkeypatch)
    task_id = "review-task"
    manager.tasks[task_id] = {
        "id": task_id,
        "course_id": "course-1",
        "status": "waiting_for_review",
        "guided_workflow": {
            "review_step": "outline",
            "steps": [{"key": "outline", "status": "waiting_for_confirmation"}],
        },
    }
    manager.save_tasks(strict=True)
    previous = deepcopy(manager.tasks[task_id])
    draft = deepcopy(previous)
    draft["status"] = "pending"
    draft["guided_workflow"]["review_step"] = None
    draft["guided_workflow"]["steps"][0]["status"] = "confirmed"
    monkeypatch.setattr(manager, "_write_task_index_atomic", fail_atomic_write)

    with pytest.raises(OSError, match="disk unavailable"):
        manager._commit_task_draft(task_id, draft)

    assert manager.tasks[task_id] == previous


def test_second_leader_cannot_load_or_modify_same_data_directory(
    tmp_path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    task_file = data_dir / "generation_jobs.json"
    data_dir.mkdir(parents=True)
    task_file.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", task_file)
    first = TaskManager(
        RuntimeStorage(data_dir),
        course_service=None,
        ws_service=None,
        runtime_mode="leader",
    )
    original = task_file.read_bytes()
    loaded_by_second = False
    original_load_tasks = TaskManager.load_tasks

    def tracked_load_tasks(self) -> None:
        nonlocal loaded_by_second
        if self is not first:
            loaded_by_second = True
        original_load_tasks(self)

    monkeypatch.setattr(TaskManager, "load_tasks", tracked_load_tasks)
    try:
        with pytest.raises(
            TaskLeaderConflictError,
            match="Another TaskManager owns this data directory",
        ):
            TaskManager(
                RuntimeStorage(data_dir),
                course_service=None,
                ws_service=None,
                runtime_mode="leader",
            )
        assert loaded_by_second is False
        assert task_file.read_bytes() == original
        assert first.leader_health() == {
            "mode": "leader",
            "state": "acquired",
            "ready": True,
        }
    finally:
        first._release_leader_lock()


@pytest.mark.asyncio
async def test_consumer_starts_only_after_reconciliation_and_persistence(
    tmp_path,
    monkeypatch,
) -> None:
    manager = build_manager(tmp_path, monkeypatch)
    manager.tasks["recoverable"] = {
        "id": "recoverable",
        "course_id": "course-1",
        "type": "course_generation",
        "status": "running",
    }
    order: list[str] = []

    async def reconcile(_task_id: str) -> bool:
        order.append("reconciled")
        return True

    original_save = manager.save_tasks

    def save_tasks(*, strict: bool = False) -> None:
        original_save(strict=strict)
        if strict:
            order.append("persisted")

    async def consumer() -> None:
        order.append("consumer_started")
        while manager._running:
            await asyncio.sleep(0)

    monkeypatch.setattr(manager, "_reconcile_task_after_restart", reconcile)
    monkeypatch.setattr(manager, "save_tasks", save_tasks)
    monkeypatch.setattr(manager, "_consumer_loop", consumer)

    await manager.start()
    await asyncio.sleep(0)
    try:
        assert order[:3] == ["reconciled", "persisted", "consumer_started"]
        assert manager._task_queue.qsize() == 1
    finally:
        await manager.shutdown(timeout=0)


@pytest.mark.asyncio
async def test_read_only_mode_can_load_but_never_start_or_write(
    tmp_path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    task_file = data_dir / "generation_jobs.json"
    data_dir.mkdir(parents=True)
    task_file.write_text(
        json.dumps({
            "kept": {
                "id": "kept",
                "course_id": "course-1",
                "type": "course_generation",
                "status": "completed",
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", task_file)
    manager = TaskManager(
        RuntimeStorage(data_dir),
        course_service=None,
        ws_service=None,
        runtime_mode="read_only",
    )

    assert manager.tasks["kept"]["status"] == "completed"
    with pytest.raises(TaskLeaderConflictError, match="cannot modify"):
        await manager.create_task("course-2", enqueue=False)
    with pytest.raises(TaskLeaderConflictError, match="cannot start"):
        await manager.start()
