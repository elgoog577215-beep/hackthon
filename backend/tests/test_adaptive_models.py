"""
adaptive_models / change_set_state 单元测试（Phase 1：数据底座）。

覆盖：
  - EvidenceItem / CourseChangeSet 的序列化正确性
  - accept / reject / regenerate 状态机的正常路径
  - 非法状态转换（非 pending 出发、重复接受/拒绝）报错路径
  - reject 时确实生成新 EvidenceItem 且 content 包含拒绝理由
"""

import os
import sys

# 将 backend 目录加入 sys.path，与仓库内其他测试文件保持一致的写法
_backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _backend_dir)

import pytest

from adaptive_models import (
    ChangeItem,
    CourseChangeSet,
    EvidenceItem,
    PendingChangeOverlay,
)
from change_set_state import (
    InvalidChangeSetTransition,
    accept_change_set,
    regenerate_change_set,
    reject_change_set,
)


# ---------------------------------------------------------------------------
# 构造辅助
# ---------------------------------------------------------------------------

def _make_change_set(status: str = "pending") -> CourseChangeSet:
    return CourseChangeSet(
        course_id="course-1",
        scope="section",
        scope_node_ids=["node-2", "node-3"],
        change_items=[
            ChangeItem(
                target_node_id="node-2",
                operation="modify",
                before="原内容",
                after="补充说明后的内容",
                reason="学生连续追问，推导颗粒度偏粗",
            ),
            ChangeItem(
                target_node_id="node-3",
                operation="add",
                before=None,
                after="预防性补充内容",
                reason="预防性建议",
            ),
        ],
        source_hypothesis_id="hyp-1",
        status=status,
    )


# ---------------------------------------------------------------------------
# 序列化测试
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_evidence_item_round_trip(self):
        item = EvidenceItem(
            node_id="node-1",
            evidence_type="dialogue_reask",
            strength=0.7,
            strength_label="high",
            content="学生连续两次要求更详细解释",
            course_id="course-1",
        )
        dumped = item.model_dump()
        restored = EvidenceItem.model_validate(dumped)
        assert restored.id == item.id
        assert restored.node_id == "node-1"
        assert restored.evidence_type == "dialogue_reask"
        assert restored.content == "学生连续两次要求更详细解释"

    def test_evidence_item_json_round_trip(self):
        item = EvidenceItem(
            node_id="node-1", evidence_type="wrong_answer", content="错题上下文摘要"
        )
        json_str = item.model_dump_json()
        restored = EvidenceItem.model_validate_json(json_str)
        assert restored == item

    def test_course_change_set_round_trip(self):
        cs = _make_change_set()
        dumped = cs.model_dump()
        restored = CourseChangeSet.model_validate(dumped)
        assert restored.id == cs.id
        assert restored.scope == "section"
        assert restored.scope_node_ids == ["node-2", "node-3"]
        assert restored.source_hypothesis_id == "hyp-1"
        assert len(restored.change_items) == 2
        assert restored.status == "pending"

    def test_pending_change_overlay_groups_by_node(self):
        cs = _make_change_set()
        overlay = PendingChangeOverlay.from_change_sets("course-1", [cs])
        grouped = overlay.by_node_id
        assert set(grouped.keys()) == {"node-2", "node-3"}
        assert grouped["node-2"][0].reason == "学生连续追问，推导颗粒度偏粗"

    def test_pending_change_overlay_filters_non_pending(self):
        pending_cs = _make_change_set(status="pending")
        accepted_cs = _make_change_set(status="accepted")
        overlay = PendingChangeOverlay.from_change_sets("course-1", [pending_cs, accepted_cs])
        assert len(overlay.change_sets) == 1
        assert overlay.change_sets[0].id == pending_cs.id


# ---------------------------------------------------------------------------
# 状态机：正常路径
# ---------------------------------------------------------------------------

class TestStateMachineHappyPath:
    def test_accept_change_set(self):
        cs = _make_change_set()
        result = accept_change_set(cs)
        assert cs.status == "accepted"
        assert cs.resolved_at is not None
        assert len(result.applied_items) == 2
        as_dict = result.to_dict()
        assert as_dict["status"] == "accepted"
        assert as_dict["change_set_id"] == cs.id

    def test_reject_change_set_returns_new_evidence(self):
        cs = _make_change_set()
        updated_cs, evidence = reject_change_set(cs, reason="这段解释我已经理解，不需要补充")
        assert updated_cs.status == "rejected"
        assert updated_cs.resolved_at is not None
        assert isinstance(evidence, EvidenceItem)
        assert evidence.evidence_type == "reject_reason"
        assert "这段解释我已经理解，不需要补充" in evidence.content
        assert evidence.metadata["rejected_change_set_id"] == cs.id
        assert evidence.course_id == cs.course_id

    def test_reject_change_set_without_reason_still_generates_evidence(self):
        cs = _make_change_set()
        _, evidence = reject_change_set(cs, reason=None)
        assert evidence.evidence_type == "reject_reason"
        assert "未填写拒绝理由" in evidence.content

    def test_regenerate_change_set_produces_new_pending_skeleton(self):
        cs = _make_change_set()
        new_cs = regenerate_change_set(cs, extra_instruction="请举一个具体数值例子")
        assert cs.status == "regenerated"
        assert cs.resolved_at is not None
        assert new_cs.id != cs.id
        assert new_cs.status == "pending"
        assert new_cs.source_hypothesis_id == cs.source_hypothesis_id
        assert new_cs.scope_node_ids == cs.scope_node_ids
        # 不得复用完全相同的输出：after 内容应被清空待重新生成
        for item in new_cs.change_items:
            assert item.after is None
        assert "请举一个具体数值例子" in new_cs.change_items[0].reason


# ---------------------------------------------------------------------------
# 状态机：非法转换路径
# ---------------------------------------------------------------------------

class TestStateMachineInvalidTransitions:
    def test_accept_already_accepted_raises(self):
        cs = _make_change_set(status="accepted")
        with pytest.raises(InvalidChangeSetTransition):
            accept_change_set(cs)

    def test_accept_already_rejected_raises(self):
        cs = _make_change_set(status="rejected")
        with pytest.raises(InvalidChangeSetTransition):
            accept_change_set(cs)

    def test_reject_already_accepted_raises(self):
        cs = _make_change_set(status="accepted")
        with pytest.raises(InvalidChangeSetTransition):
            reject_change_set(cs, reason="改变主意了")

    def test_reject_already_rejected_raises_idempotent_protection(self):
        cs = _make_change_set(status="rejected")
        with pytest.raises(InvalidChangeSetTransition):
            reject_change_set(cs, reason="再次拒绝")

    def test_regenerate_already_regenerated_raises(self):
        cs = _make_change_set(status="regenerated")
        with pytest.raises(InvalidChangeSetTransition):
            regenerate_change_set(cs)

    def test_regenerate_accepted_raises(self):
        cs = _make_change_set(status="accepted")
        with pytest.raises(InvalidChangeSetTransition):
            regenerate_change_set(cs)

    def test_invalid_transition_error_message_mentions_status(self):
        cs = _make_change_set(status="accepted")
        with pytest.raises(InvalidChangeSetTransition) as exc_info:
            reject_change_set(cs, reason="x")
        assert "accepted" in str(exc_info.value)
        assert cs.id in str(exc_info.value)
