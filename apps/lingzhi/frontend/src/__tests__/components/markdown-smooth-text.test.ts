import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { safeRevealEnd } from '@/composables/useSmoothText'
let wrapper: ReturnType<typeof mount> | undefined
beforeEach(() => { vi.useFakeTimers(); Object.defineProperty(document, 'hidden', { configurable: true, value: false }) })
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })
async function advance(ms: number) { await vi.advanceTimersByTimeAsync(ms); await nextTick() }
describe('smooth live Markdown', () => {
  it('keeps history immediate and progressively reveals new text within a bounded delay', async () => {
    wrapper = mount(MarkdownRenderer, { props: { content: '已保存的内容。', smoothStream: true } })
    expect(wrapper.text()).toContain('已保存的内容。')
    const target = '已保存的内容。' + '新的讲解逐渐展开。'.repeat(30)
    await wrapper.setProps({ content: target })
    await advance(120)
    expect(wrapper.text().length).toBeGreaterThan(8)
    expect(wrapper.text().length).toBeLessThan(target.length)
    await advance(650)
    expect(wrapper.text()).toBe(target)
  })
  it('shows replacements immediately and never lets an old animation overwrite them', async () => {
    wrapper = mount(MarkdownRenderer, { props: { content: '', smoothStream: true } })
    await wrapper.setProps({ content: '旧回复'.repeat(100) }); await advance(80)
    await wrapper.setProps({ content: '修正后的内容' }); await advance(700)
    expect(wrapper.text()).toBe('修正后的内容')
    await wrapper.setProps({ content: '' }); expect(wrapper.text()).toBe('')
  })
  it('catches up on completion and when the browser is hidden', async () => {
    wrapper = mount(MarkdownRenderer, { props: { content: '新教学块'.repeat(100), smoothStream: true, animateInitial: true } })
    await advance(80)
    expect(wrapper.text().length).toBeLessThan(400)
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange')); await advance(32)
    expect(wrapper.text()).toBe('新教学块'.repeat(100))
  })
  it('respects reduced motion', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }))
    wrapper = mount(MarkdownRenderer, { props: { content: '直接显示', smoothStream: true, animateInitial: true } })
    expect(wrapper.text()).toBe('直接显示')
  })
  it('does not split complete math, code tokens or emoji during reveal', () => {
    expect(safeRevealEnd('公式 $x^2+y^2=z^2$ 结束', 7)).toBe(16)
    const diagram = '```mermaid\ngraph TD; A-->B\n```'
    expect(safeRevealEnd(diagram, 8)).toBe(diagram.length)
    expect(safeRevealEnd('值 `count`', 4)).toBe(9)
    expect(safeRevealEnd('好😀', 2)).toBe(3)
  })
})
