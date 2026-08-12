/**
 * The answer must render as chunks arrive, not once the stream ends.
 *
 * Regression guard for a real defect: `MarkdownRenderer` batched `content`
 * changes behind a 150ms timer whose trailing edge re-armed lazily, so a
 * streamed answer (hundreds of small chunks) reached the screen in a handful
 * of large jumps and read as "the whole answer appeared at once". Measured
 * against the real model, the typical chunk waited ~80ms to be painted; after
 * aligning renders to animation frames it waits ~15ms.
 *
 * jsdom cannot measure paint timing, so this test asserts the property that
 * actually matters and is observable here: N distinct content values must
 * produce N distinct rendered outputs, with no chunk silently swallowed.
 * End-to-end timing is covered by `scripts/verify_ai_stream_render_e2e.mjs`.
 */
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

/** Let queued animation frames run, then let Vue flush the resulting update. */
async function flushFrames() {
  for (let i = 0; i < 3; i += 1) {
    await new Promise(resolve => requestAnimationFrame(() => resolve(null)))
    await nextTick()
  }
}

describe('MarkdownRenderer streaming', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('每个到达的分片都会反映到渲染结果，不被节流吞掉', async () => {
    const wrapper = mount(MarkdownRenderer, { props: { content: '' } })
    const seen: string[] = []

    // 60 chunks, appended one at a time, exactly like the SSE reader does.
    for (let i = 1; i <= 60; i += 1) {
      await wrapper.setProps({ content: '线性相关'.repeat(i) })
      await flushFrames()
      seen.push(wrapper.text())
    }

    const distinct = new Set(seen)
    // A timer-based throttle collapses these into a handful of values.
    expect(distinct.size).toBe(60)
    // And the text only ever grows — never rewinds to an older snapshot.
    for (let i = 1; i < seen.length; i += 1) {
      expect(seen[i]!.length).toBeGreaterThan(seen[i - 1]!.length)
    }
  })

  it('连续两次内容变化之间不会丢掉中间态', async () => {
    const wrapper = mount(MarkdownRenderer, { props: { content: 'A' } })
    await flushFrames()

    await wrapper.setProps({ content: 'AB' })
    await flushFrames()
    const middle = wrapper.text()

    await wrapper.setProps({ content: 'ABC' })
    await flushFrames()

    expect(middle).toContain('AB')
    expect(wrapper.text()).toContain('ABC')
  })

  it('最终渲染结果始终等于最后一次 content，不停在中间态', async () => {
    const wrapper = mount(MarkdownRenderer, { props: { content: '' } })

    // Burst without awaiting between updates — the coalescing path.
    for (let i = 1; i <= 30; i += 1) {
      wrapper.setProps({ content: `第 ${i} 段内容` })
    }
    await flushFrames()

    expect(wrapper.text()).toContain('第 30 段内容')
  })

  it('清空内容会立即反映，不残留上一次回答', async () => {
    const wrapper = mount(MarkdownRenderer, { props: { content: '上一条回答' } })
    await flushFrames()
    expect(wrapper.text()).toContain('上一条回答')

    await wrapper.setProps({ content: '' })
    await flushFrames()
    expect(wrapper.text()).not.toContain('上一条回答')
  })
})
