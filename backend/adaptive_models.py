"""
个体化生长数据模型（Phase 1：数据底座）
==========================================

对应 docs/requirements/灵知AI课程智能体_开发规格文档.md §3 数据模型 与 §4 Requirements。

实现范围：
    EvidenceItem → AdaptationHypothesis → CourseChangeSet → PendingChangeOverlay

不包含：AI 证据聚合/假设判定逻辑、真正的 LLM 重新生成逻辑、前端展示。
这些留给后续阶段（§7 建议实施顺序 第 2/3/4 步）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def _new_id() -> str:
    """生成新的唯一 ID。"""
    return str(uuid.uuid4())


# =============================================================================
# EvidenceItem — 原子学习证据
# =============================================================================

EvidenceType = Literal[
    "dialogue_reask",       # 对话中要求更详细解释/重新解释
    "wrong_answer",         # 错题
    "note",                 # 课程内笔记
    "comprehension_check",  # 理解检查（如小测）结果
    "explicit_feedback",    # 显式反馈（如"这段完全看不懂"）
    "reject_reason",        # 学生拒绝某条变更时回流的理由（§4 待确认变更 Requirement 的 MUST）
    "skip_behavior",        # 快速跳过/停留过短等弱证据
    "other",
]

EvidenceStrength = Literal["low", "medium", "high"]


class EvidenceItem(BaseModel):
    """原子学习证据。

    对应规格文档 §3：EvidenceItem → AdaptationHypothesis → CourseChangeSet 判定链路的起点。
    """

    id: str = Field(default_factory=_new_id)
    node_id: str = Field(..., description="关联的 AdaptiveBlock / ContentBlock / Node 的 id")
    evidence_type: EvidenceType
    # strength 同时保留数值强度（0-1，供综合判断算法使用）与离散标签（供人读/前端展示）
    strength: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="证据强度 0-1，供综合判断算法使用（结合一致性/覆盖范围/时效性/可逆性/误判成本）",
    )
    strength_label: EvidenceStrength = Field(
        default="medium", description="证据强度的离散标签，供前端展示"
    )
    content: str = Field(..., description="原始证据文本或上下文摘要")
    course_id: Optional[str] = Field(default=None, description="所属课程 id，便于按课程持久化/查询")
    metadata: Dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# AdaptationHypothesis — 适配假设
# =============================================================================

class AdaptationHypothesis(BaseModel):
    """AI 基于一组 EvidenceItem 判断出的学生理解状态假设。"""

    id: str = Field(default_factory=_new_id)
    node_id: str = Field(..., description="该假设所针对的节点 id")
    hypothesis: str = Field(..., description="AI 判断的理解状态描述，如'当前推导颗粒度偏粗'")
    supporting_evidence_ids: List[str] = Field(
        default_factory=list, description="支撑该假设的 EvidenceItem.id 列表"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    course_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# CourseChangeSet — 课程变更集
# =============================================================================

ChangeSetScope = Literal["block", "section", "sections", "chapters", "book"]

ChangeOperation = Literal["add", "modify", "replace", "delete", "move", "difficulty_adjust"]

ChangeSetStatus = Literal["pending", "accepted", "rejected", "regenerated"]

# 变更集来源（Phase 3 新增，规格文档"课程与知识库 MUST 支持双向联动提案" Requirement）：
#   - evidence_driven：原有的、基于 EvidenceItem/AdaptationHypothesis 生成的变更集（默认值，保证向后兼容）
#   - content_to_kb_link：课程内容变更被接受后，自动生成的、建议同步更新知识图谱节点的联动提案
#   - kb_to_content_link：知识图谱节点被更新后，自动生成的、建议同步更新引用它的课程内容的联动提案
ChangeSetSource = Literal["evidence_driven", "content_to_kb_link", "kb_to_content_link"]

# 变更条目的目标类型（Phase 3 新增）：course_node 为课程正文节点（原有唯一取值，默认值保证向后兼容），
# kg_node 为知识图谱节点（仅联动提案会用到）。
ChangeItemTargetKind = Literal["course_node", "kg_node"]


class ChangeItem(BaseModel):
    """CourseChangeSet 内针对单个节点的变更条目。"""

    id: str = Field(default_factory=_new_id)
    target_node_id: str
    target_kind: ChangeItemTargetKind = Field(
        default="course_node",
        description=(
            "变更条目的目标类型：'course_node'（默认，课程正文节点，target_node_id 对应课程树 node_id）"
            "或 'kg_node'（知识图谱节点，target_node_id 对应知识图谱 node.id）。"
            "仅 source='content_to_kb_link' 的变更集会产出 'kg_node' 条目。"
        ),
    )
    operation: ChangeOperation
    before: Optional[str] = Field(default=None, description="变更前内容摘要")
    after: Optional[str] = Field(default=None, description="变更后内容摘要")
    reason: str = Field(default="", description="该条变更的理由")
    move_target: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "仅 operation == 'move' 时使用：约定结构 "
            "{'new_parent_node_id': str, 'new_order': Optional[int]}。"
            "new_parent_node_id 为节点移动到的新父节点 id（'root' 表示顶层）；"
            "new_order 为在新父节点的子节点列表中的目标位置（从 0 开始，缺省表示追加到末尾）。"
            "之所以单独加字段而不复用 after（after 语义是'变更后内容摘要'的字符串），"
            "是因为 after 是强类型 str，不适合塞任意结构化数据（见 routers/adaptive_changes.py accept 路由）。"
        ),
    )


class CourseChangeSet(BaseModel):
    """课程变更集：AI 基于证据/假设生成的一组待确认变更。

    MUST（规格文档 §3、§4）：
    - 必须能表达作用域（scope + scope_node_ids）
    - 必须能表达来源证据引用（source_hypothesis_id）
    - 状态转换只能从 pending 出发，不允许静默覆盖 accepted/rejected 状态（见 change_set_state.py）
    """

    id: str = Field(default_factory=_new_id)
    course_id: str
    scope: ChangeSetScope
    scope_node_ids: List[str] = Field(
        default_factory=list, description="该次变更实际影响的所有节点 id，MUST 显式列出"
    )
    change_items: List[ChangeItem] = Field(default_factory=list)
    source_hypothesis_id: Optional[str] = Field(
        default=None, description="生成该变更集所依据的 AdaptationHypothesis.id"
    )
    source: ChangeSetSource = Field(
        default="evidence_driven",
        description=(
            "变更集来源（Phase 3 新增）。默认 'evidence_driven' 保持向后兼容；"
            "'content_to_kb_link' / 'kb_to_content_link' 用于课程内容与知识图谱之间的双向联动提案。"
        ),
    )
    status: ChangeSetStatus = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = Field(
        default=None, description="状态由 pending 转为 accepted/rejected/regenerated 的时间"
    )
    generation_meta: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "生成可追溯性记录（Phase 2 新增，规格文档 §4 '生成记录可追溯' Scenario）："
            "MUST 包含 model_id / prompt_template / params 等字段，供事后复盘。"
        ),
    )


# =============================================================================
# PendingChangeOverlay — 待确认变更层
# =============================================================================

class PendingChangeOverlay(BaseModel):
    """某个 course_id 下所有 status == pending 的 CourseChangeSet 的聚合视图。

    提供按 node_id 分组的便于前端渲染的结构（高亮/差异/AI 标签，见规格文档 §4）。
    """

    course_id: str
    change_sets: List[CourseChangeSet] = Field(default_factory=list)

    @property
    def by_node_id(self) -> Dict[str, List[ChangeItem]]:
        """按受影响节点 id 分组的变更条目视图，便于前端在对应节点旁高亮展示。"""
        grouped: Dict[str, List[ChangeItem]] = {}
        for cs in self.change_sets:
            for item in cs.change_items:
                grouped.setdefault(item.target_node_id, []).append(item)
        return grouped

    @classmethod
    def from_change_sets(cls, course_id: str, change_sets: List[CourseChangeSet]) -> "PendingChangeOverlay":
        """从一组 CourseChangeSet 构建 Overlay，自动过滤出 status == pending 的条目。"""
        pending = [cs for cs in change_sets if cs.status == "pending"]
        return cls(course_id=course_id, change_sets=pending)
