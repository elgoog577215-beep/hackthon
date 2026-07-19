import { describe, expect, it } from 'vitest'
import { hasMeaningfulAnswer } from '../../utils/answer-payload'

describe('answer payload completeness', () => {
  it('treats empty choice and structured payloads as unanswered', () => {
    expect(hasMeaningfulAnswer({ selected_option_ids: [] })).toBe(false)
    expect(hasMeaningfulAnswer({ fields: {} })).toBe(false)
    expect(hasMeaningfulAnswer({ text: '   ' })).toBe(false)
  })

  it('detects meaningful values recursively', () => {
    expect(hasMeaningfulAnswer({ selected_option_id: 'B' })).toBe(true)
    expect(hasMeaningfulAnswer({ fields: { evidence: 'because' } })).toBe(true)
    expect(hasMeaningfulAnswer({ value: 0 })).toBe(true)
  })
})
