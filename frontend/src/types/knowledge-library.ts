export type KnowledgeNodeType = 'course' | 'chapter' | 'section' | 'concept_group' | 'knowledge_point'

export interface KnowledgeNode {
  knowledge_id: string
  code: string
  parent_id: string | null
  node_type: KnowledgeNodeType
  name: string
  description: string
  depth: number
  sort_order: number
  path_ids: string[]
  path_names: string[]
  aliases: string[]
  learning_actions: string[]
  typical_problems: string[]
  section_ids: string[]
  block_ids: string[]
  objective_ids: string[]
  criterion_ids: string[]
  question_ids: string[]
  misconception_ids: string[]
  skill_unit_ids: string[]
  mistake_point_ids: string[]
  improvement_ids: string[]
  mastery_criterion_ids: string[]
  statement?: string
  conditions?: string[]
  boundaries?: string[]
  counterexamples?: string[]
  granularity_status?: string
  covered_by_course: boolean
  source_status: string
  status: string
  revision_id: string
}

export interface KnowledgeRelation {
  relation_id: string
  source_knowledge_id: string
  target_knowledge_id: string
  relation_type: 'prerequisite' | 'derives' | 'equivalent_to' | 'contrasts_with' | 'applies_to' | 'generalizes'
  source_status: string
  status: 'accepted' | 'candidate' | 'rejected' | string
  reason: string
  conditions?: string[]
  distinction?: string
  derivation_steps?: string[]
  revision_id: string
}

export interface KnowledgeLibraryView {
  schema_version: 'knowledge_library_view_v3'
  asset_id: string
  library_id: string
  subject_id: string
  library_version: string
  root_node_id: string
  nodes: KnowledgeNode[]
  relations: KnowledgeRelation[]
  skill_units: SkillUnit[]
  mistake_points: MistakePoint[]
  mastery_criteria: CourseMasteryCriterion[]
  improvement_points?: ImprovementPoint[]
  usage_policy: {
    ai_must_judge_independently: boolean
    allowed_fit: Array<'hit' | 'partial' | 'miss'>
    may_invent_formal_ids: boolean
    identity_scope?: 'course_only' | 'subject_shared'
    personal_state_can_modify_library?: boolean
  }
  course_map_revision_id: string
  coverage: {
    formal_knowledge_count: number
    mapped_count: number
    unmapped_count: number
    mapped_ratio: number
    status: string
    section_count?: number
    covered_section_count?: number
  }
  unresolved_mappings: unknown[]
  status: string
  revision_id: string
  binding_revision_id: string
  lifecycle_status: 'candidate' | 'accepted' | 'rejected' | 'degraded'
  origin: 'curated' | 'model_generated' | 'course_and_domain_generated' | 'course_index' | string
  quality_report: SubjectOntologyQualityReport
  generation_audit?: {
    generation_calls: number
    review_calls: number
    repair_calls: number
    sources: string[]
    semantic_review?: { passed?: boolean; issues?: string[] } | null
    provider_failure?: { code: string; message: string; retryable: boolean } | null
  }
  source_summary?: Record<string, number>
}

export interface SubjectOntologyQualityReport {
  passed: boolean
  score: number
  metrics: {
    mapped_ratio?: number
    relation_coverage?: number
    cross_skill_ratio?: number
    [key: string]: number | boolean | undefined
  }
  issues: Array<{ code: string; severity: string; message: string }>
  blocking_issues: Array<{ code: string; severity: string; message: string }>
}

export interface KnowledgeLibraryReview {
  previous_revision_id?: string | null
  diff: { added: number; modified: number; removed: number }
}

export interface KnowledgeLibraryRow {
  node: KnowledgeNode
  depth: number
  hasChildren: boolean
  expanded: boolean
}

export interface BoundQuestion {
  asset_id: string
  question_id?: string
  prompt?: string
  practice_level?: string
}

export interface BoundCriterion {
  asset_id: string
  criterion_id?: string
  observable_performance?: string
  verification_status?: string
}

export interface BoundMisconception {
  asset_id: string
  misconception_id?: string
  error_pattern?: string
  discrimination?: string
}

export interface SkillUnit {
  skill_unit_id: string
  name: string
  learning_goal?: string
  observable_behaviors?: string[]
  primary_knowledge_id: string
  knowledge_ids: string[]
}

export interface MistakePoint {
  mistake_point_id: string
  skill_unit_id: string
  name: string
  error_pattern?: string
  cognitive_cause?: string
  discrimination?: string
  repair_strategy?: string
  knowledge_ids: string[]
}

export interface ImprovementPoint {
  improvement_point_id: string
  skill_unit_id: string
  name: string
  learning_goal?: string
  practice_strategy?: string
  knowledge_ids: string[]
}

export interface CourseMasteryCriterion {
  criterion_id: string
  name: string
  observable_performance: string
  knowledge_ids: string[]
  skill_ids: string[]
  required_independence?: string
  required_transfer?: string
  verification_method?: string
}
