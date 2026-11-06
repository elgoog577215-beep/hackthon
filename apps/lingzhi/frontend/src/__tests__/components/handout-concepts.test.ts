import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildHandoutConceptSections, conceptLayers, type HandoutConceptSection } from '@/utils/handout-concepts'
import HandoutConceptMap from '@/components/HandoutConceptMap.vue'
import HandoutKnowledgeMap from '@/components/HandoutKnowledgeMap.vue'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

const reading = [{ id: 's1', title: '导数', anchor: 's1', blocks: [
  { id: 'b1', anchor: 'b1', content: 'A 和 B 都在这段出现', knowledge: ['id-b'] },
  { id: 'b2', anchor: 'b2', content: 'A 的定义', knowledge: ['id-a'] },
] }]
const plans = [{ node_id: 's1', knowledge_structure: [{ knowledge_points: [
  { name: 'A', knowledge_id: 'id-a', statement: 'A 的说明', relations: [{ target_name: 'B', relation_type: 'derives', reason: '取极限', derivation_steps: ['建立差商', '求极限'], conditions: ['极限存在'] }] },
  { name: 'B', knowledge_id: 'id-b' },
] }], knowledge_relations: [] }]
beforeEach(async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh })))
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  await setLocale('zh')
})

describe('Handout concept relationships', () => {
  it('restores the October header and directly visible evidence for every shared reader', () => {
    const wrapper = mount(HandoutConceptMap, { props: { sections: buildHandoutConceptSections(plans, reading) } })
    expect(wrapper.get('header').text()).toContain('CONCEPT CONNECTIONS')
    expect(wrapper.get('h3').text()).toBe('概念关系')
    expect(wrapper.findAll('[data-concept-id]')).toHaveLength(2)
    expect(wrapper.find('.concept-relation-number').exists()).toBe(false)
    expect(wrapper.find('details.concept-relations').exists()).toBe(false)
    expect(wrapper.get('.concept-relations .concept-relation').text()).toContain('建立差商')
    expect(wrapper.get('.concept-relations .concept-relation').text()).toContain('极限存在')
    wrapper.unmount()
  })

  it('按被外层裁切的滚动区限制侧栏高度，并跟随窗口调整', async () => {
    const host = document.createElement('div'), scrollport = document.createElement('div')
    host.style.overflowY = 'hidden'
    scrollport.style.overflowY = 'auto'
    let hostHeight = 440
    host.getBoundingClientRect = () => ({ top: 80 } as DOMRect)
    scrollport.getBoundingClientRect = () => ({ top: 120 } as DOMRect)
    Object.defineProperty(host, 'clientHeight', { get: () => hostHeight })
    Object.defineProperty(scrollport, 'clientHeight', { value: 460 })
    host.append(scrollport)
    document.body.append(host)
    const wrapper = mount(HandoutConceptMap, { attachTo: scrollport, props: { sections: [] }, attrs: { class: 'handout-reading-aside' } })
    await nextTick()
    expect((wrapper.element as HTMLElement).style.getPropertyValue('--handout-aside-available-height')).toBe('352px')
    hostHeight = 340
    window.dispatchEvent(new Event('resize'))
    await nextTick()
    expect((wrapper.element as HTMLElement).style.getPropertyValue('--handout-aside-available-height')).toBe('252px')
    wrapper.unmount()
    host.remove()
  })
  it('独立工具栏的概念图由外层滚动，不额外限制自身高度', async () => {
    const wrapper = mount(HandoutConceptMap, { props: { sections: buildHandoutConceptSections(plans, reading) } })
    await nextTick()
    expect((wrapper.element as HTMLElement).style.getPropertyValue('--handout-aside-available-height')).toBe('')
    wrapper.unmount()
  })
  it.each(['zh', 'en'] as const)('shows reference coverage and gaps in %s without calling it mastery', async locale => {
    await setLocale(locale)
    const section = buildHandoutConceptSections(plans, reading)[0]!
    section.sourceStatus = 'historical'
    section.coverage = { status: 'historical', scope_known: true, semantics_verified: false, source_knowledge_revision: 'old', invalid_refs: [], rows: [
      { knowledge_id: 'id-a', name: 'A', revision_id: 'pa', block_ids: ['b2'], explanation_block_ids: ['b2'], example_block_ids: [], exercise_block_ids: [] },
      { knowledge_id: 'id-b', name: 'B', revision_id: 'pb', block_ids: [], explanation_block_ids: [], example_block_ids: [], exercise_block_ids: [] },
    ] }
    const wrapper = mount(HandoutConceptMap, { props: { sections: [section] } })
    expect(wrapper.get('[data-knowledge-id="id-a"]').text()).toContain('1')
    expect(wrapper.get('[data-knowledge-id="id-b"]').text()).toContain(locale === 'zh' ? '暂无正文引用' : 'No content reference')
    expect(wrapper.text()).toContain(locale === 'zh' ? '不代表讲解正确' : 'not teaching accuracy')
    expect(wrapper.text()).toContain(locale === 'zh' ? '历史知识版本' : 'historical knowledge')
    wrapper.unmount()
  })
  it('沿用知识身份绑定和知识点内部关系，不从共同出现的词语造边', () => {
    const sections = buildHandoutConceptSections(plans, reading)
    expect(sections[0]?.nodes.find(node => node.name === 'A')?.anchor).toBe('b2')
    expect(sections[0]?.relations[0]).toMatchObject({ source: 'id-a', target: 'id-b', type: 'derives', conditions: ['极限存在'], steps: ['建立差商', '求极限'] })
    expect(buildHandoutConceptSections([{ ...plans[0], knowledge_structure: [{ knowledge_points: [{ name: 'A' }, { name: 'B' }] }] }], reading)[0]?.relations).toEqual([])
    expect(buildHandoutConceptSections([], reading)[0]?.nodes).toEqual([])
  })
  it('保留关系条件，去重对称关系，丢弃无理由、未知端点和自环', () => {
    const edge = { source_name: 'A', target_name: 'B', relation_type: 'equivalent_to', reason: '同一表述', conditions: ['h≠0'], source_refs: ['ev-material-001', { filename: '材料.txt', locator: '第 1 段' }] }
    const sections = buildHandoutConceptSections([{ ...plans[0], knowledge_relations: [edge, { ...edge, source_name: 'B', target_name: 'A' }, { ...edge, conditions: ['另一条件'] }, { ...edge, target_name: '未知' }, { ...edge, reason: '' }, { ...edge, target_name: 'A' }] }], reading)
    expect(sections[0]?.relations).toHaveLength(3) // Two conditional equivalences + the recorded derivation.
    expect(sections[0]?.relations[0]?.sourceRefs).toEqual(edge.source_refs)
  })
  it('有向循环和双向关系不导致无限递归，不漏掉节点', () => {
    const section = buildHandoutConceptSections(plans, reading)[0]!
    section.relations.push({ ...section.relations[0]!, source: 'id-b', target: 'id-a', id: 'reverse' })
    expect(conceptLayers(section).flat().map(node => node.id)).toEqual(['id-a', 'id-b'])
    expect(conceptLayers(section)).toHaveLength(1)
  })
  it('显示结构化来源位置与学生资料说明，不把位置对象当成正文', () => {
    const section = buildHandoutConceptSections(plans, reading)[0]!
    section.relations[0]!.sourceRefs = [{ filename: '教材.pdf', locator: { section_path: ['向量', '线性组合'], page: 3, slide: null } }]
    const wrapper = mount(HandoutConceptMap, { props: { sections: [section], originLabel: '来自所选资料' } })
    expect(wrapper.text()).toContain('教材.pdf · 向量 › 线性组合 · 页 3')
    expect(wrapper.get('footer').text()).toBe('来自所选资料')
    expect(wrapper.text()).not.toMatch(/\[object Object\]|来自当前教案/)
    wrapper.unmount()
  })
  it('知识库重复投影不丢来源，组合前提保留 AND/OR 与必要性', () => {
    const relation = { source_name: 'A', target_name: 'B', relation_type: 'prerequisite', reason: '已有理由', relation_group_id: 'g1', group_operator: 'OR', necessity: 'helpful' }
    const section = buildHandoutConceptSections([{ ...plans[0], knowledge_relations: [relation, { ...relation, source_refs: ['ev-001'] }] }], reading)[0]!
    expect(section.relations[0]).toMatchObject({ sourceRefs: ['ev-001'], groupId: 'g1', groupOperator: 'OR', necessity: 'helpful' })
  })
  it('点击概念展开并定位当前讲义，显示推导步骤和条件', async () => {
    const root = document.createElement('article')
    root.innerHTML = '<section id="b2"><details><summary>解答</summary>正文</details></section>'
    document.body.append(root)
    const scroll = vi.fn()
    root.querySelector<HTMLElement>('#b2')!.scrollIntoView = scroll
    const wrapper = mount(HandoutConceptMap, { props: { sections: buildHandoutConceptSections(plans, reading), target: root } })
    await wrapper.get('[data-concept-id="id-a"]').trigger('click')
    expect(scroll).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    expect(root.querySelector('details')!.open).toBe(true)
    expect(wrapper.text()).toContain('极限存在')
    expect(wrapper.text()).toContain('建立差商')
    expect(wrapper.get('[data-concept-id="id-a"]').attributes('aria-pressed')).toBe('true')
    wrapper.unmount(); root.remove()
  })
  it('跟随小节阅读，中英文操作同步，缺少段落不假造定位', async () => {
    await setLocale('en')
    const sections = buildHandoutConceptSections(plans, reading)
    const second: HandoutConceptSection = { id: 's2', title: '后续小节', anchor: 's2', blockAnchors: ['b3'], nodes: [{ id: 'C', name: 'C', statement: '', anchor: '', external: true }], relations: [] }
    const root = document.createElement('article')
    root.innerHTML = '<section id="s1"></section><section id="s2"><div id="b3"></div></section>'
    root.querySelector<HTMLElement>('#s1')!.getBoundingClientRect = () => ({ top: -700 } as DOMRect)
    root.querySelector<HTMLElement>('#s2')!.getBoundingClientRect = () => ({ top: 30 } as DOMRect)
    root.querySelector<HTMLElement>('#b3')!.getBoundingClientRect = () => ({ top: 60 } as DOMRect)
    const wrapper = mount(HandoutConceptMap, { props: { sections: [...sections, second], target: root } })
    await nextTick()
    window.dispatchEvent(new Event('scroll')); await nextTick()
    expect(wrapper.find('[data-concept-id="C"]').exists()).toBe(true)
    await wrapper.get('[data-concept-id="C"]').trigger('click')
    expect(wrapper.text()).toContain('No matching passage')
    expect(wrapper.text()).toContain('Concept connections')
    expect(wrapper.find('.concept-jump').exists()).toBe(false)
    wrapper.unmount()
  })
})


