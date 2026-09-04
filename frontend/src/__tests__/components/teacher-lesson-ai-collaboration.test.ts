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
    ready: true,
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
        'el-dialog': true,
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

async function openInlineLessonAi(wrapper: ReturnType<typeof mountWorkbench>) {
  await flushPromises()
  ;(wrapper.getComponent(TeacherLessonPlanDocument).vm as any).openInlineAi()
  await flushPromises()
  return wrapper.get('.text-selection-ai__composer')
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
        'el-dialog': true,
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
        'el-dialog': true,
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

  it('教师从教案正文原位输入要求，候选直接嵌入同一篇正文', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const candidatePlan = structuredClone(lesson.plan.revisions[0]!.plan)
    candidatePlan.sections[0].learning_objective = '能用流程图准确解释爬虫四步流程'
    const createCandidate = vi.spyOn(store, 'createAiCandidate').mockResolvedValue({
      candidate_id: 'candidate-inline', lesson_unit_id: 'lesson-1', base_revision_id: 'revision-1',
      instruction: '把教学目标改成可观察行为', section_node_id: 'section-1', plan: candidatePlan, status: 'pending', created_at: '',
    })
    vi.spyOn(store, 'resolveAiCandidate').mockResolvedValue(lesson.plan)
    const wrapper = mountWorkbench()

    const composer = await openInlineLessonAi(wrapper)

    expect(wrapper.classes()).not.toContain('is-ai-collaboration')
    expect(wrapper.find('.lesson-ai-workspace').exists()).toBe(false)
    expect(composer.text()).toContain('AI 只生成候选，采用后才会写入正式教案')
    await composer.get('textarea').setValue('把教学目标改成可观察行为')
    await composer.trigger('submit')
    await flushPromises()

    expect(createCandidate.mock.calls[0]![3]).toContain('把教学目标改成可观察行为')
    expect(wrapper.get('.candidate-canvas-notice').text()).toContain('AI 候选已嵌入教案正文')
    expect(wrapper.get('.candidate-canvas-notice').text()).toContain('继续调整')
    expect(wrapper.get('.candidate-canvas-notice').text()).toContain('保留原文')
    expect(wrapper.get('.candidate-canvas-notice').text()).toContain('采用修改')
    expect(wrapper.get('[data-ai-field="knowledge_objectives"]').classes()).toContain('ai-change-target')
    expect(wrapper.get('.objective-section').classes()).not.toContain('ai-change-target')
    expect(wrapper.text()).toContain('能用流程图准确解释爬虫四步流程')
  })

  it('精确字段在对象下方生成，携带对象身份并显示真实等待时间', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const candidatePlan = structuredClone(lesson.plan.revisions[0]!.plan)
    candidatePlan.sections[0].teaching_modules[0].teacher_activity = '先让学生预测，再讲解四步流程'
    let finishCandidate: ((candidate: TeacherLessonPlanCandidate) => void) | undefined
    const createCandidate = vi.spyOn(store, 'createAiCandidate').mockImplementation(async (...args) => {
      const onProgress = args[7]
      onProgress?.({ status: 'running', message: '正在读取局部上下文', elapsed_ms: 2200 })
      return await new Promise<TeacherLessonPlanCandidate>((resolve) => { finishCandidate = resolve })
    })
    vi.spyOn(store, 'resolveAiCandidate').mockResolvedValue(lesson.plan)
    const wrapper = mountWorkbench()
    await flushPromises()

    const field = wrapper.get('[data-ai-field="teacher_activity"]')
    await field.trigger('pointerover')
    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    const composer = wrapper.get('.text-selection-ai__composer')
    await composer.get('textarea').setValue('增加学生预测环节')
    await composer.trigger('submit')
    await flushPromises()

    expect(createCandidate.mock.calls[0]![6]).toEqual({
      sectionNodeId: 'section-1',
      field: 'teacher_activity',
      itemId: 'core_explanation',
      selectedText: '教师活动：讲解四步流程',
    })
    expect(wrapper.get('.text-selection-ai__status').text()).toContain('已等待 2 秒')
    expect(wrapper.classes()).not.toContain('is-ai-collaboration')

    finishCandidate?.({
      candidate_id: 'candidate-field', lesson_unit_id: 'lesson-1', base_revision_id: 'revision-1',
      instruction: '增加学生预测环节', section_node_id: 'section-1', target_field: 'teacher_activity',
      target_item_id: 'core_explanation', selected_text: '教师活动：讲解四步流程',
      plan: candidatePlan, status: 'pending', created_at: '',
    })
    await flushPromises()

    expect(wrapper.find('.candidate-canvas-notice').exists()).toBe(false)
    expect(wrapper.get('.text-selection-ai__composer').text()).toContain('采用修改')
    expect(wrapper.get('[data-ai-field="teacher_activity"]').classes()).toContain('ai-change-target')
    expect(wrapper.get('.flow-section').classes()).not.toContain('ai-change-target')
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

  it('继续调整会替换上一版候选，采用后才形成教案工作修订', async () => {
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

    let composer = await openInlineLessonAi(wrapper)
    await composer.get('textarea').setValue('把教学目标改成可观察行为')
    await composer.trigger('submit')
    await flushPromises()

    expect(createCandidate).toHaveBeenCalledTimes(1)
    await wrapper.findAll('.candidate-canvas-notice button')[0]!.trigger('click')
    await flushPromises()
    composer = wrapper.get('.text-selection-ai__composer')
    await composer.get('textarea').setValue('同时增加课堂检查')
    await composer.trigger('submit')
    await flushPromises()

    expect(resolveCandidate).toHaveBeenCalledWith('course-1', 'lesson-1', 'candidate-1', false)
    expect(createCandidate).toHaveBeenCalledTimes(2)
    expect(createCandidate.mock.calls[1]![3]).toContain('把教学目标改成可观察行为')
    expect(createCandidate.mock.calls[1]![3]).toContain('同时增加课堂检查')

    await wrapper.get('.candidate-canvas-notice button.primary').trigger('click')
    await flushPromises()

    expect(resolveCandidate).toHaveBeenLastCalledWith('course-1', 'lesson-1', 'candidate-2', true)
    expect(wrapper.find('.candidate-canvas-notice').exists()).toBe(false)
  })

  it('文中选区把选中内容与局部要求直接送入当前教案候选链', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const createCandidate = vi.spyOn(store, 'createAiCandidate').mockResolvedValue({
      candidate_id: 'candidate-selection', lesson_unit_id: 'lesson-1', base_revision_id: 'revision-1',
      instruction: '改成可测量的表述', section_node_id: 'section-1', plan: structuredClone(lesson.plan.revisions[0]!.plan), status: 'pending', created_at: '',
    })
    const wrapper = mountWorkbench()

    wrapper.getComponent(TeacherLessonPlanDocument).vm.$emit('open-ai-selection', {
      text: '能解释爬虫的工作流程',
      instruction: '改成可测量的表述',
      source: 'selection',
    })
    await flushPromises()

    expect(wrapper.classes()).not.toContain('is-ai-collaboration')
    expect(wrapper.find('.lesson-ai-workspace').exists()).toBe(false)
    expect(createCandidate).toHaveBeenCalledTimes(1)
    expect(createCandidate.mock.calls[0]![3]).toContain('改成可测量的表述')
    expect(createCandidate.mock.calls[0]![3]).toContain('能解释爬虫的工作流程')
  })

  it('结构和跨资产要求复用整课修改方案，并直接打开审计弹窗', async () => {
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

    const composer = await openInlineLessonAi(wrapper)
    await composer.get('textarea').setValue('把第二章和第三章合并，并同步更新教案和讲稿')
    await composer.trigger('submit')
    await flushPromises()

    expect(localCandidate).not.toHaveBeenCalled()
    expect(createCoursePlan).toHaveBeenCalledTimes(1)
    expect(createCoursePlan.mock.calls[0]![0]).toMatchObject({ courseId: 'course-1' })
    expect(createCoursePlan.mock.calls[0]![0].instruction).toContain('把第二章和第三章合并')
    expect(wrapper.emitted('open-course-adjustment')?.[0]).toEqual([{ planId: 'course-change-1' }])
    expect(wrapper.find('.lesson-ai-course-plan').exists()).toBe(false)
  })

  it('刷新后把当前修订尚未处理的候选恢复到正文，并允许保留原文', async () => {
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

    expect(wrapper.get('[data-ai-field="knowledge_objectives"]').classes()).toContain('ai-change-target')
    expect(wrapper.get('.objective-section').classes()).not.toContain('ai-change-target')
    expect(wrapper.get('.candidate-canvas-notice').text()).toContain('AI 候选已嵌入教案正文')
    await wrapper.findAll('.candidate-canvas-notice button').find(button => button.text().includes('保留原文'))!.trigger('click')
    await flushPromises()

    expect(store.resolveAiCandidate).toHaveBeenCalledWith('course-1', 'lesson-1', 'candidate-restored', false)
  })
})
