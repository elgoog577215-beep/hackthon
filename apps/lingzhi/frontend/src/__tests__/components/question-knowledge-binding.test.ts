import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QuestionKnowledgeBinding from '@/components/QuestionKnowledgeBinding.vue'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get, post }, teacherReadRequestConfig: (v = {}) => v }))
vi.mock('@/shared/i18n', () => ({ t: (_key: string, fallback: string) => fallback }))
const view = (ready = true) => ({
  tree_ready: ready, can_edit: true, knowledge_baseline_revision: 'tree1', bundle_revision_id: 'b1',
  counts: { bound: 0, unbound: 1, pending: 0, stale: 0 },
  points: [{ knowledge_id: 'k1', name: '整数除法', statement: '整数除法向零截断' }],
  items: [{ revision_id: 'r1', prompt: '计算 -7 / 2', status: 'unbound', knowledge_ids: [] }],
  auto_revision_ids: ready ? ['r1'] : [],
})

describe('question knowledge binding', () => {
  beforeEach(() => { get.mockReset(); post.mockReset() })
  it('automatically binds when an adopted tree exists, then refreshes the bank', async () => {
    get.mockResolvedValue({ data: view() })
    post.mockResolvedValue({ data: { ...view(), bundle_revision_id: 'b2', auto_revision_ids: [], counts: { bound: 1 } } })
    const wrapper = mount(QuestionKnowledgeBinding, { props: { courseId: 'c1', bundleRevision: 'b1' } })
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0]?.[1]).toMatchObject({ mode: 'auto', expected_bundle_revision_id: 'b1', knowledge_baseline_revision: 'tree1' })
    expect(wrapper.emitted('updated')).toHaveLength(1)
    wrapper.unmount()
  })
  it('offers a binding button but never calls matching without a tree', async () => {
    get.mockResolvedValue({ data: view(false) })
    const wrapper = mount(QuestionKnowledgeBinding, { props: { courseId: 'c1', bundleRevision: 'b1' } })
    await flushPromises()
    expect(post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('绑定知识点')
    expect(wrapper.text()).toContain('请先生成并采用知识树')
    wrapper.unmount()
  })
  it('lets users explicitly save selected atomic points', async () => {
    get.mockResolvedValue({ data: { ...view(), auto_revision_ids: [], items: [{ ...view().items[0], status: 'pending' }] } })
    post.mockResolvedValue({ data: { ...view(), auto_revision_ids: [] } })
    const wrapper = mount(QuestionKnowledgeBinding, { props: { courseId: 'c1', bundleRevision: 'b1' } })
    await flushPromises()
    await wrapper.get('[data-testid="open-knowledge-binding"]').trigger('click')
    await wrapper.get('input[value="k1"]').setValue(true)
    await wrapper.get('[data-testid="save-knowledge-binding"]').trigger('click')
    await flushPromises()
    expect(post.mock.calls[0]?.[1]).toMatchObject({ mode: 'manual', revision_id: 'r1', knowledge_ids: ['k1'] })
    wrapper.unmount()
  })
  it('shows a recoverable failure without an automatic retry loop', async () => {
    get.mockResolvedValue({ data: view() })
    post.mockRejectedValue(new Error('offline'))
    const wrapper = mount(QuestionKnowledgeBinding, { props: { courseId: 'c1', bundleRevision: 'b1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('自动绑定暂不可用')
    expect(post).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('does not bind while the question bank is generating', async () => {
    get.mockResolvedValue({ data: view() })
    post.mockResolvedValue({ data: { ...view(), auto_revision_ids: [] } })
    const wrapper = mount(QuestionKnowledgeBinding, { props: { courseId: 'c1', bundleRevision: 'b1', generationActive: true } })
    await flushPromises()
    expect(post).not.toHaveBeenCalled()
    await wrapper.setProps({ generationActive: false })
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('ignores old course responses after switching courses', async () => {
    let resolveOld!: (value: unknown) => void
    get.mockImplementation((url: string) => url.includes('/c1/')
      ? new Promise(resolve => { resolveOld = resolve })
      : Promise.resolve({ data: { ...view(false), bundle_revision_id: 'new-bank' } }))
    const wrapper = mount(QuestionKnowledgeBinding, { props: { courseId: 'c1', bundleRevision: 'b1' } })
    await wrapper.setProps({ courseId: 'c2', bundleRevision: 'new-bank' })
    await flushPromises()
    resolveOld({ data: view() })
    await flushPromises()
    expect(post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先生成并采用知识树')
    wrapper.unmount()
  })
  it('retries all pending rows once in bounded batches', async () => {
    const rows = Array.from({ length: 10 }, (_, i) => ({ revision_id: `r${i}`, prompt: `Question ${i}`, status: 'pending', knowledge_ids: [] }))
    const data = { ...view(), items: rows, counts: { pending: 10 }, auto_revision_ids: [] }
    get.mockResolvedValue({ data })
    post.mockResolvedValue({ data })
    const wrapper = mount(QuestionKnowledgeBinding, { props: { courseId: 'c1', bundleRevision: 'b1' } })
    await flushPromises()
    await wrapper.get('[data-testid="open-knowledge-binding"]').trigger('click')
    const retry = wrapper.findAll('button').find(b => b.text().includes('重新自动匹配'))!
    await retry.trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(2)
    expect(post.mock.calls[0]?.[1].revision_ids).toHaveLength(8)
    expect(post.mock.calls[1]?.[1].revision_ids).toEqual(['r8', 'r9'])
    wrapper.unmount()
  })
})
