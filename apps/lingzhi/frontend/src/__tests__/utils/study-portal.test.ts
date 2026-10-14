import { describe, expect, it } from 'vitest'
import { configuredStudyPortal } from '@/shared/study-portal'
describe('student portal link', () => {
  it('keeps the same-instance fallback and accepts a configured student frontend', () => {
    expect(configuredStudyPortal('')).toBe('')
    expect(configuredStudyPortal('/study?view=courses')).toBe('/study?view=courses')
    expect(configuredStudyPortal('http://127.0.0.1:5175/study')).toBe('http://127.0.0.1:5175/study')
  })
  it('rejects executable URLs, credentials and ambiguous relative destinations', () => {
    for (const value of ['javascript:alert(1)', '//example.com/study', 'https://user:password@example.com/study', '../courses', 'not a url']) expect(configuredStudyPortal(value)).toBe('')
  })
})
