import { defineStore } from 'pinia'
import http from '../utils/http'

export interface TeachingPlanOperation {
  operation_id: string
  path: string
  before: unknown
  after: unknown
  source?: 'manual' | 'ai' | 'restore'
}

export interface TeachingPlanDraft {
  draft_id: string
  base_plan_revision_id: string
  base_course_document_revision: string
  changed_paths: string[]
  operations: TeachingPlanOperation[]
  validation?: TeachingPlanValidation
  updated_at?: string
}

export interface TeachingPlanValidation {
  passed: boolean
  issues?: Array<{ code?: string; message?: string; severity?: string }>
  blockers?: Array<{ code?: string; message?: string; severity?: string }>
}

export interface TeachingPlanImpactItem {
  group?: string
  type: string
  id: string
  reason: string
  status?: string
}

export interface TeachingPlanImpact {
  changed: TeachingPlanImpactItem[]
  needs_regeneration: TeachingPlanImpactItem[]
  stale: TeachingPlanImpactItem[]
  unchanged: TeachingPlanImpactItem[]
  blocked: TeachingPlanImpactItem[]
  blocking: boolean
}

export interface TeachingPlanChangeSet {
  change_set_id: string
  draft_id: string
  status: 'draft' | 'ready' | 'blocked' | 'stale' | 'superseded' | 'applied' | 'rejected'
  operations: TeachingPlanOperation[]
  validation?: TeachingPlanValidation
  impact_report?: TeachingPlanImpact
  created_at?: string
  applied_revision_id?: string
}

export interface TeachingPlanAICandidate {
  candidate_id: string
  draft_id: string
  status: 'ready' | 'accepted' | 'rejected' | 'stale'
  rationale?: string
  operations: TeachingPlanOperation[]
  validation?: TeachingPlanValidation
  impact_report?: TeachingPlanImpact
  created_at?: string
}

export interface TeachingPlanRevision {
  revision_id: string
  revision_number: number
  parent_revision_id?: string
  restored_from_revision_id?: string
  created_by?: string
  created_at?: string
  quality_report?: TeachingPlanValidation
}

export interface TeachingPlanWorkbench {
  course_id: string
  enabled: boolean
  available: boolean
  read_only_reason: string
  current_plan_revision_id: string
  course_document_revision: string
  draft: TeachingPlanDraft | null
  revisions: TeachingPlanRevision[]
  change_sets: TeachingPlanChangeSet[]
  ai_candidates: TeachingPlanAICandidate[]
  editable_fields: Array<{ path: string; state: 'editable' | 'readonly'; reason: string }>
  downstream: Record<string, unknown>
}

export interface TeachingPlanReview {
  draft_id: string
  base_plan_revision_id: string
  diff: { operations: TeachingPlanOperation[] }
  impact_report: TeachingPlanImpact
  validation: TeachingPlanValidation
}

