import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import TextSelectionAiAction from '../../components/TextSelectionAiAction.vue'
vi.mock('../../shared/i18n', () => ({
  t: (key: string) => key.split('.').pop(),
}))
let wrapper: VueWrapper
function fixture(
  markup = '<section data-ai-section-id="s1"><p data-ai-field="teacher_activity" data-ai-item-id="m1">保留前句。DeepSeek 4.0。保留后句。</p></section>',
) {
  const host = document.createElement('main')
  host.innerHTML = markup
  document.body.append(host)
  wrapper = mount(TextSelectionAiAction, {
    attachTo: document.body,
    props: { container: host, sourceRevision: 'r1' },
  })
  return host
}
async function open(element: Element) {
  element.dispatchEvent(new Event('pointerover', { bubbles: true }))
  await nextTick()
  ;(
    document.querySelector('.block-ai-menu [data-action=ask]') as HTMLButtonElement
  ).click()
  await nextTick()
}
async function submit(value: string) {
  if (!document.querySelector('textarea')) {
    (document.querySelector('.inline-edit-followups button') as HTMLButtonElement)?.click()
    await nextTick()
  }
  const input = document.querySelector('textarea')!
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  document
    .querySelector('form')!
    .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await nextTick()
}
function clickText(text: string) {
  const button = Array.from(
    document.querySelectorAll<HTMLButtonElement>('button'),
  ).find((b) => b.textContent?.trim() === text)!
  button.click()
  return nextTick()
}
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
describe('文中 AI 修改的完整操作', () => {
  it('在精确段落后展开，不移动焦点滚动，不把大组作为宿主', async () => {
    const host = fixture()
    const p = host.querySelector('p')!
    const focus = vi.spyOn(HTMLTextAreaElement.prototype, 'focus')
    await open(p)
    expect(p.nextElementSibling?.querySelector('textarea')).toBeTruthy()
    expect(focus).toHaveBeenCalledWith({ preventScroll: true })
    await submit('改成 5.0')
    expect(wrapper.emitted('invoke')?.[0]?.[0]).toMatchObject({
      text: p.textContent,
      source: 'block',
      target: { sectionNodeId: 's1', field: 'teacher_activity', itemId: 'm1' },
    })
  })
  it('选词只发送选词，并清除浏览器选区以便输入', async () => {
    const host = fixture()
    const p = host.querySelector('p')!
    const removeAllRanges = vi.fn()
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      toString: () => 'DeepSeek 4.0',
      removeAllRanges,
      getRangeAt: () => ({
        startContainer: p.firstChild,
        endContainer: p.firstChild,
        getBoundingClientRect: () => ({ right: 300, bottom: 250 }),
      }),
    } as unknown as Selection)
    document.dispatchEvent(new MouseEvent('mouseup'))
    await nextTick()
    ;(
      document.querySelector('.block-ai-menu [data-action=ask]') as HTMLButtonElement
    ).click()
    await nextTick()
    await submit('升到 5.0')
    expect(wrapper.emitted('invoke')?.[0]?.[0]).toMatchObject({
      text: 'DeepSeek 4.0',
      source: 'selection',
    })
    expect(removeAllRanges).toHaveBeenCalled()
  })
  it('生成失败保留输入，可重试；生成成功显示差异，继续调整保留原要求', async () => {
    const host = fixture()
    await open(host.querySelector('p')!)
    await submit('改成 5.0')
    await wrapper.setProps({ busy: true })
    await wrapper.setProps({ busy: false, errorMessage: '暂时失败' })
    expect(document.querySelector('textarea')?.value).toBe('改成 5.0')
    expect(document.querySelector('[role="alert"]')?.textContent).toBe(
      '暂时失败',
    )
    await submit('改成 5.0')
    await wrapper.setProps({ busy: true, errorMessage: '' })
    await wrapper.setProps({
      busy: false,
      candidatePending: true,
      changes: [{ before: '4.0', after: '5.0' }],
    })
    expect(document.querySelectorAll('.inline-edit-diff .markdown-renderer')).toHaveLength(2)
    expect(host.querySelector('p')?.textContent).toContain('4.0')
    await submit('补充一个例子')
    expect(wrapper.emitted('invoke')?.at(-1)?.[0]).toMatchObject({
      instruction: '改成 5.0\n补充一个例子',
    })
  })
  it('应用失败保留建议，成功后关闭；收起不会丢失生成状态', async () => {
    const host = fixture()
    await open(host.querySelector('p')!)
    await submit('修改')
    await wrapper.setProps({ busy: true })
    ;(
      document.querySelector('[aria-label="collapse"]') as HTMLButtonElement
    ).click()
    await nextTick()
    expect(document.querySelector('textarea')).toBeNull()
    await wrapper.setProps({ busy: false, candidatePending: true })
    ;(
      document.querySelector('[aria-label="expand"]') as HTMLButtonElement
    ).click()
    await nextTick()
    await clickText('apply')
    expect(wrapper.emitted('resolve')?.[0]).toEqual([true])
    await wrapper.setProps({ busy: true })
    await wrapper.setProps({ busy: false, errorMessage: '保存失败' })
    expect(document.querySelector('.inline-edit-decisions')).toBeTruthy()
    await clickText('apply')
    await wrapper.setProps({ busy: true })
    await wrapper.setProps({
      busy: false,
      candidatePending: false,
      errorMessage: '',
    })
    expect(document.querySelector('textarea')).toBeNull()
  })
  it('来源变化阻止提交和应用，但仍允许保留原文退出', async () => {
    const host = fixture()
    await open(host.querySelector('p')!)
    await wrapper.setProps({ candidatePending: true, sourceRevision: 'r2' })
    expect(document.querySelector('[role="alert"]')?.textContent).toBe(
      'sourceChanged',
    )
    const apply = Array.from(document.querySelectorAll('button')).find(
      (b) => b.textContent === 'apply',
    )!
    expect(apply.disabled).toBe(true)
    await clickText('discard')
    expect(wrapper.emitted('resolve')?.[0]).toEqual([false])
    await wrapper.setProps({ candidatePending: false })
    expect(document.querySelector('textarea')).toBeNull()
  })
  it('按学生端悬停显示解释、举例、简化、修改，快捷操作直接生成', async () => {
    const host = fixture()
    host.querySelector('p')!.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()
    expect(Array.from(document.querySelectorAll('.block-ai-menu button')).map(button => button.textContent?.trim())).toEqual(['explain','example','simplify','edit'])
    ;(document.querySelector('[data-action=example]') as HTMLButtonElement).click()
    await nextTick()
    expect(wrapper.emitted('invoke')?.[0]?.[0]).toMatchObject({ instruction:'examplePrompt',source:'block' })
    expect(document.querySelector('textarea')).toBeNull()
    expect(host.querySelector('p')!.nextElementSibling?.querySelector('.text-selection-ai__composer')).toBeTruthy()
    await wrapper.setProps({busy:true})
    await wrapper.setProps({busy:false,candidatePending:true,changes:[{before:'原文',after:'例子'}]})
    expect(document.querySelector('textarea')).toBeNull()
    await clickText('iterate')
    expect(document.querySelector('textarea')).toBeTruthy()
  })
  it('中文输入法回车只确认文字，正常回车才提交', async () => {
    const host = fixture()
    await open(host.querySelector('p')!)
    const input = document.querySelector('textarea')!
    input.value = '改成中文例子'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }))
    expect(wrapper.emitted('invoke')).toBeUndefined()
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    expect(wrapper.emitted('invoke')).toHaveLength(1)
  })
  it('表格中的修改嵌入当前行后，不破坏表格结构', async () => {
    const host = fixture(
      '<table><tbody><tr><td>教师活动</td><td>学生观察</td></tr></tbody></table>',
    )
    await open(host.querySelector('td')!)
    const row = host.querySelector('tr')!.nextElementSibling!
    expect(row.tagName).toBe('TR')
    expect(row.querySelector('td')?.colSpan).toBe(2)
    expect(row.querySelector('textarea')).toBeTruthy()
  })
})
