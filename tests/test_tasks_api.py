"""任务生命周期 API 的状态语义测试。"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from task_manager import TaskStateConflict


@pytest.fixture
def task_manager(monkeypatch):
    import dependencies

    manager = MagicMock()
    manager.pause_task = AsyncMock()
    manager.resume_task = AsyncMock()
    manager.delete_task = AsyncMock()
    manager.clear_failed_tasks = AsyncMock(return_value=0)
    monkeypatch.setattr(dependencies, "_task_manager", manager)
    return manager


@pytest.fixture
async def client(task_manager):
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as api:
        yield api


@pytest.mark.asyncio
async def test_pause_missing_task_returns_404(client, task_manager):
    task_manager.pause_task.side_effect = KeyError("missing")

    response = await client.post("/api/tasks/missing/pause")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pause_terminal_task_returns_state_conflict(client, task_manager):
    task_manager.pause_task.side_effect = TaskStateConflict(
        "Task cannot be paused in its current state",
        status="completed",
    )

    response = await client.post("/api/tasks/done/pause")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "task_state_conflict"
    assert response.json()["detail"]["status"] == "completed"


@pytest.mark.asyncio
async def test_delete_missing_task_returns_404(client, task_manager):
    task_manager.delete_task.side_effect = KeyError("missing")

    response = await client.delete("/api/tasks/missing")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_clear_failed_tasks_awaits_cleanup(client, task_manager):
    task_manager.clear_failed_tasks.return_value = 2

    response = await client.delete("/api/tasks/failed")

    assert response.status_code == 200
    assert response.json() == {"status": "success", "removed": 2}
    task_manager.clear_failed_tasks.assert_awaited_once()
