import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import TextSelectionAiAction from '../../components/TextSelectionAiAction.vue'

function selectionFixture(text: string) {
  const host = document.createElement('section')
  const paragraph = document.createElement('p')
  paragraph.textContent = text
  host.appendChild(paragraph)
  document.body.appendChild(host)
  Object.defineProperty(host, 'clientWidth', { configurable: true, value: 640 })
  host.getBoundingClientRect = () => ({
    x: 100, y: 100, left: 100, top: 100, right: 740, bottom: 500, width: 640, height: 400,
    toJSON: () => ({}),
  })
  const range = {
    startContainer: paragraph.firstChild,
    endContainer: paragraph.firstChild,
    getBoundingClientRect: () => ({
      x: 180, y: 220, left: 180, top: 220, right: 420, bottom: 242, width: 240, height: 22,
      toJSON: () => ({}),
    }),
  } as unknown as Range
  return { host, range }
}

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('文中选区 AI 快捷操作', () => {
  it('仅在当前文档选中有效文字后浮出入口，并就地收集修改要求', async () => {
    const { host, range } = selectionFixture('理解函数模型并确定定义域')
    const removeAllRanges = vi.fn()
    vi.spyOn(window, 'getSelection').mockReturnValue({
      toString: () => '理解函数模型并确定定义域',
      rangeCount: 1,
      getRangeAt: () => range,
      removeAllRanges,
    } as unknown as Selection)
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: { container: host, label: 'AI 修改' },
    })

    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    await nextTick()

    expect(wrapper.get('button').text()).toContain('AI 修改')
    await wrapper.get('button').trigger('click')
    expect(host.querySelector('blockquote')?.textContent).toContain('理解函数模型并确定定义域')
    const textarea = host.querySelector('textarea') as HTMLTextAreaElement
    textarea.value = '改成可观察、可检查的学习行为'
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await nextTick()
    expect(wrapper.emitted('invoke')).toEqual([[
      {
        text: '理解函数模型并确定定义域',
        instruction: '改成可观察、可检查的学习行为',
        source: 'selection',
      },
    ]])
    expect(removeAllRanges).not.toHaveBeenCalled()
  })

  it('短选区不打断用户', async () => {
    const { host, range } = selectionFixture('函')
    vi.spyOn(window, 'getSelection').mockReturnValue({
      toString: () => '函',
      rangeCount: 1,
      getRangeAt: () => range,
    } as unknown as Selection)
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: { container: host },
    })

    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    await nextTick()

    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('悬停段落时提供同一个嵌入式修改入口', async () => {
    const { host } = selectionFixture('以真实任务理解函数模型')
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: { container: host, label: 'AI 修改' },
    })

    host.querySelector('p')!.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()

    expect(wrapper.get('.text-selection-ai__trigger').text()).toContain('AI 修改')
    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    expect(host.querySelector('blockquote')?.textContent).toContain('以真实任务理解函数模型')
    expect(host.querySelector('.text-selection-ai__composer')?.textContent).toContain('修改当前段落')
  })

  it('把精确对象身份随请求发送，并把输入框追加在对象下方', async () => {
    const host = document.createElement('section')
    const section = document.createElement('section')
    section.dataset.aiSectionId = 'section-1'
    const inlineAnchor = document.createElement('div')
    inlineAnchor.dataset.aiInlineAnchor = 'true'
    const field = document.createElement('p')
    field.dataset.aiField = 'teacher_activity'
    field.dataset.aiItemId = 'module-1'
    field.dataset.aiLabel = '教师活动'
    field.textContent = '教师演示转换过程'
    inlineAnchor.appendChild(field)
    section.appendChild(inlineAnchor)
    host.appendChild(section)
    document.body.appendChild(host)
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 640 })
    host.getBoundingClientRect = () => ({
      x: 0, y: 0, left: 0, top: 0, right: 640, bottom: 400, width: 640, height: 400,
      toJSON: () => ({}),
    })
    field.getBoundingClientRect = () => ({
      x: 20, y: 40, left: 20, top: 40, right: 420, bottom: 80, width: 400, height: 40,
      toJSON: () => ({}),
    })
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: { container: host, targetSelector: '[data-ai-field]' },
    })

    field.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()
    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    expect(inlineAnchor.nextElementSibling?.classList.contains('text-selection-ai-host')).toBe(true)
    expect(field.querySelector('.text-selection-ai-host')).toBeNull()
    expect(section.textContent).toContain('教师活动 · 修改当前段落')

    const textarea = section.querySelector('textarea') as HTMLTextAreaElement
    textarea.value = '增加学生预测'
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    section.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await nextTick()

    expect(wrapper.emitted('invoke')).toEqual([[
      {
        text: '教师演示转换过程',
        instruction: '增加学生预测',
        source: 'block',
        target: {
          sectionNodeId: 'section-1',
          field: 'teacher_activity',
          itemId: 'module-1',
          label: '教师活动',
        },
      },
    ]])
  })
})
