import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
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
    expect(items.find(item => item.blockId === 'example')?.html?.match(/reference-formula/g)).toHaveLength(1)
    expect(items.some(item => ['code', 'folded', 'answer', 'linked-answer'].includes(item.blockId))).toBe(false)
    expect(result[1]!.items[0]?.kind).toBe('definition')
  })
  it('shows whole handout first, filters by kind/scope, searches and returns stable block IDs', async () => {
    const wrapper = mount(HandoutReferencePanel, { props: { sections, currentSection: 'a' }, global: { stubs: { MarkdownRenderer: { props: ['content'], template: '<div>{{ content }}</div>' }, MathText: { props: ['content'], template: '<span>{{ content }}</span>' } } } })
    expect(wrapper.findAll('.reference-item')).toHaveLength(4)
    await wrapper.findAll('.reference-kinds button')[1]!.trigger('click')
    expect(wrapper.findAll('.reference-item')).toHaveLength(3)
    await wrapper.findAll('.reference-kinds button')[2]!.trigger('click')
    expect(wrapper.findAll('.reference-item')).toHaveLength(2)
    await wrapper.findAll('.reference-scope button')[1]!.trigger('click')
    expect(wrapper.findAll('.reference-item')).toHaveLength(1)
    await wrapper.get('.reference-jump').trigger('click')
    expect(wrapper.emitted('jump')).toEqual([['definition']])
    await wrapper.setProps({ currentSection: 'b' })
    expect(wrapper.text()).toContain('随机变量')
    expect(wrapper.text()).not.toContain('条件概率')
    await wrapper.get('input').setValue('不存在')
    expect(wrapper.findAll('.reference-item')).toHaveLength(0)
    expect(wrapper.text()).toContain('没有匹配')
    await wrapper.get('input').setValue('')
    await wrapper.setProps({ sections: [{ id: 'b', title: '修订后的讲义', blocks: [block('new', 'definition', '新版定义', '新概念')] }] })
    expect(wrapper.text()).toContain('新版定义')
    expect(wrapper.text()).not.toContain('随机变量')
    activeLocale.value = 'en'
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Definitions')
    expect(wrapper.text()).toContain('Go to passage')
    wrapper.unmount()
  })
})
