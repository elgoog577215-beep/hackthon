"""
课程内容 <-> 知识图谱双向联动提案测试（Phase 3）。

覆盖：
  1. 接受一条引用了已知知识图谱概念的内容变更，会自动生成一条新的 pending
     CourseChangeSet（source="content_to_kb_link"），且不会绕过审核直接改写 KG 节点。
  2. 更新一个被课程内容引用的知识图谱节点，会自动生成一条新的 pending
     CourseChangeSet（source="kb_to_content_link"），且不会绕过审核直接改写课程内容。
  3. 联动提案生成后，在它自己被 accept 之前，目标（KG 节点 / 课程节点）必须保持不变。

所有 storage 磁盘 IO 均 mock，不发真实网络请求、不读写真实数据目录。
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

_backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _backend_dir)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adaptive_models import ChangeItem, CourseChangeSet


COURSE_ID = "course-1"
NODE_ID = "node-1"
KG_NODE_ID = "kg-1"


def _make_course_data() -> dict:
    return {
        "course_id": COURSE_ID,
        "course_name": "测试课程",
        "nodes": [
            {
                "node_id": NODE_ID,
                "parent_node_id": "root",
                "node_name": "第一节",
                "node_level": 1,
                "node_content": "这里介绍了牛顿第二定律的基本形式",
                "content_blocks": [],
            },
        ],
    }


def _make_kg_graph() -> dict:
    return {
        "nodes": [
            {
                "id": KG_NODE_ID,
                "label": "牛顿第二定律",
                "type": "concept",
                "description": "力等于质量乘以加速度",
                "chapter_id": None,
                "x": 0,
                "y": 0,
                "color": None,
                "created_by": "user",
                "created_at": 0,
                "updated_at": 0,
            }
        ],
        "edges": [],
        "updated_at": 0,
    }


def _make_content_change_set() -> CourseChangeSet:
    return CourseChangeSet(
        course_id=COURSE_ID,
        scope="block",
        scope_node_ids=[NODE_ID],
        change_items=[
            ChangeItem(
                target_node_id=NODE_ID,
                target_kind="course_node",
                operation="modify",
                before="这里介绍了牛顿第二定律的基本形式",
                after="牛顿第二定律指出：合外力等于质量与加速度的乘积（F=ma），补充了矢量方向说明。",
                reason="学生对方向性理解不足",
            ),
        ],
        source_hypothesis_id="hyp-1",
        status="pending",
    )


@pytest.fixture
def adaptive_client():
    """挂载 adaptive_changes 路由，mock storage（含知识图谱读写）。"""
    from routers import adaptive_changes as router_module
    from routers import knowledge_graph as kg_module

    mock_storage = MagicMock()
    mock_storage.load_course = MagicMock(return_value=_make_course_data())
    mock_storage.save_course = AsyncMock()
    mock_storage.load_change_sets = MagicMock(return_value=[])
    mock_storage.save_change_set = AsyncMock()
    mock_storage.save_evidence_item = AsyncMock()
    mock_storage.load_knowledge_graph = MagicMock(return_value=_make_kg_graph())
    mock_storage.save_knowledge_graph = MagicMock()

    app = FastAPI()
    app.include_router(router_module.router, prefix="/api")
    app.include_router(kg_module.router, prefix="/api")

    with patch.object(router_module, "storage", mock_storage), \
         patch.object(kg_module, "storage", mock_storage), \
         patch("dependencies.storage", mock_storage):
        client = TestClient(app)
        yield client, mock_storage, router_module


class TestContentToKbLinkage:
    def test_accept_content_change_generates_pending_kb_linkage(self, adaptive_client):
        client, mock_storage, _ = adaptive_client
        cs = _make_content_change_set()
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200

        # save_change_set 被调用两次：一次保存被 accept 的原变更集，一次保存新生成的联动提案。
        assert mock_storage.save_change_set.await_count == 2
        saved_payloads = [call.args[1] for call in mock_storage.save_change_set.await_args_list]
        linkage_payloads = [p for p in saved_payloads if p.get("source") == "content_to_kb_link"]
        assert len(linkage_payloads) == 1

        linkage = linkage_payloads[0]
        assert linkage["status"] == "pending"
        kg_items = linkage["change_items"]
        assert len(kg_items) == 1
        assert kg_items[0]["target_kind"] == "kg_node"
        assert kg_items[0]["target_node_id"] == KG_NODE_ID

    def test_kg_node_not_modified_before_linkage_is_accepted(self, adaptive_client):
        """审核门未被绕过：content_to_kb_link 提案生成后，KG 节点本身不应被直接写入。"""
        client, mock_storage, _ = adaptive_client
        cs = _make_content_change_set()
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200

        # save_knowledge_graph 不应在这一步被调用：联动提案只落一条 pending change_set，
        # 不直接改写 KG。
        mock_storage.save_knowledge_graph.assert_not_called()

    def test_accepting_generated_linkage_updates_kg_node(self, adaptive_client):
        """把生成的联动提案自己 accept 之后，才应真正写入 KG 节点（复用同一条 accept 路径）。"""
        client, mock_storage, _ = adaptive_client
        cs = _make_content_change_set()
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200

        linkage_payload = next(
            call.args[1] for call in mock_storage.save_change_set.await_args_list
            if call.args[1].get("source") == "content_to_kb_link"
        )
        linkage_id = linkage_payload["id"]

        # 现在让 load_change_sets 返回这条联动提案，再次调用 accept。
        mock_storage.load_change_sets = MagicMock(return_value=[linkage_payload])
        mock_storage.save_change_set.reset_mock()
        mock_storage.save_knowledge_graph.reset_mock()

        resp2 = client.post(f"/api/courses/{COURSE_ID}/change_sets/{linkage_id}/accept")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert KG_NODE_ID in data2["applied_kg_node_ids"]
        mock_storage.save_knowledge_graph.assert_called_once()


class TestKbToContentLinkage:
    def test_update_kg_node_generates_pending_content_linkage(self, adaptive_client):
        client, mock_storage, _ = adaptive_client

        resp = client.put(
            f"/api/courses/{COURSE_ID}/knowledge_graph/nodes/{KG_NODE_ID}",
            json={"description": "力等于质量乘以加速度，方向与合外力方向一致"},
        )
        assert resp.status_code == 200

        assert mock_storage.save_change_set.await_count == 1
        saved_course_id, saved_payload = mock_storage.save_change_set.await_args.args
        assert saved_course_id == COURSE_ID
        assert saved_payload["source"] == "kb_to_content_link"
        assert saved_payload["status"] == "pending"
        items = saved_payload["change_items"]
        assert len(items) == 1
        assert items[0]["target_kind"] == "course_node"
        assert items[0]["target_node_id"] == NODE_ID

    def test_course_node_not_modified_before_linkage_is_accepted(self, adaptive_client):
        client, mock_storage, _ = adaptive_client

        resp = client.put(
            f"/api/courses/{COURSE_ID}/knowledge_graph/nodes/{KG_NODE_ID}",
            json={"description": "力等于质量乘以加速度，方向与合外力方向一致"},
        )
        assert resp.status_code == 200

        # save_course 不应被调用：联动提案只落一条 pending change_set，不直接改写课程内容。
        mock_storage.save_course.assert_not_called()

    def test_accepting_generated_linkage_updates_course_node(self, adaptive_client):
        client, mock_storage, _ = adaptive_client

        resp = client.put(
            f"/api/courses/{COURSE_ID}/knowledge_graph/nodes/{KG_NODE_ID}",
            json={"description": "力等于质量乘以加速度，方向与合外力方向一致"},
        )
        assert resp.status_code == 200

        saved_course_id, linkage_payload = mock_storage.save_change_set.await_args.args
        linkage_id = linkage_payload["id"]

        mock_storage.load_change_sets = MagicMock(return_value=[linkage_payload])
        mock_storage.save_change_set.reset_mock()
        mock_storage.save_course.reset_mock()

        resp2 = client.post(f"/api/courses/{COURSE_ID}/change_sets/{linkage_id}/accept")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert NODE_ID in data2["applied_node_ids"]
        mock_storage.save_course.assert_called_once()
