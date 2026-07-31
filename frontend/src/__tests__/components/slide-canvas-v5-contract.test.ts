import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SlideCanvas from '../../components/SlideCanvas.vue'
import layoutContract from '../../../../shared/slide-layout-contract-v5.json'

const baseProps = {
  pageNumber: 4,
  pageCount: 20,
  deckTitle: '热力学课程',
}

describe('SlideCanvas V5 final page contract', () => {
  it('loads the same V5 layout catalog used by PPTX export', () => {
    const layouts = new Set(layoutContract.layouts.map(item => item.layout))

    expect(layoutContract.schema_version).toBe('slide_layout_contract_v5')
    expect(layoutContract.minimum_title_font_pt).toBeGreaterThanOrEqual(35)
    expect(layoutContract.minimum_body_font_pt).toBeGreaterThanOrEqual(16)
    expect(layouts).toEqual(new Set([
      'cover-minimal',
      'agenda-linear',
      'chapter-entry',
      'hero-claim',
      'editorial-body',
      'balanced-two-column',
      'classification-3',
      'process-sequence',
      'formula-explanation',
      'figure-text',
      'diagram-full',
      'worked-example',
      'practice-feedback',
      'chapter-recap',
      'course-synthesis',
    ]))
  })

  it('renders the explicit title instead of promoting takeaway copy', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          eyebrow: '核心概念',
          title: '热力学系统的三种类型',
          takeaway: '根据系统与环境之间的交互方式，热力学将系统分为三类。',
          blocks: [{
            block_id: 'classification',
            type: 'bullets',
            items: ['孤立系统', '封闭系统', '开放系统'],
          }],
          quality: {
            requested_layout: 'two-column',
            resolved_layout: 'classification-3',
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

    expect(wrapper.get('.deck-canvas__heading h2').text()).toBe('热力学系统的三种类型')
    expect(wrapper.attributes('data-layout-contract')).toBe('slide_layout_contract_v5')
  })

  it('uses resolved layout instead of stale requested layout', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          eyebrow: '核心概念',
          title: '系统边界决定交换方式',
          takeaway: '系统边界决定交换方式。',
          composition: 'split-visual',
          blocks: [{
            block_id: 'definition',
            type: 'rich_text',
            content: '系统边界决定可发生的交换。',
          }],
          visuals: [],
          quality: {
            requested_layout: 'two-column',
            resolved_layout: 'editorial-body',
            resolved_composition: 'statement',
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

    expect(wrapper.attributes('data-layout')).toBe('editorial-body')
    expect(wrapper.get('.deck-canvas__blocks').attributes('data-layout')).toBe('editorial-body')
  })

  it('renders three sibling concepts as three semantic classification regions', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          eyebrow: '核心概念',
          title: '热力学系统的三种类型',
          blocks: [{
            block_id: 'classification',
            type: 'bullets',
            items: ['孤立系统', '封闭系统', '开放系统'],
          }],
          quality: {
            requested_layout: 'two-column',
            resolved_layout: 'classification-3',
          },
        },
      },
      global: {
        stubs: {
          MarkdownRenderer: { props: ['content'], template: '<span>{{ content }}</span>' },
          SlideVisualRenderer: { template: '<span />' },
        },
      },
    })

    expect(wrapper.findAll('.deck-classification__item')).toHaveLength(3)
    expect(wrapper.find('.deck-classification').text()).toContain('孤立系统')
  })

  it('keeps the V5 cover minimal', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        pageNumber: 1,
        slide: {
          layout: 'cover',
          eyebrow: '课程课件',
          title: '热力学与统计物理',
          subtitle: '',
          blocks: [],
          quality: {
            requested_layout: 'cover-minimal',
            resolved_layout: 'cover-minimal',
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

    expect(wrapper.find('.deck-cover__wash').exists()).toBe(false)
    expect(wrapper.find('.deck-cover__brand').exists()).toBe(false)
    expect(wrapper.get('.deck-cover__content h2').text()).toBe('热力学与统计物理')
  })

  it('does not repeat a promoted single claim as body copy', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          eyebrow: '常见误区',
          title: '只验证加法保持不够，还必须验证数乘保持',
          takeaway: '只验证加法保持不够，还必须验证数乘保持。',
          blocks: [{
            block_id: 'claim',
            type: 'rich_text',
            content: '只验证加法保持不够，还必须验证数乘保持。',
          }],
          quality: {
            requested_layout: 'two-column',
            resolved_layout: 'hero-claim',
            suppress_redundant_body: true,
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

    expect(wrapper.find('.deck-claim-only').exists()).toBe(true)
    expect(wrapper.find('.deck-canvas__blocks').exists()).toBe(false)
  })

  it.each([
    ['worked-example', '.deck-worked-example'],
    ['practice-feedback', '.deck-practice-feedback'],
    ['chapter-recap', '.deck-chapter-recap'],
    ['course-synthesis', '.deck-course-synthesis'],
  ])('renders %s with its dedicated semantic composition', (layout, selector) => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          eyebrow: '课堂推进',
          title: '用可检验步骤推进理解',
          key_message: '每一步都需要可见证据。',
          blocks: [{
            block_id: 'semantic-content',
            type: layout === 'practice-feedback' ? 'exercise' : 'process',
            items: ['识别条件', '选择方法', '检查结论'],
          }],
          quality: {
            requested_layout: layout,
            resolved_layout: layout,
          },
        },
      },
      global: {
        stubs: {
          MarkdownRenderer: { props: ['content'], template: '<span>{{ content }}</span>' },
          SlideVisualRenderer: { template: '<span />' },
        },
      },
    })

    expect(wrapper.find(selector).exists()).toBe(true)
    expect(wrapper.find('.deck-canvas__blocks').exists()).toBe(false)
  })
})
