import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningMatrix from '@/components/LearningMatrix.vue'

const point = { knowledge_id: 'k1', knowledge_revision_id: 'r1', name: '整数除法截断', section_refs: ['s1'], block_refs: [], statement: '向零截断' }
function fixture(count = 9) {
  return [{ point, current: count ? 'review' : 'unassessed', notes: [{ id: 'n1', content: '我的理解', summary: '除法笔记' }], activity: true,
    attempts: Array.from({ length: count }, (_, i) => ({ id: `a${i}`, questionId: `q${i}`, questionLabel: `Q${i + 1}`, number: 1,
      time: '2026-10-17T10:00:00Z', outcome: i % 2 ? 'correct' : 'incorrect', support: i === 1 ? 'assisted' : 'independent',
      answer: '-2', feedback: '计算反馈', question: { prompt: '-9 / 4 的结果是什么？' }, nodeId: 's1' })) }]
}
const render = (extra = {}) => mount(LearningMatrix, { props: { rows: fixture(), sections: [{ id: 's1', name: '第1讲' }], courseTitle: 'C17', ...extra } as any })
describe('knowledge-row learning matrix', () => {
  it('shows recent records and expands the same point without losing earlier attempts', async () => {
    const w = render()
    expect(w.findAll('[data-attempt-id]')).toHaveLength(4)
    await w.get('[data-testid="expand-k1"]').trigger('click')
    expect(w.findAll('[data-attempt-id]')).toHaveLength(9)
    expect(w.text()).not.toContain('%')
  })
  it('expands a long history in bounded batches instead of rendering thousands of tiles', async () => {
    const w = render({ rows: fixture(101) })
    await w.get('[data-testid="expand-k1"]').trigger('click')
    expect(w.findAll('[data-attempt-id]')).toHaveLength(24)
    await w.get('[data-testid="more-k1"]').trigger('click')
    expect(w.findAll('[data-attempt-id]')).toHaveLength(48)
    await w.get('[data-testid="expand-k1"]').trigger('click')
    expect(w.findAll('[data-attempt-id]')).toHaveLength(4)
  })
  it('opens the exact attempt, shows its help label and safely renders its answer', async () => {
    const w = render({ rows: fixture(2) })
    await w.get('[data-attempt-id="a1"]').trigger('click')
    expect(w.get('[data-testid="attempt-detail"]').text()).toContain('-9 / 4')
    expect(w.get('[data-testid="attempt-detail"]').text()).toContain('提示后')
    expect(w.get('[data-testid="attempt-detail"]').text()).toContain('-2')
    await w.get('[data-testid="practice-current-question"]').trigger('click')
    expect(w.emitted('practice')?.[0]).toEqual(['s1', 'q1'])
    await w.get('[aria-label="关闭作答详情"]').trigger('click')
    expect(w.find('[data-testid="attempt-detail"]').exists()).toBe(false)
  })
  it('filters knowledge by search, with an honest empty result', async () => {
    const w = render()
    await w.get('input[type="search"]').setValue('不存在')
    expect(w.findAll('[data-attempt-id]')).toHaveLength(0)
    expect(w.text()).toContain('没有匹配的知识点')
  })
  it('links the point, original lecture and exact saved note through emitted actions', async () => {
    const w = render({ rows: fixture(1) })
    await w.get('[data-testid="knowledge-k1"]').trigger('click')
    expect(w.emitted('knowledge')?.[0]).toEqual([point])
    await w.get('[data-testid="notes-k1"]').trigger('click')
    await w.get('[data-testid="open-note-n1"]').trigger('click')
    expect(w.emitted('record')?.[0]).toEqual(['n1'])
    await w.get('[data-attempt-id="a0"]').trigger('click')
    await w.get('[data-testid="locate-lecture"]').trigger('click')
    expect(w.emitted('lecture')?.[0]).toEqual([point])
  })
  it('keeps unknown points visible and offers practice only with a real task', () => {
    const rows = fixture(0); const w = render({ rows })
    expect(w.text()).toContain('尚无作答记录')
    expect(w.find('[data-testid="practice-k1"]').exists()).toBe(false)
  })
  it('opens a real bound practice task and filters sections and unchecked points', async () => {
    const rows = fixture(0); (rows[0] as any).practice = { nodeId: 's1', revision: 'q-real' }
    const w = render({ rows })
    await w.get('[data-testid="practice-k1"]').trigger('click')
    expect(w.emitted('practice')?.[0]).toEqual(['s1', 'q-real'])
    await w.get('select').setValue('s1')
    const buttons = w.findAll('.matrix-filters button')
    await buttons[1]!.trigger('click')
    expect(w.text()).toContain('没有匹配的知识点')
    await buttons[2]!.trigger('click')
    expect(w.text()).toContain('尚无作答记录')
  })
  it('paginates knowledge rows without confusing pagination with attempt history', async () => {
    const rows = Array.from({ length: 10 }, (_, i) => ({ ...fixture(0)[0], point: { ...point, knowledge_id: `k${i}`, name: `Point ${i}` } }))
    const w = render({ rows })
    expect(w.findAll('.matrix-row')).toHaveLength(8)
    await w.get('[aria-label="下一页知识点"]').trigger('click')
    expect(w.findAll('.matrix-row')).toHaveLength(2)
    await w.get('[aria-label="上一页知识点"]').trigger('click')
    expect(w.findAll('.matrix-row')).toHaveLength(8)
  })
  it('clears selection and expansion when the course context changes', async () => {
    const w = render({ courseId: 'c1' })
    await w.get('[data-attempt-id="a8"]').trigger('click')
    await w.setProps({ courseId: 'c2', rows: [] } as any)
    expect(w.find('[data-testid="attempt-detail"]').exists()).toBe(false)
  })
  it('restores the same learner/course/revision view after returning from an existing tool', async () => {
    const w = render({ courseId: 'c-preserve', viewKey: 'u1:c-preserve:v1' })
    await w.get('input[type="search"]').setValue('整数')
    await w.get('[data-testid="expand-k1"]').trigger('click')
    await w.get('[data-attempt-id="a0"]').trigger('click')
    w.unmount()
    const restored = render({ courseId: 'c-preserve', viewKey: 'u1:c-preserve:v1' })
    expect((restored.get('input[type="search"]').element as HTMLInputElement).value).toBe('整数')
    expect(restored.findAll('[data-attempt-id]')).toHaveLength(9)
    expect(restored.get('[data-testid="attempt-detail"]').text()).toContain('Q1')
    const other = render({ courseId: 'c-preserve', viewKey: 'u2:c-preserve:v1' })
    expect((other.get('input[type="search"]').element as HTMLInputElement).value).toBe('')
    expect(other.find('[data-testid="attempt-detail"]').exists()).toBe(false)
  })
})
