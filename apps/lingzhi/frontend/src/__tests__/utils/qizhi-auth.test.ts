import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('Qizhi production authentication bridge', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubEnv('VITE_QIZHI_AUTH_REQUIRED', 'true')
    localStorage.clear()
    sessionStorage.clear()
  })

  it('attaches the shared-origin Qizhi token to HTTP and WebSocket requests', async () => {
    localStorage.setItem('auth_token', 'header.payload.signature')
    const {
      getQizhiAccessToken,
      qizhiWebSocketProtocols,
      teacherIdentityHeaders,
    } = await import('../../utils/http')

    expect(getQizhiAccessToken()).toBe('header.payload.signature')
    expect(teacherIdentityHeaders().get('Authorization')).toBe(
      'Bearer header.payload.signature',
    )
    expect(qizhiWebSocketProtocols()).toEqual([
      'lingzhi-auth-v1',
      'qizhi-bearer.header.payload.signature',
    ])
  })
})
