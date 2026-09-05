import { defineStore } from 'pinia'
import http, { activeIdentityHeaders } from '../utils/http'
import { createUuid } from '../utils/client-id'
import { postGenerationStream } from '../shared/generation-stream'

export interface EvolutionEvidence {
  evidence_id: string
  source_id: string
  source_type: 'learning_event' | 'learning_record' | 'practice_attempt'
  evidence_kind: string
  summary: string
  strength: number
  is_counterevidence?: boolean
  created_at?: string
  anchor: { section_id: string; block_id: string; resolution_status: string }
}

export interface EvolutionOperation {
  operation_id: string
  operation_type: string
  target_block_id: string
  target_section_id: string
  scope: 'current' | 'next'
  reason: string
  payload: Record<string, any>
}

export interface CourseEvolutionOperationJournalEntry {
  schema_version: 'course_evolution_operation_journal_v1'
  operation_id: string
  domain: string
  status: 'pending' | 'applying' | 'applied' | 'failed'
  attempt: number
  previous_revision_id: string
  expected_result_revision_id: string
  result_revision_id: string
  result_receipt: Record<string, any>
  error_code: string
  detail: string
  retryable: boolean
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  updated_at: string
}

export type CourseEvolutionAnchorRole =
  | 'reasoning'
  | 'application'
  | 'example'
  | 'checkpoint'
  | 'concept'

export type CourseAdjustmentScope =
  | 'current_block'
  | 'current_section'
  | 'current_chapter'
  | 'whole_course'

export interface CreateCourseAdjustmentInput {
  sectionId: string
  instruction: string
  scopeSelection?: CourseAdjustmentScope
  blockId?: string
  expectedDocumentRevision?: string
  expectedBlockRevision?: string
  direction?: 'simplify' | 'expand' | 'custom'
  anchorRole?: CourseEvolutionAnchorRole
  requestId?: string
}

export interface TeacherCourseChangeContext {
  schema_version: 'teacher_course_change_context_v1'
  index_schema_version: 'teacher_course_change_index_v1'
  course_id: string
  course_title: string
  source_mode: 'formal_course' | 'authoring_workspace' | 'mixed' | 'unavailable'
  ready: boolean
  readiness_message: string
  base_revision_vector: Record<string, string>
  assets: Array<{
    asset_type: string
    label: string
    state: 'available' | 'partial' | 'missing' | 'stale'
    count: number
    source: string
    revision: string
  }>
  outline: Array<{
    node_id: string
    parent_node_id: string
    node_name: string
    node_level: number
    learning_objective?: string
    source?: string
  }>
  units: Array<{
    unit_id: string
    asset_type: string
    unit_type: string
    title: string
    text: string
    section_ids: string[]
    parent_id: string
    role: string
    source_revision: string
    source_state: string
    metadata: Record<string, any>
  }>
  updated_at: string
  summary: {
    available_assets: number
    missing_assets: number
    indexed_units: number
    outline_nodes: number
  }
}

export type TeacherMigrationDisposition =
  | 'reuse_exact'
  | 'reuse_rebind'
  | 'rewrite_partial'
  | 'regenerate'
  | 'retire'

export interface TeacherCourseOutlineReviewNode {
  provisional_id: string
  title: string
  parent_ref: string
  source_node_ids: string[]
  learning_focus?: string
}

export interface AdaptationHypothesis {
  hypothesis_id: string
  claim: string
  confidence: number
  confidence_reasons: string[]
  evidence_assessment: Record<string, any>
  validation_plan: string
  status: string
}

