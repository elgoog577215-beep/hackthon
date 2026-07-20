import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { activeLocale, setLocale } from '@/shared/i18n'

describe('i18n document language', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({}),
    })))
  })

  afterEach(async () => {
    await setLocale('zh')
    vi.unstubAllGlobals()
  })

  it('keeps the active locale and document language in sync', async () => {
    await setLocale('zh')
    expect(activeLocale.value).toBe('zh')
    expect(document.documentElement.lang).toBe('zh-CN')

    await setLocale('en')
    expect(activeLocale.value).toBe('en')
    expect(document.documentElement.lang).toBe('en')
  })
})
