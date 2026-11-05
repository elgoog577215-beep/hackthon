import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getUsageAuthorization } from '@/utils/usage-authorization'
import { getActiveRequestIdentity, getQizhiAccessToken, isQizhiAuthRequired } from '@/utils/http'
import { getStudyIdentity, getStudyToken } from '@/utils/study-identity'
vi.mock('@/utils/http', () => ({ getActiveRequestIdentity: vi.fn(), getQizhiAccessToken: vi.fn(), isQizhiAuthRequired: vi.fn() }))
vi.mock('@/utils/study-identity', () => ({ getStudyIdentity: vi.fn(), getStudyToken: vi.fn() }))
beforeEach(() => {
  vi.mocked(isQizhiAuthRequired).mockReturnValue(false)
  vi.mocked(getQizhiAccessToken).mockReturnValue('')
  vi.mocked(getActiveRequestIdentity).mockReturnValue('teacher-browser')
  vi.mocked(getStudyIdentity).mockReturnValue({ id: 'local-student:one', username: 'guest', role: 'student' })
  vi.mocked(getStudyToken).mockReturnValue('student-session')
})
describe('usage event credentials', () => {
  it('authenticates the independent student without attaching their token to teacher events', () => {
    expect(getUsageAuthorization('local-student:one')).toBe('student-session')
    expect(getUsageAuthorization('teacher-browser')).toBe('')
  })
  it('defers another student or an expired session', () => {
    expect(getUsageAuthorization('local-student:two')).toBeNull()
    vi.mocked(getStudyToken).mockReturnValue('')
    expect(getUsageAuthorization('local-student:one')).toBeNull()
  })
  it('uses school credentials for the current identity, without local fallback', () => {
    vi.mocked(isQizhiAuthRequired).mockReturnValue(true)
    vi.mocked(getQizhiAccessToken).mockReturnValue('school-session')
    expect(getUsageAuthorization('teacher-browser')).toBe('school-session')
    expect(getUsageAuthorization('local-student:one')).toBeNull()
    vi.mocked(getQizhiAccessToken).mockReturnValue('')
    expect(getUsageAuthorization('teacher-browser')).toBeNull()
  })
})
