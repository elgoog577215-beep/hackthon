import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { studyApi, studySession } from '@/api/study'
import { getStudyIdentity, setStudyIdentity } from '@/utils/study-identity'

const qizhi = vi.hoisted(() => ({ token: '' }))
vi.mock('@/utils/http', () => ({
  getQizhiAccessToken: () => qizhi.token,
  INTERACTIVE_READ_TIMEOUT_MS: 10000,
  withApiBase: (path: string) => path,
}))

beforeEach(() => {
  qizhi.token = ''
  studySession.set('expired-local-session')
  vi.stubGlobal('fetch', vi.fn(async (_url: string, options: RequestInit) => {
    const authorization = new Headers(options.headers).get('Authorization')
    return {
      ok: authorization !== 'Bearer expired-local-session',
      status: authorization ? 401 : 200,
      json: async () => authorization
        ? { detail: '登录已失效，请重新登录' }
        : { local_login_enabled: true, token: 'new-session' },
    }
  }))
})

afterEach(() => { studySession.clear(); vi.unstubAllGlobals() })

describe('student login recovery', () => {
  it('discovers login and submits credentials while an expired session is stored', async () => {
    expect(await studyApi.config()).toMatchObject({ local_login_enabled: true })
    expect(await studyApi.guest()).toMatchObject({ token: 'new-session' })
    expect(await studyApi.login('student_demo', 'test-password', false)).toMatchObject({ token: 'new-session' })
    expect(await studyApi.login('new_student', 'test-password', true)).toMatchObject({ token: 'new-session' })
    expect(studySession.get()).toBe('expired-local-session')
  })

  it('also omits a stale unified token from public login requests', async () => {
    qizhi.token = 'expired-qizhi-session'
    await studyApi.config()
    await studyApi.login('student_demo', 'test-password', false)
    for (const [, options] of vi.mocked(fetch).mock.calls) {
      expect(new Headers(options?.headers).has('Authorization')).toBe(false)
    }
  })

  it('keeps protected requests authenticated and rejects an expired session', async () => {
    await expect(studyApi.me()).rejects.toMatchObject({ status: 401 })
    expect(new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).get('Authorization'))
      .toBe('Bearer expired-local-session')
  })
})


it('keeps a verified session usable without browser storage and masks it after logout', async () => {
  const user = { id: 'student-new', username: 'student', role: 'student' }
  const writes = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError') })
  const removals = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new DOMException('Denied', 'SecurityError') })
  try {
    studySession.set('new-session')
    setStudyIdentity(user)
    expect(studySession.get()).toBe('new-session')
    expect(getStudyIdentity()).toEqual(user)
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => user } as Response)
    await studyApi.me()
    expect(new Headers(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers).get('Authorization')).toBe('Bearer new-session')
    studySession.clear()
    expect(studySession.get()).toBe('')
    expect(getStudyIdentity()).toBeNull()
  } finally { writes.mockRestore(); removals.mockRestore() }
  // Storage still contains the old token, but a failed clear must not revive it.
  expect(studySession.get()).toBe('')
  expect(getStudyIdentity()).toBeNull()
  studySession.clear()
})
