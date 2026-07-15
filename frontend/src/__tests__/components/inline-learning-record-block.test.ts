import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    run: vi.fn(),
  },
}))

vi.mock('highlight.js/styles/atom-one-dark.css', () => ({}))

import InlineLearningRecordBlock from '@/components/InlineLearningRecordBlock.vue'

describe('InlineLearningRecordBlock', () => {
  it('AI 摘要统一渲染 Markdown 与容错公式', () => {
    const wrapper = mount(InlineLearningRecordBlock, {
      props: {
        note: {
          id: 'ai-summary-math',
          sourceType: 'ai',
          summary: '**重点**：$\\\\vec{a}=(a_1,a_2)$\n\nk\\vec{a}=(ka_1,ka_2)这说明坐标规则一致。',
        } as any,
      },
    })

    expect(wrapper.find('strong').text()).toBe('AI 问答摘要')
    expect(wrapper.html()).toContain('accent-body')
    expect(wrapper.html()).not.toContain('math-fallback')
    expect(wrapper.text()).not.toContain('**')
    expect(wrapper.text()).not.toContain('\\vec')
    expect(wrapper.text()).toContain('这说明坐标规则一致。')
  })
})
