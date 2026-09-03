/**
 * 共享类型定义
 * 从 course.ts 提取的所有接口和类型，供各拆分后的 Store 共用。
 */

import type { CourseType } from '@/shared/prompt-config'

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
  label?: string
  block_role?: string
  required?: boolean
  teaching_purpose: string
  knowledge_names: string[]
  teaching_guidance?: string
  planned_minutes?: number | null
  teacher_activity?: string
  student_activity?: string
}

/**
 * 教案呈现对象。后端 `course_lesson_dossier_v1` 的镜像。
 *
 * 栏目（rubric）是**恒定**的：`rubric_keys` 里的每一栏在每一节都存在，内容为空时
 * `status="empty"`。前端因此不允许按内容多少 `v-if` 掉整栏——那正是各节篇幅与
 * 颗粒度看起来忽大忽小的来源。
 */
export interface LessonDossierRubric {
  key: string
  kind: 'facts' | 'list' | 'split_list' | 'table' | string
  status: 'filled' | 'empty'
  item_count: number
  [payload: string]: unknown
}

export interface LessonDossierTimelineEntry {
  sequence: number
  module_id: string
  label: string
  block_role: string
  required: boolean
  teaching_purpose: string
  teaching_guidance: string
  teacher_activity: string
  student_activity: string
  knowledge_names: string[]
  minutes: number | null
  minutes_source: 'planned' | 'derived' | 'unset'
  start_minute: number | null
  end_minute: number | null
}

export interface LessonDossierAlignmentRow {
  knowledge_id: string
  name: string
  ownership: 'owned' | 'reused'
  knowledge_type: string
  modules: Array<{ module_id: string; label: string; sequence: number }>
  capabilities: string[]
  mastery: Array<{ performance: string; verification: string }>
  checks: string[]
  homework: string[]
  gaps: string[]
}

/** 学科模板合同视图。顶层合同落地前只做观测，不约束生成。 */
export interface LessonTemplateContract {
  schema_version: 'lesson_template_contract_v1'
  contract_state: 'projected_from_archetype' | 'unbound' | string
  template_id: string
  template_label: string
  template_version: string
  primary_mode: string
  course_stage: string
  purpose: string
  evidence_contract: string
  guardrails: string[]
  archetype_module_ids: string[]
  planned_module_ids: string[]
  actual_module_ids: string[]
  module_conformance: {
    matched: number
    missing_required: string[]
    unplanned: string[]
  }
}

export interface LessonDossierGranularity {
  knowledge_point_count: number
  module_count: number
  planned_minutes: number
  objective_count: number
  capability_count: number
  mastery_count: number
  misconception_count: number
  check_count: number
  homework_count: number
  alignment_gap_count: number
  filled_rubric_count: number
  rubric_count: number
}

export interface CourseLessonDossier {
  schema_version: 'course_lesson_dossier_v1'
  node_id: string
  sequence: number
  title: string
  chapter_title: string
  template: LessonTemplateContract
  rubric_keys: string[]
  rubrics: LessonDossierRubric[]
  granularity: LessonDossierGranularity
}

