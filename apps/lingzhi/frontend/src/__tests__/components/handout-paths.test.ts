import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import HandoutLearningPaths from '@/components/HandoutLearningPaths.vue'
import HandoutKnowledgeMap from '@/components/HandoutKnowledgeMap.vue'
import { buildHandoutPaths, pathRows } from '@/utils/handout-paths'
import { conceptNeighborhood, type HandoutConceptSection } from '@/utils/handout-concepts'
import { activeLocale } from '@/shared/i18n'

const sections = [{ id: 's', title: '选法', blocks: [
  { block_id: 'b', content_type: 'method', title: '先检查条件', content: '根据是否可导选方法。' },
  { block_id: 'answer', content_type: 'answer', title: '自测答案', content: '答案。' },
] }]
const ref = { kind: 'handout', revision_id: 'r', node_id: 's', block_id: 'b' }
const plan = { node_id: 's', handout_revision_id: 'r', reading_schema_version: 'study_reading_v1', learning_paths: [{ id: 'p', title: '求导方法', kind: 'method', steps: [
  { id: '1', parent_id: '', stage: 'start', text: '是否可导', source_refs: [ref] },
  { id: '2', parent_id: '1', stage: 'step', text: '求导规则', condition: '可导', reason: '满足规则', source_refs: [ref] },
  { id: '3', parent_id: '1', stage: 'step', text: '使用定义', condition: '待判断', reason: '检查极限', source_refs: [ref] },
  { id: '4', parent_id: '2', stage: 'result', text: '得到导数', source_refs: [ref] },
] }] }
const globals = { stubs: { MathText: { props: ['content'], template: '<span>{{ content }}</span>' }, HandoutConceptMap: true } }
const mapSections: HandoutConceptSection[] = [
  { id: 's', title: '第一讲', anchor: 's', blockAnchors: ['b'], nodes: [{ id: 'a', name: '同名概念', statement: '第一种含义', anchor: 'b', external: false }], relations: [] },
  { id: 't', title: '第二讲', anchor: 't', blockAnchors: ['c'], nodes: [{ id: 'b', name: '同名概念', statement: '另一种含义', anchor: 'c', external: false }, { id: 'a', name: '同名概念', statement: '第一种含义', anchor: 'b', external: true }], relations: [{ id: 'edge', source: 'a', target: 'b', type: 'contrasts_with', reason: '含义不同', conditions: [], distinction: '', steps: [], sourceRefs: [], groupId: '', groupOperator: '', necessity: '' }] },
]
beforeEach(() => { activeLocale.value = 'zh' })

describe('source-bound learning paths', () => {
  it('keeps sibling branches together and preserves each step’s source', () => {
    const result = buildHandoutPaths([plan], sections, 'r', { s: 'ready' })[0]!
    expect(pathRows(result.paths[0]!).map(r => r.step.id)).toEqual(['1', '2', '4', '3'])
    expect(result.paths[0]!.steps[1]!.sources).toEqual([{ blockId: 'b', title: '先检查条件' }])
    expect(result.passages).toEqual([{ blockId: 'b', title: '先检查条件' }])
  })
  it('hides stale, incomplete and answer-linked paths instead of inventing replacement steps', () => {
    expect(buildHandoutPaths([plan], sections, 'new', { s: 'ready' })[0]!.paths).toEqual([])
    expect(buildHandoutPaths([plan], sections, 'r', { s: 'stale' })[0]!.paths).toEqual([])
    expect(buildHandoutPaths([plan], sections, 'r', { s: 'legacy' })[0]!.paths).toEqual([])
    const invalid = structuredClone(plan)
    invalid.learning_paths[0]!.steps[1]!.source_refs[0]!.block_id = 'answer'
    expect(buildHandoutPaths([invalid], sections, 'r', { s: 'ready' })[0]!.paths).toEqual([])
  })
  it('renders conditions, reasons, empty states, search and stable jumps in both languages', async () => {
    const data = buildHandoutPaths([plan], sections, 'r', { s: 'ready' })
    const wrapper = mount(HandoutLearningPaths, { props: { sections: data, currentSection: 's' }, global: globals })
    expect(wrapper.text()).toContain('可导')
    expect(wrapper.text()).toContain('满足规则')
    expect(wrapper.text()).toContain('未整理独立的检验步骤')
    await wrapper.get('.path-sources button').trigger('click')
    expect(wrapper.emitted('jump')).toEqual([['b']])
    await wrapper.get('input').setValue('不存在')
    expect(wrapper.find('.learning-path').exists()).toBe(false)
    expect(wrapper.text()).toContain('没有匹配')
    await wrapper.setProps({ sections: buildHandoutPaths([], sections, 'r', { s: 'legacy' }) })
    expect(wrapper.text()).toContain('尚未整理思维链')
    activeLocale.value = 'en'; await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Learning paths have not been organized')
    wrapper.unmount()
  })
})

describe('course knowledge map', () => {
  it('retains distinct same-name concepts and cross-lecture edges by saved identity', () => {
    const graph = conceptNeighborhood(mapSections, new Set(['a']), '关联')
    expect(graph.nodes.map(n => n.id)).toEqual(['a', 'b'])
    expect(graph.nodes[0]!.external).toBe(false)
    expect(graph.relations).toHaveLength(1)
    expect(conceptNeighborhood(mapSections, new Set(), '').nodes).toEqual([])
  })
  it('follows reading in current scope and explores exact neighborhoods across the course', async () => {
    const wrapper = mount(HandoutKnowledgeMap, { props: { sections: mapSections, currentSection: 's', navigate: () => {} }, global: globals })
    expect(wrapper.getComponent({ name: 'HandoutConceptMap' }).props('sections')[0].id).toBe('s')
    await wrapper.setProps({ currentSection: 't' })
    expect(wrapper.getComponent({ name: 'HandoutConceptMap' }).props('sections')[0].id).toBe('t')
    await wrapper.findAll('.reading-aid-scope button')[1]!.trigger('click')
    expect(wrapper.findAll('.map-lecture button')).toHaveLength(2)
    await wrapper.findAll('.map-lecture button')[0]!.trigger('click')
    expect(wrapper.getComponent({ name: 'HandoutConceptMap' }).props('sections')[0].relations).toHaveLength(1)
    await wrapper.get('.map-reset').trigger('click')
    await wrapper.get('input').setValue('另一种')
    expect(wrapper.findAll('.map-lecture button')).toHaveLength(1)
    expect(wrapper.text()).toContain('第二讲')
    expect(wrapper.text()).not.toContain('第一讲')
    wrapper.unmount()
  })
})
