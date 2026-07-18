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

  it('一次独立复验通过只显示初步支持，不冒充持续确认', () => {
    useCourseEvolutionStore().applyPayload('course-1', {
      evidence_items: evidence,
      hypotheses: [],
      course_evolution_plans: [{
        ...plan,
        status: 'applied',
        effect_evaluation: {
          status: 'effective',
          verification_level: 'initial_support',
          interaction_event_ids: ['interaction-1'],
          attempt_ids: ['attempt-2'],
          verification_summary: {
            baseline: { attempt_count: 1, passed: false },
            course_change: { applied_block_count: 3, interaction_completed: true },
            follow_up: { attempt_count: 1, passed: true, distinct_task_count: 1 },
            interpretation: '本轮独立复验通过，原判断获得新证据支持；仍需后续不同任务持续确认。',
          },
        },
      }],
    })

    const wrapper = mount(CourseEvolutionPanel, { props: { courseId: 'course-1' } })

    expect(wrapper.get('article').attributes('data-effect')).toBe('effective')
    expect(wrapper.text()).toContain('本轮独立复验通过')
    expect(wrapper.text()).toContain('原判断获得新证据支持')
    expect(wrapper.text()).toContain('调整前')
    expect(wrapper.text()).toContain('课程生长')
    expect(wrapper.text()).toContain('独立复验')
    expect(wrapper.text()).not.toContain('持续证据已确认')
  })

  it('两个不同正式任务持续通过后才显示持续证据已确认', () => {
    useCourseEvolutionStore().applyPayload('course-1', {
      evidence_items: evidence,
      hypotheses: [],
      course_evolution_plans: [{
        ...plan,
        status: 'applied',
        effect_evaluation: {
          status: 'effective',
          verification_level: 'confirmed',
          verification_summary: {
            baseline: { attempt_count: 1, passed: false },
            course_change: { applied_block_count: 3, interaction_completed: true },
            follow_up: { attempt_count: 2, passed: true, distinct_task_count: 2 },
            interpretation: '多个不同正式任务持续通过，当前课程变化获得稳定证据支持。',
          },
        },
      }],
    })

    const wrapper = mount(CourseEvolutionPanel, { props: { courseId: 'course-1' } })

    expect(wrapper.text()).toContain('持续证据已确认')
    expect(wrapper.text()).toContain('多个不同正式任务持续通过')
  })

  it('在当前小节展示六步生长入口，并区分升级旧块与新增缺失块', async () => {
    useCourseEvolutionStore().applyPayload('course-1', {
      evidence_items: [],
      hypotheses: [],
      course_evolution_plans: [{
        ...plan,
        source_kind: 'manual_section_request',
        target_section_id: 's1',
        growth_direction: 'challenge',
        generation_status: 'ready',
        requested_roles: ['reasoning', 'application'],
        operations: [
          {
            operation_id: 'replace-reasoning',
            operation_type: 'REPLACE_COURSE_BLOCK',
            target_block_id: 'b1',
            target_section_id: 's1',
            scope: 'current',
            reason: '保留块身份并强化理论推导。',
            payload: {
              action: 'REPLACE',
              desired_role: 'reasoning',
              before_preview: '原理论。',
              after_preview: '更完整的理论推导。',
            },
          },
          {
            operation_id: 'insert-application',
            operation_type: 'INSERT_COURSE_BLOCK',
            target_block_id: 'b1',
            target_section_id: 's1',
            scope: 'current',
            reason: '原本缺少实战应用。',
            payload: {
              action: 'INSERT',
              desired_role: 'application',
              after_preview: '新增实战任务。',
            },
          },
        ],
        impact_summary: {
          ...plan.impact_summary,
          affected_section_ids: ['s1'],
          quality_report: { passed: true },
        },
      }],
    })

    const wrapper = mount(CourseEvolutionPanel, {
      props: { courseId: 'course-1', sectionId: 's1' },
    })

    expect(wrapper.findAll('.growth-steps li')).toHaveLength(6)
    await wrapper.get('.evolution-details-toggle').trigger('click')
    expect(wrapper.text()).toContain('升级')
    expect(wrapper.text()).toContain('新增')
    expect(wrapper.text()).toContain('结构化同源检查已通过')
    expect(wrapper.text()).toContain('整体确认并更新课程')
  })

  it('把重复全对先呈现为挑战建议，不在候选生成前直接更新课程', () => {
    useCourseEvolutionStore().applyPayload('course-1', {
      evidence_items: evidence.filter((item: any) => item.source_type === 'practice_attempt'),
      hypotheses: [],
      course_evolution_plans: [{
        ...plan,
        target_section_id: 's1',
        growth_direction: 'challenge',
        generation_status: 'suggested',
        operations: [],
        impact_summary: {
          ...plan.impact_summary,
          affected_section_ids: ['s1'],
          diagnosis: '当前小节已稳定通过，可以提升理论深度和迁移距离。',
        },
      }],
    })

    const wrapper = mount(CourseEvolutionPanel, {
      props: { courseId: 'course-1', sectionId: 's1' },
    })

    expect(wrapper.get('.challenge-suggestion').text()).toContain('当前难度已稳定通过')
    expect(wrapper.get('.challenge-suggestion').text()).toContain('旧难度掌握记录会保留')
    expect(wrapper.get('.challenge-suggestion button').text()).toContain('生成升级方案')
    expect(wrapper.find('.evolution-actions').exists()).toBe(false)
  })
})
