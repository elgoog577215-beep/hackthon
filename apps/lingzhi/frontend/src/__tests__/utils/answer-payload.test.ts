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

describe('hasMeaningfulAnswer 分步作答 (J3)', () => {
  it('全空步骤不算已作答——step_index 是编号不是内容', () => {
    expect(hasMeaningfulAnswer({
      steps: [
        { text: '', step_index: 1, step_id: '' },
        { text: '   ', step_index: 2, step_id: '' },
      ],
    })).toBe(false)
  })

  it('任意一步写了内容就算已作答', () => {
    expect(hasMeaningfulAnswer({
      steps: [
        { text: '', step_index: 1, step_id: '' },
        { text: '先配方', step_index: 2, step_id: '' },
      ],
    })).toBe(true)
  })

  it('步骤全空但整体作答有内容时仍算已作答', () => {
    expect(hasMeaningfulAnswer({
      steps: [{ text: '', step_index: 1, step_id: '' }],
      text: '最小值是 -1',
    })).toBe(true)
  })
})
