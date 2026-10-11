import { getQizhiAccessToken, withApiBase } from '../utils/http'

export type StudyPurpose = 'systematic' | 'exam_prep'
export interface StudyUser { id: string; username: string; role: string }
export interface StudySource { id: string; filename: string; sha256: string; status: string; warnings: string[]; error: string; sections: { id: string; title: string; characters: number }[] }
export interface StudyBlock { block_id: string; content_type: string; type_label: string; title: string; content: string; knowledge_names: string[]; answer_to: string }
export interface StudySection { id: string; title: string; blocks: StudyBlock[]; complete: boolean; fragment: string; source: { filename: string; asset_id: string; source_sha256: string } }
export interface StudySummary { id: string; title: string; purpose: StudyPurpose; status: string; task_id: string; updated_at: string }
export interface StudyMaterial extends StudySummary {
  sources: { node_id: string; title: string; filename: string; asset_id: string; source_sha256: string; characters: number }[]
  plans: unknown[]
  revisions: { id: string; status: string; sections: StudySection[] }[]
  notes: Record<string, { content: string; updated_at: string }>
  task?: { id: string; status: string; progress: number; completed_nodes: number; total_nodes: number; message: string; error_code: string }
}
export interface StudyGenerationRequest {
  request_id: string; title: string; purpose: StudyPurpose
  selections: { asset_id: string; section_id: string }[]
  level: string; time_minutes: number; requirements: string; language: 'zh' | 'en'
}
const SESSION_KEY = 'lingzhi_student_session_v1'
export const studySession = {
  get: () => sessionStorage.getItem(SESSION_KEY) || '',
  set: (token: string) => sessionStorage.setItem(SESSION_KEY, token),
  clear: () => sessionStorage.removeItem(SESSION_KEY),
}
export class StudyApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getQizhiAccessToken() || studySession.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(withApiBase(`/api/study${path}`), { ...options, headers })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    throw new StudyApiError(response.status, typeof detail === 'string' ? detail : detail?.message || body.error?.message || `HTTP ${response.status}`)
  }
  if (path.endsWith('/export') || path.endsWith('/download')) return await response.blob() as T
  return await response.json() as T
}
const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })
export const studyApi = {
  config: () => request<{ local_login_enabled: boolean; identity_provider: string }>('/auth/config'),
  me: () => request<StudyUser>('/auth/me'),
  login: (username: string, password: string, register: boolean) => request<{ token: string; user: StudyUser }>(`/auth/${register ? 'register' : 'login'}`, json({ username, password })),
  logout: () => request('/auth/logout', { method: 'POST' }),
  sources: () => request<StudySource[]>('/sources'),
  addText: (title: string, content: string) => request<StudySource>('/sources/text', json({ title, content })),
  upload: (file: File) => { const form = new FormData(); form.append('file', file); return request<StudySource>('/sources/upload', { method: 'POST', body: form }) },
  downloadSource: (id: string) => request<Blob>(`/sources/${encodeURIComponent(id)}/download`),
  list: () => request<StudySummary[]>('/materials'),
  generate: (body: StudyGenerationRequest) => request<StudyMaterial>('/materials', json(body)),
  get: (id: string) => request<StudyMaterial>(`/materials/${encodeURIComponent(id)}`),
  resume: (id: string) => request(`/materials/${encodeURIComponent(id)}/continue`, { method: 'POST' }),
  note: (id: string, revision_id: string, content: string) => request<{ content: string; updated_at: string }>(`/materials/${encodeURIComponent(id)}/note`, { ...json({ revision_id, content }), method: 'PUT' }),
  export: (id: string) => request<Blob>(`/materials/${encodeURIComponent(id)}/export`),
}
