import { mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import ColumnResizeHandle from '@/components/ColumnResizeHandle.vue'
import { useResizableColumns } from '@/composables/useResizableColumns'

const key = 'test:column-widths'
const Host = defineComponent({
  components: { ColumnResizeHandle },
  setup() {
    const root = ref<HTMLElement | null>(null), showLeft = ref(true), showRight = ref(true)
    const columns = useResizableColumns(root, {
      storageKey: key, left: 240, right: 360, leftMin: 180, rightMin: 260,
      leftVisible: showLeft, rightVisible: showRight,
    })
    return { root, showLeft, showRight, ...columns }
  },
  template: `<section ref="root" :style="layoutStyle">
    <aside v-if="showLeft" />
    <ColumnResizeHandle v-if="showLeft" v-bind="leftHandle" />
    <main />
    <ColumnResizeHandle v-if="showRight" v-bind="rightHandle" />
    <aside v-if="showRight" />
  </section>`,
})

let wrapper: VueWrapper, containerWidth = 1400
async function open() {
  wrapper = mount(Host, { attachTo: document.body })
  Object.defineProperty(wrapper.element, 'clientWidth', { get: () => containerWidth })
  window.dispatchEvent(new Event('resize'))
  await nextTick()
  return wrapper
}
function widths() {
  const style = (wrapper.element as HTMLElement).style
  return {
    left: parseFloat(style.getPropertyValue('--column-left-width')),
    right: parseFloat(style.getPropertyValue('--column-right-width')),
  }
}
function pointer(type: string, x: number, id = 1) {
  const event = new MouseEvent(type, { clientX: x, button: 0, bubbles: true, cancelable: true })
  Object.defineProperty(event, 'pointerId', { value: id })
  return event
}
async function drag(side: number, from: number, to: number) {
  wrapper.findAll('[role="separator"]')[side]!.element.dispatchEvent(pointer('pointerdown', from))
  window.dispatchEvent(pointer('pointermove', to))
  window.dispatchEvent(pointer('pointerup', to))
  await nextTick()
}

beforeEach(() => { localStorage.removeItem(key); containerWidth = 1400 })
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; document.documentElement.style.cssText = '' })

describe('resizable workspace columns', () => {
  it('drags both boundaries, keeps the other side stable, and restores widths after reopening', async () => {
    await open()
    await drag(0, 240, 320)
    expect(widths()).toEqual({ left: 320, right: 360 })
    await drag(1, 1040, 970)
    expect(widths()).toEqual({ left: 320, right: 430 })
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual({ left: 320, right: 430 })
    wrapper.unmount()
    await open()
    expect(widths()).toEqual({ left: 320, right: 430 })
  })

  it('reserves readable space for the center and both side panels at drag limits', async () => {
    await open()
    await drag(0, 240, 3000)
    expect(widths()).toEqual({ left: 620, right: 360 })
    await drag(1, 1040, -2000)
    expect(widths()).toEqual({ left: 620, right: 360 })
    await drag(0, 620, -3000)
    await drag(1, 1040, 3000)
    expect(widths()).toEqual({ left: 180, right: 260 })
  })

  it('fits a smaller container without losing saved preferences when it grows again', async () => {
    await open()
    await drag(0, 240, 320)
    const saved = localStorage.getItem(key)
    containerWidth = 1000
    window.dispatchEvent(new Event('resize'))
    await nextTick()
    const smaller = widths()
    expect(smaller.left).toBeGreaterThanOrEqual(180)
    expect(smaller.right).toBeGreaterThanOrEqual(260)
    expect(smaller.left + smaller.right).toBeCloseTo(580)
    expect(localStorage.getItem(key)).toBe(saved)
    containerWidth = 1400
    window.dispatchEvent(new Event('resize'))
    await nextTick()
    expect(widths()).toEqual({ left: 320, right: 360 })
  })

  it('keeps a hidden panel preference when the other panel is resized', async () => {
    await open()
    await drag(1, 1040, 970)
    ;(wrapper.vm as any).showRight = false
    await nextTick()
    expect(wrapper.findAll('[role="separator"]')).toHaveLength(1)
    expect(widths().right).toBe(0)
    await drag(0, 240, 280)
    ;(wrapper.vm as any).showRight = true
    await nextTick()
    expect(widths()).toEqual({ left: 280, right: 430 })
  })

  it('supports physical arrow direction, bounds, and reset from keyboard and double click', async () => {
    await open()
    const [left, right] = wrapper.findAll('[role="separator"]')
    await left!.trigger('keydown', { key: 'ArrowRight' })
    await right!.trigger('keydown', { key: 'ArrowLeft', shiftKey: true })
    expect(widths()).toEqual({ left: 252, right: 400 })
    await left!.trigger('keydown', { key: 'Home' })
    expect(widths().left).toBe(180)
    await left!.trigger('keydown', { key: 'End' })
    expect(Number(left!.attributes('aria-valuenow'))).toBe(Number(left!.attributes('aria-valuemax')))
    await left!.trigger('dblclick')
    await right!.trigger('keydown', { key: 'Enter' })
    expect(widths()).toEqual({ left: 240, right: 360 })
  })

  it('ignores other pointers and restores cursor and selection after cancellation or unmount', async () => {
    document.documentElement.style.cursor = 'crosshair'
    document.documentElement.style.userSelect = 'text'
    await open()
    const left = wrapper.find('[role="separator"]')
    left.element.dispatchEvent(pointer('pointerdown', 240))
    window.dispatchEvent(pointer('pointermove', 400, 2))
    window.dispatchEvent(pointer('pointerup', 400, 2))
    await nextTick()
    expect(widths().left).toBe(240)
    expect(document.documentElement.style.cursor).toBe('col-resize')
    window.dispatchEvent(pointer('pointercancel', 240))
    expect(document.documentElement.style.cursor).toBe('crosshair')
    expect(document.documentElement.style.userSelect).toBe('text')
    left.element.dispatchEvent(pointer('pointerdown', 240))
    wrapper.unmount()
    expect(document.documentElement.style.cursor).toBe('crosshair')
    expect(document.documentElement.style.userSelect).toBe('text')
    window.dispatchEvent(pointer('pointermove', 600))
    expect(JSON.parse(localStorage.getItem(key)!).left).toBe(240)
  })

  it('ignores corrupted stored widths', async () => {
    localStorage.setItem(key, '{"left":-20,"right":null}')
    await open()
    expect(widths()).toEqual({ left: 240, right: 360 })
  })
})
