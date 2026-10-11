import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildHandoutConceptSections, conceptLayers, type HandoutConceptSection } from '@/utils/handout-concepts'
import HandoutConceptMap from '@/components/HandoutConceptMap.vue'
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
  it('沿用知识身份绑定和知识点内部关系，不从共同出现的词语造边', () => {
    const sections = buildHandoutConceptSections(plans, reading)
    expect(sections[0]?.nodes.find(node => node.name === 'A')?.anchor).toBe('b2')
    expect(sections[0]?.relations[0]).toMatchObject({ source: 'A', target: 'B', type: 'derives', conditions: ['极限存在'], steps: ['建立差商', '求极限'] })
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
    section.relations.push({ ...section.relations[0]!, source: 'B', target: 'A', id: 'reverse' })
    expect(conceptLayers(section).flat().map(node => node.id)).toEqual(['A', 'B'])
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
    await wrapper.get('[data-concept-id="A"]').trigger('click')
    expect(scroll).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    expect(root.querySelector('details')!.open).toBe(true)
    expect(wrapper.text()).toContain('极限存在')
    expect(wrapper.text()).toContain('建立差商')
    expect(wrapper.get('[data-concept-id="A"]').attributes('aria-pressed')).toBe('true')
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
