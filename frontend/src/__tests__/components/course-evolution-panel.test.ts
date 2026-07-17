import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import CourseEvolutionPanel from '@/components/CourseEvolutionPanel.vue'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'

const evidence = [
  {
    evidence_id: 'e-dialogue',
    source_type: 'learning_event',
    evidence_kind: 'learner_question',
    summary: '为什么右边的变换先做？',
    strength: 0.84,
    anchor: { section_id: 's1', block_id: 'b1', resolution_status: 'resolved' },
  },
  {
    evidence_id: 'e-note',
    source_type: 'learning_record',
    evidence_kind: 'record_note',
    summary: '计算会做，但顺序总是理解反。',
    strength: 0.5,
    anchor: { section_id: 's1', block_id: 'b1', resolution_status: 'resolved' },
  },
  {
    evidence_id: 'e-practice',
    source_type: 'practice_attempt',
    evidence_kind: 'formal_failure',
    summary: '变换顺序判断错误。',
    strength: 0.95,
    anchor: { section_id: 's1', block_id: 'b1', resolution_status: 'resolved' },
  },
] as any

const plan = {
  change_set_id: 'plan-1',
  hypothesis_id: 'hypothesis-1',
  evidence_ids: evidence.map((item: any) => item.evidence_id),
  operations: [{
    operation_id: 'operation-1',
    operation_type: 'ADD_ANIMATION',
    target_block_id: 'b1',
    target_section_id: 's1',
    scope: 'current',
    reason: '用分步变换呈现先后关系。',
    payload: {},
  }],
  allowed_scopes: ['current', 'current_and_next'],
  impact_summary: {
    diagnosis: '学习者会执行计算，但尚未理解复合变换的先后顺序。',
    validation_plan: '观察后续同能力正式题与新增支持的实际使用。',
    knowledge_labels: ['矩阵复合'],
    ability_labels: ['解释复合顺序'],
    misconception_labels: ['把矩阵乘法只理解为行乘列'],
    dependent_block_ids: ['b2', 'b3'],
  },
  expected_effect: '在当前位置补充交互解释，并提前调整后续内容。',
  status: 'pending',
  effect_evaluation: {},
} as any

describe('CourseEvolutionPanel', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('把三类痕迹收束为明确诊断、调整范围和复验计划', () => {
    useCourseEvolutionStore().applyPayload('course-1', {
      evidence_items: evidence,
      hypotheses: [{
        hypothesis_id: 'hypothesis-1',
        claim: plan.impact_summary.diagnosis,
        confidence: 1.8,
        confidence_reasons: ['三类独立证据'],
        validation_plan: plan.impact_summary.validation_plan,
        status: 'candidate_created',
      }],
      course_evolution_plans: [plan],
    })

    const wrapper = mount(CourseEvolutionPanel, { props: { courseId: 'course-1' } })

    expect(wrapper.findAll('.evolution-evidence span')).toHaveLength(3)
    expect(wrapper.get('.evolution-diagnosis').text()).toContain('学习者会执行计算，但尚未理解复合变换的先后顺序')
    expect(wrapper.text()).toContain('关联后续 2 个教学块')
    expect(wrapper.find('.evolution-details-toggle').exists()).toBe(true)
  })

  it('只有后续复验支持后才显示绿色已生长状态', () => {
    useCourseEvolutionStore().applyPayload('course-1', {
      evidence_items: evidence,
      hypotheses: [],
      course_evolution_plans: [{
        ...plan,
        status: 'applied',
        effect_evaluation: {
          status: 'effective',
          interaction_event_ids: ['interaction-1'],
          attempt_ids: ['attempt-2'],
        },
      }],
    })

    const wrapper = mount(CourseEvolutionPanel, { props: { courseId: 'course-1' } })

    expect(wrapper.get('article').attributes('data-effect')).toBe('effective')
    expect(wrapper.text()).toContain('课程变化已验证')
    expect(wrapper.text()).toContain('原判断获得新证据支持')
  })
})
