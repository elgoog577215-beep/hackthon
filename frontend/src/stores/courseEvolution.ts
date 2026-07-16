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

export interface EvolutionChangeSet {
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

export const useCourseEvolutionStore = defineStore('courseEvolution', {
  state: () => ({
    courseId: '',
    evidenceItems: [] as EvolutionEvidence[],
    hypotheses: [] as Array<Record<string, any>>,
    changeSets: [] as EvolutionChangeSet[],
    summary: {} as Record<string, number>,
    loading: false,
    actingId: '',
  }),
  getters: {
    pendingChangeSets: state => state.changeSets.filter(item => item.status === 'pending'),
    appliedChangeSets: state => state.changeSets.filter(item => item.status === 'applied'),
  },
  actions: {
    applyPayload(courseId: string, payload: Record<string, any>) {
      this.courseId = courseId
      this.evidenceItems = payload.evidence_items || []
      this.hypotheses = payload.hypotheses || []
      this.changeSets = payload.change_sets || []
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
    async accept(changeSetId: string, selectedScope: 'current' | 'current_and_next') {
      this.actingId = changeSetId
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${changeSetId}/accept`,
          { selected_scope: selectedScope },
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } finally {
        this.actingId = ''
      }
    },
    async reject(changeSetId: string, reason = '') {
      this.actingId = changeSetId
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${changeSetId}/reject`,
          { reason },
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } finally {
        this.actingId = ''
      }
    },
    async undo(changeSetId: string) {
      this.actingId = changeSetId
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/evolution/change-sets/${changeSetId}/undo`,
        )
        this.applyPayload(this.courseId, response.data)
        return response.data
      } finally {
        this.actingId = ''
      }
    },
  },
})
