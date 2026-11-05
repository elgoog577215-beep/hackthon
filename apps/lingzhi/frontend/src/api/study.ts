import { getQizhiAccessToken, INTERACTIVE_READ_TIMEOUT_MS, withApiBase } from '../utils/http'
import { getStudyToken, setStudyToken, setStudyIdentity } from '../utils/study-identity'
import { studyCopy } from '../shared/study-copy'
import type { NextLearningAction } from '../stores/learningProgress'

export type StudyPurpose = 'systematic' | 'exam_prep'
export type StudyGenerationMode = 'direct' | 'materials'
export const STUDY_UPLOAD_ACCEPT = '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.md,.markdown,.txt,.csv,.json,.py,.js,.ts,.html,.css,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff'
export interface StudyUser { id: string; username: string; role: string; guest?: boolean }
export interface StudySource { id: string; filename: string; sha256: string; status: string; warnings: string[]; error: string; sections: { id: string; title: string; characters: number }[] }
export interface StudyBlock { block_id: string; content_type: string; type_label: string; title: string; content: string; knowledge_names: string[]; answer_to: string }
export interface StudySection { id: string; title: string; blocks: StudyBlock[]; complete: boolean; fragment: string; source?: { kind?: 'uploaded' | 'ai_generated'; filename?: string; asset_id?: string; source_sha256?: string } }
export interface StudySummary { id: string; title: string; purpose: StudyPurpose; generation_mode?: StudyGenerationMode; status: string; task_id: string; updated_at: string; source_course_ids?: string[] }
export interface StudyMaterial extends StudySummary {
  sources: { node_id: string; title: string; filename: string; asset_id: string; source_sha256: string; characters: number }[]
  concepts_complete?: boolean
  reading_tools_complete?: boolean
  reading_tool_states?: Record<string, import('../utils/handout-paths').ReadingToolState>
  plans: unknown[]
  revisions: { id: string; status: string; sections: StudySection[] }[]
  notes: Record<string, { content?: string; updated_at: string; entries?: StudyNote[] }>
  task?: { id: string; status: string; progress: number; phase_progress?: number; completed_nodes: number; total_nodes: number; message: string; error_code: string }
}
export interface StudyGenerationRequest {
  request_id: string; title: string; purpose: StudyPurpose
  selections: { asset_id: string; section_id: string }[]
  level: string; time_minutes: number; requirements: string; language: 'zh' | 'en'
}
export interface StudyNote {
  id: string; revision_id: string; section_id: string; section_title: string; block_id: string; block_title: string; content_type: string
  quote: string; anchor_prefix: string; anchor_suffix: string; content: string; kind: 'mark' | 'note'; question_state: 'none' | 'open' | 'answered'
  important: boolean; version: number; source_type: 'self' | 'ai'; source_message_id?: string; created_at: string; updated_at: string; source_sha256: string
  location_status: 'current' | 'changed' | 'missing' | 'historical'
}
export interface StudyNoteInput {
  request_id: string; revision_id: string; section_id: string; block_id: string; quote: string; anchor_prefix?: string; anchor_suffix?: string
  content: string; kind: StudyNote['kind']; question_state: StudyNote['question_state']; important: boolean; source_message_id?: string
}
export interface NoteDraftSuggestion { noteId: string; noteVersion: number; content: string; messageId: string; basedOnDraft: string }
export interface AssistantContext { section_id: string; section_title: string; block_id: string; block_title: string; quote: string; note_id?: string; note_version?: number }
export interface AssistantMessage { message_id: string; role: 'user' | 'assistant'; content: string; status: string; context_ref: AssistantContext; task_ref?: { task_id: string }; note_draft?: string; note_version?: number; based_on_note_draft?: string }
export interface AssistantConversation { conversation_id: string; messages: AssistantMessage[] }
export const studySession = {
  get: getStudyToken,
  set: setStudyToken,
  clear: () => { setStudyToken(null); setStudyIdentity(null) },
}
export class StudyApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  // Login discovery and credentials must remain usable after a session expires.
  const publicAuth = ['/auth/config', '/auth/login', '/auth/register', '/auth/guest'].includes(path)
  const token = publicAuth ? '' : getQizhiAccessToken() || studySession.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const binary = path.endsWith('/export') || path.endsWith('/download')
  const controller = new AbortController()
  const abort = () => controller.abort(options.signal?.reason)
  if (options.signal?.aborted) abort()
  else options.signal?.addEventListener('abort', abort, { once: true })
  let timedOut = false
  const upload = typeof FormData !== 'undefined' && options.body instanceof FormData
  const timeout = upload ? 0 : !binary && (!options.method || options.method === 'GET') ? INTERACTIVE_READ_TIMEOUT_MS : 120000
  const timer = timeout ? setTimeout(() => { timedOut = true; controller.abort() }, timeout) : undefined
  try {
    const response = await fetch(withApiBase(`/api/study${path}`), { ...options, headers, signal: controller.signal })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      const detail = body.detail
      throw new StudyApiError(response.status, typeof detail === 'string' ? detail : detail?.message || body.error?.message || `HTTP ${response.status}`)
    }
    if (binary) return await response.blob() as T
    return await response.json() as T
  } catch (error) {
    if (timedOut) throw new StudyApiError(408, studyCopy('requestTimeout'))
    throw error
  } finally {
    if (timer) clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}
