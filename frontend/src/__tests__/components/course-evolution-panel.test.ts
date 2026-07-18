import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CourseEvolutionPanel from '@/components/CourseEvolutionPanel.vue'
import enMessages from '@/../public/locales/en/translation.json'
import zhMessages from '@/../public/locales/zh/translation.json'
import { setLocale } from '@/shared/i18n'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { useCourseStore } from '@/stores/course'
import { useLearningProgressStore } from '@/stores/learningProgress'

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
          scene_analysis: {
            analysis_source: 'ai_semantic',
            scene_summary: '学习者已经掌握基础，希望升级理论推导并加入真实行业决策。',
            rationale: '当前要求同时涉及解释深度和跨情境应用。',
            source_requirement: 'verified_current_sources',
            source_status: 'verification_required',
          },
        },
      }],
    })

    const wrapper = mount(CourseEvolutionPanel, {
      props: { courseId: 'course-1', sectionId: 's1' },
    })

    expect(wrapper.findAll('.growth-steps li')).toHaveLength(6)
    expect(wrapper.get('.evolution-diagnosis').text()).toContain('AI 场景理解')
    expect(wrapper.get('.evolution-diagnosis').text()).toContain('升级理论推导并加入真实行业决策')
    expect(wrapper.get('.source-requirement').text()).toContain('不会把模型记忆当成行业证据')
    await wrapper.get('.evolution-details-toggle').trigger('click')
    expect(wrapper.text()).toContain('升级')
    expect(wrapper.text()).toContain('新增')
    expect(wrapper.text()).toContain('结构化同源检查已通过')
    expect(wrapper.text()).toContain('整体确认并更新课程')
  })

  it('在输入旁让用户先选择当前小节或全课程硬范围', async () => {
    const store = useCourseEvolutionStore()
    store.applyPayload('course-1', {
      evidence_items: [],
      hypotheses: [],
      course_evolution_plans: [],
    })
    const createPlan = vi.spyOn(store, 'createSectionPlan').mockResolvedValue({} as any)
    const wrapper = mount(CourseEvolutionPanel, {
      props: { courseId: 'course-1', sectionId: 's1' },
    })

    expect(wrapper.get('[data-scope="current_section"]').attributes('aria-checked')).toBe('true')
    await wrapper.get('[data-scope="whole_course"]').trigger('click')
    await wrapper.get('.section-growth-request input').setValue('以后所有例子都讲得详细一点')
    await wrapper.get('.generate-plan').trigger('click')

    expect(createPlan).toHaveBeenCalledWith(
      's1',
      '以后所有例子都讲得详细一点',
      'whole_course',
    )
  })

  it('把全课程匹配结果放进多节点审阅层，并只提交用户勾选的操作', async () => {
    const wholeCoursePlan = {
      ...plan,
      source_kind: 'manual_section_request',
      target_section_id: 's1',
      scope_selection: 'whole_course',
      generation_status: 'ready',
      requested_roles: ['example'],
      operations: [
        {
          operation_id: 'replace-example-1',
          operation_type: 'REPLACE_COURSE_BLOCK',
          target_block_id: 'b1',
          target_section_id: 's1',
          scope: 'current',
          reason: '第一节的例子需要更详细。',
          payload: {
            action: 'REPLACE',
            desired_role: 'example',
            target_section_title: '第一节',
            target_block_title: '例子讲解',
            before_preview: '原例子一。',
            after_preview: '分步骤展开的例子一。',
          },
        },
        {
          operation_id: 'replace-example-2',
          operation_type: 'REPLACE_COURSE_BLOCK',
          target_block_id: 'b2',
          target_section_id: 's2',
          scope: 'current',
          reason: '第二节的例子需要更详细。',
          payload: {
            action: 'REPLACE',
            desired_role: 'example',
            target_section_title: '第二节',
            target_block_title: '例子讲解',
            before_preview: '原例子二。',
            after_preview: '分步骤展开的例子二。',
          },
        },
      ],
      impact_summary: {
        ...plan.impact_summary,
        diagnosis: '你限定了当前全课程；AI 将这句话解释为调整例子讲解，共匹配 2 个现有教学节点。',
        target_role_labels: ['例子讲解'],
        matched_block_count: 2,
        affected_section_ids: ['s1', 's2'],
        matching_policy: '只升级当前课程中已存在且教学作用匹配的块。',
      },
    } as any
    const store = useCourseEvolutionStore()
    store.applyPayload('course-1', {
      evidence_items: [],
      hypotheses: [],
      course_evolution_plans: [wholeCoursePlan],
    })
    const accept = vi.spyOn(store, 'accept').mockResolvedValue({} as any)
    vi.spyOn(useCourseStore(), 'refreshCourseData').mockResolvedValue(undefined as any)
    vi.spyOn(useLearningProgressStore(), 'loadRuntime').mockResolvedValue(undefined as any)
    const wrapper = mount(CourseEvolutionPanel, {
      props: { courseId: 'course-1', sectionId: 's1' },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.get('.semantic-scope-summary').text()).toContain('匹配 2 个节点')
    await wrapper.get('.evolution-actions .primary').trigger('click')
    expect(wrapper.get('.review-workbench').attributes('role')).toBe('dialog')
    expect(wrapper.findAll('.review-list > li')).toHaveLength(2)
    expect(wrapper.text()).toContain('当前全课程')
    expect(wrapper.text()).toContain('例子讲解')

    const choices = wrapper.findAll('.operation-choice input')
    await choices[1]!.setValue(false)
    await wrapper.get('.apply-selected').trigger('click')
    await flushPromises()

    expect(accept).toHaveBeenCalledWith(
      'plan-1',
      'current',
      ['replace-example-1'],
    )
  })

  it('英文模式完整呈现硬范围和多节点审阅操作', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/')
        ? enMessages
        : zhMessages,
    })))
    await setLocale('en')

    try {
      useCourseEvolutionStore().applyPayload('course-1', {
        evidence_items: [],
        hypotheses: [],
        course_evolution_plans: [{
          ...plan,
          source_kind: 'manual_section_request',
          target_section_id: 's1',
          scope_selection: 'whole_course',
          generation_status: 'ready',
          requested_roles: ['example'],
          operations: [
            {
              operation_id: 'replace-example-1',
              operation_type: 'REPLACE_COURSE_BLOCK',
              target_block_id: 'b1',
              target_section_id: 's1',
              scope: 'current',
              reason: 'Make the first example more explicit.',
              payload: {
                action: 'REPLACE',
                desired_role: 'example',
                target_section_title: 'Section 1',
                target_block_title: 'Worked example',
                before_preview: 'Original example one.',
                after_preview: 'Step-by-step example one.',
              },
            },
            {
              operation_id: 'replace-example-2',
              operation_type: 'REPLACE_COURSE_BLOCK',
              target_block_id: 'b2',
              target_section_id: 's2',
              scope: 'current',
              reason: 'Make the second example more explicit.',
              payload: {
                action: 'REPLACE',
                desired_role: 'example',
                target_section_title: 'Section 2',
                target_block_title: 'Worked example',
                before_preview: 'Original example two.',
                after_preview: 'Step-by-step example two.',
              },
            },
          ],
          impact_summary: {
            ...plan.impact_summary,
            diagnosis: 'The request targets example blocks across the course.',
            target_role_labels: ['Worked examples'],
            matched_block_count: 2,
            affected_section_ids: ['s1', 's2'],
            matching_policy: 'Only existing matching blocks are included.',
          },
        }],
      })
      const wrapper = mount(CourseEvolutionPanel, {
        props: { courseId: 'course-1', sectionId: 's1' },
        global: { stubs: { Teleport: true } },
      })

      expect(wrapper.text()).toContain('Current section only')
      expect(wrapper.text()).toContain('Apply across course')
      expect(wrapper.get('.evolution-actions .primary').text()).toContain('Review 2 nodes')
      await wrapper.get('.evolution-actions .primary').trigger('click')
      expect(wrapper.get('.review-workbench').text()).toContain('Whole-course impact review')
      expect(wrapper.get('.apply-selected').text()).toContain('Apply 2 selected')
    } finally {
      await setLocale('zh')
      vi.unstubAllGlobals()
    }
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

  it('AI 场景判断不可用时明确显示规则保底，而不是让流程卡住', () => {
    useCourseEvolutionStore().applyPayload('course-1', {
      evidence_items: [],
      hypotheses: [],
      course_evolution_plans: [{
        ...plan,
        target_section_id: 's1',
        generation_status: 'ready',
        impact_summary: {
          ...plan.impact_summary,
          affected_section_ids: ['s1'],
          scene_analysis: {
            analysis_source: 'deterministic_fallback',
            scene_summary: '学习者当前存在理解阻力，需要通过例子讲解降低断点。',
            rationale: '根据用户明确提到的理解信号进行规则判断。',
            source_requirement: 'course_only',
            source_status: 'course_grounded',
          },
        },
      }],
    })

    const wrapper = mount(CourseEvolutionPanel, {
      props: { courseId: 'course-1', sectionId: 's1' },
    })

    expect(wrapper.get('.evolution-diagnosis').text()).toContain('规则保底判断')
    expect(wrapper.get('.evolution-diagnosis').text()).toContain('通过例子讲解降低断点')
    expect(wrapper.find('.source-requirement').exists()).toBe(false)
  })
})
