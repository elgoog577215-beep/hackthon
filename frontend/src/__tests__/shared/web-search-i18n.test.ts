import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import enLocale from '../../../public/locales/en/translation.json'
import zhLocale from '../../../public/locales/zh/translation.json'

/**
 * The backend emits machine codes (message_code / reason / status) that the
 * teacher-facing UI must render as human text. If the backend adds a code and
 * the locales miss it, the UI would show a raw identifier like
 * "web_search_provider_failed". These tests read the real backend sources so
 * that drift fails here instead of shipping.
 */

const BACKEND = resolve(__dirname, '../../../../backend')

const readBackend = (name: string): string =>
  readFileSync(resolve(BACKEND, name), 'utf8')

interface WebSearchTranslations {
  messageCode: Record<string, string>
  reason: Record<string, string>
  status: Record<string, string>
  gatewayError: Record<string, string>
}

const webSearch = (locale: typeof enLocale): WebSearchTranslations =>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (locale as any).courseGeneration.materials.webSearch

const uniqueMatches = (source: string, pattern: RegExp): string[] => {
  const found = new Set<string>()
  for (const match of source.matchAll(pattern)) {
    if (match[1]) found.add(match[1])
  }
  return [...found].sort()
}

describe('web search i18n coverage', () => {
  const search = readBackend('web_material_search.py')
  const gateway = readBackend('web_retrieval.py')
  const service = readBackend('course_service.py')

  it('translates every message_code the backend emits', () => {
    const emitted = uniqueMatches(
      search + service,
      /message_code(?:=|":\s*)"(web_search_[a-z_]+)"/g,
    )
    // Guard against the regex silently matching nothing.
    expect(emitted.length).toBeGreaterThanOrEqual(5)

    for (const locale of [enLocale, zhLocale]) {
      const codes = webSearch(locale).messageCode
      for (const code of emitted) {
        expect(codes[code], `missing message_code: ${code}`).toBeTruthy()
      }
    }
  })

  it('translates every rejection reason surfaced to teachers', () => {
    const reasons = uniqueMatches(search, /"reason":\s*"([a-z_]+)"/g)
    expect(reasons).toContain('excluded_by_teacher')
    expect(reasons).toContain('insufficient_text')

    for (const locale of [enLocale, zhLocale]) {
      const translated = webSearch(locale).reason
      for (const reason of reasons) {
        expect(translated[reason], `missing reason: ${reason}`).toBeTruthy()
      }
    }
  })

  it('translates every gateway error code', () => {
    // The gateway's ERROR_CODES set is what reaches the teacher on failure.
    const block = gateway.match(/ERROR_CODES\s*=\s*\{([^}]*)\}/)
    expect(block, 'ERROR_CODES not found in web_retrieval.py').toBeTruthy()
    const source = block?.[1]
    if (!source) throw new Error('ERROR_CODES body not found in web_retrieval.py')
    const codes = uniqueMatches(source, /"([a-z_]+)"/g)
    expect(codes.length).toBeGreaterThanOrEqual(5)

    for (const locale of [enLocale, zhLocale]) {
      const translated = webSearch(locale).gatewayError
      for (const code of codes) {
        expect(translated[code], `missing gateway error: ${code}`).toBeTruthy()
      }
    }
  })

  it('translates every report status the backend sets', () => {
    const statuses = uniqueMatches(search, /status(?:=|":\s*)"([a-z_]+)"/g)
    expect(statuses).toContain('ready')

    for (const locale of [enLocale, zhLocale]) {
      const translated = webSearch(locale).status
      for (const status of statuses) {
        expect(translated[status], `missing status: ${status}`).toBeTruthy()
      }
    }
  })

  it('keeps en and zh web search keys in exact parity', () => {
    const flatten = (value: unknown, prefix = ''): string[] => {
      if (typeof value !== 'object' || value === null) return [prefix]
      return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
        flatten(child, prefix ? `${prefix}.${key}` : key),
      )
    }
    expect(flatten(webSearch(enLocale)).sort()).toEqual(
      flatten(webSearch(zhLocale)).sort(),
    )
  })

  it('does not leave machine codes as their own translation', () => {
    for (const locale of [enLocale, zhLocale]) {
      const block = webSearch(locale)
      for (const group of ['messageCode', 'reason', 'status', 'gatewayError'] as const) {
        for (const [code, text] of Object.entries(block[group])) {
          expect(text, `${group}.${code} is untranslated`).not.toBe(code)
        }
      }
    }
  })
})
