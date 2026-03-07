"""
课程 API 测试
测试 /api/courses 相关端点的 CRUD 操作。
"""

import sys
import os
import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from httpx import AsyncClient, ASGITransport
from conftest import MockStorage, make_course


@pytest.fixture
def mock_storage():
    return MockStorage()


@pytest.fixture
def patched_app(mock_storage):
    """Patch storage 和 ai_service 后返回 app"""
    import storage as storage_mod
    import dependencies as deps_mod
    import routers.courses as courses_mod

    orig_storage = storage_mod.storage
    orig_deps_storage = deps_mod.storage
    orig_courses_storage = courses_mod.storage

    storage_mod.storage = mock_storage
    deps_mod.storage = mock_storage
    courses_mod.storage = mock_storage

    from main import app
    yield app

    storage_mod.storage = orig_storage
    deps_mod.storage = orig_deps_storage
    courses_mod.storage = orig_courses_storage


@pytest.fixture
async def client(patched_app):
    transport = ASGITransport(app=patched_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_courses_empty(client, mock_storage):
    """空课程列表应返回空数组"""
    resp = await client.get("/api/courses")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_courses_with_data(client, mock_storage):
    """有课程时应返回课程列表"""
    course = make_course(course_id="c1", course_name="Python入门")
    mock_storage.save_course("c1", course)

    resp = await client.get("/api/courses")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["course_name"] == "Python入门"


@pytest.mark.asyncio
async def test_get_course(client, mock_storage):
    """获取单个课程"""
    course = make_course(course_id="c1", num_nodes=2)
    mock_storage.save_course("c1", course)

    resp = await client.get("/api/courses/c1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_name"] == "测试课程"
    assert len(data["nodes"]) == 2


@pytest.mark.asyncio
async def test_get_course_not_found(client, mock_storage):
    """获取不存在的课程应返回 404"""
    resp = await client.get("/api/courses/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_course(client, mock_storage):
    """删除课程"""
    mock_storage.save_course("c1", make_course(course_id="c1"))
    assert len(mock_storage.list_courses()) == 1

    resp = await client.delete("/api/courses/c1")
    assert resp.status_code == 200
    assert len(mock_storage.list_courses()) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_course(client, mock_storage):
    """删除不存在的课程不应报错"""
    resp = await client.delete("/api/courses/nonexistent")
    assert resp.status_code == 200
