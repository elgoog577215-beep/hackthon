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
  it('仅在当前文档选中有效文字后浮出入口，并把选区交给 AI', async () => {
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
    expect(wrapper.emitted('invoke')).toEqual([[{ text: '理解函数模型并确定定义域' }]])
    expect(removeAllRanges).toHaveBeenCalledTimes(1)
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
})