it('keeps each lecture’s relations when concept names repeat across lectures', () => {
  const repeated = ['s1', 's2'].map(node_id => ({ node_id,
    knowledge_structure: [{ knowledge_points: [{ name: '变量' }, { name: '类型' }] }],
    knowledge_relations: [{ source_name: '变量', target_name: '类型', relation_type: 'applies_to', reason: '变量具有类型' }] }))
  const sections = buildHandoutConceptSections(repeated, ['s1', 's2'].map(id => ({ id, title: id, anchor: id,
    blocks: [{ id: id + '-b', anchor: id + '-b', content: '变量具有类型', knowledge: ['变量', '类型'] }] })))
  expect(sections.map(section => section.relations.length)).toEqual([1, 1])
  expect(sections[1]?.nodes.every(node => node.anchor === 's2-b')).toBe(true)
  expect(sections[1]?.relations[0]?.source).toBe('legacy:s2:变量')
})


it('navigates through exact handout evidence when concept labels differ from prose', () => {
  const reading = [{ id: 's', title: '类型', anchor: 's', blocks: [{ id: 'b', anchor: 'block-b', content: 'int 用于表示整数。', knowledge: [] }] }]
  const plan = { node_id: 's', handout_revision_id: 'r',
    knowledge_structure: [{ knowledge_points: [{ name: '整型 (int)' }, { name: '数据类型' }] }],
    knowledge_relations: [{ source_name: '整型 (int)', target_name: '数据类型', relation_type: 'generalizes', reason: '属于基本类型',
      source_refs: [{ kind: 'handout', revision_id: 'r', node_id: 's', block_id: 'b' }] }] }
  expect(buildHandoutConceptSections([plan], reading)[0]?.nodes.map(node => node.anchor)).toEqual(['block-b', 'block-b'])
  plan.knowledge_relations[0]!.source_refs[0]!.revision_id = 'old'
  expect(buildHandoutConceptSections([plan], reading)[0]?.nodes.every(node => !node.anchor)).toBe(true)
})