export interface TeacherCourseChangePlanning {
  schema_version: 'course_change_plan_v1'
  scenario_matrix_version: 'course_change_scenario_matrix_v1'
  plan_id: string
  course_id: string
  intent: {
    schema_version: 'course_change_intent_v1'
    intent_id: string
    course_id: string
    raw_request: string
    interpreted_goal: string
    scope_hint: Record<string, any>
    hard_constraints: string[]
    soft_preferences: string[]
    protected_requirements: string[]
    source_refs: string[]
    signals: Array<{
      signal_id: string
      kind: 'semantic' | 'structural' | 'mixed' | 'uncertain'
      evidence: string
      confidence: number
      source: string
    }>
    assumptions: string[]
    blocking_questions: string[]
    can_proceed_without_clarification: boolean
    interpretation_revision: string
  }
  base_revision_vector: Record<string, string>
  execution_strategies: Array<'semantic_impact' | 'structural_regeneration'>
  strategy_status: 'provisional' | 'resolved'
  scenario_tags: string[]
  structural_operations: Array<Record<string, any>>
  unit_migrations: Array<{
    migration_id: string
    asset_type: string
    unit_type: string
    source_unit_ids: string[]
    target_unit_ids: string[]
    disposition: 'reuse_exact' | 'reuse_rebind' | 'rewrite_partial' | 'regenerate' | 'retire' | 'blocked'
    reason: string
    confidence: number
    requires_review: boolean
    candidate_status: 'not_started' | 'ready' | 'failed' | 'not_required'
    metadata?: Record<string, any>
  }>
  structure_review_status: 'not_required' | 'pending' | 'confirmed'
  status: 'draft' | 'impact_ready' | 'needs_clarification' | 'candidate_ready' | 'blocked'
  supersedes_plan_id: string
  replan_reasons: string[]
  created_at: string
  updated_at: string
}

export interface CourseEvolutionPlan {
  plan_id?: string
  plan_kind?: 'course_evolution_plan'
  write_target?: 'course_document'
  change_set_id: string
  hypothesis_id: string
  source_kind?: 'learning_evidence' | 'manual_section_request' | 'manual_request'
  target_section_id?: string
  request_text?: string
  growth_direction?: 'remediation' | 'challenge' | 'author_directed'
  generation_job_id?: string
  review_revision?: number
  generation_status?: 'suggested' | 'generating' | 'ready' | 'failed' | 'stale'
  requested_roles?: string[]
  evidence_ids: string[]
  operations: EvolutionOperation[]
  teacher_change_planning?: TeacherCourseChangePlanning | null
  scope_selection?: CourseAdjustmentScope
  allowed_scopes: Array<'current' | 'current_and_next'>
  selected_scope?: 'current' | 'current_and_next'
  selected_operation_ids?: string[]
  excluded_operation_ids?: string[]
  impact_summary: Record<string, any>
  expected_effect: string
  // 'accepted' 表示用户已确认、课程提交尚未回执确认的中间态：
  // 它既不该出现在待处理队列，也还不能当作已应用展示。
  status: 'pending' | 'accepted' | 'applied' | 'rejected' | 'stale' | 'undo_partial' | 'undone'
  applied_block_ids?: string[]
  application_receipt?: Record<string, any>
  operation_journal?: CourseEvolutionOperationJournalEntry[]
  undo_receipt?: Record<string, any>
  effect_evaluation: Record<string, any>
}

export type EvolutionChangeSet = CourseEvolutionPlan

export type CourseEvolutionApplicationPhase = 'navigator' | 'content' | 'settled'

export interface CourseEvolutionApplicationPresentation {
  planId: string
  affectedSectionIds: string[]
  appliedBlockIds: string[]
  operationIds: string[]
  targetSectionId: string
  targetBlockId: string
  targetOperationId: string
}

export interface CourseEvolutionApplicationVisual extends CourseEvolutionApplicationPresentation {
  token: number
  phase: CourseEvolutionApplicationPhase
}

