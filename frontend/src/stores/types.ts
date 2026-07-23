/**
 * 共享类型定义
 * 从 course.ts 提取的所有接口和类型，供各拆分后的 Store 共用。
 */

export type NodeGenerationStatus = 'pending' | 'generating' | 'completed' | 'error' | 'skipped'

export interface NodeGenerationConfig {
  difficulty?: 'beginner' | 'intermediate' | 'advanced'
  style: string
  target_word_range: [number, number]
  include_code_examples: boolean
  include_exercises: boolean
  custom_instruction?: string
}

export interface ContentBlock {
  block_id: string
  parent_block_id?: string | null
  type: 'intro' | 'orientation' | 'prerequisite' | 'objective' | 'concept' | 'reasoning' | 'example' | 'counterexample' | 'application' | 'activity' | 'feedback' | 'exercise' | 'checkpoint' | 'misconception' | 'remediation' | 'summary' | 'transfer' | 'custom'
  title: string
  content: string
  summary?: string
  order: number
  status?: 'draft' | 'final'
  metadata?: Record<string, unknown>
  content_fingerprint?: string
  block_revision_id?: string
}

export type CourseBlockKind = 'rich_text' | 'formula' | 'code' | 'image' | 'audio' | 'video' | 'diagram' | 'table' | 'callout' | 'source_excerpt' | 'practice_ref' | 'code_lab' | 'reflection' | 'project' | 'mastery_check' | 'review_checkpoint' | 'remediation_slot' | 'graph_embed'
export type CourseBlockRole = 'orientation' | 'prerequisite' | 'objective' | 'concept' | 'reasoning' | 'example' | 'counterexample' | 'application' | 'activity' | 'feedback' | 'misconception' | 'checkpoint' | 'remediation' | 'summary' | 'transfer'

export interface CourseDocumentBlock {
  block_id: string
  section_id: string
  parent_group_id?: string | null
  position: number
  kind: CourseBlockKind
  role: CourseBlockRole
  payload: Record<string, unknown>
  asset_refs: string[]
  objective_refs: string[]
  concept_refs: string[]
  evidence_refs: string[]
  visibility_rule: Record<string, unknown>
  internal_revision: string
  status: 'draft' | 'final' | 'retired'
}

export interface CourseDocumentSection {
  section_id: string
  parent_section_id?: string | null
  title: string
  position: number
  level: number
  learning_objective: string
  objective_id: string
  objective_revision_id: string
  attributes: Record<string, unknown>
}

export interface CourseDocument {
  schema_version: 'course_document_v1'
  course_id: string
  title: string
  document_revision: string
  sections: CourseDocumentSection[]
  blocks: CourseDocumentBlock[]
}

export interface CourseDocumentEnvelope {
  course_id: string
  course_name: string
  current_course_version_id: string
  subject_pedagogy_profile?: {
    primary_mode: string
    secondary_mode?: string | null
    secondary_intensity?: string | null
    confidence?: string
    rationale?: string
  } | null
  generation_quality_report?: Record<string, unknown> | null
  teaching_plan?: CourseTeachingPlanProjection | null
  source_format: 'canonical' | 'legacy_projection'
  migration: { required: boolean; source_checksum?: string | null; migrated_at?: string | null }
  document: CourseDocument
}

export interface CourseTeachingPlanModule {
  module_id: string
  teaching_purpose: string
  knowledge_names: string[]
  teaching_guidance?: string
}

export interface CourseTeachingPlanSection {
  node_id: string
  knowledge_structure: Array<{
    concept_group?: string
    description?: string
    knowledge_points?: Array<{
      knowledge_id?: string
      knowledge_status?: 'bound' | 'awaiting_compilation' | string
      name?: string
      statement?: string
      description?: string
      knowledge_type?: string
      conditions?: string[]
      boundaries?: string[]
      counterexamples?: string[]
      capability?: string
      capability_points?: Array<string | Record<string, unknown>>
      misconceptions?: Array<string | Record<string, unknown>>
      mastery_criteria?: Array<string | Record<string, unknown>>
      aliases?: string[]
      prerequisite_names?: string[]
    }>
  }>
  key_points: string[]
  reused_knowledge_names: string[]
  knowledge_relations: Array<Record<string, unknown>>
  teaching_modules: CourseTeachingPlanModule[]
}

export interface CourseTeachingPlanOverall {
  course_title: string
  positioning: string
  target_audience: string
  learning_objectives: string[]
  prerequisites: string[]
  teaching_strategy: {
    primary_mode: string
    secondary_mode: string
    rationale: string
  }
  assessment_methods: string[]
  chapters: Array<{
    chapter_id: string
    chapter_number: string
    title: string
    learning_focus: string
    section_count: number
    section_ids: string[]
  }>
  knowledge_tags: Array<{
    knowledge_id: string
    name: string
    section_count: number
  }>
}

