import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import HandoutReferencePanel from '@/components/HandoutReferencePanel.vue'
import { buildHandoutReference, type ReferenceSection, type ReferenceRange } from '@/utils/handout-reference'
import { activeLocale } from '@/shared/i18n'
const block = (id: string, type: string, content: string, title = id) => ({ block_id: id, content_type: type, title, content })
function marked(id: string, content: string, pieces: {title: string; kind: ReferenceRange['kind']; content: string}[]) {
  return { ...block(id, 'explanation', content), reference_schema_version: 'handout_reference_v1', references: pieces.map((p, i) => {
    const start = Array.from(content.slice(0, content.indexOf(p.content))).length
    return { ...p, id: `r${i + 1}`, start, end: start + Array.from(p.content).length }
  }) }
}
const statement = '当 $P(B)>0$ 时，\n\n$$P(A|B)=\\frac{P(A\\cap B)}{P(B)}$$'
const rule = '字典键必须可哈希，例如字符串和整数。'
const sections: ReferenceSection[] = [
  { id: 'a', title: '第一讲', blocks: [marked('multi', '动机🙂。\n\n' + statement + '\n\n长篇证明不在速览。\n\n' + rule,
    [{title:'条件概率',kind:'formula',content:statement},{title:'字典键',kind:'rule',content:rule}])] },
  { id: 'b', title: '第二讲', blocks: [block('legacy', 'definition', '旧版长解释。'.repeat(100), '旧版定义')] },
]
beforeEach(() => { activeLocale.value = 'zh' })

describe('Source-bound handout reference', () => {
  it('projects multiple exact statements from one block, preserving conditions and Unicode offsets', () => {
    const items = buildHandoutReference(sections)[0]!.items
    expect(items).toHaveLength(2)
    expect(items[0]!.content).toBe(statement)
    expect(items[0]!.html).toContain('katex-display')
    expect(items[1]!.content).toBe(rule)
    expect(items.map(x => x.html).join('')).not.toContain('长篇证明')
  })
  it('rejects stale ranges instead of displaying an old or first-paragraph summary', () => {
    const changed = structuredClone(sections)
    changed[0]!.blocks[0]!.content = changed[0]!.blocks[0]!.content.replace('P(B)>0','P(B)=0')
    const items = buildHandoutReference(changed)[0]!.items
    expect(items.some(i => i.title === '条件概率')).toBe(false)
    const wrapper = mount(HandoutReferencePanel, { props: { sections: changed, currentSection: 'a' } })
    // At least the unchanged range remains safely bound to its exact source.
    expect(wrapper.text()).not.toContain('长篇证明')
  })
  it('uses compact formula extraction for legacy math and a source index for unmarked prose', () => {
    const items = buildHandoutReference([{id:'s',title:'旧讲义',blocks:[
      block('math','definition',statement + '\n\n' + '很长的证明。'.repeat(80)),
      block('text','method','很长的讲解。'.repeat(80),'方法'),
      block('boxed','explanation','$$\\boxed{x=1}$$\n\n$$temporary=9$$'),
    ]}])[0]!.items
    expect(items[0]!.html).toContain('katex-display')
    expect(items[0]!.html).toContain('当')
    expect(items[0]!.html).not.toContain('很长的证明')
    expect(items[1]!.mode).toBe('source')
    expect(items[1]!.html).toBe('')
    expect(items[2]!.html).not.toContain('temporary')
  })
  it('excludes exercises, answers, literal code and folded content', () => {
    const items = buildHandoutReference([{id:'s',title:'范围',blocks:[
      block('exercise','exercise','$$secret=1$$'),block('answer','answer','$$secret=2$$'),
      {...marked('linked',rule,[{title:'秘密',kind:'rule',content:rule}]),answer_to:'exercise'},
      block('code','explanation','```html\n$$not_math=1$$\n```'),
      block('folded','definition','<details><summary>外层</summary><details>$$secret=3$$</details>$$secret=4$$</details>\n\n$$public=1$$'),
    ]}])[0]!.items
    expect(items.map(i=>i.blockId)).toEqual(['folded'])
    expect(items[0]!.html).not.toContain('secret')
  })
  it('shows all lectures, highlights one exact reference, and supports search and source jumps', async () => {
    const wrapper = mount(HandoutReferencePanel, {props:{sections,currentSection:'a',currentBlock:'multi'}})
    expect(wrapper.findAll('.reference-item')).toHaveLength(3)
    expect(wrapper.findAll('.reference-item-number').map(n=>n.text())).toEqual(['1','2','1'])
    expect(wrapper.find('.reference-chapter-number').exists()).toBe(false)
    expect(wrapper.findAll('.reference-item.is-current')).toHaveLength(1)
    expect(wrapper.find('.reference-details').exists()).toBe(false)
    await wrapper.get('.reference-open').trigger('click')
    expect(wrapper.emitted('jump')).toEqual([['multi', 'multi:r1']])
    expect(wrapper.find('.aid-scope-toggle').exists()).toBe(false)
    expect(wrapper.findAll('.reference-item')).toHaveLength(3)
    await wrapper.get('.aid-search-toggle').trigger('click')
    await wrapper.get('input').setValue('不存在')
    expect(wrapper.text()).toContain('没有匹配')
    await wrapper.get('input').setValue('')
    await wrapper.setProps({currentSection:'b'})
    activeLocale.value='en';await wrapper.vm.$nextTick()
    expect(wrapper.attributes('aria-label')).toBe('Quick reference')
    expect(wrapper.text()).toContain('not marked here')
    expect(wrapper.text()).not.toContain('旧版长解释')
  })
})


it('keeps browsing independent of body location and navigates only on a click', async () => {
  const wrapper=mount(HandoutReferencePanel,{props:{sections,currentSection:'a'}})
  const root=wrapper.get('.reference-results').element as HTMLElement
  root.scrollTop=300
  await wrapper.get('.reference-results').trigger('wheel')
  await wrapper.get('.reference-results').trigger('scroll')
  await wrapper.setProps({currentSection:'b',currentBlock:'legacy'})
  expect(root.scrollTop).toBe(300)
  expect(wrapper.emitted('jump')).toBeUndefined()
  expect(wrapper.emitted('follow')).toBeUndefined()
  await wrapper.findAll('.reference-item')[1]!.get('.reference-expression').trigger('click')
  expect(wrapper.emitted('jump')).toEqual([['multi','multi:r2']])
  wrapper.unmount()
})


it('keeps adjacent legacy formula conditions and complete variable definitions without distant prose or orphan labels', () => {
  const content = '设另一个不相关的概念。\n\n## 条件概率\n\n当 $P(B)>0$ 时，\n\n$$P(A|B)=1$$\n\n其中：\n\n- $A$ 是事件。\n- $B$ 是条件事件。'
  const item=buildHandoutReference([{id:'s',title:'s',blocks:[block('b','definition',content)]}])[0]!.items[0]!
  expect(item.html).toContain('其中')
  expect(item.html).toContain('<ul>')
  expect(item.html).toContain('条件事件')
  expect(item.html).not.toContain('不相关')
  const orphan=buildHandoutReference([{id:'s',title:'s',blocks:[block('b','definition','$$x=1$$\n\n其中：\n\n## 下一节')]}])[0]!.items[0]!
  expect(orphan.html).not.toContain('其中')
})
