import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MorphingDialog from '@/components/MorphingDialog.vue'

describe('MorphingDialog', () => {
  beforeEach(() => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    delete (HTMLElement.prototype as any).animate
    document.body.innerHTML = ''
    document.body.style.overflow = ''
  })

  it('从来源矩形生成展开动画', async () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
    const animate = vi.fn().mockImplementation(() => ({
      finished: Promise.resolve(),
      cancel: vi.fn(),
    }))
    Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: animate })
    const wrapper = mount(MorphingDialog, {
      props: {
        ariaLabel: '章节练习',
        originRect: { top: 320, left: 280, width: 680, height: 112 },
      },
      slots: { default: '<button>答题</button>' },
    })
    const panel = document.body.querySelector<HTMLElement>('.morphing-dialog__panel')!
    vi.spyOn(panel, 'getBoundingClientRect').mockReturnValue({
      top: 100, left: 200, right: 1240, bottom: 880, width: 1040, height: 780,
      x: 200, y: 100, toJSON: () => ({}),
    })
    await flushPromises()

    const panelAnimation = animate.mock.calls.find(([frames]) => (
      Array.isArray(frames) && String(frames[0]?.transform || '').includes('translate3d(80px, 220px')
    ))
    expect(panelAnimation).toBeTruthy()
    wrapper.unmount()
  })

  it('减少动态效果时不调用位移缩放动画', async () => {
    const animate = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: animate })
    const wrapper = mount(MorphingDialog, {
      props: { ariaLabel: '章节练习', originRect: { top: 100, left: 100, width: 500, height: 100 } },
    })
    await flushPromises()

    expect(animate).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('建立模态语义并用 Escape 关闭', async () => {
    const wrapper = mount(MorphingDialog, {
      props: { ariaLabel: '章节练习' },
      slots: { default: '<button class="inside">答题</button>' },
    })
    await flushPromises()

    const panel = document.body.querySelector<HTMLElement>('.morphing-dialog__panel')
    expect(panel?.getAttribute('role')).toBe('dialog')
    expect(panel?.getAttribute('aria-modal')).toBe('true')
    expect(panel?.getAttribute('aria-label')).toBe('章节练习')
    panel?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('点击遮罩关闭并在卸载后归还页面滚动状态', async () => {
    document.body.style.overflow = 'auto'
    const wrapper = mount(MorphingDialog, {
      props: { ariaLabel: '章节练习' },
      slots: { default: '<button>答题</button>' },
    })
    await flushPromises()
    expect(document.body.style.overflow).toBe('hidden')

    document.body.querySelector<HTMLElement>('.morphing-dialog__backdrop')?.click()
    await flushPromises()
    expect(wrapper.emitted('close')).toHaveLength(1)

    wrapper.unmount()
    expect(document.body.style.overflow).toBe('auto')
  })

  it('把 Tab 焦点约束在弹窗内部', async () => {
    const wrapper = mount(MorphingDialog, {
      props: { ariaLabel: '章节练习' },
      slots: { default: '<button class="first">第一项</button><button class="last">最后一项</button>' },
    })
    await flushPromises()
    const panel = document.body.querySelector<HTMLElement>('.morphing-dialog__panel')!
    const first = panel.querySelector<HTMLElement>('.first')!
    const last = panel.querySelector<HTMLElement>('.last')!

    last.focus()
    last.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(first)

    first.focus()
    first.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }))
    expect(document.activeElement).toBe(last)
    wrapper.unmount()
  })
})