it('lets the student inspect concepts before explicitly returning to the handout', async () => {
  const navigate = vi.fn()
  const wrapper = mount(HandoutConceptMap, { props: { sections: buildHandoutConceptSections(plans, reading), navigate } })
  await wrapper.get('[data-concept-id="id-a"]').trigger('click')
  expect(wrapper.get('.concept-detail').text()).toContain('A 的说明')
  expect(navigate).toHaveBeenCalledWith('b2')
  await wrapper.get('.concept-jump').trigger('click')
  expect(navigate).toHaveBeenCalledWith('b2')
  wrapper.unmount()
})

it('restores directly readable relation steps and follows the reading section without new path records', async () => {
  const sections = buildHandoutConceptSections(plans, reading)
  const navigate = vi.fn()
  const wrapper = mount(HandoutConceptMap, { props: { sections, currentSection: 's1', navigate } })
  expect(wrapper.find('.concept-relations .concept-relation').exists()).toBe(true)
  expect(wrapper.get('details.concept-relation').attributes('open')).toBeDefined()
  expect(wrapper.findAll('.concept-relation-fields dt').map(n => n.text())).toContain('关系依据')
  expect(wrapper.findAll('.concept-relation-fields dt').map(n => n.text())).toContain('推导步骤')
  expect(wrapper.find('.concept-relation-number').exists()).toBe(false)
  expect(wrapper.find('.concept-coverage').exists()).toBe(false)
  expect(wrapper.text()).toContain('建立差商')
  expect(wrapper.text()).toContain('求极限')
  expect(wrapper.text()).toContain('极限存在')
  await wrapper.get('[data-concept-id="id-a"]').trigger('click')
  expect(navigate).toHaveBeenCalledWith('b2')
  wrapper.unmount()
})

