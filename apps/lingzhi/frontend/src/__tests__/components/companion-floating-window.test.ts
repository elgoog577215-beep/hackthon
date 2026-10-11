import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CompanionFloatingWindow from '@/components/CompanionFloatingWindow.vue'

describe('non-modal companion window', () => {
  beforeEach(() => vi.stubGlobal('PointerEvent', MouseEvent))
  afterEach(() => vi.unstubAllGlobals())
  it('allows background interaction and supports dragging, resizing and reset', async () => {
    const wrapper = mount(CompanionFloatingWindow, { props:{ visible:true, detail:false, windowId:'test' }, global:{ stubs:{ Teleport:true } } })
    await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.attributes('aria-modal')).toBe('false')
    expect(wrapper.find('.companion-modal-backdrop').exists()).toBe(false)
    const start = wrapper.get('[role="dialog"]').attributes('style')
    const move = wrapper.get('.window-move')
    async function pointer(type:string, values:Record<string,number> = {}) {
      move.element.dispatchEvent(Object.assign(new Event(type, { bubbles:true }), values))
      await flushPromises()
    }
    await pointer('pointerdown', { button:0, pointerId:1, clientX:300, clientY:100 })
    await pointer('pointermove', { pointerId:1, clientX:350, clientY:140 })
    await pointer('pointerup', { pointerId:1 })
    expect(wrapper.get('[role="dialog"]').attributes('style')).not.toBe(start)
    const beforeResize = (wrapper.get('[role="dialog"]').element as HTMLElement).style.width
    await wrapper.get('.window-resize').trigger('keydown', { key:'ArrowRight' })
    expect(parseFloat((wrapper.get('[role="dialog"]').element as HTMLElement).style.width)).toBe(parseFloat(beforeResize) + 20)
    await pointer('pointerdown', { button:0, pointerId:2, clientX:100, clientY:100 })
    await pointer('pointermove', { pointerId:2, clientX:-10000, clientY:-10000 })
    await pointer('pointercancel')
    expect((wrapper.get('[role="dialog"]').element as HTMLElement).style.left).toBe('8px')
    expect((wrapper.get('[role="dialog"]').element as HTMLElement).style.top).toBe('8px')
    await wrapper.findAll('.window-titlebar > button')[1]!.trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('style')).toBe(start)
    wrapper.unmount()
  })
})
