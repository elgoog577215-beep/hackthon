import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'
import { activeLocale, localeResourceUrl, setLocale } from '@/shared/i18n'

function messageAt(messages: Record<string, unknown>, key: string): unknown {
  return key.split('.').reduce<unknown>((current, segment) => (
    current && typeof current === 'object'
      ? (current as Record<string, unknown>)[segment]
      : undefined
  ), messages)
}

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

  it('resolves locale files under the production Vite base path', () => {
    expect(localeResourceUrl('zh', '/lingzhi/'))
      .toBe('/lingzhi/locales/zh/translation.json')
    expect(localeResourceUrl('en', '/'))
      .toBe('/locales/en/translation.json')
  })

  it('requests translation JSON through the active Vite base path resolver', async () => {
    await setLocale('en')

    expect(fetch).toHaveBeenLastCalledWith(
      localeResourceUrl('en'),
      {
        cache: 'no-cache',
        headers: { Accept: 'application/json' },
      },
    )
  })

  it('covers every teacher calendar translation key in both locales', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/views/TeacherTeachingCalendarView.vue'),
      'utf8',
    )
    const literalKeys = [...source.matchAll(/\bt\(\s*['"]([^'"]+)['"]/g)]
      .map(match => match[1])
      .filter((key): key is string => Boolean(key))
    const keys = [
      ...new Set([
        ...literalKeys,
        ...Array.from({ length: 7 }, (_, index) => `teacherHome.weekdays.${index + 1}`),
      ]),
    ]

    for (const [locale, messages] of [['zh', zhMessages], ['en', enMessages]] as const) {
      for (const key of keys) {
        expect(messageAt(messages, key), `${locale}:${key}`).toEqual(expect.any(String))
      }
    }
  })
})
