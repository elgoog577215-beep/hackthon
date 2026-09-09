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
    expect(wrapper.get('.journey li.active').text()).toContain('输入想法')
    expect(wrapper.get('.request-composer').text()).toContain('这次想让课程怎么变')
    expect(wrapper.get('.readiness-strip').text()).toContain('课程准备情况')
    expect(wrapper.get('.readiness-strip').text()).toContain('部分完成')
    expect(wrapper.get('.readiness-strip').text()).toContain('尚未生成')
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

    expect(wrapper.get('.journey li.active').text()).toContain('选择影响范围')
    expect(wrapper.get('.scan-main').text()).toContain('索引召回')
    expect(wrapper.get('.scan-main').text()).toContain('AI 判断')
    expect(wrapper.findAll('.scanning-state aside li')).toHaveLength(4)
    expect(wrapper.get('.scanning-state aside').text()).not.toContain('题库')
    wrapper.unmount()
  })

  it('分析中可以取消当前全课任务', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.applyAnalysisTask({
      id: 'analysis-task-cancel',
      type: 'teacher_course_change_analysis',
      status: 'running',
      message: '正在分析整课影响',
    })
    const cancel = vi.spyOn(store, 'cancelAnalysisTask').mockResolvedValue(true)
    const wrapper = mountWorkspace(pinia)

    const button = wrapper.get('[data-testid="cancel-global-analysis"]')
    expect(button.attributes('type')).toBe('button')
    expect(button.text()).toContain('取消当前分析')
    await button.trigger('click')

    expect(cancel).toHaveBeenCalledTimes(1)
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
    const generate = vi.spyOn(store, 'generateSuggested').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.journey li.active').text()).toContain('选择影响范围')
    expect(wrapper.get('.request-context').text()).toContain('本次目标')
    expect(wrapper.findAll('.impact-nav nav button')).toHaveLength(2)
    expect(wrapper.get('.impact-list').text()).toContain('原讲稿只介绍方法')
    await wrapper.get('.impact-check input').setValue(false)
    expect(wrapper.get('.scope-counts').text()).toContain('排除1')
    await wrapper.get('.review-actionbar .button-primary').trigger('click')
    expect(review).toHaveBeenCalledWith('change-1', ['m2'], {
      migrationDispositions: { m1: 'rewrite_partial', m2: 'regenerate' },
    })
    expect(generate).toHaveBeenCalledWith('change-1')
    wrapper.unmount()
  })

  it('支持搜索、批量选择和直接改变处理方式', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      impact_summary: {
        analysis_mode: 'ai_ranked',
        affected_units: [
          { migration_id: 'm1', unit_id: 'script:b1', asset_type: 'script', unit_type: 'script_block', title: '案例引入', before_preview: '保留现有案例。', section_ids: ['s1'], source_state: 'current', disposition: 'regenerate', reason: '需同步讲稿', confidence: .9, candidate_status: 'not_started' },
          { migration_id: 'm2', unit_id: 'script:b2', asset_type: 'script', unit_type: 'script_block', title: '公式推导', before_preview: '展开公式。', section_ids: ['s2'], source_state: 'current', disposition: 'regenerate', reason: '需同步讲稿', confidence: .9, candidate_status: 'not_started' },
        ],
      },
    })]
    const review = vi.spyOn(store, 'reviewCoursePlan').mockResolvedValue({} as any)
    vi.spyOn(store, 'generateSuggested').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    await wrapper.get('.impact-tools > select').setValue('s1')
    expect(wrapper.findAll('.impact-list article')).toHaveLength(1)
    await wrapper.get('.impact-tools > select').setValue('')
    await wrapper.get('.impact-tools input').setValue('案例')
    expect(wrapper.findAll('.impact-list article')).toHaveLength(1)
    await wrapper.get('.impact-tools button:last-child').trigger('click')
    expect(wrapper.get('.scope-counts').text()).toContain('排除1')
    await wrapper.get('.disposition-control select').setValue('reuse_rebind')
    expect(wrapper.get('.review-actionbar').text()).toContain('建议需要更新')
    await wrapper.get('.review-actionbar .button-primary').trigger('click')
    expect(review).toHaveBeenCalledWith('change-1', ['m2'], {
      migrationDispositions: { m1: 'reuse_rebind', m2: 'regenerate' },
    })
    wrapper.unmount()
  })

  it('修正理解会指向旧方案，放弃方案需二次确认', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      impact_summary: {
        affected_units: [{ migration_id: 'm1', unit_id: 'script:b1', asset_type: 'script', unit_type: 'script_block', title: '案例', before_preview: '原内容', section_ids: ['s1'], source_state: 'current', disposition: 'regenerate', reason: '需调整', confidence: .8, candidate_status: 'not_started' }],
      },
    })]
    const create = vi.spyOn(store, 'createCoursePlan').mockResolvedValue({} as any)
    const reject = vi.spyOn(store, 'reject').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    await wrapper.get('.request-context button').trigger('click')
    await wrapper.get('.correction-bar textarea').setValue('保留原案例')
    await wrapper.get('.correction-bar').trigger('submit')
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ supersedesPlanId: 'change-1' }))

    await wrapper.get('.review-actionbar .button-danger').trigger('click')
    expect(reject).not.toHaveBeenCalled()
    expect(wrapper.get('.review-actionbar .button-danger').text()).toContain('再次点击')
    await wrapper.get('.review-actionbar .button-danger').trigger('click')
    expect(reject).toHaveBeenCalledWith('change-1', expect.any(String))
    wrapper.unmount()
  })

  it('需要澄清时始终提供确认当前理解并继续分析的操作', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    const basePlanning = planning()
    store.plans = [plan({
      teacher_change_planning: planning({
        status: 'needs_clarification',
        intent: {
          ...basePlanning.intent,
          blocking_questions: ['实践项目是否必须可运行？'],
          can_proceed_without_clarification: false,
        },
      }),
      impact_summary: {
        request_asset_types: ['outline', 'lesson_plan', 'script'],
        coverage: { scanned_units: 19, indexed_units: 116 },
      },
    })]
    const create = vi.spyOn(store, 'createCoursePlan').mockResolvedValue({
      analysis_task: { id: 'analysis-task-2', status: 'pending' },
    } as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.clarification-actions').text()).toContain('确认当前理解')
    await wrapper.get('.clarification-actions .button-primary').trigger('click')

    expect(create).toHaveBeenCalledWith({
      courseId: 'course-1',
      requestId: expect.any(String),
      instruction: '所有案例都补充完整推导，但保留原始资料。',
      supersedesPlanId: 'change-1',
      assetTypes: ['outline', 'lesson_plan', 'script'],
      confirmedInterpretation: true,
    })
    wrapper.unmount()
  })

  it('扫描未完成时只提供系统重试，不再要求老师填写或确认', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    const basePlanning = planning()
    store.plans = [plan({
      teacher_change_planning: planning({
        status: 'blocked',
        intent: {
          ...basePlanning.intent,
          blocking_questions: [],
          system_blockers: [{
            code: 'analysis_incomplete',
            message: '有 90 个内容单元未完成检查，请重新分析，避免遗漏修改。',
            retryable: true,
            affected_unit_count: 90,
          }],
          can_proceed_without_clarification: true,
        } as any,
      }),
      impact_summary: {
        request_asset_types: ['outline', 'lesson_plan', 'script'],
        coverage: { scanned_units: 26, indexed_units: 116, unscanned_unit_ids: Array.from({ length: 90 }, (_, index) => `unit-${index}`) },
      },
    })]
    const create = vi.spyOn(store, 'createCoursePlan').mockResolvedValue({
      analysis_task: { id: 'analysis-task-retry', status: 'pending' },
    } as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.text()).toContain('有 90 个内容单元未完成检查')
    expect(wrapper.find('.clarification-question').exists()).toBe(false)
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('确认当前理解并继续分析')
    await wrapper.get('[data-testid="retry-incomplete-scan"]').trigger('click')

    expect(create).toHaveBeenCalledWith({
      courseId: 'course-1',
      requestId: expect.any(String),
      instruction: '所有案例都补充完整推导，但保留原始资料。',
      supersedesPlanId: 'change-1',
      assetTypes: ['outline', 'lesson_plan', 'script'],
    })
    wrapper.unmount()
  })

  it('扫描已结束但方案阻断时可以二次确认后放弃当前全课修改', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    const basePlanning = planning()
    store.plans = [plan({
      teacher_change_planning: planning({
        status: 'blocked',
        intent: {
          ...basePlanning.intent,
          system_blockers: [{
            code: 'analysis_incomplete',
            message: '有 90 个内容单元未完成检查，请重新分析，避免遗漏修改。',
            retryable: true,
            affected_unit_count: 90,
          }],
        } as any,
      }),
      impact_summary: { coverage: { scanned_units: 26, indexed_units: 116 } },
    })]
    const reject = vi.spyOn(store, 'reject').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    const discard = wrapper.get('[data-testid="discard-blocked-plan"]')
    expect(discard.attributes('type')).toBe('button')
    expect(discard.text()).toContain('放弃本次全课修改')
    await discard.trigger('click')
    expect(reject).not.toHaveBeenCalled()
    expect(discard.text()).toContain('再次点击确认放弃')
    await discard.trigger('click')

    expect(reject).toHaveBeenCalledWith('change-1', '教师在审阅工作区主动放弃方案')
    expect(wrapper.find('.request-state').exists()).toBe(true)
    wrapper.unmount()
  })

  it('逐题选择必答项并把结构化答案交给同一后台分析链', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    const basePlanning = planning()
    store.plans = [plan({
      teacher_change_planning: planning({
        status: 'needs_clarification',
        intent: {
          ...basePlanning.intent,
          clarification_set_id: 'clarify-projects',
          clarifications: [
            {
              question_id: 'project_placement',
              prompt: '实践项目放在哪里？',
              response_type: 'single_choice',
              required: true,
              options: [
                { option_id: 'fixed_section', label: '每讲末尾固定小节', impact: '结构统一', recommended: true },
                { option_id: 'inline_case', label: '作为案例穿插', impact: '更贴合内容', recommended: false },
              ],
            },
            {
              question_id: 'project_reuse',
              prompt: '第六讲是否复用前几讲项目？',
              response_type: 'single_choice',
              required: true,
              options: [
                { option_id: 'new_each', label: '每讲新建项目', impact: '覆盖完整', recommended: true },
                { option_id: 'capstone', label: '第六讲综合复用', impact: '形成综合项目', recommended: false },
              ],
            },
          ],
          blocking_questions: ['实践项目放在哪里？', '第六讲是否复用前几讲项目？'],
          can_proceed_without_clarification: false,
        } as any,
      }),
      impact_summary: { request_asset_types: ['outline', 'lesson_plan', 'script'] },
    })]
    const create = vi.spyOn(store, 'createCoursePlan').mockResolvedValue({
      analysis_task: { id: 'analysis-task-choices', status: 'pending' },
    } as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.findAll('.clarification-question fieldset')).toHaveLength(2)
    expect(wrapper.findAll('.clarification-question input[type="radio"]')).toHaveLength(4)
    const confirm = wrapper.get('[data-testid="confirm-clarification-answers"]')
    expect(confirm.attributes('disabled')).toBeDefined()

    await wrapper.findAll('.clarification-question input[type="radio"]')[0]!.setValue(true)
    await wrapper.findAll('.clarification-question input[type="radio"]')[3]!.setValue(true)
    expect(confirm.attributes('disabled')).toBeUndefined()
    await confirm.trigger('click')

    expect(create).toHaveBeenCalledWith({
      courseId: 'course-1',
      requestId: expect.any(String),
      instruction: '所有案例都补充完整推导，但保留原始资料。',
      supersedesPlanId: 'change-1',
      assetTypes: ['outline', 'lesson_plan', 'script'],
      clarificationSetId: 'clarify-projects',
      clarificationAnswers: [
        { question_id: 'project_placement', option_id: 'fixed_section' },
        { question_id: 'project_reuse', option_id: 'capstone' },
      ],
    })
    wrapper.unmount()
  })

  it('精确候选直接展示前后差异并以一个操作组应用勾选项', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      operations: [{ operation_id: 'op-exact', operation_type: 'REPLACE_COURSE_BLOCK', target_block_id: 'block-1', target_section_id: 's1', scope: 'current', reason: '术语统一', payload: {} }],
      allowed_scopes: ['current'],
      teacher_change_planning: planning({ status: 'candidate_ready' }),
      impact_summary: {
        analysis_mode: 'ai_ranked',
        candidate_bundle: { operation_count: 1 },
        affected_units: [{ migration_id: 'm1', unit_id: 'course_content:block-1', asset_type: 'course_content', unit_type: 'course_block', title: '应用场景', before_preview: '先画受力图。', after_preview: '先画自由体图。', section_ids: ['s1'], source_state: 'current', disposition: 'rewrite_partial', reason: '术语统一', confidence: .98, candidate_status: 'ready', operation_id: 'op-exact', change_count: 1 }],
      },
    })]
    const accept = vi.spyOn(store, 'accept').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.candidate-diff').text()).toContain('先画受力图')
    expect(wrapper.get('.candidate-diff').text()).toContain('先画自由体图')
    expect(wrapper.get('.review-actionbar .button-primary').text()).toContain('应用 1 项修改')
    await wrapper.get('.review-actionbar .button-primary').trigger('click')
    expect(accept).toHaveBeenCalledWith('change-1', 'current', ['op-exact'])
    wrapper.unmount()
  })

  it('结构变化独立展示新旧课程树并在确认后生成联动建议', async () => {
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
    const review = vi.spyOn(store, 'reviewCoursePlan').mockResolvedValue({} as any)
    const generate = vi.spyOn(store, 'generateSuggested').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.journey li.active').text()).toContain('选择影响范围')
    await wrapper.get('.review-actionbar .button-primary').trigger('click')
    expect(review).toHaveBeenCalledWith('change-1', ['m1'], {
      migrationDispositions: { m1: 'regenerate' },
    })
    expect(generate).not.toHaveBeenCalled()

    store.plans[0]!.impact_summary.scope_review = {
      reviewed_at: '2026-08-25T10:06:00Z',
      selected_migration_ids: ['m1'],
    }
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.journey li.active').text()).toContain('审阅修改方案')
    expect(wrapper.get('.tree-comparison').text()).toContain('第三章 原理与项目')
    expect(wrapper.get('.tree-comparison').text()).toContain('第四章 项目实践')
    expect(wrapper.get('.migration-panel').text()).toContain('重新生成')
    expect(wrapper.get('.migration-panel').text()).toContain('需要按新结构重组')
    await wrapper.findAll('.structure-edit-row>input')[0]!.setValue('第三章 基础原理')
    expect(wrapper.get('.migration-panel .button-primary').text()).toContain('确认方案并生成建议')
    expect(wrapper.get('.migration-panel .button-primary').attributes('disabled')).toBeUndefined()
    await wrapper.get('.migration-panel .button-primary').trigger('click')
    expect(review).toHaveBeenCalledWith('change-1', ['m1'], {
      confirmStructure: true,
      migrationDispositions: { m1: 'regenerate' },
      proposedOutline: [
        { provisional_id: 'n1', title: '第三章 基础原理', parent_ref: 'root', source_node_ids: [], learning_focus: '' },
        { provisional_id: 'n2', title: '第四章 项目实践', parent_ref: 'root', source_node_ids: [], learning_focus: '' },
      ],
    })
    expect(generate).toHaveBeenCalledWith('change-1')
    wrapper.unmount()
  })

  it('结构已确认但候选未就绪时只能重试生成，不能提前应用', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      operations: [{ operation_id: 'outline-op', operation_type: 'REBUILD_COURSE_OUTLINE', target_block_id: '', target_section_id: '', scope: 'current', reason: '章节重构', payload: {} }],
      teacher_change_planning: planning({
        structural_operations: [{ operation_id: 'op1', operation_type: 'REBUILD_OUTLINE', base_blueprint_revision_id: 'outline-1', idempotency_key: 'k1', source_node_ids: ['c1'], target_parent_id: '', target_position: null, proposed_nodes: [], reason: '章节重构', assumptions: [], confidence: .9, requires_teacher_checkpoint: true }],
        structure_review_status: 'confirmed',
        status: 'impact_ready',
      }),
      impact_summary: {
        candidate_bundle: { operation_count: 1, domain_generation_pending: true },
        scope_review: { reviewed_at: '2026-08-25T10:06:00Z', selected_migration_ids: ['m1'] },
        proposed_outline: [{ provisional_id: 'n1', title: '第三章 新结构', parent_ref: 'root' }],
        affected_units: [{ migration_id: 'm1', unit_id: 'script:l1', asset_type: 'script', unit_type: 'script', title: '第三章讲稿', before_preview: '旧讲稿', section_ids: ['c1'], source_state: 'current', disposition: 'regenerate', reason: '结构变化', confidence: .8, candidate_status: 'not_started' }],
      },
    })]
    const accept = vi.spyOn(store, 'accept').mockResolvedValue({} as any)
    const generate = vi.spyOn(store, 'generateSuggested').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.migration-panel .button-primary').text()).toContain('生成联动建议')
    await wrapper.get('.migration-panel .button-primary').trigger('click')
    expect(generate).toHaveBeenCalledWith('change-1')
    expect(accept).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('应用 4 成功 1 失败时按 journal 汇编并只重试失败 operation ID', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      status: 'applied',
      selected_scope: 'current',
      selected_operation_ids: ['outline-ok', 'plan-ok', 'script-ok', 'bank-ok', 'ppt-failed'],
      operation_journal: [
        { schema_version: 'course_evolution_operation_journal_v1', operation_id: 'outline-ok', domain: 'outline', status: 'applied', attempt: 1, previous_revision_id: 'outline-1', expected_result_revision_id: 'outline-2', result_revision_id: 'outline-2', result_receipt: { title: '大纲', detail: '已更新' }, error_code: '', detail: '已更新', retryable: false, created_at: '', updated_at: '' },
        { schema_version: 'course_evolution_operation_journal_v1', operation_id: 'plan-ok', domain: 'lesson_plan', status: 'applied', attempt: 1, previous_revision_id: 'plan-1', expected_result_revision_id: 'plan-2', result_revision_id: 'plan-2', result_receipt: { title: '教案', detail: '已更新' }, error_code: '', detail: '已更新', retryable: false, created_at: '', updated_at: '' },
        { schema_version: 'course_evolution_operation_journal_v1', operation_id: 'script-ok', domain: 'script', status: 'applied', attempt: 1, previous_revision_id: 'script-1', expected_result_revision_id: 'script-2', result_revision_id: 'script-2', result_receipt: { title: '讲义', detail: '已更新' }, error_code: '', detail: '已更新', retryable: false, created_at: '', updated_at: '' },
        { schema_version: 'course_evolution_operation_journal_v1', operation_id: 'bank-ok', domain: 'question_bank', status: 'applied', attempt: 1, previous_revision_id: 'bank-1', expected_result_revision_id: 'bank-2', result_revision_id: 'bank-2', result_receipt: { title: '题库', detail: '已更新' }, error_code: '', detail: '已更新', retryable: false, created_at: '', updated_at: '' },
        { schema_version: 'course_evolution_operation_journal_v1', operation_id: 'ppt-failed', domain: 'ppt', status: 'failed', attempt: 1, previous_revision_id: 'ppt-1', expected_result_revision_id: 'ppt-2', result_revision_id: '', result_receipt: { title: 'PPT', detail: '应用失败' }, error_code: 'ppt_apply_failed', detail: '应用失败', retryable: true, created_at: '', updated_at: '' },
      ],
      application_receipt: {
        applied_count: 99,
        failed_count: 1,
        unchanged_count: 0,
        items: [
          { operation_id: 'script-ok', title: '讲稿', status: 'applied', detail: '已更新' },
          { operation_id: 'ppt-failed', title: 'PPT', status: 'failed', detail: '应用失败' },
        ],
      },
    })]
    const accept = vi.spyOn(store, 'accept').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.receipt-state dl').text()).toContain('已更新4')
    expect(wrapper.get('.receipt-state dl').text()).toContain('失败1')
    expect(wrapper.findAll('.receipt-items li')).toHaveLength(5)
    expect(wrapper.get('.receipt-actions').text()).toContain('只重试失败项')
    await wrapper.findAll('.receipt-actions button')[0]!.trigger('click')
    expect(accept).toHaveBeenCalledWith(
      'change-1',
      'current',
      ['ppt-failed'],
      { retryFailed: true },
    )
    wrapper.unmount()
  })

  it('下游撤销只要有一项失败就显示未完成并仅允许重试', async () => {
    const pinia = createPinia()
    const store = useCourseEvolutionStore(pinia)
    store.plans = [plan({
      status: 'undo_partial',
      application_receipt: { applied_count: 4, failed_count: 0, unchanged_count: 0 },
      undo_receipt: {
        domain_candidates: {
          status: 'partial',
          undone_count: 3,
          failed_count: 1,
          items: [
            { operation_id: 'ppt-1', domain: 'ppt', status: 'failed', detail: 'PPT 工作稿已变化' },
            { operation_id: 'script-1', domain: 'script', status: 'undone', detail: '已恢复到原版本' },
          ],
        },
      },
    })]
    const undo = vi.spyOn(store, 'undo').mockResolvedValue({} as any)
    const wrapper = mountWorkspace(pinia)

    expect(wrapper.get('.receipt-state').classes()).toContain('is-partial-undo')
    expect(wrapper.get('.receipt-state h3').text()).toContain('撤销尚未全部完成')
    expect(wrapper.get('.receipt-state dl').text()).toContain('已恢复3')
    expect(wrapper.get('.receipt-state dl').text()).toContain('失败1')
    expect(wrapper.get('.receipt-actions').text()).toContain('重试未完成的撤销')
    expect(wrapper.get('.receipt-actions').text()).not.toContain('继续修改课程')
    await wrapper.get('.receipt-actions button').trigger('click')
    expect(undo).toHaveBeenCalledWith('change-1')
    wrapper.unmount()
  })
})
