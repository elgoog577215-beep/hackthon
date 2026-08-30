import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, onMounted } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherCourseWorkbench from '@/components/TeacherCourseWorkbench.vue'
import TeacherLessonPlanDocument from '@/components/TeacherLessonPlanDocument.vue'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { useTeacherLessonAuthoringStore, type TeacherLessonPlanCandidate, type TeacherLessonProjection } from '@/stores/teacherLessonAuthoring'
import http from '@/utils/http'

const lesson: TeacherLessonProjection = {
  lesson_unit_id: 'lesson-1',
  number: 1,
  title: '第1讲 爬虫概述',
  duration_minutes: 45,
  sections: [{ section_node_id: 'section-1', title: '1.1 爬虫的定义与流程' }],
  arrangement: {
    schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'arrangement-1',
    lesson_unit_id: 'lesson-1', source_outline_revision_id: 'outline-1',
    lesson_type: 'theory', lesson_type_label: '理论讲授', blocks: [],
    status: 'confirmed', confirmed: true, source_state: 'current',
  },
  script: {
    current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '',
    source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [],
  },
  plan: {
    lesson_unit_id: 'lesson-1',
    working_revision_id: 'revision-1',
    confirmed_revision_id: '',
    source_state: 'current',
    revisions: [{
      revision_id: 'revision-1', lesson_unit_id: 'lesson-1', source_outline_revision_id: 'outline-1',
      generation_source: 'model', status: 'draft', warnings: [], actor: 'teacher', created_at: '',
      plan: {
        schema_version: 'course_teaching_plan_v3',
        sections: [{
          node_id: 'section-1', learning_objective: '能解释爬虫的工作流程', key_points: ['定义'],
          key_difficulties: [], in_class_checks: [], homework: [], teaching_notes: [],
          teaching_modules: [{
            module_id: 'core_explanation', planned_minutes: 20,
            teacher_activity: '讲解四步流程', student_activity: '绘制流程图',
          }],
        }],
      },
    }],
    ppt_assets: [],
  },
}

function mountWorkbench() {
  return mount(TeacherCourseWorkbench, {
    props: {
      courseId: 'course-1',
      courseTitle: '人工智能通识课',
      generationOptions: {} as any,
      initialStage: 'lesson',
    },
    global: {
      stubs: {
        CourseReferenceTray: true,
        CompanionDocumentStudio: true,
        QuestionBankReviewPanel: true,
        TeacherScriptDocument: true,
        CourseOutlineReview: true,
        MarkdownRenderer: true,
      },
    },
  })
}

async function openLessonAi(wrapper: ReturnType<typeof mountWorkbench>, label = 'AI 修改') {
  const trigger = wrapper.findAll('.lesson-toolbar-actions button').find(button => button.text().includes(label))
  if (!trigger) throw new Error(`未找到教案工具栏中的${label}入口`)
  await trigger.trigger('click')
}

function mountQuestionBankWorkbench(focusReferenceSources: () => void) {
  const QuestionBankReviewPanel = defineComponent({
    name: 'QuestionBankReviewPanel',
    emits: ['open-ai', 'references-change'],
    setup(_props, { emit, expose }) {
      expose({ focusReferenceSources })
      onMounted(() => emit('references-change', [{
        asset_id: 'asset-course-1',
        material_asset_id: 'material-course-1',
        filename: '整课讲义.pdf',
        source_label: '整课讲义',
        role: 'primary',
      }]))
      return () => h('section', { class: 'question-bank-stub' }, [
        h('button', {
          type: 'button',
          class: 'open-question-ai',
          onClick: () => emit('open-ai'),
        }, 'AI 生成题目'),
      ])
    },
  })
  return mount(TeacherCourseWorkbench, {
    props: {
      courseId: 'course-1',
      courseTitle: '人工智能通识课',
      generationOptions: {} as any,
      initialStage: 'question-bank',
    },
    global: {
      stubs: {
        CourseReferenceTray: true,
        CompanionDocumentStudio: true,
        QuestionBankReviewPanel,
        TeacherScriptDocument: true,
        CourseOutlineReview: true,
        MarkdownRenderer: true,
      },
    },
  })
}

function mountActualQuestionBankWorkbench() {
  return mount(TeacherCourseWorkbench, {
    props: {
      courseId: 'course-1',
      courseTitle: '人工智能通识课',
      generationOptions: {} as any,
      initialStage: 'question-bank',
    },
    global: {
      stubs: {
        CourseReferenceTray: true,
        CompanionDocumentStudio: true,
        TeacherScriptDocument: true,
        CourseOutlineReview: true,
        MarkdownRenderer: true,
      },
    },
  })
}

