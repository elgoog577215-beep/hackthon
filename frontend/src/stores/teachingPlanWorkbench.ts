import { defineStore } from 'pinia'
import http, { getTeacherIdentity, teacherIdentityHeaders } from '../utils/http'
import { createUuid } from '../utils/client-id'
import type { CourseTeachingPlanProjection } from './types'
import { postGenerationStream } from '../shared/generation-stream'

export interface TeachingPlanOperation {
  operation_id: string
  path: string
  before: unknown
  after: unknown
  source?: 'manual' | 'ai' | 'restore'
}

const teacherRequestConfig = <T extends Record<string, unknown>>(extra?: T) => ({
  headers: { 'X-User-Id': getTeacherIdentity() },
  ...(extra || {}),
})

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
  can_initialize: boolean
  read_only_reason: string
  current_plan_revision_id: string
  course_document_revision: string
  teaching_plan: CourseTeachingPlanProjection
  draft: TeachingPlanDraft | null
  revisions: TeachingPlanRevision[]
  change_sets: TeachingPlanChangeSet[]
  ai_candidates: TeachingPlanAICandidate[]
  // 后端 field_permission 返回三态；分小节的字段几乎都是
  // requires_impact_review（可写草稿，但应用前必须有完整影响报告）。
  editable_fields: Array<{
    path: string
    state: 'editable' | 'requires_impact_review' | 'readonly'
    reason: string
    value_hash?: string
  }>
  // 学科模板为每节提供的候选教学环节：前端据此渲染增删入口。
  // 必需环节由模板规定，取消勾选会被后端的必需环节合同拒绝。
  section_module_options?: Record<string, Array<{
    module_id: string
    label: string
    required: boolean
    selected: boolean
    output_contract: string
  }>>
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
  `${prefix}_${createUuid()}`
)

function apiErrorCode(error: any): string {
  if (typeof error?.code === 'string') return error.code
  const detail = error?.response?.data?.detail
  if (detail && typeof detail === 'object' && typeof detail.code === 'string') return detail.code
  return error?.response?.status === 409 ? 'teaching_plan_conflict' : 'teaching_plan_request_failed'
}

function apiErrorMessage(error: any): string {
  if (typeof error?.message === 'string' && error?.detail) return error.message
  const detail = error?.response?.data?.detail
  return detail && typeof detail === 'object' && typeof detail.message === 'string'
    ? detail.message
    : ''
}

