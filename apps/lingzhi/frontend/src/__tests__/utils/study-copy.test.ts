import { afterEach, describe, expect, it } from 'vitest'
import { activeLocale } from '../../shared/i18n'
import { studyCopy } from '../../shared/study-copy'

const originalLocale = activeLocale.value

afterEach(() => {
  activeLocale.value = originalLocale
})

describe('student handout tool labels', () => {
  it('uses the current concept-relations label in Chinese and English', () => {
    activeLocale.value = 'zh'
    expect(studyCopy('conceptRelations')).toBe('概念关系')

    activeLocale.value = 'en'
    expect(studyCopy('conceptRelations')).toBe('Concepts')
  })
})
