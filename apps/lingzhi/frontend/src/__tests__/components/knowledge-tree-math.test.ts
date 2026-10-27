import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Tree from '@/components/KnowledgeMasteryTree.vue'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import { createContentKnowledgeTree } from '@/utils/knowledge-tree-layout'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'

const name = String.raw`$\frac{f(x)-f(a)}{x-a}$ 的极限取决于分子分母趋零速度`
const originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype,'scrollIntoView')
beforeEach(async () => {
  Object.defineProperty(HTMLElement.prototype,'scrollIntoView',{configurable:true,value:vi.fn()})
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
  await setLocale('zh')
})
afterEach(() => {
  vi.restoreAllMocks(); vi.unstubAllGlobals()
  if(originalScrollIntoView)Object.defineProperty(HTMLElement.prototype,'scrollIntoView',originalScrollIntoView)
  else Reflect.deleteProperty(HTMLElement.prototype,'scrollIntoView')
})

it('renders formulas in course, branch and leaf labels while preserving text, identity and selection', async () => {
  const points = [{ knowledge_id:'k1', parent_id:'cat', name }]
  const tree = createContentKnowledgeTree('c', String.raw`函数 $f(x)$`, [{ id:'cat', name:String.raw`条件 $x\ne a$` }], points)
  const original = structuredClone(tree)
  const w = mount(Tree, { props: { contentTree: tree, showMastery: false } })
  try {
    expect(w.get('.tree-course strong').find('.katex').exists()).toBe(true)
    expect(w.get('.tree-branch-name').find('.katex').exists()).toBe(true)
    const leaf = w.get('[data-knowledge-id="k1"]')
    expect(leaf.find('.katex .mfrac').exists()).toBe(true)
    expect(leaf.get('.tree-leaf-copy strong').text()).toContain('的极限取决于分子分母趋零速度')
    expect(leaf.find('.katex-html').text()).not.toContain('\\frac')
    expect(w.find('.math-fallback,.katex-error').exists()).toBe(false)
    await leaf.trigger('click')
    expect(w.emitted('select')?.[0]?.[0]).toBe('k1')
    expect(tree).toEqual(original)
  } finally { w.unmount() }
})

it('uses the same math rendering for the selected knowledge title and conditions', async () => {
  const point = { knowledge_id:'k1', parent_id:'cat', name, statement:name, conditions:[String.raw`$x\ne a$`],
    section_refs:['cpu'], source_refs:[], source_quotes:[] }
  const tree = { revision_id:'kb', source_mode:'handouts', categories:[{id:'cat',name:'极限'}], knowledge_points:[point], relations:[] }
  const view = { enabled:true, can_edit:true, workflow:'knowledge_first_generic_v1', source_mode:'handouts',
    tree, history:[tree], knowledge_revision:'kb', document_revision:'d', result_version:'v', candidates:[],
    jobs:[], active_jobs:[], handouts:[], source_handouts:[], lesson_options:[{lesson_id:'cpu', title:'导数', can_generate:true}] }
  vi.spyOn(http,'get').mockResolvedValue({ data:view })
  const w = mount(Manager,{ props:{courseId:'c',treeOnly:true,initialLessonId:'cpu'} }); await flushPromises()
  try {
    await w.get('[data-knowledge-id="k1"]').trigger('click'); await flushPromises()
    expect(w.get('.point-card h2').find('.katex .mfrac').exists()).toBe(true)
    expect(w.get('.point-card li').find('.katex').exists()).toBe(true)
    expect(w.get('.point-card h2').text()).toContain('的极限取决于分子分母趋零速度')
    expect(point.name).toBe(name)
  } finally { w.unmount() }
})