export interface CourseLessonDossierConsistency {
  schema_version: 'course_lesson_dossier_consistency_v1'
  section_count: number
  rubric_keys: string[]
  uniform_rubric_structure: boolean
  rubric_coverage: Array<{ key: string; filled_sections: number; section_count: number }>
  bands: Record<string, {
    median: number
    low: number
    high: number
    min: number
    max: number
    filled_sections: number
    section_count: number
  }>
  sections: Array<{
    node_id: string
    sequence: number
    title: string
    template_id: string
    granularity: LessonDossierGranularity
    flags: string[]
  }>
  outlier_node_ids: string[]
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
  planned_minutes?: number | null
  key_difficulties?: string[]
  teacher_activities?: string[]
  student_activities?: string[]
  resource_refs?: string[]
  in_class_checks?: string[]
  homework?: string[]
  teaching_notes?: string[]
  dossier?: CourseLessonDossier
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
  classroom?: {
    academic_term?: string
    total_class_hours?: number | null
    lesson_duration_minutes?: number | null
    teaching_context?: string
    class_size?: number | null
    class_profile?: string
    teaching_preparation?: string[]
    course_assessment_plan?: string[]
  }
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
  dossier_consistency?: CourseLessonDossierConsistency
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
  learning_path_role?: 'focus' | 'standard' | 'compressed' | 'verify_in_project' | 'milestone'
  path_reason?: string
  objective_id?: string
  objective_revision_id?: string
  content_blocks?: ContentBlock[]
  course_blocks?: CourseDocumentBlock[]
  citation_map?: Record<string, string>
  source_cards?: Array<{
    source_id: string
    title?: string
    url: string
    domain?: string
    published_date?: string | null
    trust_tier?: string
    license?: string | null
  }>
  citation_invalid_refs?: string[]
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
  /** Stable failure classification; the raw error_summary is technical detail. */
  error_code?: string
  error_retryable?: boolean
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
  /** 「第2章第3节 · 不确定性原理」——正文阶段之前与旧任务上可能没有。 */
  current_node_location?: {
    chapter_number: number | null
    chapter_name: string
    section_number: number | null
    node_name: string
    label: string
  } | null
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
    error_code?: string
    retryable?: boolean
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
    course_status?: string | null
    authoring_surface?: string | null
    academic_year?: string
    term?: string
    course_code?: string
    preparation_state?: 'preparing' | 'prepared'
    preparation_summary?: {
        planned_lessons: number
        outline_confirmed: boolean
        confirmed_lesson_plans: number
        confirmed_handouts: number
        confirmed_ppts: number
    }
    current_course_version_id?: string
    updated_at?: string
    next_session?: {
        session_id: string
        sequence: number
        date: string
        start_time: string
        end_time: string
        content_summary: string
        location: string
        lesson_plan_status?: string
        ppt_status?: string
    }
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
    source_ready?: boolean
    parsed_ready?: boolean
}

export interface TaskPhaseHistoryEntry {
    phase: string
    status: 'active' | 'completed' | 'error' | 'paused' | string
    progress?: number
    message?: string
    started_at?: string
    updated_at?: string
}

export interface TaskRecovery {
    state: 'none' | 'auto_resuming' | 'manual_resume' | 'quality_blocked' | 'conflict' | 'unavailable' | 'completed'
    can_resume: boolean
    reason_code: string
    reason: string
    checkpoint: TaskRecoveryCheckpoint
    quality_failure?: {
        fingerprint: string
        repeat_count: number
        blocker_count: number
        repair_scopes: Array<'difficulty_contract' | 'learning_assets' | 'manual_review' | string>
        supported: boolean
        truncated?: boolean
        blockers: Array<{
            code: string
            severity: string
            message: string
            suggestion: string
            target_id: string
            target_type: 'asset' | 'node' | 'course' | string
            gate?: string
            asset_type?: string
        }>
    }
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
    status: 'idle' | 'running' | 'paused' | 'completed' | 'error' | 'pending' | 'waiting_for_input' | 'waiting_for_review' | 'completed_with_warnings' | 'conflict'
    progress: number
    currentStep: string
    currentPhase?: string
    taskType?: string
    phaseProgress?: number
    phaseDetail?: Record<string, unknown>
    phaseHistory?: TaskPhaseHistoryEntry[]
    heartbeatAt?: string
    updatedAt?: string
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
    courseType?: CourseType
    style?: string
    requirements?: string
    error?: string
    errorCode?: string
    errorUserMessage?: string
    /** Sections that failed generation, as reported by the backend failure report. */
    failedNodes?: FailureReport['failed_nodes']
    /** Which AI provider is currently serving calls (process-wide, not per task). */
    providerRoute?: {
        route: 'primary' | 'fallback'
        switched_at?: string | null
        reason_code?: string | null
        fallback_endpoint?: string | null
        switch_count?: number
    }
    recovery?: TaskRecovery
    publicationAllowed?: boolean
    qualityStatus?: string
    guidedWorkflow?: GuidedGenerationWorkflow
}