describe('教案 AI 协作编辑模式', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    window.localStorage.clear()
    vi.spyOn(http, 'get').mockResolvedValue({ data: { total: 0 } })
  })

  it('按当前小节缺口优先排列六项快捷修改，并把完整要求送入教案候选链', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const createCandidate = vi.spyOn(store, 'createAiCandidate').mockResolvedValue({
      candidate_id: 'candidate-quick-action', lesson_unit_id: 'lesson-1', base_revision_id: 'revision-1',
      instruction: '', section_node_id: 'section-1', plan: structuredClone(lesson.plan.revisions[0]!.plan), status: 'pending', created_at: '',
    })
    vi.spyOn(store, 'resolveAiCandidate').mockResolvedValue(lesson.plan)
    const wrapper = mountWorkbench()

    await openLessonAi(wrapper)

    const actions = wrapper.findAll('.lesson-ai-quick-grid button')
    expect(actions).toHaveLength(6)
    expect(actions.map(action => action.text())).toEqual([
      '补充检查点', '突出重点难点', '调整时间节奏', '加入课堂案例', '让目标可观察', '增加课堂互动',
    ])

    await actions[0]!.trigger('click')
    await flushPromises()

    expect(createCandidate).toHaveBeenCalledTimes(1)
    expect(createCandidate.mock.calls[0]![3]).toContain('补充能判断学生是否达成目标的课堂检查点')
  })

  it('题库 AI 固定使用整门课程范围和题库内部资料', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const focusReferenceSources = vi.fn()
    const wrapper = mountQuestionBankWorkbench(focusReferenceSources)
    await flushPromises()

    await wrapper.get('.open-question-ai').trigger('click')

    expect(wrapper.classes()).toContain('is-ai-collaboration')
    expect(wrapper.text()).toContain('整门课程题库')
    expect(wrapper.text()).toContain('人工智能通识课')
    expect(wrapper.text()).not.toContain('当前讲次题库')
    const sources = wrapper.get('.lesson-ai-sources')
    expect(sources.text()).toContain('1')
    expect(sources.attributes('title')).toContain('整课讲义')
    expect(sources.attributes('aria-expanded')).toBe('true')

    await sources.trigger('click')
    expect(focusReferenceSources).toHaveBeenCalledTimes(1)
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(false)

    await wrapper.get('.lesson-ai-composer textarea').setValue('重新弄一下')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(window.localStorage.getItem('teacher-course-workbench:ai-session:course-1:question-bank:course')).toContain('重新弄一下')
    expect([...Array(window.localStorage.length)].map((_, index) => window.localStorage.key(index)))
      .not.toContain('teacher-course-workbench:ai-session:course-1:question-bank:lesson-1:question-bank')
  })

  it('真实题库面板可以打开同一工作台的 AI 助手', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const wrapper = mountActualQuestionBankWorkbench()
    await flushPromises()

    await wrapper.get('.question-bank-ai-action').trigger('click')
    await wrapper.get('.question-generation-studio__ai').trigger('click')
    await flushPromises()

    expect(wrapper.classes()).toContain('is-ai-collaboration')
    expect(wrapper.get('.lesson-ai-workspace').text()).toContain('整门课程题库')
  })

  it('支持键盘调整 AI 面板宽度并保存教师偏好', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const wrapper = mountQuestionBankWorkbench(vi.fn())

    await wrapper.get('.open-question-ai').trigger('click')
    const resizer = wrapper.get('.ai-workspace-resizer')

    await resizer.trigger('keydown', { key: 'Home' })
    expect(resizer.attributes('aria-valuenow')).toBe('360')

    await resizer.trigger('keydown', { key: 'ArrowLeft' })
    expect(resizer.attributes('aria-valuenow')).toBe('384')
    expect(wrapper.attributes('style')).toContain('--ai-pane-width: 384px')
    expect(window.localStorage.getItem('teacher-course-workbench:ai-pane-width')).toBe('384')
  })

  it('在稳定右栏多轮修改左侧候选并保留确认边界', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const candidatePlan = structuredClone(lesson.plan.revisions[0]!.plan)
    candidatePlan.sections[0].learning_objective = '能用流程图准确解释爬虫四步流程'
    const createCandidate = vi.spyOn(store, 'createAiCandidate').mockImplementation(async (_course, _lesson, _revision, instruction) => ({
      candidate_id: `candidate-${createCandidate.mock.calls.length}`,
      lesson_unit_id: 'lesson-1',
      base_revision_id: 'revision-1',
      instruction,
      section_node_id: 'section-1',
      plan: structuredClone(candidatePlan),
      status: 'pending',
      created_at: '',
    } satisfies TeacherLessonPlanCandidate))
    const resolveCandidate = vi.spyOn(store, 'resolveAiCandidate').mockResolvedValue(lesson.plan)
    const wrapper = mountWorkbench()

    await openLessonAi(wrapper)

    expect(wrapper.classes()).not.toContain('is-ai-collaboration')
    expect(wrapper.find('.lesson-ai-workspace').exists()).toBe(true)
    expect(wrapper.get('.stage-rail').attributes('style')).toBeUndefined()
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(false)
    expect(wrapper.text()).toContain('AI 助手')
    expect(wrapper.text()).toContain('1.1 爬虫的定义与流程')
    expect(wrapper.text()).not.toContain('从哪里开始修改')
    expect(wrapper.text()).not.toContain('点击后生成可审阅候选')

    await wrapper.get('.lesson-ai-sources').trigger('click')
    expect(wrapper.classes()).not.toContain('is-ai-collaboration')
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(true)
    expect(wrapper.find('.lesson-ai-workspace').exists()).toBe(false)
    await wrapper.findAll('.context-pane-tabs button')[0]!.trigger('click')
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(false)
    expect(wrapper.find('.lesson-ai-workspace').exists()).toBe(true)

    await wrapper.get('.lesson-ai-composer textarea').setValue('把教学目标改成可观察行为')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(createCandidate).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('能用流程图准确解释爬虫四步流程')
    expect(wrapper.get('.objective-section').classes()).toContain('ai-change-target')
    expect(wrapper.text()).toContain('修改候选')
    expect(wrapper.text()).toContain('1 处修改')
    expect(wrapper.text()).toContain('教学目标')

    await wrapper.get('.lesson-ai-composer textarea').setValue('同时增加课堂检查')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(resolveCandidate).toHaveBeenCalledWith('course-1', 'lesson-1', 'candidate-1', false)
    expect(createCandidate).toHaveBeenCalledTimes(2)
    expect(createCandidate.mock.calls[1]![3]).toContain('把教学目标改成可观察行为')
    expect(createCandidate.mock.calls[1]![3]).toContain('同时增加课堂检查')
    expect(wrapper.text()).toContain('上一版候选已由本轮要求替换')

    await wrapper.get('.lesson-ai-review button.primary').trigger('click')
    await flushPromises()

    expect(resolveCandidate).toHaveBeenLastCalledWith('course-1', 'lesson-1', 'candidate-2', true)
    expect(wrapper.text()).toContain('候选已采用，并形成新的教案工作修订')
  })

  it('文中选区调用 AI 时自动切到助手并保留选中内容', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const wrapper = mountWorkbench()

    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(true)
    wrapper.getComponent(TeacherLessonPlanDocument).vm.$emit('open-ai-selection', {
      text: '能解释爬虫的工作流程',
    })
    await flushPromises()

    expect(wrapper.classes()).not.toContain('is-ai-collaboration')
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(false)
    expect(wrapper.findAll('.context-pane-tabs button')[0]!.attributes('aria-selected')).toBe('true')
    expect(wrapper.get('.lesson-ai-selection').text()).toContain('能解释爬虫的工作流程')
    expect(wrapper.get('.lesson-ai-composer textarea').attributes('placeholder')).toContain('如何修改这段内容')
  })

  it('模糊要求先向教师澄清，再按所选方向生成候选', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const candidatePlan = structuredClone(lesson.plan.revisions[0]!.plan)
    candidatePlan.sections[0].learning_objective = '能复述并说明爬虫四步流程'
    const createCandidate = vi.spyOn(store, 'createAiCandidate').mockResolvedValue({
      candidate_id: 'candidate-clarified', lesson_unit_id: 'lesson-1', base_revision_id: 'revision-1',
      instruction: '', section_node_id: 'section-1', plan: candidatePlan, status: 'pending', created_at: '',
    })
    vi.spyOn(store, 'resolveAiCandidate').mockResolvedValue(lesson.plan)
    const wrapper = mountWorkbench()

    await openLessonAi(wrapper)
    await wrapper.get('.lesson-ai-composer textarea').setValue('帮我改好一点')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(createCandidate).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('你希望优先调整哪一部分')
    expect(wrapper.get('.lesson-ai-workspace').attributes('data-phase')).toBe('clarifying')

    await wrapper.findAll('.lesson-ai-clarification button')[0]!.trigger('click')
    await flushPromises()

    expect(createCandidate).toHaveBeenCalledTimes(1)
    expect(createCandidate.mock.calls[0]![3]).toContain('帮我改好一点')
    expect(createCandidate.mock.calls[0]![3]).toContain('补充能判断学生是否达成目标的课堂检查点')
  })

  it('结构和跨资产要求复用整课修改方案，并在原助手中交给教师确认', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [structuredClone(lesson)]
    const localCandidate = vi.spyOn(lessonStore, 'createAiCandidate')
    const courseEvolutionStore = useCourseEvolutionStore()
    const createCoursePlan = vi.spyOn(courseEvolutionStore, 'createCoursePlan').mockResolvedValue({
      course_evolution_plans: [{
        change_set_id: 'course-change-1',
        impact_summary: {
          request_id: 'request-placeholder',
          affected_units: [
            { asset_type: 'outline' },
            { asset_type: 'lesson_plan' },
            { asset_type: 'script' },
          ],
        },
        teacher_change_planning: {
          status: 'impact_ready',
          structural_operations: [{ operation_id: 'move-1' }],
          intent: { blocking_questions: [] },
        },
      }],
    } as any)
    createCoursePlan.mockImplementation(async input => ({
      course_evolution_plans: [{
        change_set_id: 'course-change-1',
        impact_summary: {
          request_id: input.requestId,
          affected_units: [
            { asset_type: 'outline' },
            { asset_type: 'lesson_plan' },
            { asset_type: 'script' },
          ],
        },
        teacher_change_planning: {
          status: 'impact_ready',
          structural_operations: [{ operation_id: 'move-1' }],
          intent: { blocking_questions: [] },
        },
      }],
    } as any))
    const wrapper = mountWorkbench()

    await openLessonAi(wrapper)
    await wrapper.get('.lesson-ai-composer textarea').setValue('把第二章和第三章合并，并同步更新教案和讲稿')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(localCandidate).not.toHaveBeenCalled()
    expect(createCoursePlan).toHaveBeenCalledTimes(1)
    expect(createCoursePlan.mock.calls[0]![0]).toMatchObject({ courseId: 'course-1' })
    expect(createCoursePlan.mock.calls[0]![0].instruction).toContain('把第二章和第三章合并')
    expect(wrapper.get('.lesson-ai-course-plan').text()).toContain('整课修改方案')
    expect(wrapper.get('.lesson-ai-course-plan').text()).toContain('3 个受影响单元')
    expect(wrapper.get('.lesson-ai-course-plan').text()).toContain('大纲、教案、讲义')

    await wrapper.get('.lesson-ai-course-plan button').trigger('click')
    expect(wrapper.emitted('open-course-adjustment')?.[0]).toEqual([{ planId: 'course-change-1' }])
  })

  it('整课方案失败后保留原要求，并用同一个请求标识重试', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [structuredClone(lesson)]
    const courseEvolutionStore = useCourseEvolutionStore()
    const createCoursePlan = vi.spyOn(courseEvolutionStore, 'createCoursePlan')
      .mockRejectedValueOnce(new Error('模型暂时不可用'))
      .mockImplementationOnce(async input => ({
        course_evolution_plans: [{
          change_set_id: 'course-change-retry',
          impact_summary: { request_id: input.requestId, affected_units: [{ asset_type: 'lesson_plan' }] },
          teacher_change_planning: {
            status: 'candidate_ready', structural_operations: [], intent: { blocking_questions: [] },
          },
        }],
      } as any))
    const wrapper = mountWorkbench()

    await openLessonAi(wrapper)
    await wrapper.get('.lesson-ai-composer textarea').setValue('把 A 这个名词永远都替换成 B')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('模型暂时不可用')
    const firstRequestId = createCoursePlan.mock.calls[0]![0].requestId
    await wrapper.get('.lesson-ai-assistant-line.is-error button').trigger('click')
    await flushPromises()

    expect(createCoursePlan).toHaveBeenCalledTimes(2)
    expect(createCoursePlan.mock.calls[1]![0].requestId).toBe(firstRequestId)
    expect(wrapper.get('.lesson-ai-course-plan').text()).toContain('整课修改方案')
    expect(wrapper.text()).toContain('把 A 这个名词永远都替换成 B')
  })

  it('刷新后恢复当前修订尚未处理的候选', async () => {
    const store = useTeacherLessonAuthoringStore()
    const restoredLesson = structuredClone(lesson)
    const restoredPlan = structuredClone(lesson.plan.revisions[0]!.plan)
    restoredPlan.sections[0].learning_objective = '能画出爬虫四步流程图'
    restoredLesson.plan.ai_candidates = [{
      candidate_id: 'candidate-restored', lesson_unit_id: 'lesson-1', base_revision_id: 'revision-1',
      instruction: '让目标可观察', section_node_id: 'section-1', plan: restoredPlan, status: 'pending', created_at: '',
    }]
    store.lessons = [restoredLesson]
    vi.spyOn(store, 'resolveAiCandidate').mockResolvedValue(restoredLesson.plan)
    const wrapper = mountWorkbench()
    await flushPromises()

    expect(wrapper.get('.objective-section').classes()).toContain('ai-change-target')
    await openLessonAi(wrapper, 'AI 方案')
    expect(wrapper.text()).toContain('已恢复上次未处理的修改候选')
    expect(wrapper.get('.lesson-ai-workspace').attributes('data-phase')).toBe('review')
    await wrapper.findAll('.lesson-ai-review button').find(button => button.text().includes('放弃'))!.trigger('click')
    await flushPromises()

    expect(store.resolveAiCandidate).toHaveBeenCalledWith('course-1', 'lesson-1', 'candidate-restored', false)
  })

  it('按课程、课次与稳定小节恢复未结束的对话', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const first = mountWorkbench()

    await openLessonAi(first)
    await first.get('.lesson-ai-composer textarea').setValue('帮我改好一点')
    await first.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(first.text()).toContain('帮我改好一点')
    expect([...Array(window.localStorage.length)].map((_, index) => window.localStorage.key(index)))
      .toContain('teacher-course-workbench:ai-session:course-1:lesson:lesson-1:section-1')
    first.unmount()

    const second = mountWorkbench()
    await openLessonAi(second)
    await flushPromises()

    expect(second.text()).toContain('帮我改好一点')
    expect(second.text()).toContain('你希望优先调整哪一部分')
    expect(second.get('.lesson-ai-workspace').attributes('data-phase')).toBe('clarifying')
  })

  it('切换实际教案小节时同步左侧正文与独立对话，不把修改串到别的小节', async () => {
    const scopedLesson = structuredClone(lesson)
    scopedLesson.sections.push({ section_node_id: 'section-2', title: '1.2 HTTP 请求与响应' })
    scopedLesson.plan.revisions[0]!.plan.sections.push({
      node_id: 'section-2', learning_objective: '能区分请求与响应', key_points: ['请求结构'],
      key_difficulties: ['状态码'], in_class_checks: [], homework: [], teaching_notes: [],
      teaching_modules: [{
        module_id: 'core_explanation', planned_minutes: 25,
        teacher_activity: '对比请求与响应', student_activity: '分析报文',
      }],
    })
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [scopedLesson]
    const wrapper = mountWorkbench()

    await openLessonAi(wrapper)
    await wrapper.get('.lesson-ai-composer textarea').setValue('帮我改好一点')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    const scopeSelect = wrapper.get('.lesson-ai-scope-select select')
    expect((scopeSelect.element as HTMLSelectElement).value).toBe('section-1')
    await scopeSelect.setValue('section-2')
    await flushPromises()

    expect((scopeSelect.element as HTMLSelectElement).value).toBe('section-2')
    expect(wrapper.text()).toContain('1.2 HTTP 请求与响应')
    expect(wrapper.text()).not.toContain('帮我改好一点')
    expect(wrapper.find('.lesson-ai-quick-grid').exists()).toBe(true)
    expect(wrapper.findAll('.lesson-section-tabs button')[1]!.classes()).toContain('active')
    expect(window.localStorage.getItem('teacher-course-workbench:ai-session:course-1:lesson:lesson-1:section-1')).toContain('帮我改好一点')

    await wrapper.findAll('.lesson-section-tabs button')[0]!.trigger('click')
    await flushPromises()

    expect((scopeSelect.element as HTMLSelectElement).value).toBe('section-1')
    expect(wrapper.text()).toContain('帮我改好一点')
    expect(wrapper.text()).toContain('你希望优先调整哪一部分')
    expect(wrapper.get('.lesson-ai-workspace').attributes('data-phase')).toBe('clarifying')
  })
})
