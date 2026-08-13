import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import CourseEvolutionReviewOverlay from '@/components/CourseEvolutionReviewOverlay.vue'
import { useCourseStore } from '@/stores/course'

describe('CourseEvolutionReviewOverlay', () => {
  beforeEach(() => setActivePinia(createPinia()))
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

  function mountWithPlan(impactSummary: Record<string, unknown>, operations: any[]) {
    const courseStore = useCourseStore()
    courseStore.nodes = [
      { node_id: 'section-1', node_name: '1.2 矩阵', node_level: 2, parent_node_id: 'root' },
      { node_id: 'section-2', node_name: '1.3 复合变换', node_level: 2, parent_node_id: 'root' },
      { node_id: 'section-3', node_name: '1.4 逆变换', node_level: 2, parent_node_id: 'root' },
    ] as any
    return mount(CourseEvolutionReviewOverlay, {
      props: {
        plan: {
          change_set_id: 'plan-scope',
          hypothesis_id: 'hypothesis-scope',
          evidence_ids: [],
          generation_status: 'ready',
          operations,
          allowed_scopes: ['current', 'current_and_next'],
          impact_summary: impactSummary,
          expected_effect: '范围内内容更容易理解。',
          status: 'pending',
          effect_evaluation: {},
        } as any,
        selectedScope: 'current_and_next',
        selectedOperationIds: operations.map(operation => operation.operation_id),
      },
      global: { stubs: { Teleport: true } },
    })
  }

  const operation = (id: string, sectionId: string) => ({
    operation_id: id,
    operation_type: 'ADD_ANIMATION',
    target_block_id: `block-${id}`,
    target_section_id: sectionId,
    scope: 'current',
    reason: '范围内调整。',
    payload: { body: `候选 ${id}` },
  })

  it('确认前展示的受影响小节数等于方案自身声明的范围', () => {
    // The preview is the precondition for letting scope widen, so its number
    // must equal the range the domain will apply.
    //
    // Built so the two plausible implementations disagree: ONE operation
    // (targeting section-1) but THREE affected sections, because the domain
    // derives that field from `affected_block_ids`, which includes dependent
    // blocks in later sections. Counting operations would say "1 section" and
    // understate the blast radius — the only direction of error that matters.
    const wrapper = mountWithPlan(
      {
        diagnosis: '顺序理解缺口。',
        dependent_block_ids: ['block-b', 'block-c'],
        affected_section_ids: ['section-1', 'section-2', 'section-3'],
      },
      [operation('a', 'section-1')],
    )

    const preview = wrapper.get('[data-testid="course-impact-preview"]')
    expect(preview.text()).toContain('将影响 3 个小节')
    expect(preview.text()).not.toContain('将影响 1 个小节')
    const rows = wrapper.findAll('[data-testid="impact-section"]')
    expect(rows).toHaveLength(3)
    expect(rows.map(row => row.text()).join(' ')).toContain('1.4 逆变换')
    expect(preview.text()).toContain('确认前不会修改正式课程')
  })

  it('受影响范围只有一节时不因为关联块而夸大', () => {
    const wrapper = mountWithPlan(
      {
        diagnosis: '本节解释不足。',
        dependent_block_ids: ['block-b', 'block-c'],
        affected_section_ids: ['section-1'],
      },
      [operation('a', 'section-1'), operation('b', 'section-1')],
    )

    // Two operations and two dependent blocks, but one section.
    expect(wrapper.get('[data-testid="course-impact-preview"]').text()).toContain('将影响 1 个小节')
    expect(wrapper.findAll('[data-testid="impact-section"]')).toHaveLength(1)
  })

  it('方案没有声明范围时退回操作目标，不显示为零', () => {
    const wrapper = mountWithPlan(
      { diagnosis: '缺少声明字段的旧方案。' },
      [operation('a', 'section-1'), operation('b', 'section-2')],
    )

    expect(wrapper.get('[data-testid="course-impact-preview"]').text()).toContain('将影响 2 个小节')
  })
})
