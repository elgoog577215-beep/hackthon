import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../../components/TeacherKnowledgeManager.vue'
import { setLocale } from '../../shared/i18n'
import zh from '../../../public/locales/zh/translation.json'

const mock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../../utils/http', () => ({ default: mock }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { courseId: 'c1' } }) }))
const tree = (revision: string) => ({ revision_id: revision, categories: [{ id: 'types', name: '类型转换', parent_id: null }, { id: 'g', name: '整数运算', parent_id: 'types' }],
  knowledge_points: [{ knowledge_id: 'k1', key: 'K-T01', name: '整数除法', parent_id: 'g', revision_id: 'kpv1', statement: '向零截断', conditions: ['C17'], meta_question: '结果是什么？', meta_answer: '整数', source_refs: ['T-S1'] }], relations: [], misconceptions: [] })
const base = () => ({ title: 'C17', scope: '三组试点', enabled: true, can_edit: true, document_revision: 'doc1', knowledge_revision: '', tree: null,
  candidate: null, history: [], jobs: [], handouts: [{ topic: 'types', title: '类型转换', revisions: [] }], provenance: '复核材料' })
const mountView = () => mount(View, { props: {courseId:'c1'}, global: { stubs: { RouterLink: { template: '<a><slot /></a>' }, MarkdownRenderer: { props: ['content'], template: '<div>{{ content }}</div>' } } } })

beforeEach(async () => {
  vi.clearAllMocks()
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
  await setLocale('zh')
  mock.post.mockResolvedValue({ data: {} })
})
afterEach(() => vi.useRealTimers())

describe('embedded teacher knowledge manager', () => {
  it('shows teaching review issues and prevents adopting a failed candidate', async () => {
    const candidate = { ...tree('new'), teaching_assessment: { ready_for_adoption: false, capability_units: 1, criteria: 1, new_mistakes: 3, semantic_passed_units: 0 },
      skill_units: [{ skill_id: 's1', unit_key: 'T1', name: '判定字面量类型', knowledge_ids: ['k1'], observable_behavior: '给出类型与理由', review: { issues: [{ field: 'repair', message: '不能假定位宽' }] } }] }
    mock.get.mockResolvedValue({ data: { ...base(), candidate, candidate_job_id: 'job-new' } })
    const w = mountView(); await flushPromises()
    expect(w.text()).toContain('不能假定位宽')
    expect(w.text()).toContain('暂时不能采用')
    expect(w.findAll('button').find(b => b.text() === '采用这版知识树')!.attributes('disabled')).toBeDefined()
    w.unmount()
  })
  it('disables handout generation until a tree is adopted', async () => {
    mock.get.mockResolvedValue({ data: base() })
    const w = mountView(); await flushPromises()
    await w.findAll('button').find(b => b.text() === '讲义')!.trigger('click')
    expect(w.findAll('button').find(b => b.text() === '生成本讲讲义')!.attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('请先查看并采用知识树')
    w.unmount()
  })
  it('adopts the server candidate with both frozen source revisions', async () => {
    const state = { ...base(), candidate: tree('kb1'), candidate_job_id: 'job1' }
    mock.get.mockResolvedValue({ data: state })
    const w = mountView(); await flushPromises()
    expect(w.text()).toContain('整数除法')
    await w.findAll('button').find(b => b.text() === '采用这版知识树')!.trigger('click'); await flushPromises()
    expect(mock.post).toHaveBeenCalledWith('/api/courses/c1/knowledge-first/adopt/job1', { document_revision: 'doc1', knowledge_revision: '' })
    w.unmount()
  })
  it('opens the historical knowledge revision when clicking a stale handout reference', async () => {
    const revision = { revision_id: 'h1', source_knowledge_revision: 'old', source_terminology_revision: 'term1', stale: true,
      sections: [{ blocks: [{ block_id: 'b1', title: '例题', content: '说明', knowledge_refs: [{ knowledge_id: 'k1', revision_id: 'kpv1' }] }] }] }
    mock.get.mockResolvedValue({ data: { ...base(), tree: tree('new'), knowledge_revision: 'new', history: [tree('old'), tree('new')],
      handouts: [{ topic: 'types', title: '类型转换', revisions: [revision], current_revision_id: 'h1' }] } })
    const w = mountView(); await flushPromises()
    await w.findAll('button').find(b => b.text() === '讲义')!.trigger('click')
    expect(w.text()).toContain('当前知识树已变化')
    await w.get('.ref-chips button').trigger('click')
    expect((w.get('select').element as HTMLSelectElement).value).toBe('old')
    expect(w.get('.point-card h2').text()).toBe('整数除法')
    w.unmount()
  })
  it('does not expose generation controls to a read-only learner', async () => {
    mock.get.mockResolvedValue({ data: { ...base(), can_edit: false } })
    const w = mountView(); await flushPromises()
    expect(w.findAll('button').some(b => b.text() === '生成知识树')).toBe(false)
    w.unmount()
  })
})
