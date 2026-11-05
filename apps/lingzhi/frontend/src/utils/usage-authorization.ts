import { getActiveRequestIdentity, getQizhiAccessToken, isQizhiAuthRequired } from './http'
import { getStudyIdentity, getStudyToken } from './study-identity'

// Resolve credentials at delivery time. Never store tokens with queued events
// or send a previous learner's events with the current learner's session.
export const getUsageAuthorization = (ownerId: string): string | null => {
  if (isQizhiAuthRequired()) {
    return ownerId === getActiveRequestIdentity() ? getQizhiAccessToken() || null : null
  }
  if (ownerId.startsWith('local-student:')) {
    return ownerId === getStudyIdentity()?.id ? getStudyToken() || null : null
  }
  return ''
}
