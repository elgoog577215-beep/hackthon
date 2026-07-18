// 与后端 backend/change_proposals.py + backend/routers/change_proposals.py 字段对齐的类型定义。
// 规格文档 §4 "AI 变更 MUST 以待确认形式呈现" / "变更作用域 MUST 可控且显式"。

import type { CourseDocumentEnvelope } from '../stores/types'

export type ChangeProposalScope = 'block' | 'section' | 'sections' | 'chapters' | 'book'

export type ChangeProposalSource = 'manual' | 'representation_semantic' | 'block_regeneration' | 'personalization' | 'evidence' | 'kb_link'

export type PersonalizationDirection = 'simplify' | 'expand' | 'custom'

export type ChangeProposalItemStatus = 'pending' | 'applied' | 'rejected'

export type ChangeProposalStatus = 'pending' | 'resolved'

// 并行后端 agent 可能为 item 追加的可选字段，缺省按 course_block 处理。
export type ChangeProposalItemTargetKind = 'course_block' | 'course_objective' | 'kg_node'

export interface ChangeProposalBlockPayload {
  markdown?: string
  summary?: string
  title?: string
  learning_objective?: string
  [key: string]: unknown
}

export interface ChangeProposalAfterPayload {
  payload: ChangeProposalBlockPayload
}

export type ChangeProposalContent =
  | string
  | ChangeProposalBlockPayload
  | ChangeProposalAfterPayload
  | null

export interface ChangeProposalItem {
  item_id: string
  block_id: string
  before: ChangeProposalContent
  // 后端契约：`after === null` 表示"内容尚未生成"（例如重新生成后暂时未能
  // 立即产出新内容），是一个明确的语义状态，不是异常；渲染层 MUST 不把它当
  // 空字符串直接插值展示，见 SideAIPanel.vue 的 isAwaitingGeneration()。
  after: ChangeProposalContent
  reason: string
  status: ChangeProposalItemStatus
  target_kind?: ChangeProposalItemTargetKind
  selected?: boolean
  expected_block_revision?: string
}

export interface ChangeProposal {
  change_kind?: 'course_authoring_change' | 'legacy_compatibility_change'
  write_target?: 'base_course' | 'knowledge_review'
  proposal_id: string
  course_id: string
  scope: ChangeProposalScope
  target_block_ids: string[]
  items: ChangeProposalItem[]
  source: ChangeProposalSource
  status: ChangeProposalStatus
  created_at: string
  generation_meta?: Record<string, unknown>
}

export interface CreatePersonalizationProposalInput {
  courseId: string
  blockId: string
  requestId: string
  expectedDocumentRevision: string
  expectedBlockRevision: string
  direction: PersonalizationDirection
  feedback: string
}

export interface ChangeProposalApplyReceipt {
  affected_block_ids?: string[]
  revision_change?: Record<string, unknown>
  [key: string]: unknown
}

export interface RepresentationSyncResult {
  status: string
  rebuilt?: Array<{
    representation_type?: string
    rebuilt_unit_ids?: string[]
    [key: string]: unknown
  }>
  quality?: Record<string, unknown>
  [key: string]: unknown
}

export interface ApplySelectedChangeProposalResult {
  proposal: ChangeProposal
  receipt: ChangeProposalApplyReceipt
  document: CourseDocumentEnvelope
  representation_sync: RepresentationSyncResult
}
