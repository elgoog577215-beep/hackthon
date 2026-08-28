import { afterEach, describe, expect, it, vi } from 'vitest'
import { createUuid } from '@/utils/client-id'

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

describe('createUuid', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses crypto.randomUUID when the secure-context API is available', () => {
    const randomUUID = vi.fn(() => '11111111-1111-4111-8111-111111111111')
    vi.stubGlobal('crypto', { randomUUID })

    expect(createUuid()).toBe('11111111-1111-4111-8111-111111111111')
    expect(randomUUID).toHaveBeenCalledOnce()
  })

  it('builds a UUID with getRandomValues when randomUUID is unavailable over HTTP', () => {
    const getRandomValues = vi.fn((target: Uint8Array) => {
      target.set(Array.from({ length: 16 }, (_, index) => index))
      return target
    })
    vi.stubGlobal('crypto', { getRandomValues })

    expect(createUuid()).toBe('00010203-0405-4607-8809-0a0b0c0d0e0f')
    expect(getRandomValues).toHaveBeenCalledOnce()
  })

  it('keeps returning valid distinct UUIDs when Web Crypto is absent', () => {
    vi.stubGlobal('crypto', undefined)

    const first = createUuid()
    const second = createUuid()

    expect(first).toMatch(UUID_V4)
    expect(second).toMatch(UUID_V4)
    expect(second).not.toBe(first)
  })
})
