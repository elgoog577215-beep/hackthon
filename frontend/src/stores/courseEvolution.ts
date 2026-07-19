import { defineStore } from 'pinia'
import http from '../utils/http'

export interface EvolutionEvidence {
  evidence_id: string
  source_id: string
  source_type: 'learning_event' | 'learning_record' | 'practice_attempt'
  evidence_kind: string
  summary: string
  strength: number
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

export type CourseEvolutionAnchorRole =
  | 'reasoning'
  | 'application'
  | 'example'
  | 'checkpoint'
  | 'concept'

export type CourseAdjustmentScope =
  | 'current_block'
  | 'current_section'
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

export interface AdaptationHypothesis {
  hypothesis_id: string
  claim: string
  confidence: number
  confidence_reasons: string[]
  evidence_assessment: Record<string, any>
  validation_plan: string
  status: string
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
  generation_status?: 'suggested' | 'generating' | 'ready' | 'failed' | 'stale'
  requested_roles?: string[]
  evidence_ids: string[]
  operations: EvolutionOperation[]
  scope_selection?: CourseAdjustmentScope
  allowed_scopes: Array<'current' | 'current_and_next'>
  selected_scope?: 'current' | 'current_and_next'
  selected_operation_ids?: string[]
  excluded_operation_ids?: string[]
  impact_summary: Record<string, any>
  expected_effect: string
  status: 'pending' | 'applied' | 'rejected' | 'stale' | 'undone'
  applied_block_ids?: string[]
  application_receipt?: Record<string, any>
  undo_receipt?: Record<string, any>
  effect_evaluation: Record<string, any>
}

export type EvolutionChangeSet = CourseEvolutionPlan

export const useCourseEvolutionStore = defineStore('courseEvolution', {
  state: () => ({
    courseId: '',
    evidenceItems: [] as EvolutionEvidence[],
    hypotheses: [] as AdaptationHypothesis[],
    plans: [] as CourseEvolutionPlan[],
    permissions: null as Record<string, any> | null,
    summary: {} as Record<string, number>,
    loading: false,
    actingId: '',
    generating: false,
    generationError: '',
  }),
  getters: {
    pendingPlans: state => state.plans.filter(item => item.status === 'pending'),
    appliedPlans: state => state.plans.filter(item => item.status === 'applied'),
  },
  actions: {
    applyPayload(courseId: string, payload: Record<string, any>) {
      this.courseId = courseId
      this.evidenceItems = payload.evidence_items || []
      this.hypotheses = payload.hypotheses || []
      this.plans = payload.course_evolution_plans || payload.change_sets || payload.adaptation_plans || []
      this.permissions = payload.permissions || null
      this.summary = payload.summary || {}
    },
    async load(courseId: string) {
      this.loading = true
      try {
        const response = await http.get(`/api/courses/${courseId}/evolution`)
        this.applyPayload(courseId, response.data)
        return response.data
      } finally {
        this.loading = false
      }
    },
    async refreshProgress(courseId?: string) {
      const targetCourseId = courseId || this.courseId
      if (!targetCourseId) return null
      const response = await http.get(
        `/api/courses/${targetCourseId}/evolution/progress`,
        { silentError: true },
      )
      this.applyPayload(targetCourseId, response.data)
      return response.data
    },
    async evaluate(courseId: string) {
      this.loading = true
      try {
        const response = await http.post(`/api/courses/${courseId}/evolution/evaluate`)
        this.applyPayload(courseId, response.data)
        return response.data
      } finally {
        this.loading = false
      }
    },
    async createPlan(input: CreateCourseAdjustmentInput) {
      this.generating = true
      this.generationError = ''
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/plans`,
          {
            request_id: input.requestId
              || globalThis.crypto?.randomUUID?.()
              || `course-adjustment-${Date.now()}`,
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
        this.applyPayload(this.courseId, response.data)
        return response.data
      } catch (error: any) {
        this.generationError = String(
          error?.response?.data?.detail?.message
          || error?.response?.data?.detail
          || error?.message
          || 'course_adjustment_generation_failed',
        )
        throw error
      } finally {
        this.generating = false
      }
    },
    async createSectionPlan(
      sectionId: string,
      instruction: string,
      scopeSelection: 'current_section' | 'whole_course' = 'current_section',
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
      this.actingId = planId
      this.generationError = ''
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${planId}/generate`,
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } catch (error: any) {
        this.generationError = String(
          error?.response?.data?.detail?.message
          || error?.response?.data?.detail
          || error?.message
          || 'section_evolution_generation_failed',
        )
        throw error
      } finally {
        this.actingId = ''
      }
    },
    async accept(
      planId: string,
      selectedScope: 'current' | 'current_and_next',
      selectedOperationIds?: string[],
    ) {
      this.actingId = planId
      try {
        const payload: Record<string, any> = { selected_scope: selectedScope }
        if (selectedOperationIds !== undefined) {
          payload.selected_operation_ids = selectedOperationIds
        }
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${planId}/accept`,
          payload,
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } finally {
        this.actingId = ''
      }
    },
    async reject(planId: string, reason = '') {
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${planId}/reject`,
          { reason },
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } finally {
        this.actingId = ''
      }
    },
    async undo(planId: string) {
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${planId}/undo`,
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } finally {
        this.actingId = ''
      }
    },
    async adjust(planId: string) {
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${planId}/adjust`,
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } finally {
        this.actingId = ''
      }
    },
  },
})
