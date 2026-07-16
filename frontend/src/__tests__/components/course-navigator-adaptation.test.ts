import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import CourseNavigatorNode from '@/components/CourseNavigatorNode.vue'
import { useCourseStore } from '@/stores/course'
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
        adaptation_plans: [{
          change_set_id: 'plan-1',
          status: 'pending',
          impact_summary: { affected_section_ids: ['section-1'] },
          operations: [{ target_section_id: 'section-1' }],
        }],
      },
    } as any

    const wrapper = mount(CourseNavigatorNode, {
      props: { node, depth: 0 },
    })

    expect(wrapper.find('.adaptation-marker').text()).toContain('AI 建议')
    expect(wrapper.findAll('.adaptation-marker')).toHaveLength(2)
  })

  it('已应用方案不再占用待处理目录标记', () => {
    useLearningProgressStore().runtime = {
      course_evolution: {
        adaptation_plans: [{
          change_set_id: 'plan-1',
          status: 'applied',
          impact_summary: { affected_section_ids: ['section-1'] },
          operations: [{ target_section_id: 'section-1' }],
        }],
      },
    } as any

    const wrapper = mount(CourseNavigatorNode, {
      props: { node, depth: 0 },
    })

    expect(wrapper.find('.adaptation-marker').exists()).toBe(false)
  })
})
