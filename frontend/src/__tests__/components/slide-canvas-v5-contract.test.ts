import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SlideCanvas from '../../components/SlideCanvas.vue'
import slideCanvasSource from '../../components/SlideCanvas.vue?raw'
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
      'cover-editorial',
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
      'parallel-examples',
      'question-prompt',
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

  it('renders an editorial V5 cover with supporting context', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        pageNumber: 1,
        slide: {
          layout: 'cover',
          eyebrow: '课程课件',
          title: '热力学与统计物理',
          subtitle: '原理、方法与应用',
          blocks: [],
          quality: {
            requested_layout: 'cover-editorial',
            resolved_layout: 'cover-editorial',
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

    expect(wrapper.find('.deck-cover__wash').exists()).toBe(true)
    expect(wrapper.find('.deck-cover__brand').exists()).toBe(true)
    expect(wrapper.get('.deck-cover__content h2').text()).toBe('热力学与统计物理')
    expect(wrapper.get('.deck-cover__content p').text()).toBe('原理、方法与应用')
  })

  it('renders parallel applications without invented reasoning labels', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          eyebrow: '实际应用',
          title: '第零定律的实际应用',
          blocks: [{
            block_id: 'applications',
            type: 'bullets',
            items: ['空调温控', '冷链运输', '体温测量'],
          }],
          quality: {
            requested_layout: 'parallel-examples',
            resolved_layout: 'parallel-examples',
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

    expect(wrapper.findAll('.deck-parallel-examples article')).toHaveLength(3)
    expect(wrapper.text()).not.toContain('已知')
    expect(wrapper.text()).not.toContain('推理')
    expect(wrapper.text()).not.toContain('结论')
  })

  it('uses explicit worked-example labels instead of positional semantics', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          eyebrow: '例题推演',
          title: '按步骤验证判断',
          blocks: [{
            block_id: 'worked-steps',
            type: 'process',
            items: ['整理条件', '完成推演', '检查结果'],
          }],
          quality: {
            requested_layout: 'worked-example',
            resolved_layout: 'worked-example',
            worked_step_labels: ['条件', '推演', '验证'],
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

    expect(wrapper.findAll('.deck-worked-example article small').map(node => node.text())).toEqual([
      '条件',
      '推演',
      '验证',
    ])
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

  it('renders hero claims without leaking the generic learning-question fallback', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          eyebrow: '承上启下',
          title: '下一节：热力学第一定律',
          key_message: '下一节将深入探讨热力学第一定律及其在不同系统中的表现形式。',
          teaching_job: '用来源问题检查理解',
          blocks: [],
          quality: {
            requested_layout: 'hero-claim',
            resolved_layout: 'hero-claim',
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

    expect(wrapper.find('.deck-hero-claim').exists()).toBe(true)
    expect(wrapper.find('.deck-canvas__navigation').exists()).toBe(false)
    expect(wrapper.find('.deck-canvas__message').exists()).toBe(false)
    expect(wrapper.text()).toContain('下一节将深入探讨热力学第一定律')
    expect(wrapper.text()).not.toContain('用来源问题检查理解')
    expect(wrapper.text()).not.toContain('本节学习问题')
  })

  it('reserves vertical space for the message before rendering a visual story', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'concept',
          title: '快速冷却和缓慢降温的比较',
          key_message: '最终状态相同，过程量可能不同。',
          teaching_job: '比较两种过程',
          blocks: [{
            block_id: 'comparison',
            type: 'rich_text',
            content: '比较能量消耗和热量传递。',
          }],
          visuals: [{
            visual_id: 'visual-1',
            kind: 'relational_diagram',
            purpose: 'explain',
            alt_text: '过程量比较示意图',
          }],
          quality: {
            requested_layout: 'figure-text',
            resolved_layout: 'figure-text',
            resolved_composition: 'split-visual',
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

    expect(wrapper.get('.deck-canvas__story').attributes('data-has-message')).toBe('true')
    expect(slideCanvasSource).toMatch(
      /\.deck-canvas__story\[data-has-message="true"\]\s*\{\s*top:38%;\s*\}/,
    )
  })

  it('keeps every prompt visible when a question slide contains multiple questions', () => {
    const wrapper = mount(SlideCanvas, {
      props: {
        ...baseProps,
        slide: {
          layout: 'practice',
          title: '判断系统类型',
          blocks: [{
            block_id: 'questions',
            type: 'exercise',
            items: ['盖子没有打开时属于哪类系统？', '盖子打开并有蒸汽逸出时呢？'],
          }],
          quality: {
            requested_layout: 'question-prompt',
            resolved_layout: 'question-prompt',
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

    expect(wrapper.text()).toContain('盖子没有打开时属于哪类系统？')
    expect(wrapper.text()).toContain('盖子打开并有蒸汽逸出时呢？')
  })
})