export const useCourseEvolutionStore = defineStore('courseEvolution', {
  state: () => ({
    courseId: '',
    courseEpoch: 0,
    contextRequestSequence: 0,
    payloadRequestSequence: 0,
    evidenceItems: [] as EvolutionEvidence[],
    hypotheses: [] as AdaptationHypothesis[],
    plans: [] as CourseEvolutionPlan[],
    courseContext: null as TeacherCourseChangeContext | null,
    permissions: null as Record<string, any> | null,
    summary: {} as Record<string, number>,
    loading: false,
    actingId: '',
    generating: false,
    generationError: '',
    progressDisconnected: false,
    generationMessage: '',
    contextLoading: false,
    applicationVisual: null as CourseEvolutionApplicationVisual | null,
    applicationVisualCounter: 0,
  }),
  getters: {
    pendingPlans: state => state.plans.filter(item => item.status === 'pending'),
    appliedPlans: state => state.plans.filter(item => item.status === 'applied'),
    // 因知识语义变化而失效的方案：必须让用户看到"为什么失效"，
    // 否则候选只是从列表里消失，看起来像系统吞了它。
    knowledgeStalePlans: state => state.plans.filter(
      item => item.status === 'stale'
        && item.impact_summary?.knowledge_drift?.verdict === 'conflict',
    ),
  },
  actions: {
    selectCourse(courseId: string) {
      if (this.courseId === courseId) return
      this.courseId = courseId
      this.courseEpoch += 1
      this.loading = false
      this.contextLoading = false
      this.courseContext = null
      this.plans = []
      this.evidenceItems = []
      this.hypotheses = []
      this.permissions = null
      this.summary = {}
      this.applicationVisual = null
      this.actingId = ''
      this.generating = false
      this.generationError = ''
      this.progressDisconnected = false
      this.generationMessage = ''
    },
    applyPayload(courseId: string, payload: Record<string, any>) {
      if (this.courseId !== courseId) this.selectCourse(courseId)
      this.evidenceItems = payload.evidence_items || []
      this.hypotheses = payload.hypotheses || []
      this.plans = payload.course_evolution_plans || payload.change_sets || payload.adaptation_plans || []
      this.permissions = payload.permissions || null
      this.summary = payload.summary || {}
    },
    beginApplicationVisual(presentation: CourseEvolutionApplicationPresentation) {
      const token = this.applicationVisualCounter + 1
      this.applicationVisualCounter = token
      this.applicationVisual = {
        ...presentation,
        token,
        phase: 'navigator',
      }
      return token
    },
    setApplicationVisualPhase(token: number, phase: CourseEvolutionApplicationPhase) {
      if (!this.applicationVisual || this.applicationVisual.token !== token) return
      this.applicationVisual.phase = phase
    },
    clearApplicationVisual(planId?: string) {
      if (planId && this.applicationVisual?.planId !== planId) return
      this.applicationVisual = null
    },
    async load(courseId: string) {
      this.selectCourse(courseId)
      const sequence = ++this.payloadRequestSequence
      this.loading = true
      try {
        const response = await http.get(`/api/courses/${courseId}/evolution`)
        if (this.courseId === courseId && sequence === this.payloadRequestSequence) this.applyPayload(courseId, response.data)
        return response.data
      } finally {
        if (this.courseId === courseId && sequence === this.payloadRequestSequence) this.loading = false
      }
    },
    async refreshProgress(courseId?: string) {
      const targetCourseId = courseId || this.courseId
      if (!targetCourseId) return null
      this.selectCourse(targetCourseId)
      if (this.actingId || this.generating) return null
      const sequence = ++this.payloadRequestSequence
      const response = await http.get(
        `/api/courses/${targetCourseId}/evolution/progress`,
        { silentError: true },
      )
      if (this.courseId === targetCourseId && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, response.data)
      return response.data
    },
    async evaluate(courseId: string) {
      this.selectCourse(courseId)
      const sequence = ++this.payloadRequestSequence
      this.loading = true
      try {
        const response = await http.post(`/api/courses/${courseId}/evolution/evaluate`)
        if (this.courseId === courseId && sequence === this.payloadRequestSequence) this.applyPayload(courseId, response.data)
        return response.data
      } finally {
        if (this.courseId === courseId && sequence === this.payloadRequestSequence) this.loading = false
      }
    },
    async loadCourseContext(courseId?: string) {
      const targetCourseId = courseId || this.courseId
      if (!targetCourseId) return null
      this.selectCourse(targetCourseId)
      const sequence = ++this.contextRequestSequence
      this.contextLoading = true
      try {
        const response = await http.get(
          `/api/courses/${targetCourseId}/evolution/course-context`,
          { silentError: true },
        )
        if (this.courseId === targetCourseId && sequence === this.contextRequestSequence) this.courseContext = response.data
        return response.data as TeacherCourseChangeContext
      } finally {
        if (this.courseId === targetCourseId && sequence === this.contextRequestSequence) this.contextLoading = false
      }
    },
    async createCoursePlan(input: { instruction: string; requestId?: string; courseId?: string; supersedesPlanId?: string; literalReplacement?: { before: string; after: string }; assetTypes?: string[] }) {
      const targetCourseId = input.courseId || this.courseId
      if (!targetCourseId) throw new Error('course_change_course_required')
      this.selectCourse(targetCourseId)
      const epoch = this.courseEpoch
      const sequence = ++this.payloadRequestSequence
      this.generating = true
      this.generationError = ''
      try {
        const response = await http.post(
          `/api/courses/${targetCourseId}/evolution/course-plans`,
          {
            request_id: input.requestId
              || createUuid(),
            instruction: input.instruction,
            ...(input.literalReplacement ? { literal_replacement: input.literalReplacement } : {}),
            ...(input.assetTypes ? { asset_types: input.assetTypes } : {}),
            ...(input.supersedesPlanId
              ? { supersedes_plan_id: input.supersedesPlanId }
              : {}),
          },
        )
        if (epoch === this.courseEpoch && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, response.data)
        return response.data
      } catch (error: any) {
        if (epoch === this.courseEpoch) this.generationError = String(
          error?.response?.data?.detail?.message
          || error?.response?.data?.detail
          || error?.message
          || 'course_change_analysis_failed',
        )
        throw error
      } finally {
        if (epoch === this.courseEpoch) this.generating = false
      }
    },
    async reviewCoursePlan(
      planId: string,
      selectedMigrationIds: string[],
      options: {
        confirmStructure?: boolean
        migrationDispositions?: Record<string, TeacherMigrationDisposition>
        proposedOutline?: TeacherCourseOutlineReviewNode[]
      } = {},
    ) {
      const targetCourseId = this.courseId
      const epoch = this.courseEpoch
      const sequence = ++this.payloadRequestSequence
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${targetCourseId}/evolution/course-plans/${planId}/review`,
          {
            selected_migration_ids: selectedMigrationIds,
            confirm_structure: Boolean(options.confirmStructure),
            ...(options.migrationDispositions !== undefined
              ? { migration_dispositions: options.migrationDispositions }
              : {}),
            ...(options.proposedOutline !== undefined
              ? { proposed_outline: options.proposedOutline }
              : {}),
          },
        )
        if (epoch === this.courseEpoch && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, response.data)
        return response.data
      } finally {
        if (epoch === this.courseEpoch && this.actingId === planId) this.actingId = ''
      }
    },
    async createPlan(input: CreateCourseAdjustmentInput) {
      const targetCourseId = this.courseId
      const epoch = this.courseEpoch
      const sequence = ++this.payloadRequestSequence
      this.generating = true
      this.generationError = ''
      try {
        const response = await http.post(
          `/api/courses/${targetCourseId}/evolution/plans`,
          {
            request_id: input.requestId
              || createUuid(),
            instruction: input.instruction,
            section_id: input.sectionId,
            scope_selection: input.scopeSelection || 'current_section',
            block_id: input.blockId || '',
            expected_document_revision: input.expectedDocumentRevision || '',
            expected_block_revision: input.expectedBlockRevision || '',
            direction: input.direction || 'custom',
            anchor_role: input.anchorRole,
          },
        )
        if (epoch === this.courseEpoch && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, response.data)
        return response.data
      } catch (error: any) {
        if (epoch === this.courseEpoch) this.generationError = String(
          error?.response?.data?.detail?.message
          || error?.response?.data?.detail
          || error?.message
          || 'course_adjustment_generation_failed',
        )
        throw error
      } finally {
        if (epoch === this.courseEpoch) this.generating = false
      }
    },
    async createSectionPlan(
      sectionId: string,
      instruction: string,
      scopeSelection: 'current_section' | 'current_chapter' | 'whole_course' = 'current_section',
      anchorRole?: CourseEvolutionAnchorRole,
    ) {
      return this.createPlan({
        sectionId,
        instruction,
        scopeSelection,
        anchorRole,
      })
    },
    async generateSuggested(planId: string) {
      const targetCourseId = this.courseId
      const epoch = this.courseEpoch
      const sequence = ++this.payloadRequestSequence
      this.actingId = planId
      this.generationError = ''
      this.progressDisconnected = false
      this.generationMessage = ''
      try {
        const payload = await postGenerationStream<Record<string, any>>(
          `/api/courses/${targetCourseId}/evolution/change-sets/${planId}/generate`,
          {},
          {
            headers: activeIdentityHeaders(),
            onProgress: progress => {
              if (epoch === this.courseEpoch) this.generationMessage = progress.message || ''
            },
          },
        )
        if (epoch === this.courseEpoch && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, payload)
        return payload
      } catch (error: any) {
        if (epoch === this.courseEpoch) this.generationError = String(
          error?.response?.data?.detail?.message
          || error?.response?.data?.detail
          || error?.message
          || 'course_adjustment_generation_failed',
        )
        throw error
      } finally {
        if (epoch === this.courseEpoch && this.actingId === planId) this.actingId = ''
        if (epoch === this.courseEpoch) this.generationMessage = ''
      }
    },
    async accept(
      planId: string,
      selectedScope: 'current' | 'current_and_next',
      selectedOperationIds?: string[],
      options: { retryFailed?: boolean } = {},
    ) {
      const targetCourseId = this.courseId
      const epoch = this.courseEpoch
      const sequence = ++this.payloadRequestSequence
      this.actingId = planId
      try {
        const payload: Record<string, any> = { selected_scope: selectedScope }
        if (selectedOperationIds !== undefined) {
          payload.selected_operation_ids = selectedOperationIds
        }
        if (options.retryFailed) payload.retry_failed = true
        const response = await http.post(
          `/api/courses/${targetCourseId}/evolution/change-sets/${planId}/accept`,
          payload,
        )
        if (epoch === this.courseEpoch && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, response.data)
        return response.data
      } finally {
        if (epoch === this.courseEpoch && this.actingId === planId) this.actingId = ''
      }
    },
    async reject(planId: string, reason = '') {
      const targetCourseId = this.courseId
      const epoch = this.courseEpoch
      const sequence = ++this.payloadRequestSequence
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${targetCourseId}/evolution/change-sets/${planId}/reject`,
          { reason },
        )
        if (epoch === this.courseEpoch && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, response.data)
        return response.data
      } finally {
        if (epoch === this.courseEpoch && this.actingId === planId) this.actingId = ''
      }
    },
    async undo(planId: string) {
      const targetCourseId = this.courseId
      const epoch = this.courseEpoch
      const sequence = ++this.payloadRequestSequence
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${targetCourseId}/evolution/change-sets/${planId}/undo`,
        )
        if (epoch === this.courseEpoch && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, response.data)
        return response.data
      } finally {
        if (epoch === this.courseEpoch && this.actingId === planId) this.actingId = ''
      }
    },
    async adjust(planId: string) {
      const targetCourseId = this.courseId
      const epoch = this.courseEpoch
      const sequence = ++this.payloadRequestSequence
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${targetCourseId}/evolution/change-sets/${planId}/adjust`,
        )
        if (epoch === this.courseEpoch && sequence === this.payloadRequestSequence) this.applyPayload(targetCourseId, response.data)
        return response.data
      } finally {
        if (epoch === this.courseEpoch && this.actingId === planId) this.actingId = ''
      }
    },
  },
})

