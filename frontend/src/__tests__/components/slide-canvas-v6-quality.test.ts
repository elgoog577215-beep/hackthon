import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SlideCanvas from '../../components/SlideCanvas.vue'


const baseProps = {
  pageNumber: 2,
  pageCount: 12,
  deckTitle: '工程学习路径',
  theme: 'qizhi-classroom' as const,
}


describe('SlideCanvas V6 sample-quality compositions', () => {
  it('keeps the full audience title and formats composite-function commands', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          title: '复合函数定义域要求内层输出落入外层定义域 $(f\\circ g)(x)=\\ln(1-x^2)$',
          blocks: [{ block_id: 'body', type: 'statement', content: '先检查外层函数的输入条件。' }],
        },
      },
      global: {
        stubs: {
          MarkdownRenderer: { props: ['content'], template: '<span>{{ content }}</span>' },
          SlideVisualRenderer: { template: '<span />' },
        },
      },
    })

    const heading = wrapper.get('h2').text()
    expect(heading).toContain('复合函数定义域要求内层输出落入外层定义域')
    expect(heading).toContain('(f∘ g)(x)=ln(1-x^2)')
    expect(heading).not.toContain('\\circ')
  })

  it('renders agenda entries with chapter title and source-derived description', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'roadmap',
          title: '课程目录',
          blocks: [{
            block_id: 'agenda',
            type: 'bullets',
            items: ['第一章 环境验证', '第二章 生命周期'],
            metadata: {
              agenda_entries: [
                { index: 1, title: '第一章 环境验证', description: '先验证开发环境与语言基线。' },
                { index: 2, title: '第二章 生命周期', description: '用可运行实验建立状态模型。' },
              ],
            },
          }],
          quality: { resolved_layout: 'agenda-linear' },
        },
      },
      global: {
        stubs: {
          MarkdownRenderer: { props: ['content'], template: '<span>{{ content }}</span>' },
          SlideVisualRenderer: { template: '<span />' },
        },
      },
    })

    expect(wrapper.find('.deck-agenda').exists()).toBe(true)
    expect(wrapper.findAll('.deck-agenda__item')).toHaveLength(2)
    expect(wrapper.text()).toContain('第一章 环境验证')
    expect(wrapper.text()).toContain('先验证开发环境与语言基线。')
  })

  it('renders code with language, continuation and a separate line-number gutter', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'code',
          title: '对象池接口',
          blocks: [{
            block_id: 'code',
            type: 'code',
            content: 'void OnSpawn();\nvoid OnDespawn();',
            metadata: {
              code_language: 'csharp',
              code_start_line: 12,
              code_end_line: 13,
            },
          }],
          quality: {
            resolved_layout: 'code',
            v6_continuation_index: 2,
            v6_continuation_count: 3,
          },
        },
      },
      global: {
        stubs: {
          MarkdownRenderer: { template: '<span />' },
          SlideVisualRenderer: { template: '<span />' },
        },
      },
    })

    expect(wrapper.get('.slide-code-frame__header').text()).toBe('C# · 2/3')
    expect(wrapper.findAll('.slide-code-frame__lines li').map(node => node.text())).toEqual(['12', '13'])
    expect(wrapper.text()).toContain('void OnSpawn();')
    expect(wrapper.text()).not.toContain('CODE')
    expect(wrapper.text()).not.toContain('SOURCE')
  })
})
