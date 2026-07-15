/**
 * 结构化同源 + 个体化生长：AI 待确认变更相关类型定义
 * 与后端 backend/adaptive_models.py 的 Pydantic 模型字段对齐。
 *
 * 参见 docs/requirements/灵知AI课程智能体_开发规格文档.md
 * - Requirement: AI 变更 MUST 以待确认形式呈现，不得直接写入正式课程
 * - Requirement: 变更作用域 MUST 可控且显式
 */

/** 证据类型：支撑某个自适应假设的原始信号来源 */
export type EvidenceType =
  | 'dialogue_reask'
  | 'wrong_answer'
  | 'note'
  | 'comprehension_check'
  | 'explicit_feedback'

export interface EvidenceItem {
  id: string
  node_id: string
  evidence_type: EvidenceType
  /** 证据强度，范围建议 0-1 */
  strength: number
  content: string
  created_at: number
}

/** AI 对学生某节点掌握情况/需求的假设，由若干证据支撑 */
export interface AdaptationHypothesis {
  id: string
  node_id: string
  hypothesis: string
  supporting_evidence_ids: string[]
  /** 置信度，范围建议 0-1 */
  confidence: number
  created_at: number
}

/** 变更作用域：当前块、当前小节、多个小节、多个章节、全书 */
export type ChangeScope = 'block' | 'section' | 'sections' | 'chapters' | 'book'

/** 变更集状态 */
export type ChangeSetStatus = 'pending' | 'accepted' | 'rejected' | 'regenerated'

/** 单个节点上的变更操作类型 */
export type ChangeOperation = 'insert' | 'update' | 'delete' | 'reorder'

/**
 * 变更集中的单条变更项。
 * before/after 与 reason 必须保留（不能只存最终结果），
 * 供前端以高亮、差异标记方式呈现。
 */
export interface ChangeItem {
  target_node_id: string
  operation: ChangeOperation
  before: string | null
  after: string | null
  reason: string
  /** 变更来源：证据驱动（默认）、内容联动至知识库、知识库联动至内容 */
  source?: 'evidence_driven' | 'content_to_kb_link' | 'kb_to_content_link'
  /** 变更作用目标的类型：课程节点（默认）或知识图谱节点 */
  target_kind?: 'course_node' | 'kg_node'
}

/**
 * 一次 AI 生成的、待确认的课程变更集。
 * 学生可对集合内不同节点分别接受/拒绝，而非只能整体操作。
 */
export interface CourseChangeSet {
  id: string
  course_id: string
  scope: ChangeScope
  /** 该次变更实际影响的节点范围，需在 UI 中显式呈现 */
  scope_node_ids: string[]
  change_items: ChangeItem[]
  source_hypothesis_id: string | null
  status: ChangeSetStatus
  created_at: number
  resolved_at: number | null
}

/** 按 node_id 分组的待确认变更叠加层，供课程正文视图渲染角标/高亮使用 */
export interface PendingChangeOverlay {
  course_id: string
  /** key: node_id, value: 影响该节点的待确认变更集列表 */
  byNodeId: Record<string, CourseChangeSet[]>
}