export interface CourseTeachingPlanProjection {
  schema_version: 'course_teaching_plan_projection_v1'
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | string
  revision_id: string
  strategy: string
  section_count: number
  knowledge_point_count: number
  teaching_module_count: number
  overall?: CourseTeachingPlanOverall
  sections: CourseTeachingPlanSection[]
}

export interface CourseBlockEditTarget {
  nodeId: string
  nodeName: string
  block: CourseDocumentBlock
}

export interface BlockRegenerationQualityGate {
  key: string
  passed: boolean
  severity: string
  message: string
}

export interface BlockRegenerationQualityReport {
  passed: boolean
  status: 'passed' | 'failed'
  gates: BlockRegenerationQualityGate[]
  issues: string[]
}

export interface BlockRegenerationCandidate {
  candidate_id: string
  request_id: string
  course_id: string
  block_id: string
  section_id: string
  status: 'generating' | 'generation_failed' | 'ready' | 'quality_failed' | 'applied' | 'rejected' | 'stale'
  action_type: 'rewrite' | 'simplify' | 'example' | 'expand'
  instruction: string
  expected_document_revision: string
  expected_block_revision: string
  proposed_block: CourseDocumentBlock
  quality_report: BlockRegenerationQualityReport | null
  attempts: Array<{ run_id?: string; attempt: number; quality_report: BlockRegenerationQualityReport }>
  receipt?: Record<string, unknown> | null
  retryable?: boolean
  retry_count?: number
  failure_code?: string | null
  failure_reason?: string
}

export interface BlockRegenerationApplyResult {
  candidate: BlockRegenerationCandidate
  receipt: Record<string, unknown>
  document: CourseDocumentEnvelope
}

export type SelectionRewriteAction = 'rewrite' | 'simplify' | 'example' | 'exercise' | 'ask' | 'expand'

export interface SelectionRewritePayload {
  selected_text: string
  node_content: string
  heading_path: string[]
  before_context: string
  after_context: string
  user_requirement?: string
  action_type: SelectionRewriteAction
  course_context?: string
  previous_context?: string
}

export interface SelectionRewriteResult {
  replacement_text: string
  selected_text: string
  action_type: SelectionRewriteAction
  heading_path: string[]
  context_summary: string
}

export interface Node {
  node_id: string
  parent_node_id: string
  node_name: string
  node_level: number
  node_content: string
  learning_objective?: string
  objective_id?: string
  objective_revision_id?: string
  content_blocks?: ContentBlock[]
  course_blocks?: CourseDocumentBlock[]
  node_type: 'original' | 'custom' | 'extend'
  children?: Node[]
  is_read?: boolean
  quiz_score?: number
  // 节点生成状态与配置
  generation_status: NodeGenerationStatus
  content_state?: 'pending' | 'generating' | 'draft' | 'finalized' | 'failed' | 'error' | 'skipped'
  generation_config?: NodeGenerationConfig
  generated_chars: number
  error_summary?: string
  difficulty_contract?: Record<string, unknown>
  generation_quality?: Record<string, unknown>
}

export interface CourseBlockNavigationTarget {
  node: Node
  blockId: string
}

export interface TaskProgress {
  task_id: string
  course_id: string
  status: string
  progress: number
  current_node_name: string
  completed_nodes: number
  total_nodes: number
  estimated_time_remaining: number
}

export interface FailureReport {
  task_id: string
  course_id: string
  failed_nodes: Array<{
    node_id: string
    node_name: string
    error: string
    retry_count: number
  }>
  total_failed: number
}

export interface WSMessage {
  type: 'progress_update' | 'node_completed' | 'node_finalized' | 'stream_chunk' | 'task_completed' | 'task_error' | 'failure_report'
  task_id: string
  course_id: string
  payload: Record<string, unknown>
}

export interface WSCommand {
  type: 'subscribe' | 'unsubscribe' | 'skip_node' | 'retry_node' | 'stop_node' | 'custom_instruction' | 'retry_all_failed' | 'pause_task' | 'resume_task' | 'cancel_task'
  course_id: string
  node_id?: string
  payload?: Record<string, unknown>
}

export interface Annotation {
  anno_id: string
  node_id: string
  course_id?: string
  question: string
  answer: string
  anno_summary: string
  source_type: string
  quote?: string
}

