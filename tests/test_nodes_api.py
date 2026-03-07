"""
节点操作 API 测试
测试 /api/courses/{course_id}/nodes 相关端点。
"""

import sys
import os
import pytest
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from httpx import AsyncClient, ASGITransport
from conftest import MockStorage, make_course


@pytest.fixture
def mock_storage():
    return MockStorage()


@pytest.fixture
def patched_app(mock_storage):
    """Patch storage 后返回 app"""
    import storage as storage_mod
    import dependencies as deps_mod
    import routers.courses as courses_mod
    import routers.nodes as nodes_mod

    originals = {
        'storage': storage_mod.storage,
        'deps': deps_mod.storage,
        'courses': courses_mod.storage,
        'nodes': nodes_mod.storage,
    }

    storage_mod.storage = mock_storage
    deps_mod.storage = mock_storage
    courses_mod.storage = mock_storage
    nodes_mod.storage = mock_storage

    from main import app
    yield app

    storage_mod.storage = originals['storage']
    deps_mod.storage = originals['deps']
    courses_mod.storage = originals['courses']
    nodes_mod.storage = originals['nodes']


@pytest.fixture
async def client(patched_app):
    transport = ASGITransport(app=patched_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def course_with_nodes(mock_storage):
    """创建一个带有层级节点的课程"""
    cid = "test-course-1"
    root_id = "node-root-1"
    child_id = "node-child-1"
    course = {
        "course_id": cid,
        "course_name": "测试课程",
        "nodes": [
            {
                "node_id": root_id,
                "parent_node_id": "root",
                "node_name": "第1章",
                "node_level": 1,
                "node_content": "第一章内容",
                "node_type": "original",
            },
            {
                "node_id": child_id,
                "parent_node_id": root_id,
                "node_name": "1.1 小节",
                "node_level": 2,
                "node_content": "小节内容",
                "node_type": "original",
            },
        ],
    }
    mock_storage.save_course(cid, course)
    return {"course_id": cid, "root_id": root_id, "child_id": child_id}


# --- 添加节点 ---

async def test_add_node_to_root(client, mock_storage, course_with_nodes):
    """添加根级节点"""
    cid = course_with_nodes["course_id"]
    resp = await client.post(f"/api/courses/{cid}/nodes", json={
        "parent_node_id": "root",
        "node_name": "新章节",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_name"] == "新章节"
    assert data["node_level"] == 1
    assert data["parent_node_id"] == "root"
    # 验证持久化
    course = mock_storage.load_course(cid)
    assert len(course["nodes"]) == 3


async def test_add_child_node(client, mock_storage, course_with_nodes):
    """添加子节点"""
    cid = course_with_nodes["course_id"]
    parent_id = course_with_nodes["root_id"]
    resp = await client.post(f"/api/courses/{cid}/nodes", json={
        "parent_node_id": parent_id,
        "node_name": "1.2 新小节",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_level"] == 2
    assert data["parent_node_id"] == parent_id


async def test_add_node_to_nonexistent_course(client):
    """向不存在的课程添加节点应返回 404"""
    resp = await client.post("/api/courses/nonexistent/nodes", json={
        "parent_node_id": "root",
        "node_name": "测试",
    })
    assert resp.status_code == 404


# --- 更新节点 ---

async def test_update_node_name(client, mock_storage, course_with_nodes):
    """更新节点名称"""
    cid = course_with_nodes["course_id"]
    nid = course_with_nodes["root_id"]
    resp = await client.put(f"/api/courses/{cid}/nodes/{nid}", json={
        "node_name": "重命名后的章节",
    })
    assert resp.status_code == 200
    course = mock_storage.load_course(cid)
    node = next(n for n in course["nodes"] if n["node_id"] == nid)
    assert node["node_name"] == "重命名后的章节"


async def test_update_node_read_status(client, mock_storage, course_with_nodes):
    """标记节点为已读"""
    cid = course_with_nodes["course_id"]
    nid = course_with_nodes["root_id"]
    resp = await client.put(f"/api/courses/{cid}/nodes/{nid}", json={
        "is_read": True,
    })
    assert resp.status_code == 200
    course = mock_storage.load_course(cid)
    node = next(n for n in course["nodes"] if n["node_id"] == nid)
    assert node["is_read"] is True


async def test_update_nonexistent_node(client, mock_storage, course_with_nodes):
    """更新不存在的节点应返回 404"""
    cid = course_with_nodes["course_id"]
    resp = await client.put(f"/api/courses/{cid}/nodes/nonexistent", json={
        "node_name": "test",
    })
    assert resp.status_code == 404


# --- 删除节点 ---

async def test_delete_leaf_node(client, mock_storage, course_with_nodes):
    """删除叶子节点"""
    cid = course_with_nodes["course_id"]
    child_id = course_with_nodes["child_id"]
    resp = await client.delete(f"/api/courses/{cid}/nodes/{child_id}")
    assert resp.status_code == 200
    course = mock_storage.load_course(cid)
    assert len(course["nodes"]) == 1  # 只剩根节点


async def test_delete_parent_cascades(client, mock_storage, course_with_nodes):
    """删除父节点应级联删除子节点"""
    cid = course_with_nodes["course_id"]
    root_id = course_with_nodes["root_id"]
    resp = await client.delete(f"/api/courses/{cid}/nodes/{root_id}")
    assert resp.status_code == 200
    course = mock_storage.load_course(cid)
    assert len(course["nodes"]) == 0  # 父子都被删除


async def test_delete_nonexistent_node(client, mock_storage, course_with_nodes):
    """删除不存在的节点应返回 404"""
    cid = course_with_nodes["course_id"]
    resp = await client.delete(f"/api/courses/{cid}/nodes/nonexistent")
    assert resp.status_code == 404
