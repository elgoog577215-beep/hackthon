import { getQizhiAccessToken, INTERACTIVE_READ_TIMEOUT_MS, withApiBase } from '../utils/http'
import { getStudyToken } from '../utils/study-identity'
import { practiceCopy } from '../shared/study-practice-copy'

export type PracticeIntent = 'practice' | 'correction' | 'retry'
export type PracticeErrorType = 'unknown' | 'concept' | 'condition' | 'method' | 'execution' | 'expression'
export type PracticeReviewState = 'needs_review' | 'corrected' | 'revisit'
export interface PracticeReview { error_type: PracticeErrorType; reflection: string; state: PracticeReviewState }
export interface PersonalPracticeQuestion {
  question_id: string; question_revision_id: string; section_id: string; section_title: string
  block_id: string; title: string; prompt: string; has_answer: boolean; has_hint: boolean
}
export interface PersonalPracticeAttempt {
  attempt_id: string; revision: number; status: 'in_progress' | 'submitted' | 'grading' | 'graded'
  grading_state?: 'idle' | 'running' | 'interrupted' | 'pending_review' | 'complete'
  can_request_grade?: boolean; grading_retry_after_seconds?: number
  question_revision_id: string; node_id: string; node_name: string
  answer_payload: { text: string }; submitted_answer_payload?: { text: string }
  result?: { status: string; score?: number; passed: boolean | null; feedback: string; grading_confidence: number; mastery_eligible: false; grading_method: string }
  solution_revealed: boolean; revealed_hints: { level: number; content: string }[]
  origin_attempt_id?: string; can_continue?: boolean; created_at?: string; updated_at?: string; attempt_number?: number; solution_exposure_origin_attempt_id?: string
  metadata: { material_id: string; revision_id: string; block_id: string; title: string; prompt: string; intent: PracticeIntent; review?: PracticeReview; review_updated?: boolean; has_answer?: boolean }
}
export interface PersonalPracticeIndex { material_id: string; revision_id: string; questions: PersonalPracticeQuestion[]; attempts: PersonalPracticeAttempt[] }
export class PersonalPracticeApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
async function request<T>(materialId: string, path = '', options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const abort = () => controller.abort(options.signal?.reason)
  if (options.signal?.aborted) abort()
  else options.signal?.addEventListener('abort', abort, { once: true })
  let timedOut = false
  const timeout = setTimeout(() => { timedOut = true; controller.abort() }, !options.method || options.method === 'GET' ? INTERACTIVE_READ_TIMEOUT_MS : 120000)
  const headers = new Headers(options.headers)
  const token = getQizhiAccessToken() || getStudyToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body) headers.set('Content-Type', 'application/json')
  try {
    const response = await fetch(withApiBase(`/api/study/materials/${encodeURIComponent(materialId)}/practice${path}`), { ...options, headers, signal: controller.signal })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new PersonalPracticeApiError(response.status, typeof body.detail === 'string' ? body.detail : body.detail?.message || body.error?.message || `HTTP ${response.status}`)
    }
    return await response.json() as T
  } catch (error) {
    if (timedOut) throw new PersonalPracticeApiError(408, practiceCopy('timeout'))
    throw error
  } finally {
    clearTimeout(timeout)
    options.signal?.removeEventListener('abort', abort)
  }
}
const json = (body: unknown, method = 'POST'): RequestInit => ({ method, body: JSON.stringify(body) })
const attemptPath = (attemptId: string) => `/attempts/${encodeURIComponent(attemptId)}`
export const personalPracticeApi = {
  list: (materialId: string, signal?: AbortSignal) => request<PersonalPracticeIndex>(materialId, '', { signal }),
  start: (materialId: string, body: { revision_id: string; question_id: string; request_id: string; intent: PracticeIntent; origin_attempt_id?: string; language: 'zh' | 'en' }) => request<PersonalPracticeAttempt>(materialId, '/attempts', json(body)),
  saveDraft: (materialId: string, attemptId: string, body: { expected_revision: number; answer: string }) => request<PersonalPracticeAttempt>(materialId, `${attemptPath(attemptId)}/draft`, json(body, 'PUT')),
  hint: (materialId: string, attemptId: string, expected_revision: number) => request<{ attempt: PersonalPracticeAttempt; content: string }>(materialId, `${attemptPath(attemptId)}/hint`, json({ expected_revision })),
  solution: (materialId: string, attemptId: string, expected_revision: number) => request<{ attempt: PersonalPracticeAttempt; content: string }>(materialId, `${attemptPath(attemptId)}/solution`, json({ expected_revision })),
  submit: (materialId: string, attemptId: string, body: { request_id: string; expected_revision: number; answer: string }) => request<PersonalPracticeAttempt>(materialId, `${attemptPath(attemptId)}/submit`, json(body)),
  grade: (materialId: string, attemptId: string, expected_revision: number) => request<PersonalPracticeAttempt>(materialId, `${attemptPath(attemptId)}/grade`, json({ expected_revision })),
  review: (materialId: string, attemptId: string, body: PracticeReview & { expected_revision: number }) => request<PersonalPracticeAttempt>(materialId, `${attemptPath(attemptId)}/review`, json(body, 'PUT')),
}