const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })
export const studyApi = {
  courses: (signal?: AbortSignal) => request<StudyCourse[]>('/courses', { signal }),
  path: (id: string) => request<StudyLearningPath>(`/courses/${encodeURIComponent(id)}/path`),
  courseSource: (id: string, revision_id: string) => request<StudySource>(`/courses/${encodeURIComponent(id)}/sources`, json({ revision_id })),
  updateCourse: (id: string, expected_release_id: string) => request(`/courses/${encodeURIComponent(id)}/exchange/update`, json({ expected_release_id })),
  coursePpt: (id: string, assetId: string, expected_release_id: string) => request<Blob>(`/courses/${encodeURIComponent(id)}/exchange/ppt/${encodeURIComponent(assetId)}/download`, json({ expected_release_id })),
  courseFeedback: (id: string) => request<{ items: CourseFeedback[]; replies_available: boolean }>(`/courses/${encodeURIComponent(id)}/exchange/feedback`),
  sendCourseFeedback: (id: string, body: { request_id: string; expected_release_id: string; text: string }) => request<{ feedback_id: string; status: string }>(`/courses/${encodeURIComponent(id)}/exchange/feedback`, json(body)),
  retryCourseFeedback: (id: string, feedbackId: string) => request(`/courses/${encodeURIComponent(id)}/exchange/feedback/${encodeURIComponent(feedbackId)}/retry`, { method: 'POST' }),
  config: () => request<{ local_login_enabled: boolean; identity_provider: string; development_identity?: boolean; guest_login_enabled?: boolean }>('/auth/config'),
  guest: () => request<{ token: string; user: StudyUser }>('/auth/guest', { method: 'POST' }),
  me: () => request<StudyUser>('/auth/me'),
  login: (username: string, password: string, register: boolean) => request<{ token: string; user: StudyUser }>(`/auth/${register ? 'register' : 'login'}`, json({ username, password })),
  logout: () => request('/auth/logout', { method: 'POST' }),
  sources: () => request<StudySource[]>('/sources'),
  addText: (title: string, content: string) => request<StudySource>('/sources/text', json({ title, content })),
  upload: (file: File) => { const form = new FormData(); form.append('file', file); return request<StudySource>('/sources/upload', { method: 'POST', body: form }) },
  downloadSource: (id: string) => request<Blob>(`/sources/${encodeURIComponent(id)}/download`),
  list: (signal?: AbortSignal) => request<StudySummary[]>('/materials', { signal }),
  generate: (body: StudyGenerationRequest) => request<StudyMaterial>('/materials', json(body)),
  get: (id: string) => request<StudyMaterial>(`/materials/${encodeURIComponent(id)}`),
  resume: (id: string) => request(`/materials/${encodeURIComponent(id)}/continue`, { method: 'POST' }),
  note: (id: string, revision_id: string, content: string) => request<{ content: string; updated_at: string }>(`/materials/${encodeURIComponent(id)}/note`, { ...json({ revision_id, content }), method: 'PUT' }),
  listNotes: (id: string, revisionId?: string) => request<{ entries: StudyNote[] }>(`/materials/${encodeURIComponent(id)}/notes${revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : ''}`),
  createNote: (id: string, body: StudyNoteInput) => request<StudyNote>(`/materials/${encodeURIComponent(id)}/notes`, json(body)),
  updateNote: (id: string, noteId: string, body: { expected_version: number; content?: string; kind?: StudyNote['kind']; question_state?: StudyNote['question_state']; important?: boolean; source_message_id?: string }) => request<StudyNote>(`/materials/${encodeURIComponent(id)}/notes/${encodeURIComponent(noteId)}`, { ...json(body), method: 'PATCH' }),
  deleteNote: (id: string, noteId: string, version: number) => request(`/materials/${encodeURIComponent(id)}/notes/${encodeURIComponent(noteId)}?expected_version=${version}`, { method: 'DELETE' }),
  export: (id: string) => request<Blob>(`/materials/${encodeURIComponent(id)}/export`),
  assistant: (id: string) => request<AssistantConversation>(`/materials/${encodeURIComponent(id)}/assistant`),
  ask: (id: string, body: { request_id: string; revision_id: string; section_id: string; block_id: string; quote: string; text: string; language: 'zh' | 'en'; note_id?: string; note_version?: number; note_draft?: string }) => request<AssistantConversation>(`/materials/${encodeURIComponent(id)}/assistant`, json(body)),
  continueAnswer: (id: string, taskId: string) => request(`/materials/${encodeURIComponent(id)}/assistant/${encodeURIComponent(taskId)}/continue`, { method: 'POST' }),
}
export interface PublishedCoursePpt { asset_id: string; filename: string; sha256: string; size_bytes: number }
export interface StudyCourse { course_id: string; title: string; revision_id: string; section_count: number; reading_available: boolean; grant: { grant_id: string; label: string }; exchange_origin?: { node_id: string; source_course_id: string; release_id: string }; update_available?: boolean; question_count?: number; feedback_policy?: { formal_practice: string; personal_materials: string }; published_ppts?: PublishedCoursePpt[] }
export interface CourseFeedback { feedback_id: string; kind: 'course_question' | 'practice_result'; payload: { text?: string; attempt_id?: string }; status: string; created_at: string; reply?: string; revision?: number }
export interface StudyLearningPath { course_id: string; next_action: NextLearningAction; chapter: { chapter_id: string; chapter_name: string }; attempt_count: number; steps: { chapter_id: string; title: string; progress: { learning: string; mastery: string }; action: NextLearningAction }[] }