// 领域错误的 details 里带着可执行信息（例如 redirect_to_outline_edit 的目录
// 编辑器 endpoint）。只记 code 会把这些信息丢掉，前端就只能显示一句文案、
// 没法真的把教师送过去。
function apiErrorDetail(error: any): Record<string, unknown> {
  if (error?.detail && typeof error.detail === 'object') return { ...error.detail }
  const detail = error?.response?.data?.detail
  return detail && typeof detail === 'object' ? { ...detail } : {}
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
    pendingAction: '' as '' | 'confirmSource' | 'initialize' | 'ai' | 'review' | 'apply' | 'restore' | 'discard',
    errorCode: '',
    errorMessage: '',
    errorDetail: {} as Record<string, unknown>,
    generationMessage: '',
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
      this.pendingAction = ''
      this.generationMessage = ''
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
    },

    applyWorkbench(workbench: TeachingPlanWorkbench) {
      if (this.courseId && this.courseId !== workbench.course_id) {
        this.review = null
        this.revisionDiff = null
        this.savingPaths = []
      }
      this.workbench = workbench
      this.courseId = workbench.course_id
    },

    async load(courseId: string) {
      if (!courseId) return this.reset()
      this.loading = true
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
      try {
        const { data } = await http.get(`/api/courses/${courseId}/teaching-plan/workbench`, teacherRequestConfig({ silentError: true }))
        this.applyWorkbench(data.workbench)
        return this.workbench
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async confirmGenerationPreview(courseId: string, sourceTaskId: string) {
      if (!courseId) return null
      this.pendingAction = 'confirmSource'
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/teacher/courses/${courseId}/authoring/confirm-generation-preview`,
          { confirm: true, source_task_id: sourceTaskId },
          teacherRequestConfig({ silentError: true }),
        )
        await this.load(courseId)
        return data
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.pendingAction = ''
      }
    },

    async initializeBaseline() {
      if (!this.workbench || !this.courseId) return null
      this.pendingAction = 'initialize'
      this.errorCode = ''
      this.errorMessage = ''
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/baseline`,
          {
            base_course_document_revision: this.workbench.course_document_revision,
            idempotency_key: requestId('initialize_plan'),
          },
          teacherRequestConfig({ silentError: true }),
        )
        this.applyWorkbench(data.workbench)
        return data.receipt || null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        throw error
      } finally {
        this.pendingAction = ''
      }
    },

    async beginDraft() {
      if (!this.workbench || !this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/drafts`,
          {
            base_plan_revision_id: this.workbench.current_plan_revision_id,
            base_course_document_revision: this.workbench.course_document_revision,
            idempotency_key: requestId('create_draft'),
          },
          teacherRequestConfig({ silentError: true }),
        )
        this.applyWorkbench(data.workbench)
        this.review = null
        return this.draft
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      }
    },

    async patchDraft(path: string, value: unknown, expectedValueHash?: string) {
      const draft = this.draft
      if (!draft || !this.workbench || !this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
      this.savingPaths = [...new Set([...this.savingPaths, path])]
      try {
        const { data } = await http.patch(
          `/api/courses/${this.courseId}/teaching-plan/drafts/${draft.draft_id}`,
          {
            path,
            value,
            expected_value_hash: expectedValueHash ?? (
              this.workbench.editable_fields.find(field => field.path === path)?.value_hash || ''
            ),
            base_plan_revision_id: draft.base_plan_revision_id,
            idempotency_key: requestId('patch_draft'),
          },
          teacherRequestConfig({ silentError: true }),
        )
        this.applyWorkbench(data.workbench)
        this.review = null
        return this.draft
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.savingPaths = this.savingPaths.filter(item => item !== path)
      }
    },

    async reviewDraft() {
      const draft = this.draft
      if (!draft || !this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.pendingAction = 'review'
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/validate`,
          { draft_id: draft.draft_id, idempotency_key: requestId('validate_draft') },
          teacherRequestConfig({ silentError: true }),
        )
        this.review = data.review
        return this.review
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.pendingAction = ''
      }
    },

    async discardDraft() {
      const draft = this.draft
      if (!draft || !this.courseId) return
      this.errorCode = ''
      this.errorMessage = ''
      this.pendingAction = 'discard'
      this.errorDetail = {}
      try {
        const { data } = await http.delete(
          `/api/courses/${this.courseId}/teaching-plan/drafts/${draft.draft_id}`,
          teacherRequestConfig({
            data: { idempotency_key: requestId('discard_draft') },
            silentError: true,
          }),
        )
        this.applyWorkbench(data.workbench)
        this.review = null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.pendingAction = ''
      }
    },

    async createAiCandidate(paths: string[], instruction: string) {
      const draft = this.draft
      if (!draft || !this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.pendingAction = 'ai'
      this.errorDetail = {}
      this.generationMessage = ''
      try {
        const data = await postGenerationStream<{ workbench: TeachingPlanWorkbench }>(
          `/api/courses/${this.courseId}/teaching-plan/drafts/${draft.draft_id}/ai-candidates`,
          { paths, instruction, idempotency_key: requestId('ai_candidate') },
          {
            headers: teacherIdentityHeaders(),
            onProgress: progress => {
              this.generationMessage = progress.message || ''
            },
          },
        )
        this.applyWorkbench(data.workbench)
        return this.workbench?.ai_candidates.find(item => item.status === 'ready') || null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.pendingAction = ''
        this.generationMessage = ''
      }
    },

    async acceptAiCandidate(candidateId: string, operationIds: string[]) {
      if (!this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/ai-candidates/${candidateId}/accept`,
          { operation_ids: operationIds, idempotency_key: requestId('ai_accept') },
          teacherRequestConfig({ silentError: true }),
        )
        this.applyWorkbench(data.workbench)
        return this.draft
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      }
    },

    async rejectAiCandidate(candidateId: string) {
      if (!this.courseId) return
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/ai-candidates/${candidateId}/reject`,
          { idempotency_key: requestId('ai_reject') },
          teacherRequestConfig({ silentError: true }),
        )
        this.applyWorkbench(data.workbench)
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      }
    },

    async loadRevisionDiff(revisionId: string) {
      if (!this.courseId || !this.workbench) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
      try {
        const { data } = await http.get(
          `/api/courses/${this.courseId}/teaching-plan/revisions/${revisionId}/diff`,
          teacherRequestConfig({
            params: { against: this.workbench.current_plan_revision_id },
            silentError: true,
          }),
        )
        this.revisionDiff = data
        return this.revisionDiff
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      }
    },

    async restoreRevision(revisionId: string) {
      if (!this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.pendingAction = 'restore'
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/revisions/${revisionId}/restore`,
          { idempotency_key: requestId('restore_revision') },
          teacherRequestConfig({ silentError: true }),
        )
        this.applyWorkbench(data.workbench)
        this.revisionDiff = null
        return data.receipt || null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.pendingAction = ''
      }
    },

    async createChangeSet() {
      const draft = this.draft
      if (!draft || !this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.pendingAction = 'review'
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/change-sets`,
          { draft_id: draft.draft_id, idempotency_key: requestId('create_change_set') },
          teacherRequestConfig({ silentError: true }),
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
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.pendingAction = ''
      }
    },

    async applyChangeSet(changeSetId: string) {
      if (!this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.pendingAction = 'apply'
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/change-sets/${changeSetId}/apply`,
          { idempotency_key: requestId('apply_change_set') },
          teacherRequestConfig({ silentError: true }),
        )
        this.applyWorkbench(data.workbench)
        this.review = null
        return data.receipt || null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
        throw error
      } finally {
        this.pendingAction = ''
      }
    },

    async rejectChangeSet(changeSetId: string) {
      if (!this.courseId) return null
      this.errorCode = ''
      this.errorMessage = ''
      this.errorDetail = {}
      try {
        const { data } = await http.post(
          `/api/courses/${this.courseId}/teaching-plan/change-sets/${changeSetId}/reject`,
          { idempotency_key: requestId('reject_change_set') },
          teacherRequestConfig({ silentError: true }),
        )
        this.applyWorkbench(data.workbench)
        this.review = null
      } catch (error) {
        this.errorCode = apiErrorCode(error)
        this.errorMessage = apiErrorMessage(error)
        this.errorDetail = apiErrorDetail(error)
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
