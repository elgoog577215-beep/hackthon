"""
CourseChangeSet 状态机（Phase 1：数据底座）
==============================================

对应规格文档 §4 "AI 变更 MUST 以待确认形式呈现" Requirement 中
"学生处理待确认变更" Scenario：接受 / 拒绝 / 重新生成。

设计原则：
    - 纯函数/方法，不做真正的文件落盘（调用方负责把 accept 的结果写入 CourseDocument）。
    - 任何状态转换只能从 pending 出发；已 accepted/rejected 的 change_set
      不能被再次接受/拒绝（幂等保护，不允许静默覆盖）。
    - 拒绝理由 MUST 回流为新的 EvidenceItem。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from adaptive_models import ChangeItem, CourseChangeSet, EvidenceItem


class InvalidChangeSetTransition(Exception):
    """非法的 CourseChangeSet 状态转换。"""

    def __init__(self, change_set_id: str, current_status: str, attempted_action: str) -> None:
        self.change_set_id = change_set_id
        self.current_status = current_status
        self.attempted_action = attempted_action
        super().__init__(
            f"CourseChangeSet[{change_set_id}] 当前状态为 '{current_status}'，"
            f"不允许执行 '{attempted_action}'（只能从 'pending' 状态出发，且不允许重复接受/拒绝）。"
        )


def _require_pending(change_set: CourseChangeSet, action: str) -> None:
    if change_set.status != "pending":
        raise InvalidChangeSetTransition(change_set.id, change_set.status, action)


class AcceptedChangeResult:
    """accept_change_set 的返回结果：状态机产物 + 供调用方落盘的结构化内容。"""

    def __init__(self, change_set: CourseChangeSet, applied_items: List[ChangeItem]) -> None:
        self.change_set = change_set
        self.applied_items = applied_items

    def to_dict(self) -> dict:
        """便于调用方序列化/落盘的字典表示。"""
        return {
            "change_set_id": self.change_set.id,
            "course_id": self.change_set.course_id,
            "status": self.change_set.status,
            "applied_items": [item.model_dump() for item in self.applied_items],
        }


def accept_change_set(change_set: CourseChangeSet) -> AcceptedChangeResult:
    """接受一条待确认变更集。

    状态转为 accepted，返回需要写入 CourseDocument 的结构化结果（target_node_id +
    after 内容等），真正的文件落盘由调用方负责（course_service / storage 层）。

    Raises:
        InvalidChangeSetTransition: 当 change_set.status 不是 'pending' 时。
    """
    _require_pending(change_set, "accept")
    change_set.status = "accepted"
    change_set.resolved_at = datetime.now()
    return AcceptedChangeResult(change_set=change_set, applied_items=list(change_set.change_items))


def reject_change_set(
    change_set: CourseChangeSet, reason: Optional[str] = None
) -> Tuple[CourseChangeSet, EvidenceItem]:
    """拒绝一条待确认变更集。

    状态转为 rejected，并 MUST 生成一条新的 EvidenceItem，把拒绝理由回流为新证据
    （规格文档 §4 "学生处理待确认变更" Scenario）。即便学生未填写理由，也会生成
    一条 evidence_type="reject_reason" 的证据，content 中会注明"未填写理由"。

    Raises:
        InvalidChangeSetTransition: 当 change_set.status 不是 'pending' 时。
    """
    _require_pending(change_set, "reject")
    change_set.status = "rejected"
    change_set.resolved_at = datetime.now()

    reason_text = reason.strip() if reason and reason.strip() else "（学生未填写拒绝理由）"
    # 变更集可能影响多个节点，取第一个受影响节点作为证据的 node_id 锚点；
    # 若变更集为空（异常情况），退化为使用 scope_node_ids 或空字符串。
    anchor_node_id = (
        change_set.change_items[0].target_node_id
        if change_set.change_items
        else (change_set.scope_node_ids[0] if change_set.scope_node_ids else "")
    )

    evidence = EvidenceItem(
        node_id=anchor_node_id,
        evidence_type="reject_reason",
        strength=0.8,
        strength_label="high",
        content=f"学生拒绝了变更集 {change_set.id}，拒绝理由：{reason_text}",
        course_id=change_set.course_id,
        metadata={
            "rejected_change_set_id": change_set.id,
            "reason": reason_text,
        },
    )
    return change_set, evidence


def regenerate_change_set(
    change_set: CourseChangeSet, extra_instruction: Optional[str] = None
) -> CourseChangeSet:
    """将 change_set 标记为 regenerated，并返回一个新的 pending 版本骨架。

    真正基于原证据 + 用户补充意见重新调用生成服务产出新内容的逻辑，
    留待接入生成服务的阶段实现：
        TODO(生成侧): 接入 AI 生成服务，依据 change_set.source_hypothesis_id
        对应的 AdaptationHypothesis 与 extra_instruction 重新生成 change_items，
        并确保不得复用完全相同的输出（规格文档 §4 MUST）。

    Raises:
        InvalidChangeSetTransition: 当 change_set.status 不是 'pending' 时。
    """
    _require_pending(change_set, "regenerate")
    change_set.status = "regenerated"
    change_set.resolved_at = datetime.now()

    instruction_suffix = f"（重新生成，补充意见：{extra_instruction}）" if extra_instruction else "（重新生成）"
    skeleton_items = [
        ChangeItem(
            target_node_id=item.target_node_id,
            operation=item.operation,
            before=item.before,
            after=None,  # TODO(生成侧): 接入生成服务后填充新内容，不得复用原 after
            reason=f"{item.reason}{instruction_suffix}",
        )
        for item in change_set.change_items
    ]

    new_change_set = CourseChangeSet(
        course_id=change_set.course_id,
        scope=change_set.scope,
        scope_node_ids=list(change_set.scope_node_ids),
        change_items=skeleton_items,
        source_hypothesis_id=change_set.source_hypothesis_id,
        status="pending",
    )
    return new_change_set
