import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import CourseNavigatorNode from '@/components/CourseNavigatorNode.vue'
import { useCourseStore } from '@/stores/course'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { useLearningProgressStore } from '@/stores/learningProgress'
import type { Node } from '@/stores/types'

const section: Node = {
  node_id: 'section-1',
  node_name: '1.1 复合的含义',
  node_level: 2,
  parent_node_id: 'chapter-1',
  node_content: '矩阵复合表示线性变换的连续作用。',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 20,
  children: [],
}

const node: Node = {
  node_id: 'chapter-1',
  node_name: '第一章 矩阵复合',
  node_level: 1,
  parent_node_id: 'root',
  node_content: '',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 0,
  children: [section],
}

describe('course navigator personal adaptation markers', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useCourseStore().currentCourseProjection = 'published'
  })

  it('在受影响章节和小节显示轻量 AI 建议标记', () => {
    useLearningProgressStore().runtime = {
      course_evolution: {
        course_evolution_plans: [{
          change_set_id: 'plan-1',
          status: 'pending',
          impact_summary: { affected_section_ids: ['section-1'] },
          operations: [
            { operation_type: 'ADD_ANIMATION', target_section_id: 'section-1', scope: 'current' },
            { operation_type: 'ADD_TRANSITION_SUPPORT', target_section_id: 'section-1', scope: 'next' },
            { operation_type: 'ADD_CHECKPOINT', target_section_id: 'section-1', scope: 'next' },
          ],
        }],
      },
    } as any

    const wrapper = mount(CourseNavigatorNode, {
      props: { node, depth: 0 },
    })

    expect(wrapper.find('.adaptation-marker').text()).toContain('AI 建议')
    expect(wrapper.findAll('.adaptation-marker')).toHaveLength(2)
    expect(wrapper.findAll('.growth-trail li')).toHaveLength(3)
    expect(wrapper.find('.growth-trail').text()).toContain('当前位置解释')
    expect(wrapper.find('.growth-trail').text()).toContain('下一处承接')
    expect(wrapper.find('.growth-trail').text()).toContain('后续顺序检查')
    expect(wrapper.find('.growth-trail').attributes('data-state')).toBe('pending')
  })

  it('仅在影响范围内、无直接修改的小节显示黄色受影响标记', () => {
    const sibling: Node = { ...section, node_id: 'section-2', node_name: '1.2 受影响小节', children: [] }
    const chapter: Node = { ...node, children: [section, sibling] }
    useLearningProgressStore().runtime = {
      course_evolution: {
        course_evolution_plans: [{
          change_set_id: 'plan-1',
          status: 'pending',
          impact_summary: { affected_section_ids: ['section-1', 'section-2'] },
          operations: [{ operation_type: 'ADD_ANIMATION', target_section_id: 'section-1', scope: 'current' }],
        }],
      },
    } as any

    const wrapper = mount(CourseNavigatorNode, {
      props: { node: chapter, depth: 0 },
    })

    const markers = wrapper.findAll('.adaptation-marker')
    const states = markers.map(marker => marker.attributes('data-state'))
    // Chapter and directly-changed section stay紫 pending; the merely
    // affected sibling gets the yellow "受影响" marker.
    expect(states).toContain('pending')
    expect(states).toContain('impacted')
    const impacted = markers.find(marker => marker.attributes('data-state') === 'impacted')
    expect(impacted?.text()).toContain('受影响')
  })

  it('已应用但未复验的方案显示蓝色应用状态', () => {
    useLearningProgressStore().runtime = {
      course_evolution: {
        course_evolution_plans: [{
          change_set_id: 'plan-1',
          status: 'applied',
          effect_evaluation: { status: 'insufficient_evidence' },
          impact_summary: { affected_section_ids: ['section-1'] },
          operations: [{ operation_type: 'ADD_ANIMATION', target_section_id: 'section-1', scope: 'current' }],
        }],
      },
    } as any

    const wrapper = mount(CourseNavigatorNode, {
      props: { node, depth: 0 },
    })

    expect(wrapper.find('.adaptation-marker').text()).toContain('已应用')
    expect(wrapper.find('.adaptation-marker').attributes('data-state')).toBe('active')
    expect(wrapper.find('.growth-trail').attributes('data-state')).toBe('active')
  })

  it('后续正式证据通过后保留绿色个人生长标记', () => {
    const progressStore = useLearningProgressStore()
    progressStore.courseId = 'course-1'
    progressStore.runtime = {
      course_evolution: {
        course_evolution_plans: [{
          change_set_id: 'plan-1',
          status: 'applied',
          effect_evaluation: { status: 'insufficient_evidence' },
          impact_summary: { affected_section_ids: ['section-1'] },
          operations: [{ target_section_id: 'section-1' }],
        }],
      },
    } as any
    const evolutionStore = useCourseEvolutionStore()
    evolutionStore.courseId = 'course-1'
    evolutionStore.plans = [{
      change_set_id: 'plan-1',
      hypothesis_id: 'hypothesis-1',
      evidence_ids: ['evidence-1'],
      operations: [{ operation_id: 'operation-1', operation_type: 'ADD_ANIMATION', target_block_id: 'block-1', target_section_id: 'section-1', scope: 'current', reason: '', payload: {} }],
      allowed_scopes: ['current'],
      impact_summary: { affected_section_ids: ['section-1'] },
      expected_effect: '',
      status: 'applied',
      effect_evaluation: { status: 'effective' },
    }]

    const wrapper = mount(CourseNavigatorNode, {
      props: { node, depth: 0 },
    })

    expect(wrapper.find('.adaptation-marker').text()).toContain('已生长')
    expect(wrapper.find('.adaptation-marker').attributes('data-state')).toBe('validated')
    expect(wrapper.find('.growth-trail').attributes('data-state')).toBe('validated')
  })
})
