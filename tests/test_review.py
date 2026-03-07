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
def patched_app(mock_storage):
    """Patch storage 后返回 app"""
    import storage as storage_mod
    import dependencies as deps_mod
    import routers.courses as courses_mod
    import routers.review as review_mod

    originals = {
        'storage': storage_mod.storage,
        'deps': deps_mod.storage,
        'courses': courses_mod.storage,
        'review': review_mod.storage,
    }

    storage_mod.storage = mock_storage
    deps_mod.storage = mock_storage
    courses_mod.storage = mock_storage
    review_mod.storage = mock_storage

    from main import app
    yield app

    storage_mod.storage = originals['storage']
    deps_mod.storage = originals['deps']
    courses_mod.storage = originals['courses']
    review_mod.storage = originals['review']


@pytest.fixture
async def client(patched_app):
    transport = ASGITransport(app=patched_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_review_course(course_id="review-course-1", num_nodes=5, review_history=None):
    """创建带有复习历史的测试课程"""
    nodes = []
    for i in range(num_nodes):
        nodes.append({
            "node_id": f"node-{i}",
            "parent_node_id": "root",
            "node_name": f"第{i+1}章",
            "node_level": 1,
            "node_content": f"内容{i+1}",
            "node_type": "original",
        })
    return {
        "course_id": course_id,
        "course_name": "复习测试课程",
        "nodes": nodes,
        "review_history": review_history or {},
        "learning_streak": 0,
        "last_review_date": None,
    }


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
    review_history = {
        "node-0": {"next_review": today.isoformat(), "last_reviewed": None},
        "node-1": {"next_review": today.isoformat(), "last_reviewed": None},
    }
    course = _make_review_course(review_history=review_history)
    mock_storage.save_course(course["course_id"], course)

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["due_today"] == 2
    assert data["overdue"] == 0


async def test_stats_overdue(client, mock_storage):
    """过期的节点应计入 overdue"""
    yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    three_days_ago = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=3)
    review_history = {
        "node-0": {"next_review": yesterday.isoformat(), "last_reviewed": None},
        "node-1": {"next_review": three_days_ago.isoformat(), "last_reviewed": None},
    }
    course = _make_review_course(review_history=review_history)
    mock_storage.save_course(course["course_id"], course)

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overdue"] == 2
    assert data["due_today"] == 0


async def test_stats_completed_today(client, mock_storage):
    """今天完成复习的节点应计入 completed_today"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    review_history = {
        "node-0": {
            "next_review": tomorrow.isoformat(),
            "last_reviewed": today.isoformat(),
        },
        "node-1": {
            "next_review": tomorrow.isoformat(),
            "last_reviewed": today.isoformat(),
        },
    }
    course = _make_review_course(review_history=review_history)
    mock_storage.save_course(course["course_id"], course)

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed_today"] == 2


async def test_stats_mixed_states(client, mock_storage):
    """混合状态：同时有 due_today、overdue、completed_today"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    review_history = {
        "node-0": {"next_review": today.isoformat(), "last_reviewed": None},          # due today
        "node-1": {"next_review": yesterday.isoformat(), "last_reviewed": None},       # overdue
        "node-2": {"next_review": tomorrow.isoformat(), "last_reviewed": today.isoformat()},  # completed today
        # node-3, node-4: no review history
    }
    course = _make_review_course(review_history=review_history)
    course["learning_streak"] = 7
    mock_storage.save_course(course["course_id"], course)

    resp = await client.get(f"/api/courses/{course['course_id']}/review/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 5
    assert data["due_today"] == 1
    assert data["overdue"] == 1
    assert data["completed_today"] == 1
    assert data["streak_days"] == 7


async def test_stats_nonexistent_course(client):
    """不存在的课程应返回 404"""
    resp = await client.get("/api/courses/nonexistent/review/stats")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/courses/{course_id}/review/reset
# ---------------------------------------------------------------------------

async def test_reset_review_history(client, mock_storage):
    """重置复习历史应清空 review_history 和相关字段"""
    today = datetime.now().isoformat()
    course = _make_review_course(review_history={
        "node-0": {"next_review": today, "last_reviewed": today},
    })
    course["learning_streak"] = 10
    course["last_review_date"] = today
    course["last_study_date"] = today
    mock_storage.save_course(course["course_id"], course)

    resp = await client.post(f"/api/courses/{course['course_id']}/review/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"

    # 验证持久化
    saved = mock_storage.load_course(course["course_id"])
    assert saved["review_history"] == {}
    assert saved["learning_streak"] == 0
    assert saved["last_review_date"] is None
    assert saved["last_study_date"] is None


async def test_reset_nonexistent_course(client):
    """重置不存在的课程应返回 404"""
    resp = await client.post("/api/courses/nonexistent/review/reset")
    assert resp.status_code == 404
