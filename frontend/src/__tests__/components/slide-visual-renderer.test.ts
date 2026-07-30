import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SlideVisualRenderer from '@/components/SlideVisualRenderer.vue'

describe('SlideVisualRenderer', () => {
  it('renders source-bound diagram nodes and edges as one explanatory visual', () => {
    const wrapper = mount(SlideVisualRenderer, {
      props: {
        courseId: 'course-1',
        representationId: 'representation-1',
        visuals: [{
          visual_id: 'visual-1',
          kind: 'relational_diagram',
          purpose: 'structure',
          source_fragment_ids: ['fragment-1', 'fragment-2'],
          alt_text: '概念关系图',
          nodes: [
            { node_id: 'a', label: '输入空间', source_fragment_ids: ['fragment-1'] },
            { node_id: 'b', label: '线性映射', source_fragment_ids: ['fragment-2'] },
          ],
          edges: [{ source: 'a', target: 'b', relation: 'maps_to', label: '' }],
          parameters: { direction: 'horizontal' },
        }],
      },
    })

    expect(wrapper.get('[role="img"]').attributes('aria-label')).toBe('概念关系图')
    expect(wrapper.text()).toContain('输入空间')
    expect(wrapper.text()).toContain('线性映射')
    expect(wrapper.findAll('line')).toHaveLength(1)
  })

  it('renders a validated rule diagram through the native diagram adapter', () => {
    const wrapper = mount(SlideVisualRenderer, {
      props: {
        visuals: [{
          visual_id: 'rule-1',
          kind: 'rule_diagram',
          purpose: 'process',
          source_fragment_ids: ['fragment-system'],
          alt_text: 'Closed-system relation',
          nodes: [
            { node_id: 'a', label: 'Closed system', source_fragment_ids: ['fragment-system'] },
            { node_id: 'b', label: 'Environment', source_fragment_ids: ['fragment-system'] },
          ],
          edges: [{
            source: 'a',
            target: 'b',
            relation: 'maps_to',
            label: 'cannot exchange matter',
          }],
          parameters: {
            template: 'process_flow',
            direction: 'horizontal',
            relation_evidence: ['fragment-system'],
          },
        }],
      },
    })

    expect(wrapper.attributes('data-kind')).toBe('rule_diagram')
    expect(wrapper.text()).toContain('Closed system')
    expect(wrapper.text()).toContain('Environment')
    expect(wrapper.findAll('line')).toHaveLength(1)
  })

  it('renders formula visuals through the shared math renderer instead of a placeholder', () => {
    const wrapper = mount(SlideVisualRenderer, {
      props: {
        visuals: [{
          visual_id: 'formula-1',
          kind: 'formula',
          purpose: 'evidence',
          source_fragment_ids: ['fragment-formula'],
          alt_text: '线性映射定义式',
          nodes: [],
          edges: [],
          parameters: {
            formula: '$$T(au+bv)=aT(u)+bT(v)$$',
          },
        }],
      },
      global: {
        stubs: {
          MarkdownRenderer: {
            props: ['content'],
            template: '<div class="katex-test">{{ content }}</div>',
          },
        },
      },
    })

    expect(wrapper.find('.slide-visual__formula').exists()).toBe(true)
    expect(wrapper.get('.katex-test').text()).toBe('$$T(au+bv)=aT(u)+bT(v)$$')
    expect(wrapper.text()).not.toContain('ƒ(x)')
  })
})
