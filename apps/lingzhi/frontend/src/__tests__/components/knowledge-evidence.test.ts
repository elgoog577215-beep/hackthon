import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

function view() {
  const point = { knowledge_id: 'stable-id', revision_id: 'stable-rev', key: 'K1', name: '势函数定义', statement: '势函数将状态映射为实数。',
    parent_id: 'c', section_refs: ['cpu'], source_refs: ['ev'], aliases: ['Potential Function', 'PF', '潜在函数'],
    terms: [{ name: '势函数', english_name: 'Potential Function', abbreviations: ['PF'], aliases: ['潜在函数'], origin: 'source_annotation',
      evidence_refs: [{ evidence_id: 'ev' }] }], term_candidates: [],
    source_quotes: [{ evidence_id: 'ev', quote: '势函数（Potential Function）将状态映射为实数。', source_kind: 'canonical_handout_block',
      handout_ref: { lesson_id: 'cpu', script_revision_id: 'old-rev', section_id: 'sec', block_id: 'b' } }] }
  const tree = { revision_id: 'base', source_mode: 'handouts', categories: [{ id: 'c', name: '分析方法', parent_id: null }],
    knowledge_points: [point], relations: [], misconceptions: [], gaps: [], uncovered_evidence_ids: [] }
  return { enabled: true, can_edit: true, workflow: 'knowledge_first_generic_v1', source_mode: 'handouts', result_version: 'v',
    title: '课程', knowledge_revision: 'base', document_revision: 'doc', tree, history: [tree], candidates: [], jobs: [], active_jobs: [],
    handouts: [], source_handouts: [], lesson_options: [{ lesson_id: 'cpu', title: '处理器', can_generate: true }] }
}
beforeEach(async () => {
  vi.restoreAllMocks()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
  await setLocale('zh')
  vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
})
afterEach(() => vi.restoreAllMocks())

it('finds the same point by English, abbreviation and Chinese alias without changing identity', async () => {
  vi.spyOn(http, 'get').mockResolvedValue({ data: view() })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  for (const query of ['potential function', 'PF', '潜在函数']) {
    await w.get('.tree-search input').setValue(query)
    expect(w.find('[data-knowledge-id="stable-id"]').exists()).toBe(true)
  }
  await w.get('[data-knowledge-id="stable-id"]').trigger('click')
  expect(w.get('[data-testid="knowledge-terms"]').text()).toContain('Potential Function')
  expect(w.get('.point-card').text()).toContain('stable-rev')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it.each(['zh', 'en'] as const)('opens the referenced source version in %s without switching to the newest handout', async locale => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => locale === 'zh' ? zh : en })))
  await setLocale(locale)
  const get = vi.spyOn(http, 'get').mockImplementation(async url => ({ data: String(url).endsWith('/source')
    ? { available: true, content: '旧版本原文。势函数（Potential Function）将状态映射为实数。', quote: '势函数（Potential Function）将状态映射为实数。',
      source_kind: 'generated_handout', handout_ref: { lesson_id: 'cpu', script_revision_id: 'old-rev', block_id: 'b' } } : view() }))
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.get('[data-knowledge-id="stable-id"]').trigger('click')
  await w.get('[data-testid="locate-knowledge-source"]').trigger('click'); await flushPromises()
  expect(get).toHaveBeenCalledWith('/api/courses/c/knowledge-first/source', expect.objectContaining({ params: {
    tree_revision: 'base', knowledge_id: 'stable-id', evidence_id: 'ev' } }))
  const reader = w.get('[data-testid="knowledge-source-reader"]')
  expect(reader.text()).toContain('old-rev')
  expect(reader.text()).toContain('旧版本原文')
  expect(reader.get('[data-testid="knowledge-source-excerpt"]').text()).toContain('Potential Function')
  expect(reader.text()).toContain(locale === 'zh' ? '生成讲义' : 'Generated handout')
  await reader.get('[data-testid="close-knowledge-source"]').trigger('click')
  expect(w.get('.point-card h2').text()).toBe('势函数定义')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('shows a retained quotation when the original version is unavailable', async () => {
  vi.spyOn(http, 'get').mockImplementation(async url => ({ data: String(url).endsWith('/source')
    ? { available: false, reason: 'source_revision_missing', quote: '旧原文快照', source_kind: 'generated_handout',
      handout_ref: { script_revision_id: 'old-rev' } } : view() }))
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.get('[data-knowledge-id="stable-id"]').trigger('click')
  await w.get('[data-testid="locate-knowledge-source"]').trigger('click'); await flushPromises()
  expect(w.get('[data-testid="knowledge-source-reader"]').text()).toContain('旧原文快照')
  expect(w.get('[data-testid="knowledge-source-reader"]').text()).toContain('原版本暂不可用')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})
