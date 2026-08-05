import { describe, expect, it } from 'vitest'
import {
  retrievalErrorCode,
  retrievalErrorTranslationKey,
} from '@/utils/retrieval-errors'


describe('retrieval error presentation', () => {
  it('finds classified errors in receipts, packages, and AI messages', () => {
    expect(retrievalErrorCode({ error_codes: ['timeout'] })).toBe('timeout')
    expect(retrievalErrorCode({
      package: { receipt: { error_codes: ['not_configured'] } },
    })).toBe('not_configured')
    expect(retrievalErrorCode({
      retrieval_receipt: { error_codes: ['privacy_blocked'] },
    })).toBe('privacy_blocked')
  })

  it('ignores unknown provider details and returns a stable translation key', () => {
    expect(retrievalErrorCode({ error_codes: ['captcha'] })).toBeNull()
    expect(retrievalErrorTranslationKey({ error_codes: ['provider_error'] }))
      .toBe('courseGeneration.retrieval.errors.provider_error')
    expect(retrievalErrorTranslationKey({})).toBeNull()
  })
})
