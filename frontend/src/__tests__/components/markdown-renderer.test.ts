import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    run: vi.fn(),
  },
}))

vi.mock('highlight.js/styles/atom-one-dark.css', () => ({}))

import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

/**
 * Rendering is aligned to animation frames so a streamed answer paints as its
 * chunks arrive, so a frame has to elapse before the DOM is inspected.
 */
async function flushFrames() {
  for (let i = 0; i < 3; i += 1) {
    await new Promise(resolve => requestAnimationFrame(() => resolve(null)))
    await nextTick()
  }
}

describe('MarkdownRenderer', () => {
  it('搜索高亮只修改可见文本，不破坏链接属性', async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: '[class 指南](https://example.com/docs?mode=class)',
        searchWords: ['class'],
      },
    })
    await flushFrames()
    await flushPromises()

    const link = wrapper.find('a')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://example.com/docs?mode=class')
    expect(link.findAll('.markdown-search-highlight')).toHaveLength(1)
    expect(link.find('.markdown-search-highlight').text()).toBe('class')

    wrapper.unmount()
  })

  it('把课程预览中的块公式渲染为 KaTeX，而不是泄露 LaTeX 源码', async () => {
    const wrapper = mount(MarkdownRenderer, {
      props: {
        content: String.raw`### 核心教学

$$\text{函数契约} = \underbrace{\text{输入}}_{\text{参数}} + \underbrace{\text{输出}}_{\text{返回值}}$$`,
        enableCodeRun: false,
      },
    })
    // MarkdownRenderer 把渲染对齐到 requestAnimationFrame（见其 scheduleUpdate，
    // 为流式输出合帧）。只等微任务队列会在渲染发生**之前**就断言，于是看到空 DOM
    // 并报「公式没渲染」——但 KaTeX 全程都是好的。实测同一次挂载：只
    // flushPromises 得到 0 个 .katex-display，等一帧后得到 1 个，且源码未泄漏。
    await new Promise(resolve => requestAnimationFrame(() => resolve(null)))
    await flushPromises()

    expect(wrapper.find('.katex-display').exists()).toBe(true)
    expect(wrapper.text()).toContain('函数契约')
    expect(wrapper.text()).not.toContain('\\underbrace')

    wrapper.unmount()
  })
})
