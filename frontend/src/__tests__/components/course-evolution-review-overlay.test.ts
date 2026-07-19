import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CourseEvolutionReviewOverlay from '@/components/CourseEvolutionReviewOverlay.vue'

describe('CourseEvolutionReviewOverlay', () => {
  it('使用学生最终选择的范围，并把已就绪结构化内容显示为真实候选', () => {
    const wrapper = mount(CourseEvolutionReviewOverlay, {
      props: {
        plan: {
          change_set_id: 'plan-strong',
          hypothesis_id: 'hypothesis-strong',
          evidence_ids: ['evidence-strong'],
          generation_status: 'ready',
          operations: [{
            operation_id: 'operation-animation',
            operation_type: 'ADD_ANIMATION',
            target_block_id: 'block-1',
            target_section_id: 'section-1',
            scope: 'current',
            reason: '使用几何过程解释复合顺序。',
            payload: {
              body: '动画依次展示 v、Bv 与 A(Bv)。',
            },
          }],
          allowed_scopes: ['current', 'current_and_next'],
          impact_summary: {
            diagnosis: '学习者会计算，但尚未理解复合变换顺序。',
          },
          expected_effect: '建立复合顺序的几何理解。',
          status: 'pending',
          effect_evaluation: {},
        } as any,
        selectedScope: 'current_and_next',
        selectedOperationIds: ['operation-animation'],
      },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.get('.scope-contract').text()).toContain('本节及相关后续内容')
    expect(wrapper.get('.content-diff').text()).toContain('动画依次展示 v、Bv 与 A(Bv)')
    expect(wrapper.get('.review-list > li').attributes('data-status')).toBe('ready')
    expect(wrapper.text()).not.toContain('正在生成并检查这个节点')
  })
})
