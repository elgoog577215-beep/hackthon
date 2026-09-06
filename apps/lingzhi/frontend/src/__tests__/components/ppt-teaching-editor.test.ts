import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import PptTeachingEditor from '@/components/PptTeachingEditor.vue'

describe('PptTeachingEditor presentation controls', () => {
  it('keeps narration while selecting explicit stops with reasons', async () => {
    const page = { teaching: {
      presentation: { mode: 'complete', checkpoints: [] },
      expression: { kind: 'evidence' },
      elements: [{ element_id: 'a', text: '观察证据', role: 'evidence' }],
      states: [{ state_id: 'one', teaching_note: '先观察', visible_element_ids: ['a'] },
        { state_id: 'two', teaching_note: '再判断', visible_element_ids: ['a'] }],
    }, resolved_scenes: [] }
    const wrapper = mount(PptTeachingEditor, { props: { page, disabled: false } })
    await wrapper.get('[data-testid="ppt-presentation-mode"]').setValue('key_steps')
    expect(page.teaching.presentation.checkpoints).toEqual([
      { state_id: 'one', reason: '' }, { state_id: 'two', reason: '' },
    ])
    await wrapper.get('.ppt-teaching-editor__checkpoints input[type="checkbox"]').setValue(false)
    expect(page.teaching.presentation.checkpoints).toEqual([{ state_id: 'two', reason: '' }])
    await wrapper.get('.ppt-teaching-editor__checkpoints input:not([type="checkbox"])').setValue('学生先说出判断依据')
    expect(page.teaching.presentation.checkpoints).toEqual([{ state_id: 'two', reason: '学生先说出判断依据' }])
    await wrapper.get('[data-testid="ppt-presentation-mode"]').setValue('complete')
    expect(page.teaching.states.map(s => s.teaching_note)).toEqual(['先观察', '再判断'])
    expect(page.teaching.presentation.checkpoints).toEqual([])
  })

  it('prevents switching an answer page to a single complete view', async () => {
    const page = { teaching: { presentation: { mode: 'question_answer', checkpoints: [] },
      expression: { kind: 'exercise' }, elements: [{ element_id: 'a', text: '答案', role: 'answer' }], states: [] }, resolved_scenes: [] }
    const wrapper = mount(PptTeachingEditor, { props: { page, disabled: false } })
    expect(wrapper.get('option[value="complete"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('option[value="question_answer"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="ppt-presentation-mode"]').setValue('complete')
    expect(page.teaching.presentation.mode).toBe('question_answer')
  })
})
