from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import tasks


def _request(actor_id: str | None = None):
    return SimpleNamespace(headers={"X-User-Id": actor_id} if actor_id else {})


def _task(task_id: str, owner_id: str, *, status: str = "pending") -> dict:
    return {
        "id": task_id,
        "course_id": f"course-{task_id}",
        "type": "teacher_outline_generation",
        "owner_id": owner_id,
        "status": status,
        "updated_at": "2026-08-23T00:00:00Z",
    }


def test_task_list_hides_other_owners_tasks():
    raw = {
        "owned": _task("owned", "teacher-a"),
        "foreign": _task("foreign", "teacher-b"),
        "legacy": _task("legacy", ""),
    }
    manager = SimpleNamespace(
        tasks=raw,
        get_all_tasks=lambda _limit: list(raw.values()),
    )

    result = tasks.list_tasks(_request("teacher-a"), 100, manager)

    assert [item["id"] for item in result] == ["owned", "legacy"]


@pytest.mark.asyncio
async def test_foreign_actor_cannot_pause_owned_task():
    manager = SimpleNamespace(
        tasks={"job-1": _task("job-1", "teacher-a")},
        pause_task=AsyncMock(),
    )

    with pytest.raises(HTTPException) as captured:
        await tasks.pause_task("job-1", _request("teacher-b"), manager)

    assert captured.value.status_code == 404
    manager.pause_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_owned_actor_can_pause_task():
    manager = SimpleNamespace(
        tasks={"job-1": _task("job-1", "teacher-a")},
        pause_task=AsyncMock(),
    )

    result = await tasks.pause_task("job-1", _request("teacher-a"), manager)

    assert result == {"status": "paused"}
    manager.pause_task.assert_awaited_once_with("job-1")
