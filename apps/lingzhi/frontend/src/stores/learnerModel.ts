import { defineStore } from 'pinia'
import http from '../utils/http'

export type EvidenceConfidence = 'insufficient' | 'low' | 'medium' | 'high'
export type EvidenceSufficiency = 'none' | 'limited' | 'moderate' | 'strong'

export interface LearnerEvidenceRef {
  source_id: string
  type: string
  status: string
  outcome?: string
  strength?: string
  observed_at?: string | null
}

export interface LearnerObjectiveModel {
  objective_id: string
  objective_revision_id: string
  node_id: string
  node_name: string
  statement: string
  reading_status: string
  mastery_status: string
  has_historical_evidence: boolean
  confidence: EvidenceConfidence
  support_need: {
    status: 'none' | 'unknown' | 'needs_support'
    reason_code: string
    confidence: EvidenceConfidence
    evidence_refs: string[]
  }
  evidence_refs: LearnerEvidenceRef[]
  observed_at?: string | null
  valid_until?: string | null
}

export interface LearnerModelItem {
  objective_id: string
  objective_revision_id: string
  node_id: string
  node_name: string
  reason_code: string
  confidence: EvidenceConfidence
  evidence_refs: string[]
  observed_at?: string | null
  valid_until?: string | null
}

export interface LearnerModelProjection {
  schema_version: 'learner_model_v1'
  model_revision_id: string
  user_id: string
  course_id: string
  course_version_id: string
  source_revision_vector: Record<string, string | number>
  observed_at?: string | null
  data_sufficiency: {
    level: EvidenceSufficiency
    formal_evidence_count: number
    total_evidence_count: number
    covered_objective_count: number
    reason_code: string
  }
  summary: {
    total_objectives: number
    started_objectives: number
    learned_objectives: number
    mastered_objectives: number
    needs_attention_objectives: number
    formal_evidence_count: number
    active_record_count: number
  }
  objectives: LearnerObjectiveModel[]
  strengths: LearnerModelItem[]
  needs_attention: LearnerModelItem[]
  self_reports: Array<Record<string, unknown>>
  evidence_catalog: LearnerEvidenceRef[]
  model_policy: {
    deterministic: boolean
    ai_writable: boolean
    reading_is_mastery: boolean
    legacy_profile_included: boolean
    learning_os_included: boolean
  }
}

export interface LearnerModelSummary {
  model_revision_id: string
  observed_at?: string | null
  data_sufficiency: LearnerModelProjection['data_sufficiency']
  summary: LearnerModelProjection['summary']
  current_objective?: LearnerObjectiveModel | null
  strengths: LearnerModelItem[]
  needs_attention: LearnerModelItem[]
}

export const useLearnerModelStore = defineStore('learnerModel', {
  state: () => ({
    courseId: '',
    model: null as LearnerModelProjection | null,
    loading: false,
    error: '',
    requestSequence: 0,
  }),
  actions: {
    async load(courseId: string) {
      if (!courseId) return null
      const request = ++this.requestSequence
      this.loading = true
      this.error = ''
      try {
        const response = await http.get<LearnerModelProjection>(`/api/courses/${courseId}/learner-model`)
        if (request !== this.requestSequence) return this.model
        this.courseId = courseId
        this.model = response.data
        return this.model
      } catch (error) {
        if (request === this.requestSequence) {
          this.error = error instanceof Error ? error.message : 'learner_model_unavailable'
        }
        throw error
      } finally {
        if (request === this.requestSequence) this.loading = false
      }
    },
    clear() {
      this.courseId = ''
      this.model = null
      this.error = ''
      this.requestSequence += 1
    },
  },
})
