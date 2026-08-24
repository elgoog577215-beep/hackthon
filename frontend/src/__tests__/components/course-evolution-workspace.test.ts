import { mount } from '@vue/test-utils'
import { createPinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseEvolutionWorkspace from '@/components/CourseEvolutionWorkspace.vue'
import zhMessages from '@/../public/locales/zh/translation.json'
import { setLocale } from '@/shared/i18n'
import { useCourseEvolutionStore, type CourseEvolutionPlan, type TeacherCourseChangePlanning } from '@/stores/courseEvolution'

function planning(overrides: Partial<TeacherCourseChangePlanning> = {}): TeacherCourseChangePlanning {
  return {
    schema_version: 'course_change_plan_v1',
    scenario_matrix_version: 'course_change_scenario_matrix_v1',
    plan_id: 'teacher-plan-1',
    course_id: 'course-1',
    intent: {
      schema_version: 'course_change_intent_v1',
      intent_id: 'intent-1',
      course_id: 'course-1',
      raw_request: '把第三章讲得更适合项目课，但保留原案例。',
      interpreted_goal: '重写第三章相关内容并保留原项目案例。',
      scope_hint: {},
      hard_constraints: [],
      soft_preferences: [],
      protected_requirements: ['保留原项目案例'],
      source_refs: [],
      signals: [],
      assumptions: [],
      blocking_questions: [],
      can_proceed_without_clarification: true,
      interpretation_revision: 'intent-1',
    },
    base_revision_vector: { outline: 'r1' },
    execution_strategies: ['semantic_impact'],
    strategy_status: 'resolved',
    scenario_tags: [],
    structural_operations: [],
    unit_migrations: [],
    structure_review_status: 'not_required',
    status: 'impact_ready',
    supersedes_plan_id: '',
    replan_reasons: [],
    created_at: '2026-08-25T10:00:00Z',
    updated_at: '2026-08-25T10:05:00Z',
    ...overrides,
  }
}

function plan(overrides: Partial<CourseEvolutionPlan> = {}): CourseEvolutionPlan {
  return {
    change_set_id: 'change-1',
    hypothesis_id: 'hypothesis-1',
    evidence_ids: [],
    operations: [],
    allowed_scopes: ['current', 'current_and_next'],
    impact_summary: {},
    expected_effect: '',
    status: 'pending',
    effect_evaluation: {},
    teacher_change_planning: planning(),
    ...overrides,
  }
}

function mountWorkspace(pinia: Pinia) {
  return mount(CourseEvolutionWorkspace, {
    attachTo: document.body,
    props: {
      modelValue: true,
      courseId: 'course-1',
      courseTitle: '大学物理',
      sectionId: 'section-1',
      sectionTitle: '第一章 质点力学基础',
    },
    global: {
      plugins: [pinia],
      stubs: {
        Teleport: true,
        Transition: false,
        CourseEvolutionPanel: {
          props: ['courseId', 'sectionId', 'focusPlanId', 'surface', 'workspaceState', 'showHeading'],
          template: '<div class="evolution-workspace-stub" :data-state="workspaceState" :data-surface="surface" />',
        },
      },
    },
  })
}

describe('CourseEvolutionWorkspace', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  it('尚未提出要求时只显示自然语言入口和最近记录', async () => {
    const wrapper = mountWorkspace(createPinia())

    expect(wrapper.find('.workspace-state-request').exists()).toBe(true)
    expect(wrapper.get('.evolution-workspace-stub').attributes('data-state')).toBe('request')
    expect(wrapper.get('.recent-course-changes').text()).toContain('还没有课程修改记录')
    expect(wrapper.find('.impact-navigation').exists()).toBe(false)
    expect(wrapper.find('.migration-summary').exists()).toBe(false)

    await wrapper.get('.course-adjustment-close').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    wrapper.unmount()
  })

  it('AI 正在理解时并列保留老师原话、AI 理解和修正入口', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({ teacher_change_planning: planning({ status: 'needs_clarification' }) })]
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.workspace-state-interpreting').text()).toContain('把第三章讲得更适合项目课')
    expect(wrapper.get('.workspace-state-interpreting').text()).toContain('重写第三章相关内容')
    expect(wrapper.get('.secondary-action').text()).toContain('修正 AI 的理解')
    await wrapper.get('.secondary-action').trigger('click')
    expect(wrapper.find('.understanding-correction textarea').exists()).toBe(true)
    wrapper.unmount()
  })

  it('扫描时只渐进展示已经发现的资产，不预先铺满五类', () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({ teacher_change_planning: planning({
      strategy_status: 'provisional',
      unit_migrations: [
        { migration_id: 'm1', asset_type: 'outline', unit_type: 'section', source_unit_ids: ['s1'], target_unit_ids: ['s2'], disposition: 'rewrite_partial', reason: '目标变化', confidence: 0.9, requires_review: false, candidate_status: 'not_started' },
        { migration_id: 'm2', asset_type: 'slide_deck', unit_type: 'slide', source_unit_ids: ['p1'], target_unit_ids: ['p2'], disposition: 'regenerate', reason: '来源变化', confidence: 0.8, requires_review: false, candidate_status: 'not_started' },
      ],
    }) })]
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.findAll('.discovered-impact li')).toHaveLength(2)
    expect(wrapper.get('.discovered-impact').text()).toContain('课程大纲')
    expect(wrapper.get('.discovered-impact').text()).toContain('PPT')
    expect(wrapper.get('.discovered-impact').text()).not.toContain('题库')
    wrapper.unmount()
  })

  it('内容变化时用左侧影响导航切换右侧真实差异', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({ teacher_change_planning: planning({
      unit_migrations: [
        { migration_id: 'm1', asset_type: 'teacher_script', unit_type: 'block', source_unit_ids: ['讲稿 3.1'], target_unit_ids: ['讲稿 3.1'], disposition: 'rewrite_partial', reason: '补齐项目背景', confidence: 0.9, requires_review: false, candidate_status: 'ready', metadata: { before_preview: '原讲稿只介绍方法。', after_preview: '新讲稿先交代项目背景，再介绍方法。' } },
        { migration_id: 'm2', asset_type: 'slide_deck', unit_type: 'slide', source_unit_ids: ['P12'], target_unit_ids: ['P12'], disposition: 'regenerate', reason: '同步讲稿', confidence: 0.9, requires_review: false, candidate_status: 'ready', metadata: { before_preview: '旧页面', after_preview: '新页面' } },
      ],
    }) })]
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.findAll('.impact-navigation nav button')).toHaveLength(2)
    expect(wrapper.get('.content-diff-card').text()).toContain('原讲稿只介绍方法')
    expect(wrapper.get('.content-diff-card').text()).toContain('新讲稿先交代项目背景')
    await wrapper.findAll('.impact-navigation nav button')[1]!.trigger('click')
    expect(wrapper.get('.content-diff-card').text()).toContain('旧页面')
    expect(wrapper.get('.evolution-workspace-stub').attributes('data-state')).toBe('content')
    wrapper.unmount()
  })

  it('结构变化时主区域核对新旧课程树，侧栏统计迁移与冲突', () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({ teacher_change_planning: planning({
      execution_strategies: ['structural_regeneration', 'semantic_impact'],
      structural_operations: [{ operation_type: 'SPLIT_OUTLINE_NODE', source_titles: ['第三章 原理与项目'], proposed_nodes: [{ provisional_id: 'n1', title: '第三章 原理' }, { provisional_id: 'n2', title: '第四章 项目实践' }] }],
      structure_review_status: 'pending',
      unit_migrations: [
        { migration_id: 'm1', asset_type: 'outline', unit_type: 'section', source_unit_ids: ['s1'], target_unit_ids: ['n1'], disposition: 'reuse_rebind', reason: '移动到原理章', confidence: 0.9, requires_review: false, candidate_status: 'ready' },
        { migration_id: 'm2', asset_type: 'lesson_plan', unit_type: 'lesson', source_unit_ids: ['l1'], target_unit_ids: ['n2'], disposition: 'blocked', reason: '课时总量冲突', confidence: 0.5, requires_review: true, candidate_status: 'not_started' },
      ],
    }) })]
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.course-tree-comparison').text()).toContain('第三章 原理与项目')
    expect(wrapper.get('.course-tree-comparison').text()).toContain('第四章 项目实践')
    expect(wrapper.get('.migration-summary').text()).toContain('迁移重绑')
    expect(wrapper.get('.migration-conflicts').text()).toContain('课时总量冲突')
    expect(wrapper.get('.evolution-workspace-stub').attributes('data-state')).toBe('structure')
    wrapper.unmount()
  })

  it('应用完成后只显示实际回执并支持整次撤销', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      status: 'applied',
      applied_block_ids: ['b1', 'b2'],
      application_receipt: { applied_count: 2, failed_items: ['PPT 第 12 页'], unchanged_items: ['保留案例 A'] },
    })]
    const undo = vi.spyOn(store, 'undo').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.application-receipt').text()).toContain('课程已按确认结果更新')
    expect(wrapper.get('.application-receipt').text()).toContain('PPT 第 12 页')
    expect(wrapper.get('.application-receipt').text()).toContain('保留案例 A')
    await wrapper.get('.undo-action').trigger('click')
    expect(undo).toHaveBeenCalledWith('change-1')
    wrapper.unmount()
  })
})
