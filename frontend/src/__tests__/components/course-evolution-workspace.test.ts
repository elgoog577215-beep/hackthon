import { mount } from '@vue/test-utils'
import { createPinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseEvolutionWorkspace from '@/components/CourseEvolutionWorkspace.vue'
import zhMessages from '@/../public/locales/zh/translation.json'
import { setLocale } from '@/shared/i18n'
import {
  useCourseEvolutionStore,
  type CourseEvolutionPlan,
  type TeacherCourseChangeContext,
  type TeacherCourseChangePlanning,
} from '@/stores/courseEvolution'

function context(): TeacherCourseChangeContext {
  return {
    schema_version: 'teacher_course_change_context_v1',
    index_schema_version: 'teacher_course_change_index_v1',
    course_id: 'course-1',
    course_title: '大学物理',
    source_mode: 'authoring_workspace',
    ready: true,
    readiness_message: '已连接课程结构与现有教学资产',
    base_revision_vector: { teacher_outline: 'outline-1' },
    assets: [
      { asset_type: 'outline', label: '课程大纲', state: 'available', count: 24, source: 'teacher_generation_workspace', revision: 'outline-1' },
      { asset_type: 'lesson_plan', label: '教案', state: 'partial', count: 3, source: 'teacher_lesson_authoring', revision: '12' },
      { asset_type: 'script', label: '讲稿', state: 'available', count: 23, source: 'teacher_lesson_authoring', revision: '12' },
      { asset_type: 'ppt', label: 'PPT', state: 'available', count: 44, source: 'teaching_representation', revision: '12' },
      { asset_type: 'question_bank', label: '题库', state: 'missing', count: 0, source: 'question_bank', revision: '' },
    ],
    outline: [
      { node_id: 'c1', parent_node_id: 'root', node_name: '第一章 原理', node_level: 1 },
      { node_id: 's1', parent_node_id: 'c1', node_name: '1.1 力与加速度', node_level: 2 },
    ],
    units: [],
    updated_at: '2026-08-25T10:00:00Z',
    summary: { available_assets: 4, missing_assets: 1, indexed_units: 94, outline_nodes: 24 },
  }
}

function planning(overrides: Partial<TeacherCourseChangePlanning> = {}): TeacherCourseChangePlanning {
  return {
    schema_version: 'course_change_plan_v1',
    scenario_matrix_version: 'course_change_scenario_matrix_v1',
    plan_id: 'change-1',
    course_id: 'course-1',
    intent: {
      schema_version: 'course_change_intent_v1',
      intent_id: 'intent-1',
      course_id: 'course-1',
      raw_request: '所有案例都补充完整推导，但保留原始资料。',
      interpreted_goal: '扩写全课案例，并同步讲稿与 PPT。',
      scope_hint: {},
      hard_constraints: [],
      soft_preferences: [],
      protected_requirements: ['保留原始资料'],
      source_refs: [],
      signals: [],
      assumptions: [],
      blocking_questions: [],
      can_proceed_without_clarification: true,
      interpretation_revision: 'intent-1',
    },
    base_revision_vector: { teacher_outline: 'outline-1' },
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
    hypothesis_id: '',
    evidence_ids: [],
    operations: [],
    allowed_scopes: [],
    impact_summary: {},
    expected_effect: '扩写全课案例',
    status: 'pending',
    application_receipt: {},
    undo_receipt: {},
    effect_evaluation: {},
    teacher_change_planning: planning(),
    ...overrides,
  }
}

function mountWorkspace(pinia: Pinia) {
  const store = useCourseEvolutionStore(pinia)
  store.courseContext = store.courseContext || context()
  vi.spyOn(store, 'refreshProgress').mockResolvedValue({} as any)
  vi.spyOn(store, 'loadCourseContext').mockResolvedValue(store.courseContext)
  return mount(CourseEvolutionWorkspace, {
    attachTo: document.body,
    props: { modelValue: true, courseId: 'course-1', courseTitle: '大学物理' },
    global: { plugins: [pinia], stubs: { Teleport: true, Transition: false } },
  })
}

describe('CourseEvolutionWorkspace', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  it('首屏同时给出自然语言入口、贯通流程和真实课程索引', async () => {
    const wrapper = mountWorkspace(createPinia())

    expect(wrapper.findAll('.journey li')).toHaveLength(4)
    expect(wrapper.get('.journey li.active').text()).toContain('说出要求')
    expect(wrapper.get('.request-composer').text()).toContain('这次想让课程怎么变')
    expect(wrapper.get('.asset-ledger').text()).toContain('24')
    expect(wrapper.get('.asset-ledger').text()).toContain('44')
    expect(wrapper.get('.asset-ledger').text()).toContain('尚未生成')
    expect(wrapper.find('.request-context').exists()).toBe(false)

    await wrapper.findAll('.icon-action')[1]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    wrapper.unmount()
  })

  it('分析中只展示实际存在的资产和索引处理链', () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.generating = true
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.journey li.active').text()).toContain('分析影响')
    expect(wrapper.get('.scan-main').text()).toContain('索引召回')
    expect(wrapper.get('.scan-main').text()).toContain('AI 判断')
    expect(wrapper.findAll('.scanning-state aside li')).toHaveLength(4)
    expect(wrapper.get('.scanning-state aside').text()).not.toContain('题库')
    wrapper.unmount()
  })

  it('内容变化用资产导航、原因和勾选范围完成精细审阅', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      impact_summary: {
        analysis_mode: 'ai_ranked',
        affected_units: [
          { migration_id: 'm1', unit_id: 'script:b1', asset_type: 'script', unit_type: 'script_block', title: '应用场景', before_preview: '原讲稿只介绍方法。', section_ids: ['s1'], source_state: 'current', disposition: 'rewrite_partial', reason: '老师要求所有案例补充推导', confidence: .91, candidate_status: 'not_started' },
          { migration_id: 'm2', unit_id: 'ppt:p1', asset_type: 'ppt', unit_type: 'slide', title: '第 12 页', before_preview: '旧页面只有结论。', section_ids: ['s1'], source_state: 'current', disposition: 'regenerate', reason: 'PPT 需要同步新的案例推导', confidence: .86, candidate_status: 'not_started' },
        ],
      },
    })]
    const review = vi.spyOn(store, 'reviewCoursePlan').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.journey li.active').text()).toContain('审阅修改')
    expect(wrapper.get('.request-context').text()).toContain('老师原话')
    expect(wrapper.findAll('.impact-nav nav button')).toHaveLength(2)
    expect(wrapper.get('.impact-list').text()).toContain('原讲稿只介绍方法')
    await wrapper.get('.impact-check input').setValue(false)
    expect(wrapper.get('.scope-counts').text()).toContain('排除1')
    await wrapper.get('.review-actionbar .button-primary').trigger('click')
    expect(review).toHaveBeenCalledWith('change-1', ['m2'])
    wrapper.unmount()
  })

  it('结构变化独立展示新旧课程树和迁移决策', () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      teacher_change_planning: planning({
        execution_strategies: ['structural_regeneration', 'semantic_impact'],
        structural_operations: [{ operation_id: 'op1', operation_type: 'REBUILD_OUTLINE', base_blueprint_revision_id: 'outline-1', idempotency_key: 'k1', source_node_ids: ['c1'], target_parent_id: '', target_position: null, proposed_nodes: [], reason: '章节重构', assumptions: [], confidence: .9, requires_teacher_checkpoint: true }],
      }),
      impact_summary: {
        current_outline: [{ node_id: 'c1', parent_node_id: 'root', node_name: '第三章 原理与项目', node_level: 1 }],
        proposed_outline: [{ provisional_id: 'n1', title: '第三章 原理', parent_ref: 'root' }, { provisional_id: 'n2', title: '第四章 项目实践', parent_ref: 'root' }],
        affected_units: [{ migration_id: 'm1', unit_id: 'lesson:l1', asset_type: 'lesson_plan', unit_type: 'lesson', title: '第三章教案', before_preview: '', section_ids: ['c1'], source_state: 'current', disposition: 'regenerate', reason: '需要按新结构重组', confidence: .8, candidate_status: 'not_started' }],
      },
    })]
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.journey li.active').text()).toContain('审阅修改')
    expect(wrapper.get('.tree-comparison').text()).toContain('第三章 原理与项目')
    expect(wrapper.get('.tree-comparison').text()).toContain('第四章 项目实践')
    expect(wrapper.get('.migration-panel').text()).toContain('重新生成')
    expect(wrapper.get('.migration-panel').text()).toContain('需要按新结构重组')
    expect(wrapper.get('.migration-panel .button-primary').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
})