const requestId = (prefix: string) => (
  `${prefix}_${typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}_${Math.random().toString(16).slice(2)}`}`
)

function apiErrorCode(error: any): string {
  const detail = error?.response?.data?.detail
  if (detail && typeof detail === 'object' && typeof detail.code === 'string') return detail.code
  return error?.response?.status === 409 ? 'teaching_plan_conflict' : 'teaching_plan_request_failed'
}

export const useTeachingPlanWorkbenchStore = defineStore('teachingPlanWorkbench', {
  state: () => ({
    courseId: '',
    workbench: null as TeachingPlanWorkbench | null,
    review: null as TeachingPlanReview | null,
    revisionDiff: null as {
      left_revision_id: string
      right_revision_id: string
      diff: { operations: TeachingPlanOperation[] }
    } | null,
    loading: false,
    savingPaths: [] as string[],
    errorCode: '',
  }),

  getters: {
    draft: state => state.workbench?.draft || null,
    isSaving: state => state.savingPaths.length > 0,
  },

  actions: {
    reset() {
      this.courseId = ''
      this.workbench = null
      this.review = null
      this.revisionDiff = null
      this.savingPaths = []
      this.errorCode = ''
    },

    applyWorkbench(workbench: TeachingPlanWorkbench) {
      if (this.courseId && this.courseId !== workbench.course_id) this.revisionDiff = null
      this.workbench = workbench
      this.courseId = workbench.course_id
    },

    async load(courseId: string) {
      if (!courseId) return this.reset()
      this.loading = true
      this.errorCode = ''
      try {
        const { data } = await http.get(`/api/courses/${courseId}/teaching-plan/workbench`, { silentError: true })
        this.applyWorkbench(data.workbench)
        return this.workbench
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async beginDraft() {
      if (!this.workbench || !this.courseId) return null
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/drafts`,
          {
            base_plan_revision_id: this.workbench.current_plan_revision_id,
            base_course_document_revision: this.workbench.course_document_revision,
            idempotency_key: requestId('create_draft'),
          },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
        this.review = null
        return this.draft
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async patchDraft(path: string, value: unknown, expectedValueHash = '') {
      const draft = this.draft
      if (!draft || !this.workbench || !this.courseId) return null
      this.errorCode = ''
      this.savingPaths = [...new Set([...this.savingPaths, path])]
      try {
        const { data } = await http.patch(
          `/api/courses/${this.courseId}/teaching-plan/drafts/${draft.draft_id}`,
          {
            path,
            value,
            expected_value_hash: expectedValueHash,
            base_plan_revision_id: draft.base_plan_revision_id,
            idempotency_key: requestId('patch_draft'),
          },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
        this.review = null
        return this.draft
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      } finally {
        this.savingPaths = this.savingPaths.filter(item => item !== path)
      }
    },

    async reviewDraft() {
      const draft = this.draft
      if (!draft || !this.courseId) return null
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/validate`,
          { draft_id: draft.draft_id, idempotency_key: requestId('validate_draft') },
          { silentError: true },
        )
        this.review = data.review
        return this.review
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async discardDraft() {
      const draft = this.draft
      if (!draft || !this.courseId) return
      this.errorCode = ''
      try {
        const { data } = await http.delete(
          `/api/courses/${this.courseId}/teaching-plan/drafts/${draft.draft_id}`,
          {
            data: { idempotency_key: requestId('discard_draft') },
            silentError: true,
          },
        )
        this.applyWorkbench(data.workbench)
        this.review = null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async createAiCandidate(paths: string[], instruction: string) {
      const draft = this.draft
      if (!draft || !this.courseId) return null
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/drafts/${draft.draft_id}/ai-candidates`,
          { paths, instruction, idempotency_key: requestId('ai_candidate') },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
        return this.workbench?.ai_candidates.find(item => item.status === 'ready') || null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async acceptAiCandidate(candidateId: string, operationIds: string[]) {
      if (!this.courseId) return null
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/ai-candidates/${candidateId}/accept`,
          { operation_ids: operationIds, idempotency_key: requestId('ai_accept') },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
        return this.draft
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async rejectAiCandidate(candidateId: string) {
      if (!this.courseId) return
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/ai-candidates/${candidateId}/reject`,
          { idempotency_key: requestId('ai_reject') },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async loadRevisionDiff(revisionId: string) {
      if (!this.courseId || !this.workbench) return null
      this.errorCode = ''
      try {
        const { data } = await http.get(
          `/api/courses/${this.courseId}/teaching-plan/revisions/${revisionId}/diff`,
          {
            params: { against: this.workbench.current_plan_revision_id },
            silentError: true,
          },
        )
        this.revisionDiff = data
        return this.revisionDiff
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async restoreRevision(revisionId: string) {
      if (!this.courseId) return null
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/revisions/${revisionId}/restore`,
          { idempotency_key: requestId('restore_revision') },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
        this.revisionDiff = null
        return data.receipt || null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async createChangeSet() {
      const draft = this.draft
      if (!draft || !this.courseId) return null
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/change-sets`,
          { draft_id: draft.draft_id, idempotency_key: requestId('create_change_set') },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
        const changeSet = this.workbench?.change_sets.find(item => item.draft_id === draft.draft_id)
        if (changeSet) {
          this.review = {
            draft_id: draft.draft_id,
            base_plan_revision_id: draft.base_plan_revision_id,
            diff: { operations: changeSet.operations || [] },
            impact_report: changeSet.impact_report || emptyImpact(),
            validation: changeSet.validation || { passed: false },
          }
        }
        return changeSet || null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async applyChangeSet(changeSetId: string) {
      if (!this.courseId) return null
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/change-sets/${changeSetId}/apply`,
          { idempotency_key: requestId('apply_change_set') },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
        this.review = null
        return data.receipt || null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },

    async rejectChangeSet(changeSetId: string) {
      if (!this.courseId) return null
      this.errorCode = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/change-sets/${changeSetId}/reject`,
          { idempotency_key: requestId('reject_change_set') },
          { silentError: true },
        )
        this.applyWorkbench(data.workbench)
        this.review = null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        throw error
      }
    },
  },
})

function emptyImpact(): TeachingPlanImpact {
  return {
    changed: [],
    needs_regeneration: [],
    stale: [],
    unchanged: [],
    blocked: [],
    blocking: false,
  }
}
