// The server verifies this session; the saved identity only selects a UI scope.
export const STUDY_SESSION_KEY = 'lingzhi_student_session_v1'
const IDENTITY_KEY = 'lingzhi_student_identity_v1'
type StudyIdentity = { id: string; username: string; role: string }
// Keep the active page usable when browser storage is full or denied. Failed
// clears also mask stale stored values until a later write succeeds.
const memory = new Map<string, string | null>()
const unsaved = new Set<string>()
function read(key: string): string | null {
  if (unsaved.has(key)) return memory.get(key) ?? null
  try { const value = sessionStorage.getItem(key); memory.set(key, value); return value }
  catch { return memory.get(key) ?? null }
}
function write(key: string, value: string | null) {
  memory.set(key, value)
  try {
    if (value === null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
    unsaved.delete(key)
  } catch { unsaved.add(key) }
}
export const getStudyToken = (): string => read(STUDY_SESSION_KEY) || ''
export const setStudyToken = (token: string | null) => write(STUDY_SESSION_KEY, token)
export const getStudyIdentity = (): StudyIdentity | null => {
  try { return JSON.parse(read(IDENTITY_KEY) || 'null') } catch { return null }
}
export const setStudyIdentity = (user: StudyIdentity | null) => write(IDENTITY_KEY, user ? JSON.stringify(user) : null)