// One polling owner per store. Closing a surface releases observation only.
const progressWatchers = new WeakMap<object, { courseId: string; refs: number; timer: ReturnType<typeof setInterval> }>()
export function observeCourseChangeProgress(store: ReturnType<typeof useCourseEvolutionStore>, courseId: string) {
  let watcher = progressWatchers.get(store)
  if (watcher && watcher.courseId !== courseId) { clearInterval(watcher.timer); progressWatchers.delete(store); watcher = undefined }
  if (!watcher) {
    let inFlight = false
    const timer = setInterval(async () => {
      if (inFlight || store.courseId !== courseId || store.actingId || store.generating || !store.plans.some(p => p.teacher_change_planning && p.status === 'pending' && p.generation_status === 'generating')) return
      inFlight = true
      try { await store.refreshProgress(courseId); if (store.courseId === courseId) store.progressDisconnected = false } catch { if (store.courseId === courseId) store.progressDisconnected = true }
      finally { inFlight = false }
    }, 1800)
    watcher = { courseId, refs: 0, timer }
    progressWatchers.set(store, watcher)
  }
  watcher.refs += 1
  const owned = watcher
  return () => { owned.refs -= 1; if (owned.refs === 0) { clearInterval(owned.timer); if (progressWatchers.get(store) === owned) progressWatchers.delete(store) } }
}
