"""
SM-2 复习调度 API 测试
测试 /api/courses/{course_id}/review 相关端点。
主要测试 get_review_stats（纯计算逻辑，无 AI 调用）和 reset_review_history。
"""

import sys
import os
import pytest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from httpx import AsyncClient, ASGITransport
from conftest import MockStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_storage():
    return MockStorage()


@pytest.fixture
def patched_app(mock_storage, monkeypatch):
    """Patch storage 后返回 app。"""
    import storage as storage_mod
    import dependencies as deps_mod
    import routers.courses as courses_mod
    import learning_events

    monkeypatch.setattr(storage_mod, "storage", mock_storage)
    monkeypatch.setattr(deps_mod, "storage", mock_storage)
    monkeypatch.setattr(courses_mod, "storage", mock_storage)
    monkeypatch.setattr(learning_events, "storage", mock_storage)

    from main import app
    yield app


@pytest.fixture
async def client(patched_app):
    transport = ASGITransport(app=patched_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-User-Id": "test-learner"},
    ) as ac:
        yield ac


def _make_review_course(course_id="review-course-1", num_nodes=5):
    """创建复习测试课程。"""
    nodes = []
    for i in range(num_nodes):
        nodes.append({
            "node_id": f"node-{i}",
            "parent_node_id": "root",
            "node_name": f"第{i+1}章",
            "node_level": 2,
            "node_content": f"内容{i+1}",
            "node_type": "original",
        })
    return {
        "course_id": course_id,
        "course_name": "复习测试课程",
        "nodes": nodes,
    }


def _review_event(
    node_id: str,
    *,
    next_review: datetime,
    created_at: datetime,
    passed: bool = True,
):
    return {
        "event_id": f"evt-{node_id}-{created_at.timestamp()}",
        "event_type": "review_result_submitted",
        "user_id": "test-learner",
        "actor": "user",
        "source": "test",
        "course_id": "review-course-1",
        "node_id": node_id,
        "node_name": node_id,
        "concept_ids": [],
        "evidence": {"quality": 4 if passed else 2, "is_correct": passed},
        "result": {
            "review_count": 1,
            "ease_factor": 2.5,
            "interval_days": 1,
            "next_review": next_review.isoformat(),
            "passed": passed,
        },
        "metadata": {},
        "created_at": created_at.isoformat(),
        "schema_version": 3,
    }


def _seed_events(mock_storage, *events):
    mock_storage.data["learning_events.json"] = list(events)


# ---------------------------------------------------------------------------
# GET /api/courses/{course_id}/review/stats
# ---------------------------------------------------------------------------

async def test_stats_empty_review_history(client, mock_storage):
    """无复习历史时，所有计数应为 0"""
    course = _make_review_course()
    mock_storage.save_course(course["course_id"], course)

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 5
    assert data["due_today"] == 0
    assert data["overdue"] == 0
    assert data["completed_today"] == 0
    assert data["streak_days"] == 0


async def test_stats_due_today(client, mock_storage):
    """今天到期的节点应计入 due_today"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    course = _make_review_course()
    mock_storage.save_course(course["course_id"], course)
    _seed_events(
        mock_storage,
        _review_event("node-0", next_review=today, created_at=today - timedelta(days=1)),
        _review_event("node-1", next_review=today, created_at=today - timedelta(days=1)),
    )

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["due_today"] == 2
    assert data["overdue"] == 0


async def test_stats_overdue(client, mock_storage):
    """过期的节点应计入 overdue"""
    yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    three_days_ago = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=3)
    course = _make_review_course()
    mock_storage.save_course(course["course_id"], course)
    _seed_events(
        mock_storage,
        _review_event("node-0", next_review=yesterday, created_at=three_days_ago),
        _review_event("node-1", next_review=three_days_ago, created_at=three_days_ago),
    )

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overdue"] == 2
    assert data["due_today"] == 0


async def test_stats_completed_today(client, mock_storage):
    """今天完成复习的节点应计入 completed_today"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    course = _make_review_course()
    mock_storage.save_course(course["course_id"], course)
    _seed_events(
        mock_storage,
        _review_event("node-0", next_review=tomorrow, created_at=today),
        _review_event("node-1", next_review=tomorrow, created_at=today),
    )

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed_today"] == 2


async def test_stats_mixed_states(client, mock_storage):
    """混合状态：同时有 due_today、overdue、completed_today"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    course = _make_review_course()
    mock_storage.save_course(course["course_id"], course)
    _seed_events(
        mock_storage,
        _review_event("node-0", next_review=today, created_at=yesterday),
        _review_event("node-1", next_review=yesterday, created_at=yesterday - timedelta(days=2)),
        _review_event("node-2", next_review=tomorrow, created_at=today),
    )

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 5
    assert data["due_today"] == 1
    assert data["overdue"] == 1
    assert data["completed_today"] == 1
    assert data["streak_days"] == 2


async def test_stats_nonexistent_course(client):
    """不存在的课程应返回 404"""
    resp = await client.get("/api/courses/nonexistent/review/stats")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/courses/{course_id}/review/reset
# ---------------------------------------------------------------------------

async def test_reset_review_history(client, mock_storage):
    """重置复习历史应写入边界事件，不回写课程。"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    course = _make_review_course()
    mock_storage.save_course(course["course_id"], course)
    _seed_events(
        mock_storage,
        _review_event("node-0", next_review=today, created_at=today),
    )

    resp = await client.post(f"/api/courses/{course['course_id']}/review/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"

    events = mock_storage.data["learning_events.json"]
    assert events[-1]["event_type"] == "review_reset"

    stats = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert stats.json()["completed_today"] == 0
    assert stats.json()["due_today"] == 0

    saved = mock_storage.load_course(course["course_id"])
    assert saved == course


async def test_reset_nonexistent_course(client):
    """重置不存在的课程应返回 404"""
    resp = await client.post("/api/courses/nonexistent/review/reset")
    assert resp.status_code == 404


async def test_submit_review_records_learning_events(client, mock_storage):
    """提交复习结果应进入统一学习事件账本。"""
    course = _make_review_course(num_nodes=2)
    mock_storage.save_course(course["course_id"], course)

    resp = await client.post(f"/api/courses/{course['course_id']}/review/submit", json={
        "course_id": course["course_id"],
        "results": [
            {
                "node_id": "node-0",
                "quality": 2,
                "time_spent_seconds": 45,
                "notes": "这里还没有完全记住，需要重讲例子。",
            },
            {
                "node_id": "node-1",
                "quality": 5,
                "time_spent_seconds": 20,
            },
        ],
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_count"] == 2

    events = mock_storage.data["learning_events.json"]
    assert [event["event_type"] for event in events] == [
        "review_result_submitted",
        "review_result_submitted",
    ]
    assert events[0]["course_id"] == course["course_id"]
    assert events[0]["node_id"] == "node-0"
    assert events[0]["node_name"] == "第1章"
    assert events[0]["evidence"]["quality"] == 2
    assert events[0]["evidence"]["is_correct"] is False
    assert events[0]["result"]["next_review"]
    assert events[1]["evidence"]["is_correct"] is True
