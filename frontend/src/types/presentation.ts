export type PresentationTemplateId = 'lingzhi-classroom' | 'lingzhi-engineering' | 'lingzhi-academic'
export type PresentationLayoutId = 'L01' | 'L02' | 'L03' | 'L04' | 'L05' | 'L06' | 'L07' | 'L08' | 'L09' | 'L10'
export type PresentationStatus = 'draft' | 'generating' | 'editing' | 'quality_blocked' | 'ready' | 'exporting' | 'exported' | 'failed'
export type PresentationStudioPhase = 'booting' | 'configuring' | 'generating' | 'editing' | 'finalizing' | 'quality_blocked' | 'export_ready'

export interface PresentationScope {
  type: 'chapter' | 'course'
  section_ids: string[]
}

export interface PresentationSourceRef {
  course_id: string
  source_format: 'canonical' | 'legacy_snapshot'
  version_id: string
  document_revision: string
  blueprint_revision_id: string
  asset_bundle_revision_id: string
  source_snapshot_id: string
  source_snapshot_sha256: string
}

export interface PresentationSlideBlock {
  block_id: string
  type: 'text' | 'bullets' | 'code' | 'quote' | 'comparison' | 'exercise' | 'callout'
  title: string
  content: string
  items: string[]
  metadata: Record<string, unknown>
}

export interface PresentationQualityIssue {
  code: string
  severity: 'info' | 'warning' | 'blocking'
  message: string
  target_type: 'deck' | 'slide' | 'source' | 'artifact'
  target_id: string
  fix_action: string
}

export interface PresentationSlide {
  slide_id: string
  position: number
  layout_id: PresentationLayoutId
  status: 'planned' | 'generating' | 'ready' | 'failed'
  title: string
  subtitle: string
  key_message: string
  blocks: PresentationSlideBlock[]
  speaker_notes: string
  source_refs: {
    section_ids: string[]
    block_ids: string[]
    block_revision_ids: string[]
    objective_ids: string[]
    asset_ids: string[]
  }
  quality: { issues: PresentationQualityIssue[]; capacity: Record<string, number | boolean> }
}

export interface PresentationRevision {
  revision_id: string
  parent_revision_id: string | null
  deck_id: string
  reason: 'initial_generation' | 'chat_patch' | 'reorder' | 'restore' | 'quality_repair'
  created_at: string
  created_by: string
  source_snapshot_id: string
  slide_order: string[]
  slides: PresentationSlide[]
}

export interface PresentationDeck {
  schema_version: number
  deck_id: string
  course_id: string
  title: string
  source_ref: PresentationSourceRef
  scope: PresentationScope
  purpose: 'teaching' | 'self_study'
  template_id: PresentationTemplateId
  status: PresentationStatus
  active_revision_id: string | null
  active_generation_id: string | null
  latest_quality_report_id: string | null
  latest_artifact_id: string | null
  source_outdated?: boolean
  current_course_version_id?: string
  created_at: string
  updated_at: string
}

export type PresentationEventType = 'deck_outline' | 'slide_upsert' | 'slide_patch' | 'progress' | 'quality_report' | 'generation_complete' | 'export_ready' | 'error'

export interface PresentationEvent {
  schema_version: 'presentation-event/v1'
  event_type: PresentationEventType
  deck_id: string
  generation_id: string
  event_seq: number
  outline_revision: number
  revision_id: string | null
  emitted_at: string
  payload: Record<string, unknown>
}

export interface PresentationProposal {
  proposal_id: string
  request_id: string
  deck_id: string
  base_revision_id: string
  scope: 'slide' | 'deck'
  slide_ids: string[]
  prompt: string
  patches: Array<Record<string, unknown>>
  summary: string
  risks: string[]
  status: 'proposed' | 'applied' | 'cancelled' | 'stale'
  created_at: string
}

export interface PresentationArtifact {
  artifact_id: string
  deck_id: string
  revision_id: string
  page_count: number
  stale: boolean
  html_url?: string
  pptx_url?: string
}

export interface PresentationRenderMeasurement {
  revision_id: string
  revision_checksum: string
  overflow: boolean
  collision: boolean
  slide_count: number
  overflow_slide_ids?: string[]
  collision_slide_ids?: string[]
}

export interface PresentationPreviewMessage {
  version: 'presentation-preview/v1'
  type: 'preview:ready' | 'slide:selected' | 'render:measured'
  deck_id: string
  revision_id: string
  revision_checksum: string
  slide_id?: string | null
  payload: Record<string, unknown>
}
