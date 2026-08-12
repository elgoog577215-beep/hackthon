"""学习事实导出/删除路由的行为验证。

除了正常路径，重点验证身份边界：学习者只能导出和删除**自己**的事实。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import learning_events
import learning_governance


class MemoryStorage:
    def __init__(self):
        self.data: dict[str, object] = {}

    def load_data(self, filename):
        import copy

        return copy.deepcopy(self.data.get(filename))

    def save_data(self, filename, value):
        import copy

        self.data[filename] = copy.deepcopy(value)


@pytest.fixture
def memory_storage(monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr(learning_events, "storage", storage)
    monkeypatch.setattr(learning_governance, "storage", storage)
    return storage


@pytest.fixture
async def client():
    """只挂载被测路由，不导入整个 `main` app。

    `main` 在模块导入期就构造 TaskManager 与表达重建服务等全局后台组件；把它拉进
    单元测试会让整个 `backend/tests` 挂起（实测：加回本文件即复现，移走即恢复）。
    路由与 `main` 的接线由真实服务器启动验证，不靠这里。
    """
    from fastapi import FastAPI

    from routers import learning_governance

    app = FastAPI()
    app.include_router(learning_governance.router, prefix="/api")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _record(user_id: str, **kwargs):
    payload = {
        "event_type": "learner_self_reported",
        "actor": "user",
        "user_id": user_id,
        "course_id": "course-1",
        "evidence": {"statement": "这段没懂"},
    }
    payload.update(kwargs)
    return learning_events.record_learning_event(**payload)


@pytest.mark.asyncio
async def test_export_returns_only_the_calling_learner_facts(memory_storage, client):
    _record("learner-1")
    _record("learner-2")

    response = await client.get(
        "/api/learning-facts/export", headers={"X-User-Id": "learner-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["manifest"]["event_count"] == 1
    assert {item["user_id"] for item in body["events"]} == {"learner-1"}


@pytest.mark.asyncio
async def test_export_requires_a_stable_learner_identity(memory_storage, client):
    response = await client.get("/api/learning-facts/export")
    assert response.status_code == 400

    shared = await client.get(
        "/api/learning-facts/export", headers={"X-User-Id": "default_user"},
    )
    assert shared.status_code == 400


@pytest.mark.asyncio
async def test_delete_removes_the_fact_and_returns_a_receipt(memory_storage, client):
    event = _record("learner-1")

    response = await client.post(
        "/api/learning-facts/delete",
        headers={"X-User-Id": "learner-1"},
        json={"scope": "event", "event_id": event["event_id"]},
    )

    assert response.status_code == 200
    receipt = response.json()
    assert receipt["deleted_event_count"] == 1
    # 回执不得含学习内容
    assert "这段没懂" not in str(receipt)
    assert learning_events.load_learning_events(user_id="learner-1") == []


@pytest.mark.asyncio
async def test_a_learner_cannot_delete_another_learners_fact(memory_storage, client):
    victim = _record("learner-2")

    response = await client.post(
        "/api/learning-facts/delete",
        headers={"X-User-Id": "learner-1"},
        json={"scope": "event", "event_id": victim["event_id"]},
    )

    # 身份来自请求头，删除范围被限制在调用者自己的事实上
    assert response.status_code == 200
    assert response.json()["deleted_event_count"] == 0
    assert len(learning_events.load_learning_events(user_id="learner-2")) == 1


@pytest.mark.asyncio
async def test_invalid_deletion_scope_is_rejected(memory_storage, client):
    missing_id = await client.post(
        "/api/learning-facts/delete",
        headers={"X-User-Id": "learner-1"},
        json={"scope": "event"},
    )
    assert missing_id.status_code == 422

    unknown_scope = await client.post(
        "/api/learning-facts/delete",
        headers={"X-User-Id": "learner-1"},
        json={"scope": "everything"},
    )
    assert unknown_scope.status_code == 422


@pytest.mark.asyncio
async def test_scope_correction_route_appends_without_rewriting(memory_storage, client):
    original = _record("learner-1", node_id="node-wrong")

    response = await client.post(
        "/api/learning-facts/scope-corrections",
        headers={"X-User-Id": "learner-1"},
        json={"event_id": original["event_id"], "corrections": {"node_id": "node-right"}},
    )

    assert response.status_code == 200
    assert response.json()["result"]["previous"] == {"node_id": "node-wrong"}

    stored = next(
        item for item in learning_events.load_learning_events(user_id="learner-1")
        if item["event_id"] == original["event_id"]
    )
    # 历史事实未被改写
    assert stored["node_id"] == "node-wrong"


@pytest.mark.asyncio
async def test_scope_correction_route_refuses_content_rewrite(memory_storage, client):
    original = _record("learner-1")

    response = await client.post(
        "/api/learning-facts/scope-corrections",
        headers={"X-User-Id": "learner-1"},
        json={
            "event_id": original["event_id"],
            "corrections": {"evidence": {"statement": "改写"}},
        },
    )

    assert response.status_code == 422
    assert "correctable_fields" in response.json()["detail"]


@pytest.mark.asyncio
async def test_source_links_route_reports_unavailable_instead_of_404(memory_storage, client):
    """课程不存在时也要返回结构化结果，而不是 404。"""
    _record("learner-1", course_id="course-gone")

    response = await client.get(
        "/api/learning-facts/source-links", headers={"X-User-Id": "learner-1"},
    )

    assert response.status_code == 200
    link = response.json()["source_links"][0]
    assert link["status"] == "unavailable"
    assert link["can_navigate"] is False
    assert link["origin"]["course_id"] == "course-gone"
