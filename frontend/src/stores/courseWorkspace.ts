import { defineStore } from 'pinia'
import http from '../utils/http'
import { useLearningSessionStore } from './learningSession'
import { useLearningProgressStore, type LearningTaskRef, type NextLearningAction } from './learningProgress'

export type CourseWorkspaceMode = 'reading' | 'overview' | 'practice' | 'mastery' | 'blueprint' | 'versions'

export interface LearningAssetItem {
  asset_id: string
  revision_id: string
  node_id?: string
  [key: string]: any
}

export interface LearningAssetsResponse {
  course_id: string
  course_version_id?: string
  bundle_revision_id?: string
  plan: Record<string, any>
  quality_report: Record<string, any>
  course_availability: CourseLearningAvailability
  assets: Record<string, LearningAssetItem[]>
}

export interface CourseLearningAvailability {
  schema_version: 'course_learning_availability_v1'
  mode: 'standard' | 'reading_only' | 'compatibility'
  reason_code: string
  capabilities: Record<string, { status: string; reason_code: string }>
}

export type PracticeSaveState = 'idle' | 'saving' | 'saved' | 'local_only' | 'conflict'

export interface PracticeAttempt {
  attempt_id: string
  task_revision_id: string
  question_revision_id?: string
  revision: number
  status: 'in_progress' | 'submitted' | 'grading' | 'graded' | 'abandoned' | 'invalidated'
  attempt_number: number
  answer_payload: Record<string, any>
  revealed_hint_levels: number[]
  solution_revealed: boolean
  ai_support_level: number
  active_seconds: number
  result?: Record<string, any>
  [key: string]: any
}

export interface DiagnosticWorkflow {
  phase: 'practice' | 'diagnostic' | 'remediation' | 'validation' | 'resolved' | 'needs_support'
  case: Record<string, any> | null
  session: Record<string, any> | null
  current_task: LearningAssetItem | null
}

export interface FormalPracticeResponse {
  course_id: string
  course_version_id?: string
  node_id?: string
  scope: 'node' | 'final' | 'all'
  course_availability: CourseLearningAvailability
  practice_availability: {
    status: 'available' | 'unavailable' | 'degraded' | 'blocked' | 'empty'
    reason_code: string
    scope: 'node' | 'final' | 'all'
    node_id?: string
  }
  questions: LearningAssetItem[]
  active_attempts: PracticeAttempt[]
  summary: Record<string, number>
}

const practiceDraftKey = (courseId: string, attemptId: string) => `practice_attempt_draft_v1:${courseId}:${attemptId}`
const requestId = () => globalThis.crypto?.randomUUID?.() || `request-${Date.now()}-${Math.random().toString(16).slice(2)}`