it('keeps the knowledge map compact and navigates from reference-style concept nodes', async () => {
  const navigate = vi.fn()
  const wrapper = mount(HandoutKnowledgeMap, { props: { sections: buildHandoutConceptSections(plans, reading), currentSection: 's1', navigate } })
  expect(wrapper.get('h3').text()).toBe('概念关系')
  expect(wrapper.get('.concept-relations').attributes('open')).toBeUndefined()
  await wrapper.get('[data-concept-id="id-a"]').trigger('click')
  expect(navigate).toHaveBeenCalledWith('b2')
  expect(wrapper.get('.concept-relations .concept-relation').text()).toContain('极限存在')
  await wrapper.get('.aid-scope-toggle').trigger('click')
  expect(wrapper.get('.map-lecture').classes()).toContain('is-current')
  await wrapper.get('.map-lecture button').trigger('click')
  expect(wrapper.find('.map-reset').exists()).toBe(true)
  wrapper.unmount()
})

it('clears a removed map focus when the available knowledge changes', async () => {
  const sections = buildHandoutConceptSections(plans, reading)
  const wrapper = mount(HandoutKnowledgeMap, { props: { sections, currentSection: 's1', navigate: vi.fn() } })
  await wrapper.get('.aid-scope-toggle').trigger('click')
  await wrapper.get('.map-lecture button').trigger('click')
  expect(wrapper.find('.map-reset').exists()).toBe(true)
  await wrapper.setProps({ sections: [{ ...sections[0]!, nodes: [{ id: 'replacement', name: '新概念', statement: '新说明', anchor: 'b2', external: false }], relations: [] }] })
  expect(wrapper.find('.map-reset').exists()).toBe(false)
  expect(wrapper.get('.map-lecture button').text()).toContain('新概念')
  wrapper.unmount()
})


it('uses the parent reading position and defaults to direct connections without losing the whole lecture', async () => {
  const section = buildHandoutConceptSections(plans, reading)[0]!
  section.nodes.push({id:'unrelated',name:'无关概念',statement:'',anchor:'b9',external:false})
  const wrapper = mount(HandoutConceptMap, {props:{sections:[section],currentSection:'s1',currentBlockAnchor:'b2'}})
  expect(wrapper.find('[data-concept-id="unrelated"]').exists()).toBe(false)
  expect(wrapper.get('.concept-view-switch button').attributes('aria-pressed')).toBe('true')
  await wrapper.findAll('.concept-view-switch button')[1]!.trigger('click')
  expect(wrapper.find('[data-concept-id="unrelated"]').exists()).toBe(true)
  expect(wrapper.find('.concept-sections').exists()).toBe(false)
  wrapper.unmount()
})
