"""
routers/adaptive_changes.py 路由测试（Phase 2：变更侧 API）。

覆盖：
  - GET pending_changes 只返回 status == pending 的变更集
  - accept：状态转 accepted，接受内容写入课程节点 content_blocks/node_content
  - reject：状态转 rejected，且回流新的 EvidenceItem 被持久化
  - regenerate：原 change_set 转 regenerated，调用 generate_change_set（mock）产出新 change_set
  - 非法状态转换（重复 accept/reject）返回 409

所有 LLM 调用与 storage 磁盘 IO 均 mock，不发真实网络请求、不读写真实数据目录。
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
                "node_content": "原有内容",
                "content_blocks": [],
            },
            {
                "node_id": "node-2",
                "parent_node_id": "root",
                "node_name": "第二节",
                "node_level": 1,
                "node_content": "",
                "content_blocks": [],
            },
        ],
    }


def _make_change_set(status: str = "pending") -> CourseChangeSet:
    return CourseChangeSet(
        course_id=COURSE_ID,
        scope="block",
        scope_node_ids=[NODE_ID],
        change_items=[
            ChangeItem(
                target_node_id=NODE_ID,
                operation="modify",
                before="原有内容",
                after="补充说明后的内容",
                reason="学生连续追问，推导颗粒度偏粗",
            ),
        ],
        source_hypothesis_id="hyp-1",
        status=status,
    )


@pytest.fixture
def app_client():
    """构建一个只挂载 adaptive_changes 路由的最小 FastAPI app，并 mock storage。"""
    from routers import adaptive_changes as router_module

    mock_storage = MagicMock()
    mock_storage.load_course = MagicMock(return_value=_make_course_data())
    mock_storage.save_course = AsyncMock()
    mock_storage.load_change_sets = MagicMock(return_value=[])
    mock_storage.save_change_set = AsyncMock()
    mock_storage.save_evidence_item = AsyncMock()

    app = FastAPI()
    app.include_router(router_module.router, prefix="/api")

    with patch.object(router_module, "storage", mock_storage), \
         patch("dependencies.storage", mock_storage):
        client = TestClient(app)
        yield client, mock_storage, router_module


class TestGetPendingChanges:
    def test_returns_only_pending_change_sets(self, app_client):
        client, mock_storage, _ = app_client
        pending = _make_change_set(status="pending")
        accepted = _make_change_set(status="accepted")
        mock_storage.load_change_sets = MagicMock(
            return_value=[pending.model_dump(mode="json"), accepted.model_dump(mode="json")]
        )

        resp = client.get(f"/api/courses/{COURSE_ID}/pending_changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_id"] == COURSE_ID
        assert len(data["change_sets"]) == 1
        assert data["change_sets"][0]["id"] == pending.id

    def test_course_not_found_returns_404(self, app_client):
        client, mock_storage, _ = app_client
        mock_storage.load_course = MagicMock(return_value={})
        resp = client.get(f"/api/courses/missing/pending_changes")
        assert resp.status_code == 404


class TestAcceptChangeSet:
    def test_accept_writes_content_and_updates_status(self, app_client):
        client, mock_storage, _ = app_client
        cs = _make_change_set(status="pending")
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert NODE_ID in data["applied_node_ids"]

        # save_course 被调用，且写入了包含 after 内容的新正文
        assert mock_storage.save_course.await_count == 1
        saved_course_id, saved_data = mock_storage.save_course.await_args.args
        node = next(n for n in saved_data["nodes"] if n["node_id"] == NODE_ID)
        assert "补充说明后的内容" in node["node_content"]

        # change_set 状态也被持久化
        assert mock_storage.save_change_set.await_count == 1

    def test_accept_already_accepted_returns_409(self, app_client):
        client, mock_storage, _ = app_client
        cs = _make_change_set(status="accepted")
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 409

    def test_accept_missing_change_set_returns_404(self, app_client):
        client, mock_storage, _ = app_client
        mock_storage.load_change_sets = MagicMock(return_value=[])
        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/missing-id/accept")
        assert resp.status_code == 404

    def test_accept_with_node_ids_filter_only_applies_selected_nodes(self, app_client):
        client, mock_storage, _ = app_client
        cs = CourseChangeSet(
            course_id=COURSE_ID,
            scope="sections",
            scope_node_ids=[NODE_ID, "node-2"],
            change_items=[
                ChangeItem(target_node_id=NODE_ID, operation="modify", after="内容A", reason="r1"),
                ChangeItem(target_node_id="node-2", operation="add", after="内容B", reason="r2"),
            ],
            status="pending",
        )
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(
            f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept",
            json={"node_ids": [NODE_ID]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied_node_ids"] == [NODE_ID]


class TestAcceptChangeSetDelete:
    def test_delete_removes_node_from_tree(self, app_client):
        client, mock_storage, _ = app_client
        cs = CourseChangeSet(
            course_id=COURSE_ID,
            scope="block",
            scope_node_ids=["node-2"],
            change_items=[
                ChangeItem(target_node_id="node-2", operation="delete", reason="内容重复，删除该节点"),
            ],
            status="pending",
        )
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["applied_node_ids"] == ["node-2"]

        assert mock_storage.save_course.await_count == 1
        _, saved_data = mock_storage.save_course.await_args.args
        remaining_ids = [n["node_id"] for n in saved_data["nodes"]]
        assert "node-2" not in remaining_ids
        assert NODE_ID in remaining_ids  # 未被删除的兄弟节点保留

    def test_delete_cascades_to_child_nodes(self, app_client):
        client, mock_storage, _ = app_client
        course_data = _make_course_data()
        course_data["nodes"].append({
            "node_id": "node-2-child",
            "parent_node_id": "node-2",
            "node_name": "第二节子节点",
            "node_level": 2,
            "node_content": "",
            "content_blocks": [],
        })
        mock_storage.load_course = MagicMock(return_value=course_data)

        cs = CourseChangeSet(
            course_id=COURSE_ID,
            scope="block",
            scope_node_ids=["node-2"],
            change_items=[
                ChangeItem(target_node_id="node-2", operation="delete", reason="删除整个子树"),
            ],
            status="pending",
        )
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200

        _, saved_data = mock_storage.save_course.await_args.args
        remaining_ids = [n["node_id"] for n in saved_data["nodes"]]
        assert "node-2" not in remaining_ids
        assert "node-2-child" not in remaining_ids  # 子节点级联删除，不留悬空引用

    def test_delete_missing_target_skips_without_error(self, app_client):
        client, mock_storage, _ = app_client
        cs = CourseChangeSet(
            course_id=COURSE_ID,
            scope="block",
            scope_node_ids=["missing-node"],
            change_items=[
                ChangeItem(target_node_id="missing-node", operation="delete", reason="目标已不存在"),
            ],
            status="pending",
        )
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied_node_ids"] == []
        assert mock_storage.save_course.await_count == 0


class TestAcceptChangeSetMove:
    def test_move_changes_parent_and_order(self, app_client):
        client, mock_storage, _ = app_client
        cs = CourseChangeSet(
            course_id=COURSE_ID,
            scope="block",
            scope_node_ids=["node-2"],
            change_items=[
                ChangeItem(
                    target_node_id="node-2",
                    operation="move",
                    reason="应该作为第一节的子节点，而不是并列章节",
                    move_target={"new_parent_node_id": NODE_ID, "new_order": 0},
                ),
            ],
            status="pending",
        )
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied_node_ids"] == ["node-2"]

        assert mock_storage.save_course.await_count == 1
        _, saved_data = mock_storage.save_course.await_args.args
        moved = next(n for n in saved_data["nodes"] if n["node_id"] == "node-2")
        assert moved["parent_node_id"] == NODE_ID
        assert moved["node_level"] == 2  # 父节点 node_level=1，子节点应为 2

    def test_move_missing_new_parent_skips_without_error(self, app_client):
        client, mock_storage, _ = app_client
        cs = CourseChangeSet(
            course_id=COURSE_ID,
            scope="block",
            scope_node_ids=["node-2"],
            change_items=[
                ChangeItem(
                    target_node_id="node-2",
                    operation="move",
                    reason="目标父节点不存在",
                    move_target={"new_parent_node_id": "no-such-node"},
                ),
            ],
            status="pending",
        )
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied_node_ids"] == []
        assert mock_storage.save_course.await_count == 0

    def test_move_into_own_descendant_rejected(self, app_client):
        client, mock_storage, _ = app_client
        course_data = _make_course_data()
        course_data["nodes"].append({
            "node_id": "node-1-child",
            "parent_node_id": NODE_ID,
            "node_name": "第一节子节点",
            "node_level": 2,
            "node_content": "",
            "content_blocks": [],
        })
        mock_storage.load_course = MagicMock(return_value=course_data)

        cs = CourseChangeSet(
            course_id=COURSE_ID,
            scope="block",
            scope_node_ids=[NODE_ID],
            change_items=[
                ChangeItem(
                    target_node_id=NODE_ID,
                    operation="move",
                    reason="试图移动到自己的子节点下面，会成环",
                    move_target={"new_parent_node_id": "node-1-child"},
                ),
            ],
            status="pending",
        )
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied_node_ids"] == []
        assert mock_storage.save_course.await_count == 0


class TestRejectChangeSet:
    def test_reject_persists_new_evidence(self, app_client):
        client, mock_storage, _ = app_client
        cs = _make_change_set(status="pending")
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        resp = client.post(
            f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/reject",
            json={"reason": "这段我已经理解了"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"

        assert mock_storage.save_evidence_item.await_count == 1
        saved_course_id, saved_evidence = mock_storage.save_evidence_item.await_args.args
        assert saved_course_id == COURSE_ID
        assert saved_evidence["evidence_type"] == "reject_reason"
        assert "这段我已经理解了" in saved_evidence["content"]

    def test_reject_already_rejected_returns_409(self, app_client):
        client, mock_storage, _ = app_client
        cs = _make_change_set(status="rejected")
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])
        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/reject")
        assert resp.status_code == 409


class TestRegenerateChangeSet:
    def test_regenerate_marks_original_and_returns_new_change_set(self, app_client):
        client, mock_storage, router_module = app_client
        cs = _make_change_set(status="pending")
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        new_cs = CourseChangeSet(
            course_id=COURSE_ID,
            scope="block",
            scope_node_ids=[NODE_ID],
            change_items=[
                ChangeItem(target_node_id=NODE_ID, operation="modify", after="全新的补充内容", reason="重新生成"),
            ],
            status="pending",
            generation_meta={"model_id": "mock-model", "prompt_template": "adaptation_service.change_set.v1"},
        )

        with patch.object(router_module, "generate_change_set", new=AsyncMock(return_value=new_cs)):
            resp = client.post(
                f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/regenerate",
                json={"extra_instruction": "请举一个具体数值例子"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] != cs.id
        assert data["change_items"][0]["after"] == "全新的补充内容"

        # 原 change_set 应该被保存为 regenerated 状态，新 change_set 也被保存
        assert mock_storage.save_change_set.await_count == 2
        first_call_args = mock_storage.save_change_set.await_args_list[0].args
        assert first_call_args[1]["status"] == "regenerated"

    def test_regenerate_generation_failure_returns_502(self, app_client):
        client, mock_storage, router_module = app_client
        cs = _make_change_set(status="pending")
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])

        with patch.object(router_module, "generate_change_set", new=AsyncMock(return_value=None)):
            resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/regenerate")

        assert resp.status_code == 502

    def test_regenerate_already_regenerated_returns_409(self, app_client):
        client, mock_storage, router_module = app_client
        cs = _make_change_set(status="regenerated")
        mock_storage.load_change_sets = MagicMock(return_value=[cs.model_dump(mode="json")])
        resp = client.post(f"/api/courses/{COURSE_ID}/change_sets/{cs.id}/regenerate")
        assert resp.status_code == 409
