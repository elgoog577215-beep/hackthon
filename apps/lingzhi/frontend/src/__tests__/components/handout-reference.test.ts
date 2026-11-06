import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HandoutReferencePanel from '@/components/HandoutReferencePanel.vue'
import { buildHandoutReference, type ReferenceSection } from '@/utils/handout-reference'
import { activeLocale } from '@/shared/i18n'
const block = (id: string, type: string, content: string, title = id) => ({ block_id: id, content_type: type, title, content })
const sections: ReferenceSection[] = [
  { id: 'a', title: '第一讲', blocks: [
    block('definition', '定义', '在 $P(B)>0$ 时，条件概率为：\n\n$$P(A|B)=\\frac{P(A\\cap B)}{P(B)}$$', '条件概率'),
    block('theorem', 'theorem', '当事件互斥时，$P(A\\cup B)=P(A)+P(B)$。', '加法定理'),
    block('example', 'example', '$$x=2$$\n\n$$x=2$$', '计算示例'),
    block('folded', 'explanation', '<details><summary>答案</summary>\n\n$$hidden=9$$\n\n</details>'),
    block('code', 'explanation', '```c\n// $not_math=1$\n```'),
    block('answer', 'answer', '$$secret=42$$'),
    { ...block('linked-answer', 'explanation', '$$secret=99$$'), answer_to: 'exercise' },
  ] },
  { id: 'b', title: '第二讲', blocks: [block('definition-2', 'definition', '随机变量是样本空间上的实值函数。', '随机变量')] },
]
beforeEach(() => { activeLocale.value = 'zh' })

describe('Handout formula and theorem reference', () => {
  it('keeps complete definitions and conditions, extracts math without code or folded answers', () => {
    const result = buildHandoutReference(sections)
    const items = result[0]!.items
    expect(items.find(item => item.id === 'definition:statement')?.content).toContain('P(B)>0')
    expect(items.find(item => item.id === 'definition:formulas')?.html).toContain('katex')
    expect(items.some(item => item.blockId === 'example')).toBe(false)
    expect(items.find(item => item.id === 'definition:formulas')?.content).toContain('P(B)>0')
    expect(items.some(item => ['code', 'folded', 'answer', 'linked-answer'].includes(item.blockId))).toBe(false)
    expect(result[1]!.items[0]?.kind).toBe('definition')
  })
  it('follows the current lecture, supports whole-course filtering and stable jumps', async () => {
    const wrapper = mount(HandoutReferencePanel, { props: { sections, currentSection: 'a' }, global: { stubs: { MarkdownRenderer: { props: ['content'], template: '<div>{{ content }}</div>' }, MathText: { props: ['content'], template: '<span>{{ content }}</span>' } } } })
    expect(wrapper.findAll('.reference-item')).toHaveLength(2)
    expect(wrapper.find('.reference-kinds').exists()).toBe(false)
    expect(wrapper.find('.reference-context').exists()).toBe(false)
    expect(wrapper.find('.aid-toolbar input').exists()).toBe(false)
    await wrapper.get('.aid-scope-toggle').trigger('click')
    expect(wrapper.findAll('.reference-item')).toHaveLength(3)
    await wrapper.get('.aid-scope-toggle').trigger('click')
    await wrapper.findAll('.reference-open')[0]!.trigger('click')
    expect(wrapper.emitted('jump')).toEqual([['definition']])
    await wrapper.setProps({ currentSection: 'b' })
    expect(wrapper.text()).toContain('随机变量是样本空间上的实值函数')
    expect(wrapper.text()).not.toContain('条件概率')
    await wrapper.get('.aid-search-toggle').trigger('click')
    await wrapper.get('input').setValue('不存在')
    expect(wrapper.findAll('.reference-item')).toHaveLength(0)
    expect(wrapper.text()).toContain('没有匹配')
    await wrapper.get('input').setValue('')
    await wrapper.setProps({ sections: [{ id: 'b', title: '修订后的讲义', blocks: [block('new', 'definition', '新版定义：$$x=2$$', '新概念')] }] })
    expect(wrapper.text()).toContain('新概念')
    expect(wrapper.text()).not.toContain('随机变量')
    activeLocale.value = 'en'
    await wrapper.vm.$nextTick()
    expect(wrapper.attributes('aria-label')).toBe('Quick reference')
    expect(wrapper.get('.reference-open').attributes('aria-label')).toContain('Go to passage')
    wrapper.unmount()
  })
  it('shows each display formula once despite nested renderer wrappers', () => {
    const items = buildHandoutReference([{ id: 's', title: '公式', blocks: [block('d', 'definition', '$$x=1$$\n\n$$x=1$$\n\n$$y=2$$')] }])[0]!.items
    const root = document.createElement('div')
    root.innerHTML = items.find(item => item.kind === 'formula')!.html!
    expect(root.querySelectorAll('.reference-formula')).toHaveLength(2)
    expect(root.querySelectorAll('.katex-display')).toHaveLength(2)
  })
  it('indexes text results, methods and pitfalls, but only canonical or boxed formulas', () => {
    const items = buildHandoutReference([{ id: 's', title: 'Skills', blocks: [
      block('r', 'result', '成立条件：$x>0$。\n\n$$y=x^2$$'),
      block('m', 'method', '先确认问题，再选择方法。'),
      block('w', 'misconception', '不要把相关性理解为因果。'),
      block('v', 'definition', '变量 $x$ 是输入。'),
      block('b', 'explanation', '$$\\boxed{a=b}$$\n\n$$temporary=9$$'),
      block('d', 'definition', '公开定义。<details><summary>提示</summary>secret</details>'),
    ] }])[0]!.items
    expect(items.filter(i => i.kind === 'formula').map(i => i.blockId)).toEqual(['r', 'b'])
    expect(items.find(i => i.blockId === 'b')?.html).not.toContain('temporary')
    expect(items.find(i => i.blockId === 'm')?.kind).toBe('method')
    expect(items.find(i => i.blockId === 'w')?.kind).toBe('warning')
    expect(items.find(i => i.blockId === 'd')?.content).not.toContain('secret')
  })

})

