from unittest.mock import AsyncMock

import pytest

from jobs.manager import TaskManager


@pytest.mark.asyncio
async def test_clear_task_records_separates_invalid_and_published_history():
    manager = object.__new__(TaskManager)
    manager.tasks = {
        "running": {"course_id": "course-1", "status": "running"},
        "failed": {"course_id": "course-1", "status": "failed"},
        "blocked": {
            "course_id": "course-1",
            "status": "completed_with_warnings",
            "publication_allowed": False,
        },
        "published-warning": {
            "course_id": "course-1",
            "status": "completed_with_warnings",
            "publication_allowed": True,
        },
        "completed": {"course_id": "course-2", "status": "completed"},
    }
    manager.delete_task = AsyncMock()

    invalid_ids = await manager.clear_task_records("invalid", course_id="course-1")
    completed_ids = await manager.clear_task_records("completed")

    assert invalid_ids == ["failed", "blocked"]
    assert completed_ids == ["published-warning", "completed"]
    assert manager.delete_task.await_count == 4


@pytest.mark.asyncio
async def test_clear_task_records_rejects_unknown_scope():
    manager = object.__new__(TaskManager)
    manager.tasks = {}

    with pytest.raises(ValueError):
        await manager.clear_task_records("all")
