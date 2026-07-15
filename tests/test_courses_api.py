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
    orig_task_manager = deps_mod._task_manager

    fake_manager = MagicMock()
    fake_manager.tasks = {}

    async def delete_course(course_id):
        mock_storage.delete_course(course_id)
        return 0

    fake_manager.delete_course = AsyncMock(side_effect=delete_course)
    fake_manager.create_generation_job = AsyncMock()

    storage_mod.storage = mock_storage
    deps_mod.storage = mock_storage
    courses_mod.storage = mock_storage
    deps_mod._task_manager = fake_manager

    from main import app
    yield app

    storage_mod.storage = orig_storage
    deps_mod.storage = orig_deps_storage
    courses_mod.storage = orig_courses_storage
    deps_mod._task_manager = orig_task_manager


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
async def test_list_courses_hides_generation_shell_without_task(client, mock_storage):
    """任务已经丢失的未发布占位记录不得伪装成可学习课程。"""
    mock_storage.list_courses = MagicMock(return_value=[{
        "course_id": "orphan-course",
        "course_name": "失联占位",
        "node_count": 0,
        "generation_job_id": "missing-job",
        "generation_status": "queued",
        "is_published": False,
    }])

    resp = await client.get("/api/courses")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_courses_keeps_generation_shell_with_task(client, mock_storage):
    """仍由真实任务承接的占位记录需要留在课程库展示进度。"""
    import dependencies as deps_module

    deps_module._task_manager.tasks = {"active-job": {"id": "active-job"}}
    mock_storage.list_courses = MagicMock(return_value=[{
        "course_id": "active-course",
        "course_name": "正在生成",
        "node_count": 0,
        "generation_job_id": "active-job",
        "generation_status": "queued",
        "is_published": False,
    }])

    resp = await client.get("/api/courses")

    assert resp.status_code == 200
    assert [course["course_id"] for course in resp.json()] == ["active-course"]


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


@pytest.mark.asyncio
async def test_material_backed_generate_course_creates_one_generation_job(client, monkeypatch):
    """课程生成入口应立即返回唯一 Job，而不是同步生成课程正文。"""
    import dependencies as deps_module

    fake_manager = MagicMock()
    fake_manager.create_generation_job = AsyncMock(return_value={
        "job_id": "job-blueprint",
        "task_id": "job-blueprint",
        "course_id": "course-blueprint",
        "course_name": "AI",
        "status": "pending",
        "phase": "queued",
    })
    monkeypatch.setattr(deps_module, "_task_manager", fake_manager)

    resp = await client.post("/api/course-generation/generate", json={
        "subject": "AI",
        "difficulty": "advanced",
        "style": "socratic",
        "requirements": "少废话",
        "pedagogy_mode": "programming_engineering",
    })

    assert resp.status_code == 202
    data = resp.json()
    assert data["job_id"] == data["task_id"] == "job-blueprint"
    assert data["course_id"] == "course-blueprint"
    fake_manager.create_generation_job.assert_awaited_once()
    snapshot = fake_manager.create_generation_job.await_args.args[0]
    assert snapshot["subject"] == "AI"
    assert snapshot["difficulty"] == "advanced"
    assert snapshot["style"] == "socratic"
    assert snapshot["requirements"] == "少废话"
    assert snapshot["pedagogy_mode"] == "programming_engineering"


@pytest.mark.asyncio
async def test_generate_course_rejects_blank_subject(client):
    """只有空白字符的课程主题不得创建后台任务。"""
    import dependencies as deps_module

    manager = deps_module._task_manager
    resp = await client.post("/api/course-generation/generate", json={
        "subject": "   \n\t",
    })

    assert resp.status_code == 422
    manager.create_generation_job.assert_not_awaited()
