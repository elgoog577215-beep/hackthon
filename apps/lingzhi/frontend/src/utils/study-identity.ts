// The server verifies this session; the saved identity only selects a UI scope.
export const STUDY_SESSION_KEY = 'lingzhi_student_session_v1'
const IDENTITY_KEY = 'lingzhi_student_identity_v1'
export const getStudyToken = (): string => {
  try { return sessionStorage.getItem(STUDY_SESSION_KEY) || '' } catch { return '' }
}
export const getStudyIdentity = (): { id: string; username: string; role: string } | null => {
  try { return JSON.parse(sessionStorage.getItem(IDENTITY_KEY) || 'null') } catch { return null }
}
export const setStudyIdentity = (user: { id: string; username: string; role: string } | null) => {
  if (user) sessionStorage.setItem(IDENTITY_KEY, JSON.stringify(user))
  else sessionStorage.removeItem(IDENTITY_KEY)
}