it('excludes inline boxed prose and whole nested folded subtrees like the reference reader', () => {
  const result = buildHandoutReference([{ id: 'scope', title: '范围', blocks: [
    block('inline', 'explanation', '正文行内 $\\boxed{x=1}$'),
    block('display', 'explanation', '$$\\boxed{x=2}$$'),
    block('nested', 'definition', '<details><summary>外层答案</summary><details>$$secret=1$$</details>$$secret=2$$</details>\n\n$$public=3$$'),
    block('unfinished', 'definition', '<details>$$secret=4$$'),
  ] }])[0]!.items.filter(item => item.kind === 'formula')
  expect(result.map(item => item.blockId)).toEqual(['display', 'nested'])
  expect(result.map(item => item.content).join(' ')).not.toContain('secret')
  expect(result.find(item => item.blockId === 'nested')!.html).not.toContain('secret')
})

it('scrolls the reference results to the current lecture without scrolling the reading page', async () => {
  const wrapper = mount(HandoutReferencePanel, { props: { sections: [
    { id: 'a', title: '第一讲', blocks: [block('one', 'definition', '$$x=1$$')] },
    { id: 'b', title: '第二讲', blocks: [block('two', 'definition', '$$x=2$$')] },
  ], currentSection: 'a' } })
  await wrapper.get('.aid-scope-toggle').trigger('click')
  const results = wrapper.get('.reference-results').element as HTMLElement
  vi.spyOn(results, 'getBoundingClientRect').mockReturnValue({ top: 100 } as DOMRect)
  vi.spyOn(wrapper.get('[data-reference-section="b"]').element, 'getBoundingClientRect').mockReturnValue({ top: 380 } as DOMRect)
  await wrapper.setProps({ currentSection: 'b' })
  await Promise.resolve()
  expect(results.scrollTop).toBe(280)
  wrapper.unmount()
})


it('shows programming methods directly from the body while keeping exercises and answers out', () => {
  const wrapper = mount(HandoutReferencePanel, { props: { currentSection: 's', sections: [{ id: 's', title: '编程', blocks: [
    block('method', 'method', '输入必须非空。\n\n1. 初始化累加值。\n2. 逐项累加。\n\n```python\ntotal += value\n```', '累加算法'),
    block('exercise', 'exercise', '请实现快速排序', '练习'),
    block('answer', 'answer', '答案内容', '参考答案'),
  ] }] } })
  expect(wrapper.findAll('.reference-item')).toHaveLength(1)
  expect(wrapper.text()).toContain('输入必须非空')
  expect(wrapper.text()).toContain('逐项累加')
  expect(wrapper.text()).not.toContain('答案内容')
  expect(wrapper.find('code').text()).toContain('total += value')
  wrapper.unmount()
})

 it('retains formula conditions and folds long prose only between complete blocks', () => {
   const content = '首段完整说明。'.repeat(60) + '\n\n- 参数：接收实际值。\n- 返回值：输出结果。'
   const data = [{ id: 'long', title: '长内容', blocks: [block('long', 'definition', content)] }]
   const item = buildHandoutReference(data)[0]!.items[0]!
   expect(item.previewHtml).toContain('首段完整说明。'.repeat(60))
   expect(item.remainderHtml).toContain('<ul>')
   const wrapper = mount(HandoutReferencePanel, { props: { sections: data, currentSection: 'long' } })
   expect(wrapper.findAll('.reference-item')).toHaveLength(1)
   expect(wrapper.find('details summary').text()).toContain('展开完整条目')
   const conditions = mount(HandoutReferencePanel, { props: { sections, currentSection: 'a' } })
   expect(conditions.find('.reference-excerpt').text()).toContain('在')
   expect(conditions.find('.reference-excerpt').html()).toContain('katex')
 })
