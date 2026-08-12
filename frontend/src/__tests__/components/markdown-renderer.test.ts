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
})
