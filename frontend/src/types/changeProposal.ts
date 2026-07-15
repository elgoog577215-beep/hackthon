// 与后端 backend/change_proposals.py + backend/routers/change_proposals.py 字段对齐的类型定义。
// 规格文档 §4 "AI 变更 MUST 以待确认形式呈现" / "变更作用域 MUST 可控且显式"。

export type ChangeProposalScope = 'block' | 'section' | 'sections' | 'chapters' | 'book'

export type ChangeProposalSource = 'manual' | 'evidence' | 'kb_link'

export type ChangeProposalItemStatus = 'pending' | 'applied' | 'rejected'

export type ChangeProposalStatus = 'pending' | 'resolved'

// 并行后端 agent 可能为 item 追加的可选字段，缺省按 course_block 处理。
export type ChangeProposalItemTargetKind = 'course_block' | 'kg_node'

export interface ChangeProposalItem {
  item_id: string
  block_id: string
  before: string
  after: string
  reason: string
  status: ChangeProposalItemStatus
  target_kind?: ChangeProposalItemTargetKind
}

export interface ChangeProposal {
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
