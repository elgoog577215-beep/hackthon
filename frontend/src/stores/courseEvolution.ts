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
  source_kind?: 'learning_evidence' | 'manual_section_request'
  target_section_id?: string
  request_text?: string
  growth_direction?: 'remediation' | 'challenge' | 'author_directed'
  generation_status?: 'suggested' | 'generating' | 'ready' | 'failed' | 'stale'
  requested_roles?: string[]
  evidence_ids: string[]
  operations: EvolutionOperation[]
  allowed_scopes: Array<'current' | 'current_and_next'>
  selected_scope?: 'current' | 'current_and_next'
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
    async createSectionPlan(sectionId: string, instruction: string) {
      this.generating = true
      this.generationError = ''
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/sections/${sectionId}/plans`,
          {
            request_id: globalThis.crypto?.randomUUID?.() || `section-${Date.now()}`,
            instruction,
          },
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
        this.generating = false
      }
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
    async accept(planId: string, selectedScope: 'current' | 'current_and_next') {
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${planId}/accept`,
          { selected_scope: selectedScope },
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
