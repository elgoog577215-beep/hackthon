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


describe('PPT manuscript reading preserves teaching structure', () => {
  function read(elements: Record<string, any>[], expression: Record<string, any>) {
    return mount(PptTeachingEditor, { props: { disabled: false, readonly: true, page: { title: '页面', teaching: { elements, expression, states: [] } } } })
  }
  it('follows derivation order and preserves code whitespace', () => {
    const code = 'if ready:\n    a = 2\n    print(a)'
    const wrapper = read([{ element_id: 'result', text: code, kind: 'code' }, { element_id: 'start', text: '先检查条件' }], { kind: 'derivation', ordered_element_ids: ['start', 'result'] })
    const reading = wrapper.get('.ppt-teaching-reading')
    expect(reading.element.children[0]!.textContent).toBe('先检查条件')
    expect(reading.get('pre code').element.textContent).toBe(code)
    expect(reading.findAll('textarea')).toHaveLength(0)
  })
  it('pairs chart labels with values and the shared unit', () => {
    const wrapper = read([{ element_id: 'unit', text: '分钟' }, { element_id: 'a', text: '观察' }, { element_id: 'b', text: '记录' }, { element_id: 'v1', text: '12.5' }, { element_id: 'v2', text: '25' }], { kind: 'chart', unit_element_id: 'unit', points: [{ label_element_id: 'b', value_element_id: 'v2' }, { label_element_id: 'a', value_element_id: 'v1' }] })
    expect(wrapper.get('thead').text()).toContain('分钟')
    const rows = wrapper.findAll('tbody tr')
    expect(rows.map(row => row.findAll('th,td').map(cell => cell.text()))).toEqual([['记录', '25'], ['观察', '12.5']])
  })
  it('keeps undirected relations and their conditions', () => {
    const wrapper = read([{ element_id: 'a', text: '方法甲' }, { element_id: 'b', text: '方法乙' }, { element_id: 'c', text: '相同输入' }], { kind: 'concept', node_element_ids: ['a', 'b'], relations: [{ relation_id: 'r', source_id: 'a', target_id: 'b', kind: 'contrasts', label: '比较', condition_element_ids: ['c'] }] })
    const relation = wrapper.get('.ppt-teaching-reading__relation')
    expect(relation.text()).toContain('— 比较')
    expect(relation.text()).not.toContain('→')
    expect(relation.get('.ppt-teaching-reading__conditions').text()).toContain('相同输入')
  })
})

describe('PPT content editing', () => {
  function editablePage() {
    return { title: '比较两种方法', teaching: {
      elements: [
        { element_id: 'a', text: '方法甲', role: 'evidence' },
        { element_id: 'b', text: '方法乙', role: 'evidence' },
      ],
      expression: { kind: 'concept', node_element_ids: ['a', 'b'], relations: [
        { relation_id: 'relation-1', source_id: 'a', target_id: 'b', kind: 'contrasts', label: '比较', condition_element_ids: [] },
      ] },
      states: [{ state_id: 'state-1', teaching_note: '请学生说明依据', visible_element_ids: ['a', 'b'] }],
      presentation: { mode: 'complete', checkpoints: [] },
    } }
  }

  it('keeps relations collapsed and edits visible speaker notes without changing structure', async () => {
    const page = editablePage()
    const originalExpression = JSON.parse(JSON.stringify(page.teaching.expression))
    const wrapper = mount(PptTeachingEditor, { props: { page, disabled: false, section: 'content' } })
    expect((wrapper.get('details').element as HTMLDetailsElement).open).toBe(false)
    expect(wrapper.find('[data-testid="ppt-page-layout"]').exists()).toBe(false)
    expect(wrapper.get('.ppt-teaching-editor__notes').find('details').exists()).toBe(false)
    await wrapper.get('.ppt-teaching-editor__notes textarea').setValue('先比较条件，再让学生说明依据')
    expect(page.teaching.states).toEqual([
      { state_id: 'state-1', teaching_note: '先比较条件，再让学生说明依据', visible_element_ids: ['a', 'b'] },
    ])
    expect(page.teaching.expression).toEqual(originalExpression)
    expect(page.teaching.elements.map(element => element.element_id)).toEqual(['a', 'b'])
    await wrapper.setProps({ section: 'layout' })
    expect(wrapper.find('.ppt-teaching-editor__notes').exists()).toBe(false)
    await wrapper.setProps({ section: 'content', disabled: true })
    expect(wrapper.get('.ppt-teaching-editor__notes textarea').attributes('disabled')).toBeDefined()
    expect((wrapper.get('.ppt-teaching-editor__notes textarea').element as HTMLTextAreaElement).value).toBe('先比较条件，再让学生说明依据')
  })
})