export const useCourseWorkspaceStore = defineStore('courseWorkspace', {
  state: () => ({
    mode: 'reading' as CourseWorkspaceMode,
    practiceScope: 'node' as 'node' | 'final' | 'all',
    assets: null as LearningAssetsResponse | null,
    blueprint: null as any,
    versions: [] as any[],
    currentVersionId: '' as string,
    versionDiff: null as any,
    practice: null as FormalPracticeResponse | null,
    diagnosticWorkflow: null as DiagnosticWorkflow | null,
    currentQuestionIndex: 0,
    currentAttempt: null as PracticeAttempt | null,
    currentDraft: {} as Record<string, any>,
    revealedHints: [] as Array<Record<string, any>>,
    revealedSolution: null as Record<string, any> | null,
    practiceResult: null as Record<string, any> | null,
    practiceHistory: null as Record<string, any> | null,
    practiceLandingView: 'current' as 'current' | 'history' | 'needs_review',
    practiceNeedsReviewCount: 0,
    practiceSaveState: 'idle' as PracticeSaveState,
    practiceSubmitRequestId: '',
    practiceStartedAt: 0,
    requestedTaskRef: null as LearningTaskRef | null,
    taskResumeError: '',
    loading: false,
    practiceLoading: false,
    saving: false,
  }),
  actions: {
    async loadAssets(courseId: string, nodeId?: string) {
      this.loading = true
      try {
        const res = await http.get(`/api/courses/${courseId}/learning-assets`, {
          params: nodeId ? { node_id: nodeId } : undefined,
        })
        this.assets = res.data
        return res.data
      } finally {
        this.loading = false
      }
    },
    async loadPractice(courseId: string, nodeId?: string, scope: 'node' | 'final' | 'all' = 'node') {
      this.loading = true
      this.practiceLoading = true
      try {
        const res = await http.get(`/api/courses/${courseId}/practice`, {
          params: { scope, ...(nodeId ? { node_id: nodeId } : {}) },
        })
        try {
          await this.loadDiagnosticWorkflow(courseId, nodeId)
        } catch {
          this.diagnosticWorkflow = null
        }
        this.practice = res.data
        this.applyRequestedTask(courseId)
        this.currentQuestionIndex = Math.min(this.currentQuestionIndex, Math.max(0, (res.data.questions || []).length - 1))
        const question = this.currentPracticeQuestion
        const active = question
          ? (res.data.active_attempts || []).find((item: PracticeAttempt) => (
              item.task_revision_id || item.question_revision_id
            ) === (question.task_revision_id || question.revision_id))
          : null
        if (active && !this.currentAttempt && !this.taskResumeError) this.applyPracticeAttempt(courseId, active)
        if (
          this.currentAttempt?.status === 'in_progress'
          || (this.diagnosticWorkflow?.phase && !['practice', 'resolved', 'needs_support'].includes(this.diagnosticWorkflow.phase))
        ) await this.syncLearningTask(courseId)
        return res.data
      } finally {
        this.practiceLoading = false
        this.loading = false
      }
    },
    async loadDiagnosticWorkflow(courseId: string, nodeId?: string) {
      const res = await http.get(`/api/courses/${courseId}/diagnostics/active`, {
        params: nodeId ? { node_id: nodeId } : undefined,
      })
      this.applyDiagnosticWorkflow(res.data)
      return res.data as DiagnosticWorkflow
    },
    applyDiagnosticWorkflow(workflow: DiagnosticWorkflow | null) {
      this.diagnosticWorkflow = workflow
    },
    prepareLearningAction(action: NextLearningAction) {
      this.requestedTaskRef = action.task_ref || null
      this.taskResumeError = ''
      this.practiceLandingView = 'current'
      this.practiceScope = 'node'
    },
    applyRequestedTask(courseId: string) {
      const requested = this.requestedTaskRef
      if (!requested) return
      if (requested.kind === 'practice') {
        const attempt = (this.practice?.active_attempts || []).find(item => (
          item.attempt_id === requested.object_id
          && (item.task_revision_id || item.question_revision_id) === requested.task_revision_id
        ))
        const questionIndex = (this.practice?.questions || []).findIndex(item => (
          (item.task_revision_id || item.revision_id) === requested.task_revision_id
        ))
        if (questionIndex < 0 || (requested.object_id && !attempt)) {
          this.currentAttempt = null
          this.taskResumeError = 'target_not_active'
          return
        }
        this.currentQuestionIndex = questionIndex
        if (attempt) this.applyPracticeAttempt(courseId, attempt)
        else {
          this.currentAttempt = null
          this.currentDraft = {}
          this.practiceResult = null
          this.practiceSaveState = 'idle'
        }
        this.requestedTaskRef = null
        return
      }
      if (['diagnostic', 'remediation', 'validation'].includes(requested.kind)) {
        const currentTaskId = this.diagnosticWorkflow?.current_task?.task_revision_id || ''
        if (!currentTaskId || currentTaskId !== requested.task_revision_id) {
          this.currentAttempt = null
          this.taskResumeError = 'target_not_active'
          return
        }
        this.requestedTaskRef = null
      }
    },
    async startPracticeAttempt(courseId: string, taskRevisionId: string, forceNew = false) {
      const res = await http.post(`/api/courses/${courseId}/practice/attempts`, {
        task_revision_id: taskRevisionId,
        practice_run_id: this.practiceRunId(courseId),
        resume: !forceNew,
      })
      this.applyPracticeAttempt(courseId, res.data.attempt)
      this.practiceResult = res.data.attempt?.result || null
      this.practiceStartedAt = Date.now()
      await this.syncLearningTask(courseId)
      return res.data.attempt as PracticeAttempt
    },
    applyPracticeAttempt(courseId: string, attempt: PracticeAttempt) {
      this.currentAttempt = attempt
      const local = this.readPracticeDraft(courseId, attempt.attempt_id)
      this.currentDraft = local?.revision >= attempt.revision
        ? { ...(attempt.answer_payload || {}), ...(local.answer_payload || {}) }
        : { ...(attempt.answer_payload || {}) }
      this.revealedHints = []
      this.revealedSolution = attempt.solution_revealed ? {} : null
      this.practiceSaveState = local?.revision > attempt.revision ? 'local_only' : 'saved'
      this.practiceSubmitRequestId = ''
    },
    async savePracticeDraft(courseId: string) {
      const attempt = this.currentAttempt
      if (!attempt || attempt.status !== 'in_progress') return attempt
      const cached = {
        revision: attempt.revision,
        answer_payload: this.currentDraft,
        saved_at: new Date().toISOString(),
      }
      localStorage.setItem(practiceDraftKey(courseId, attempt.attempt_id), JSON.stringify(cached))
      this.practiceSaveState = 'saving'
      try {
        const res = await http.patch(`/api/courses/${courseId}/practice/attempts/${attempt.attempt_id}/draft`, {
          expected_revision: attempt.revision,
          answer_payload: this.currentDraft,
          active_seconds: this.practiceActiveSeconds,
        })
        this.currentAttempt = res.data.attempt
        localStorage.setItem(practiceDraftKey(courseId, attempt.attempt_id), JSON.stringify({
          revision: res.data.attempt.revision,
          answer_payload: this.currentDraft,
          saved_at: new Date().toISOString(),
        }))
        this.practiceSaveState = 'saved'
        return res.data.attempt
      } catch (error: any) {
        if (error?.response?.status === 409) {
          this.practiceSaveState = 'conflict'
          const current = error.response?.data?.detail?.current
          if (current) this.currentAttempt = current
        } else {
          this.practiceSaveState = 'local_only'
        }
        throw error
      }
    },
    async revealPracticeHint(courseId: string, level: number) {
      const attempt = this.currentAttempt
      if (!attempt) return null
      const res = await http.post(`/api/courses/${courseId}/practice/attempts/${attempt.attempt_id}/hints/${level}`, {
        expected_revision: attempt.revision,
      })
      this.currentAttempt = res.data.attempt
      const existing = this.revealedHints.findIndex(item => item.level === level)
      if (existing >= 0) this.revealedHints[existing] = res.data.hint
      else this.revealedHints.push(res.data.hint)
      await this.syncLearningTask(courseId)
      return res.data
    },
    async recordPracticeAiSupport(courseId: string, level = 1) {
      const attempt = this.currentAttempt
      if (!attempt) return null
      const res = await http.post(`/api/courses/${courseId}/practice/attempts/${attempt.attempt_id}/ai-support`, {
        expected_revision: attempt.revision,
        level,
        summary: '在正式练习中打开 AI 老师',
      })
      this.currentAttempt = res.data.attempt
      await this.syncLearningTask(courseId)
      return res.data
    },
    async revealPracticeSolution(courseId: string) {
      const attempt = this.currentAttempt
      if (!attempt) return null
      const res = await http.post(`/api/courses/${courseId}/practice/attempts/${attempt.attempt_id}/solution`, {
        expected_revision: attempt.revision,
      })
      this.currentAttempt = res.data.attempt
      this.revealedSolution = res.data.solution || {}
      await this.syncLearningTask(courseId)
      return res.data
    },
    async submitCurrentPractice(courseId: string) {
      const attempt = this.currentAttempt
      if (!attempt) return null
      if (this.practiceSaveState === 'saving') throw new Error('practice_draft_is_saving')
      if (this.practiceSaveState === 'conflict') throw new Error('practice_draft_has_conflict')
      this.practiceSubmitRequestId ||= requestId()
      const res = await http.post(`/api/courses/${courseId}/practice/attempts/${attempt.attempt_id}/submit`, {
        expected_revision: this.currentAttempt?.revision || attempt.revision,
        answer_payload: this.currentDraft,
        active_seconds: this.practiceActiveSeconds,
        request_id: this.practiceSubmitRequestId,
      })
      this.currentAttempt = res.data.attempt
      this.practiceResult = res.data.result || res.data.attempt?.result || null
      if (res.data.workflow) this.applyDiagnosticWorkflow(res.data.workflow)
      localStorage.removeItem(practiceDraftKey(courseId, attempt.attempt_id))
      this.practiceSaveState = 'saved'
      this.practiceSubmitRequestId = ''
      await this.syncLearningTask(courseId)
      return res.data
    },
    async retryCurrentPractice(courseId: string) {
      const question = this.currentPracticeQuestion
      if (!question) return null
      this.currentDraft = {}
      this.practiceResult = null
      this.revealedSolution = null
      return this.startPracticeAttempt(courseId, question.task_revision_id || question.revision_id, true)
    },
    async loadPracticeHistory(courseId: string, view: 'all' | 'needs_review' | 'legacy' = 'all', nodeId?: string) {
      const res = await http.get(`/api/courses/${courseId}/practice/history`, {
        params: { view, ...(nodeId ? { node_id: nodeId } : {}) },
      })
      this.practiceHistory = res.data
      if (view === 'needs_review') this.practiceNeedsReviewCount = (res.data.attempts || []).length
      return res.data
    },
    async migrateLegacyPracticeData(courseId: string, courseNodeIds: string[]) {
      const wrong = this.readLegacyArray('quiz_wrong_answers')
      const history = this.readLegacyArray('quiz_history')
      const allowed = new Set(courseNodeIds)
      const matchesCourse = (item: any) => !item?.nodeId || allowed.has(String(item.nodeId))
      const matchingWrong = wrong.filter(matchesCourse)
      const matchingHistory = history.filter(matchesCourse)
      if (!matchingWrong.length && !matchingHistory.length) return { created: 0 }
      const res = await http.post(`/api/courses/${courseId}/practice/migrate-legacy`, {
        wrong_answers: matchingWrong,
        quiz_history: matchingHistory,
      })
      this.writeLegacyArray('quiz_wrong_answers', wrong.filter(item => !matchesCourse(item)))
      this.writeLegacyArray('quiz_history', history.filter(item => !matchesCourse(item)))
      return res.data
    },
    readLegacyArray(key: string): any[] {
      try {
        const value = JSON.parse(localStorage.getItem(key) || '[]')
        return Array.isArray(value) ? value : []
      } catch {
        return []
      }
    },
    writeLegacyArray(key: string, values: any[]) {
      if (values.length) localStorage.setItem(key, JSON.stringify(values))
      else localStorage.removeItem(key)
    },
    nextPracticeQuestion() {
      const total = this.practice?.questions?.length || 0
      if (this.currentQuestionIndex < total - 1) this.currentQuestionIndex += 1
      this.currentAttempt = null
      this.currentDraft = {}
      this.practiceResult = null
      this.revealedHints = []
      this.practiceSaveState = 'idle'
      this.practiceSubmitRequestId = ''
      this.practiceStartedAt = Date.now()
    },
    readPracticeDraft(courseId: string, attemptId: string) {
      try {
        return JSON.parse(localStorage.getItem(practiceDraftKey(courseId, attemptId)) || 'null')
      } catch {
        return null
      }
    },
    practiceRunId(courseId: string) {
      const key = `practice_run_v1:${courseId}`
      const current = sessionStorage.getItem(key)
      if (current) return current
      const created = requestId().replace('request-', 'run-')
      sessionStorage.setItem(key, created)
      return created
    },
    async loadBlueprint(courseId: string) {
      this.loading = true
      try {
        const res = await http.get(`/api/courses/${courseId}/blueprint`)
        this.blueprint = res.data
        return res.data
      } finally {
        this.loading = false
      }
    },
    async saveBlueprint(courseId: string, draft: any) {
      this.saving = true
      try {
        const res = await http.put(`/api/courses/${courseId}/blueprint/draft`, draft)
        this.blueprint = {
          ...this.blueprint,
          draft: res.data.draft,
          has_unconfirmed_draft: true,
        }
        return res.data
      } finally {
        this.saving = false
      }
    },
    async confirmBlueprint(courseId: string) {
      const res = await http.post(`/api/courses/${courseId}/blueprint/confirm`)
      return res.data
    },
    async discardBlueprint(courseId: string) {
      await http.delete(`/api/courses/${courseId}/blueprint/draft`)
      await this.loadBlueprint(courseId)
    },
    async confirmCriterion(courseId: string, revisionId: string, confirmed: boolean) {
      const res = await http.post(
        `/api/courses/${courseId}/learning-assets/criteria/${revisionId}/confirm`,
        { confirmed },
      )
      await this.loadAssets(courseId)
      return res.data
    },
    async loadVersions(courseId: string) {
      this.loading = true
      try {
        const res = await http.get(`/api/courses/${courseId}/versions`)
        this.versions = res.data.versions || []
        this.currentVersionId = res.data.current_version_id || ''
        return res.data
      } finally {
        this.loading = false
      }
    },
    async compareVersions(courseId: string, left: string, right: string) {
      const res = await http.get(`/api/courses/${courseId}/versions/compare`, {
        params: { left, right },
      })
      this.versionDiff = res.data
      return res.data
    },
    async restoreVersion(courseId: string, versionId: string) {
      const res = await http.post(`/api/courses/${courseId}/versions/${versionId}/restore`, {
        reason: `从 ${versionId} 恢复`,
      })
      await this.loadVersions(courseId)
      return res.data
    },
    async syncLearningTask(courseId: string) {
      const learningSession = useLearningSessionStore()
      const learningProgress = useLearningProgressStore()
      const workflow = this.diagnosticWorkflow
      const phase = workflow?.phase || 'practice'
      const task = workflow?.current_task || null
      const caseData = workflow?.case || null
      const sessionData = workflow?.session || null
      let taskRef: LearningTaskRef | null = null
      if (task && ['diagnostic', 'remediation', 'validation'].includes(phase)) {
        const kind = phase as LearningTaskRef['kind']
        taskRef = {
          kind,
          object_id: kind === 'diagnostic'
            ? String(caseData?.diagnostic_case_id || '')
            : String(sessionData?.remediation_session_id || ''),
          task_revision_id: String(task.task_revision_id || task.revision_id || ''),
          status: 'active',
          context: {
            course_id: courseId,
            course_version_id: String(caseData?.course_version_id || sessionData?.course_version_id || this.practice?.course_version_id || ''),
            node_id: String(caseData?.node_id || task.node_id || ''),
            objective_id: String(caseData?.objective_id || task.objective_id || ''),
            objective_revision_id: String(caseData?.objective_revision_id || task.objective_revision_id || ''),
          },
          return_node_id: String(caseData?.return_anchor?.node_id || caseData?.node_id || task.node_id || ''),
        }
      } else if (this.currentAttempt?.status === 'in_progress') {
        const attempt = this.currentAttempt
        taskRef = {
          kind: 'practice',
          object_id: attempt.attempt_id,
          task_revision_id: attempt.task_revision_id || attempt.question_revision_id || '',
          status: attempt.status,
          context: {
            course_id: courseId,
            course_version_id: String(attempt.course_version_id || this.practice?.course_version_id || ''),
            node_id: String(attempt.node_id || ''),
            objective_id: String(attempt.objective_id || ''),
            objective_revision_id: String(attempt.objective_revision_id || ''),
          },
          return_node_id: String(attempt.node_id || ''),
        }
      }
      if (taskRef) learningSession.setTaskContext(taskRef)
      else learningSession.clearTaskContext(this.currentAttempt?.node_id)
      await learningSession.flush()
      await learningProgress.loadRuntime(courseId, taskRef?.context.node_id)
    },
  },
  getters: {
    currentPracticeQuestion(state): LearningAssetItem | null {
      if (state.diagnosticWorkflow?.current_task) return state.diagnosticWorkflow.current_task
      return state.practice?.questions?.[state.currentQuestionIndex] || null
    },
    practiceActiveSeconds(state): number {
      if (!state.practiceStartedAt) return state.currentAttempt?.active_seconds || 0
      return Math.max(
        state.currentAttempt?.active_seconds || 0,
        Math.round((Date.now() - state.practiceStartedAt) / 1000),
      )
    },
  },
})
