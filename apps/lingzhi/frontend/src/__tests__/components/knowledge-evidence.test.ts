import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import Reader from '@/components/KnowledgeSourceReader.vue'
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

it('keeps the full rule and conditions behind a short, editable title', async () => {
  const v: any = view()
  Object.assign(v.tree.knowledge_points[0], { display_name: '势函数', knowledge_type: 'definition',
    conditions: ['状态属于约定的定义域'], check_intents: ['说明映射的输入与输出'] })
  v.presentation_revision = 'display-old'
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.get('[data-knowledge-id="stable-id"]').trigger('click'); await flushPromises()
  expect(w.get('.point-card h2').text()).toBe('势函数')
  expect(w.get('[data-testid="knowledge-type"]').text()).toBe('概念')
  expect(w.get('.claim').text()).toContain('势函数将状态映射为实数。')
  expect(w.get('.point-card').text()).toContain('状态属于约定的定义域')
  expect(w.get('[data-testid="knowledge-check-intents"]').element.tagName).toBe('DETAILS')
  await w.get('[data-testid="knowledge-name-input"]').setValue('状态势函数')
  await w.get('[data-testid="knowledge-name-form"]').trigger('submit'); await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/presentation', expect.objectContaining({
    document_revision: 'doc', knowledge_revision: 'base', tree_revision: 'base', presentation_revision: 'display-old',
    labels: [{ knowledge_id: 'stable-id', knowledge_revision: 'stable-rev', name: '状态势函数' }]
  }))
  w.unmount()
})

it('does not offer title writes to a read-only learner', async () => {
  const v: any = view(); v.can_edit = false
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.get('[data-knowledge-id="stable-id"]').trigger('click'); await flushPromises()
  expect(w.find('[data-testid="knowledge-name-form"]').exists()).toBe(false)
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it.each(['zh', 'en'] as const)('shows input materials and symbol definitions separately in %s', async locale => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => locale === 'zh' ? zh : en })))
  await setLocale(locale)
  const v: any = view()
  Object.assign(v.tree.knowledge_points[0], {
    provenance_contract: 'input_material_record_v1', symbol_definitions: ['v(t)表示速度'],
    teaching_context: ['直线运动'], conditions: ['速度函数可导']
  })
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.get('[data-knowledge-id="stable-id"]').trigger('click')
  expect(w.get('[data-testid="knowledge-symbol-definitions"]').text()).toContain('v(t)表示速度')
  expect(w.get('[data-testid="knowledge-input-material-notice"]').text()).toContain(
    locale === 'zh' ? '本轮参考材料' : 'Materials used in this generation')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it.each(['zh','en'] as const)('explains frozen split formatting in %s without claiming literal source offsets', async locale => {
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>locale==='zh'?zh:en})));await setLocale(locale)
  vi.spyOn(http,'get').mockResolvedValue({data:{available:true,quote_match:'frozen_split_passage',quote:'冻结引文',content:'原段落\n排版',source_kind:'generated_handout'}})
  const w=mount(Reader,{props:{courseId:'c',treeRevision:'base',knowledgeId:'stable-id',source:{evidence_id:'ev'}}});await flushPromises()
  expect(w.text()).toContain(locale==='zh'?'已按同一正文块的冻结分段对账':'Matched against frozen splits of this same content block')
  expect(w.text()).toContain('原段落');expect(w.text()).toContain('冻结引文');w.unmount()
})

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

it('keeps the source quotation on a failed read and retries only that read', async () => {
  let sourceReads = 0
  vi.spyOn(http, 'get').mockImplementation(async url => {
    if (!String(url).endsWith('/source')) return { data: view() }
    if (++sourceReads === 1) throw new Error('offline')
    return { data: { available: true, content: '重连后读取的旧原文', quote: '旧原文', source_kind: 'generated_handout' } }
  })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.get('[data-knowledge-id="stable-id"]').trigger('click')
  await w.get('[data-testid="locate-knowledge-source"]').trigger('click'); await flushPromises()
  const reader = w.get('[data-testid="knowledge-source-reader"]')
  expect(reader.get('[role="alert"]').text()).toContain('读取失败')
  expect(reader.get('[data-testid="knowledge-source-excerpt"]').text()).toContain('Potential Function')
  await reader.get('[role="alert"] button').trigger('click'); await flushPromises()
  expect(reader.text()).toContain('重连后读取的旧原文')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})


it.each(['zh', 'en'] as const)('shows coverage and revision-bound teaching drafts without recording learner events in %s', async locale => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => locale === 'zh' ? zh : en })))
  await setLocale(locale)
  const v: any = view()
  v.tree.knowledge_coverage = { plan_origin:'provided_coverage_plan', unit_count: 1, covered_unit_count: 1, units: [{key:'U1', statement:'势函数将状态映射为实数。'}] }
  Object.assign(v.tree.knowledge_points[0], {
    check_intents: ['独立说明定义'],
    kc_skill_profile: { knowledge_id:'stable-id', knowledge_revision:'stable-rev', basis:'knowledge_draft',
      skill: {description:'适用场景正文', assessment_focus:'检查目标正文', assessment_format:'练习方式正文', common_mistakes:'待验证易错方式', difficulty_cues:'难度变化正文'} }
  })
  vi.spyOn(http, 'get').mockResolvedValue({ data:v })
  const w = mount(Manager, { props:{courseId:'c', treeOnly:true} }); await flushPromises()
  expect(w.get('[data-testid="knowledge-coverage"]').text()).toContain('1 / 1')
  expect(w.get('[data-testid="knowledge-provided-plan"]').text()).toContain(locale==='zh'?'指定的知识清单':'specified knowledge checklist')
  await w.get('[data-knowledge-id="stable-id"]').trigger('click')
  const profile=w.get('[data-testid="knowledge-teaching-profile"]')
  expect(profile.text()).toContain(locale==='zh'?'暂无已核验题目样本':'No verified question samples')
  expect(profile.text()).toContain('练习方式正文')
  expect(w.get('[data-testid="knowledge-check-intents"]').text()).toContain('独立说明定义')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
  v.tree.knowledge_points[0].revision_id='new-revision'
  const stale=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await stale.get('[data-knowledge-id="stable-id"]').trigger('click')
  expect(stale.find('[data-testid="knowledge-teaching-profile"]').exists()).toBe(false)
  stale.unmount()
})


it.each(['zh','en'] as const)('labels automatic discovery honestly in %s',async locale=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>locale==='zh'?zh:en})));await setLocale(locale)
  const v:any=view();v.tree.knowledge_coverage={plan_origin:'material_discovery',unit_count:2,covered_unit_count:2,units:[]}
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.get('[data-testid="knowledge-discovery-plan"]').text()).toContain(locale==='zh'?'由材料自动生成':'discovered from the material')
  expect(w.find('[data-testid="knowledge-provided-plan"]').exists()).toBe(false)
  expect(http.post).not.toHaveBeenCalled();w.unmount()
})
