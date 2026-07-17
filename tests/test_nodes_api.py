"""
节点操作 API 测试
测试 /api/courses/{course_id}/nodes 相关端点。
"""

import sys
import os
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from httpx import AsyncClient, ASGITransport
from .conftest import MockStorage, make_course


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
    import learning_events

    originals = {
        'storage': storage_mod.storage,
        'deps': deps_mod.storage,
        'courses': courses_mod.storage,
        'nodes': nodes_mod.storage,
        'events': learning_events.storage,
    }

    storage_mod.storage = mock_storage
    deps_mod.storage = mock_storage
    courses_mod.storage = mock_storage
    nodes_mod.storage = mock_storage
    learning_events.storage = mock_storage

    from main import app
    yield app

    storage_mod.storage = originals['storage']
    deps_mod.storage = originals['deps']
    courses_mod.storage = originals['courses']
    nodes_mod.storage = originals['nodes']
    learning_events.storage = originals['events']


@pytest.fixture
async def client(patched_app):
    transport = ASGITransport(app=patched_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-User-Id": "test-learner"},
    ) as ac:
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


async def test_generate_subnodes_uses_unified_course_service(client, mock_storage, monkeypatch):
    """手动生成子节点应走 CourseService，返回同一套蓝图契约字段。"""
    import routers.nodes as nodes_mod

    cid = "course-subnodes"
    root_id = "L1-1"
    mock_storage.save_course(cid, {
        "course_id": cid,
        "course_name": "测试课程",
        "nodes": [{
            "node_id": root_id,
            "parent_node_id": "root",
            "node_name": "第1章 基础",
            "node_level": 1,
            "node_content": "",
            "node_type": "original",
        }],
    })
    generated = [{
        "node_id": "child-1",
        "parent_node_id": root_id,
        "node_name": "1.1 小节",
        "node_level": 2,
        "node_content": "",
        "node_type": "custom",
        "learning_objective": "能完成小节目标",
        "prerequisite_node_ids": [],
        "misconceptions": [],
        "assessment": ["能自测"],
        "scope_boundary": "只讲本节",
    }]
    fake_service = MagicMock()
    fake_service.generate_sub_nodes = AsyncMock(return_value=generated)
    monkeypatch.setattr(nodes_mod, "get_course_service", lambda: fake_service)

    resp = await client.post(f"/api/courses/{cid}/nodes/{root_id}/subnodes", json={
        "node_id": root_id,
        "node_name": "第1章 基础",
        "node_level": 1,
        "difficulty": "intermediate",
        "style": "academic",
    })

    assert resp.status_code == 200
    data = resp.json()
    fake_service.generate_sub_nodes.assert_awaited_once()
    assert data[0]["learning_objective"] == "能完成小节目标"
    assert mock_storage.load_course(cid)["nodes"][1]["scope_boundary"] == "只讲本节"


