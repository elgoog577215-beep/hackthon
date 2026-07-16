import { defineStore } from 'pinia'
import http from '../utils/http'

export interface EvolutionEvidence {
  evidence_id: string
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
  scope: 'current' | 'next'
  reason: string
  payload: Record<string, any>
}

export interface PersonalAdaptationPlan {
  plan_id?: string
  plan_kind?: 'personal_adaptation_plan'
  write_target?: 'personal_overlay'
  change_set_id: string
  hypothesis_id: string
  evidence_ids: string[]
  operations: EvolutionOperation[]
  allowed_scopes: Array<'current' | 'current_and_next'>
  selected_scope?: 'current' | 'current_and_next'
  impact_summary: Record<string, any>
  expected_effect: string
  status: 'pending' | 'applied' | 'rejected' | 'stale' | 'undone'
  effect_evaluation: Record<string, any>
}

export type EvolutionChangeSet = PersonalAdaptationPlan

export const useCourseEvolutionStore = defineStore('courseEvolution', {
  state: () => ({
    courseId: '',
    evidenceItems: [] as EvolutionEvidence[],
    hypotheses: [] as Array<Record<string, any>>,
    adaptationPlans: [] as PersonalAdaptationPlan[],
    personalCourseOverlay: null as Record<string, any> | null,
    permissions: null as Record<string, any> | null,
    summary: {} as Record<string, number>,
    loading: false,
    actingId: '',
  }),
  getters: {
    pendingPlans: state => state.adaptationPlans.filter(item => item.status === 'pending'),
    appliedPlans: state => state.adaptationPlans.filter(item => item.status === 'applied'),
  },
  actions: {
    applyPayload(courseId: string, payload: Record<string, any>) {
      this.courseId = courseId
      this.evidenceItems = payload.evidence_items || []
      this.hypotheses = payload.hypotheses || []
      this.adaptationPlans = payload.adaptation_plans || payload.change_sets || []
      this.personalCourseOverlay = payload.personal_course_overlay || null
      this.permissions = payload.permissions || null
      this.summary = payload.summary || {}
    },
    async load(courseId: string) {
      this.loading = true
      try {
        const response = await http.get(`/api/courses/${courseId}/personal-adaptation`)
        this.applyPayload(courseId, response.data)
        return response.data
      } finally {
        this.loading = false
      }
    },
    async evaluate(courseId: string) {
      this.loading = true
      try {
        const response = await http.post(`/api/courses/${courseId}/personal-adaptation/evaluate`)
        this.applyPayload(courseId, response.data)
        return response.data
      } finally {
        this.loading = false
      }
    },
    async accept(planId: string, selectedScope: 'current' | 'current_and_next') {
      this.actingId = planId
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/personal-adaptation/plans/${planId}/accept`,
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
          `/api/courses/${this.courseId}/personal-adaptation/plans/${planId}/reject`,
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
          `/api/courses/${this.courseId}/personal-adaptation/plans/${planId}/undo`,
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } finally {
        this.actingId = ''
      }
    },
  },
})
