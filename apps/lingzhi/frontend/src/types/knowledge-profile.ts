export interface KnowledgeProfileSummary {
  total_count: number; assessed_count: number; unknown_count: number
  verified_progress: number; coverage: number; assessed_average: number | null
  mastered_count: number; attention_count: number
}
export interface KnowledgeProfileNode {
  knowledge_id: string; knowledge_revision_id: string; name: string; statement: string
  parent_id: string; section_refs: string[]; block_refs?: string[]; mastery: number | null
  confidence: 'none' | 'limited' | 'moderate' | 'strong'
  status: 'unassessed' | 'supported_mastery' | 'needs_review' | 'checking'
  assessment_count: number; independent_count: number; activity_count: number
  historical_count: number; pending_attribution_count: number
  next_action: 'verify' | 'review' | 'transfer' | 'variant'
  evidence: Array<{ source_id: string; question_revision_id: string; outcome: 'passed' | 'not_passed'; support: 'independent' | 'assisted' | 'solution_seen' | 'practice_only' | 'invalid'; counted: boolean; weight: number; observed_at: string | null }>
}
export interface KnowledgeProfile {
  rule_version: string; baseline_revision: string | null; revision_id: string
  course_id: string; course_version_id: string; availability: 'ready' | 'tree_unavailable'
  summary: KnowledgeProfileSummary; nodes: KnowledgeProfileNode[]
  branches: Array<{ id: string; parent_id: string; name: string; knowledge_ids: string[]; summary: KnowledgeProfileSummary }>
  policy: { calibrated_probability: boolean; unknown_is_zero_ability: boolean; equal_leaf_weights: boolean }
}