async def test_regenerate_content_block_updates_only_target(client, mock_storage, monkeypatch):
    """局部重写只替换目标 block，并重建兼容 Markdown。"""
    import routers.nodes as nodes_mod

    cid = "course-blocks"
    nid = "L2-1-1"
    blocks = [
        {
            "block_id": "L2-1-1-1-concept",
            "type": "concept",
            "title": "核心概念",
            "content": "旧概念内容。",
            "summary": "旧概念",
            "order": 0,
            "status": "final",
        },
        {
            "block_id": "L2-1-1-2-application",
            "type": "application",
            "title": "应用场景",
            "content": "旧应用内容。",
            "summary": "旧应用",
            "order": 1,
            "status": "final",
        },
    ]
    mock_storage.save_course(cid, {
        "course_id": cid,
        "course_name": "微积分",
        "nodes": [{
            "node_id": nid,
            "parent_node_id": "L1-1",
            "node_name": "1.1 极限",
            "node_level": 2,
            "node_content": "## 核心概念\n\n旧概念内容。\n\n## 应用场景\n\n旧应用内容。",
            "content_blocks": blocks,
            "node_type": "original",
        }],
    })

    updated = dict(blocks[1])
    updated["content"] = "新的应用内容，包含两个例子。"
    fake_service = MagicMock()
    fake_service.regenerate_content_block = AsyncMock(return_value=updated)
    monkeypatch.setattr(nodes_mod, "get_course_service", lambda: fake_service)

    resp = await client.post(
        f"/api/courses/{cid}/nodes/{nid}/blocks/{blocks[1]['block_id']}/regenerate",
        json={"requirement": "应用部分更详细", "action_type": "expand"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["block"]["content"] == "新的应用内容，包含两个例子。"
    saved_node = mock_storage.load_course(cid)["nodes"][0]
    assert saved_node["content_blocks"][0]["content"] == "旧概念内容。"
    assert saved_node["content_blocks"][1]["content"] == "新的应用内容，包含两个例子。"
    assert "## 应用场景" in saved_node["node_content"]

    event = mock_storage.data["learning_events.json"][-1]
    assert event["event_type"] == "content_block_regenerated"
    assert event["course_id"] == cid
    assert event["node_id"] == nid
    assert event["evidence"]["action_type"] == "expand"
    assert event["evidence"]["block_id"] == blocks[1]["block_id"]
    assert event["result"]["status"] == "regenerated"


async def test_redefine_node_uses_course_service(client, mock_storage, monkeypatch):
    """整节重写应走 CourseService，并直接保存 Markdown 正文。"""
    import routers.nodes as nodes_mod

    cid = "course-redefine"
    nid = "node-1"
    mock_storage.save_course(cid, {
        "course_id": cid,
        "course_name": "微积分",
        "nodes": [{
            "node_id": nid,
            "parent_node_id": "root",
            "node_name": "1.1 极限",
            "node_level": 2,
            "node_content": "旧内容",
            "content_blocks": [],
            "node_type": "original",
        }],
    })
    fake_service = MagicMock()
    fake_service.redefine_content = AsyncMock(return_value="## 核心概念\n\n新内容")
    monkeypatch.setattr(nodes_mod, "get_course_service", lambda: fake_service)

    resp = await client.post(f"/api/courses/{cid}/nodes/{nid}/redefine", json={
        "node_id": nid,
        "node_name": "1.1 极限",
        "original_content": "旧内容",
        "user_requirement": "讲清楚",
        "difficulty": "advanced",
        "style": "academic",
    })

    assert resp.status_code == 200
    fake_service.redefine_content.assert_awaited_once()
    saved_node = mock_storage.load_course(cid)["nodes"][0]
    assert saved_node["node_content"] == "## 核心概念\n\n新内容"
    assert saved_node["content_blocks"] == []
    assert saved_node["node_type"] == "custom"


async def test_selection_rewrite_returns_candidate_without_saving_node(client, mock_storage, monkeypatch):
    """Markdown 选区改写只返回候选文本，确认保存交给前端。"""
    import routers.nodes as nodes_mod

    cid = "course-selection"
    nid = "node-selection"
    original = "## 理论推导\n\n旧表达需要更清楚。\n\n## 应用\n\n保留应用。"
    mock_storage.save_course(cid, {
        "course_id": cid,
        "course_name": "微积分",
        "nodes": [{
            "node_id": nid,
            "parent_node_id": "root",
            "node_name": "1.1 极限",
            "node_level": 2,
            "node_content": original,
            "content_blocks": [],
            "node_type": "original",
        }],
    })
    fake_service = MagicMock()
    fake_service.rewrite_selection = AsyncMock(return_value={
        "replacement_text": "新的表达更清楚。",
        "selected_text": "旧表达需要更清楚。",
        "action_type": "rewrite",
        "heading_path": ["理论推导"],
        "context_summary": "旧表达需要更清楚。",
    })
    monkeypatch.setattr(nodes_mod, "get_course_service", lambda: fake_service)

    resp = await client.post(f"/api/courses/{cid}/nodes/{nid}/selection-rewrite", json={
        "selected_text": "旧表达需要更清楚。",
        "node_content": original,
        "heading_path": ["理论推导"],
        "before_context": "## 理论推导\n\n",
        "after_context": "\n\n## 应用",
        "user_requirement": "讲得自然一点",
        "action_type": "rewrite",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["replacement_text"] == "新的表达更清楚。"
    fake_service.rewrite_selection.assert_awaited_once()
    saved_node = mock_storage.load_course(cid)["nodes"][0]
    assert saved_node["node_content"] == original
    assert saved_node["content_blocks"] == []

    event = mock_storage.data["learning_events.json"][-1]
    assert event["event_type"] == "markdown_selection_rewrite_requested"
    assert event["course_id"] == cid
    assert event["node_id"] == nid
    assert event["evidence"]["action_type"] == "rewrite"
    assert event["evidence"]["heading_path"] == ["理论推导"]
    assert event["result"]["status"] == "candidate_generated"


async def test_extend_and_summarize_use_course_service(client, mock_storage, monkeypatch):
    """扩展和摘要也应使用统一课程服务，而不是旧课程 AI service。"""
    import routers.nodes as nodes_mod

    cid = "course-node-actions"
    nid = "node-1"
    mock_storage.save_course(cid, {
        "course_id": cid,
        "course_name": "线性代数",
        "nodes": [{
            "node_id": nid,
            "parent_node_id": "root",
            "node_name": "1.1 向量",
            "node_level": 2,
            "node_content": "向量内容",
            "node_type": "original",
        }],
    })
    fake_service = MagicMock()
    fake_service.extend_content = AsyncMock(return_value="延伸内容")
    fake_service.summarize_content = AsyncMock(return_value="摘要内容")
    monkeypatch.setattr(nodes_mod, "get_course_service", lambda: fake_service)

    extend_resp = await client.post(f"/api/courses/{cid}/nodes/{nid}/extend", json={
        "node_id": nid,
        "node_name": "1.1 向量",
        "current_content": "向量内容",
        "user_requirement": "加应用例子",
    })
    summary_resp = await client.post(f"/api/courses/{cid}/nodes/{nid}/summarize", json={
        "node_content": "向量内容",
        "node_name": "1.1 向量",
        "user_persona": "初学者",
    })

    assert extend_resp.status_code == 200
    assert extend_resp.json()["content"] == "延伸内容"
    fake_service.extend_content.assert_awaited_once()
    assert summary_resp.status_code == 200
    assert summary_resp.json()["summary"] == "摘要内容"
    fake_service.summarize_content.assert_awaited_once_with(
        "向量内容",
        node_name="1.1 向量",
        user_persona="初学者",
        course_id=cid,
        node_id=nid,
        user_id="test-learner",
    )


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


async def test_update_node_awaits_async_storage_save(client, mock_storage, course_with_nodes, monkeypatch):
    """真实文件存储的 save_course 是 async，节点更新必须真正 await 保存。"""
    cid = course_with_nodes["course_id"]
    nid = course_with_nodes["root_id"]
    sync_save = mock_storage.save_course

    async def async_save_course(course_id, data):
        sync_save(course_id, data)

    save_mock = AsyncMock(side_effect=async_save_course)
    monkeypatch.setattr(mock_storage, "save_course", save_mock)

    resp = await client.put(f"/api/courses/{cid}/nodes/{nid}", json={
        "is_read": True,
    })

    assert resp.status_code == 200
    save_mock.assert_awaited_once()
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