export type LearningRecordType = 'note' | 'issue' | 'review_task' | 'bookmark'

export interface LearningRecord {
    record_id: string
    record_type: LearningRecordType
    status: string
    user_id: string
    course_id: string
    course_version_id?: string
    node_id: string
    node_name?: string
    objective_id?: string
    objective_revision_id?: string
    quote?: string
    title?: string
    content?: string
    origin?: string
    priority?: 'low' | 'medium' | 'high'
    tags?: string[]
    category?: string
    due_at?: string | null
    anchor?: Record<string, unknown>
    metadata?: Record<string, unknown>
    anchor_resolution?: Record<string, unknown>
    migration_status?: 'current' | 'content_updated' | 'needs_confirmation' | 'orphaned'
    revision: number
    created_at: string
    updated_at: string
}

export interface Note {
    id: string
    nodeId: string
    highlightId: string
    quote: string
    content: string
    summary?: string
    color: string
    createdAt: number
    top?: number
    sourceType?: 'user' | 'ai' | 'format' | 'wrong'
    style?: 'bold' | 'underline' | 'wave' | 'dashed' | 'highlight' | 'solid' | 'wavy'
    title?: string
    expanded?: boolean
    tags?: string[]
    category?: string
    priority?: 'low' | 'medium' | 'high'
    recordType?: LearningRecordType
    status?: string
    revision?: number
    origin?: string
    dueAt?: string | null
    migrationStatus?: 'current' | 'content_updated' | 'needs_confirmation' | 'orphaned'
    anchor?: Record<string, unknown>
    syncState?: 'saved' | 'saving' | 'local_only'
    metadata?: Record<string, unknown>
}

export interface Course {
    course_id: string
    course_name: string
    node_count: number
    generation_job_id?: string | null
    generation_status?: string | null
    is_published?: boolean
    resume?: {
        kind: string
        status: string
        node_id: string
        node_name: string
        activity_at: string
    }
}

export interface TaskRecoveryCheckpoint {
    phase: string
    completed_nodes: number
    total_nodes: number
    draft_node_ids: string[]
    failed_node_ids: string[]
    interrupted_node_ids: string[]
    requirements_ready?: boolean
    outline_ready?: boolean
    teaching_plan_ready?: boolean
    teaching_plan_mode?: 'compact' | 'batched' | string | null
    completed_teaching_plan_batches?: number
    total_teaching_plan_batches?: number
    completed_teaching_plan_sections?: number
    total_teaching_plan_sections?: number
    failed_teaching_plan_batch_id?: string | null
    next_teaching_plan_batch_index?: number
    completed_knowledge_packages?: number
    total_knowledge_packages?: number
    workspace_status?: string | null
    updated_at?: string | null
}

export interface TaskRecovery {
    state: 'none' | 'auto_resuming' | 'manual_resume' | 'quality_blocked' | 'conflict' | 'unavailable' | 'completed'
    can_resume: boolean
    reason_code: string
    reason: string
    checkpoint: TaskRecoveryCheckpoint
}

export type GuidedGenerationStepKey = 'requirements' | 'outline' | 'teaching' | 'content' | 'release'

export interface GuidedGenerationStep {
    number: number
    key: GuidedGenerationStepKey
    status: 'locked' | 'pending' | 'in_progress' | 'waiting_for_confirmation' | 'confirmed' | 'needs_regeneration' | 'failed'
    artifact_revision?: string | null
    input_revisions?: Record<string, string>
    confirmed_at?: string | null
}

export interface GuidedGenerationWorkflow {
    schema_version: 'guided_course_generation_v2' | 'guided_course_generation_v3'
    current_step: GuidedGenerationStepKey
    review_step?: GuidedGenerationStepKey | null
    steps: GuidedGenerationStep[]
    updated_at?: string
}

export interface Task {
    id: string
    courseId: string
    courseName: string
    status: 'idle' | 'running' | 'paused' | 'completed' | 'error' | 'pending' | 'waiting_for_review' | 'completed_with_warnings' | 'conflict'
    progress: number
    currentStep: string
    currentPhase?: string
    phaseProgress?: number
    phaseDetail?: Record<string, unknown>
    currentNodes?: Array<{
        node_id?: string
        node_name?: string
        name?: string
        action: string
        type: string
    }>
    completedNodes?: number
    totalNodes?: number
    logs: string[]
    shouldStop: boolean
    difficulty?: string
    compositionStyle?: string
    style?: string
    requirements?: string
    error?: string
    recovery?: TaskRecovery
    publicationAllowed?: boolean
    qualityStatus?: string
    guidedWorkflow?: GuidedGenerationWorkflow
}
