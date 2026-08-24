import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherCourseWorkbench from '@/components/TeacherCourseWorkbench.vue'
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

    await wrapper.findAll('.document-actions button').find(button => button.text().includes('AI 修改'))!.trigger('click')

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

  it('支持键盘调整 AI 面板宽度并保存教师偏好', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const wrapper = mountWorkbench()

    await wrapper.findAll('.document-actions button').find(button => button.text().includes('AI 修改'))!.trigger('click')
    const resizer = wrapper.get('.ai-workspace-resizer')

    await resizer.trigger('keydown', { key: 'Home' })
    expect(resizer.attributes('aria-valuenow')).toBe('360')

    await resizer.trigger('keydown', { key: 'ArrowLeft' })
    expect(resizer.attributes('aria-valuenow')).toBe('384')
    expect(wrapper.attributes('style')).toContain('--ai-pane-width: 384px')
    expect(window.localStorage.getItem('teacher-course-workbench:ai-pane-width')).toBe('384')
  })

  it('进入左右分屏，以多轮要求刷新左侧候选并保留确认边界', async () => {
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

    await wrapper.findAll('.document-actions button').find(button => button.text().includes('AI 修改'))!.trigger('click')

    expect(wrapper.classes()).toContain('is-ai-collaboration')
    expect(wrapper.find('.lesson-ai-workspace').exists()).toBe(true)
    expect(wrapper.get('.stage-rail').attributes('style')).toContain('display: none')
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(false)
    expect(wrapper.text()).toContain('AI 助手')
    expect(wrapper.text()).toContain('1.1 爬虫的定义与流程')
    expect(wrapper.text()).not.toContain('从哪里开始修改')
    expect(wrapper.text()).not.toContain('点击后生成可审阅候选')

    await wrapper.get('.lesson-ai-sources').trigger('click')
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(true)
    wrapper.getComponent({ name: 'CourseReferenceTray' }).vm.$emit('close')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(false)

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

    await wrapper.findAll('.document-actions button').find(button => button.text().includes('AI 修改'))!.trigger('click')
    await wrapper.get('.lesson-ai-composer textarea').setValue('帮我改好一点')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(createCandidate).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('你希望优先调整哪一部分')
    expect(wrapper.get('.lesson-ai-title [data-phase]').attributes('data-phase')).toBe('clarifying')

    await wrapper.findAll('.lesson-ai-clarification button')[0]!.trigger('click')
    await flushPromises()

    expect(createCandidate).toHaveBeenCalledTimes(1)
    expect(createCandidate.mock.calls[0]![3]).toContain('帮我改好一点')
    expect(createCandidate.mock.calls[0]![3]).toContain('补充能判断学生是否达成目标的课堂检查点')
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
    await wrapper.findAll('.document-actions button').find(button => button.text().includes('AI 方案'))!.trigger('click')
    expect(wrapper.text()).toContain('已恢复上次未处理的修改候选')
    expect(wrapper.get('.lesson-ai-title [data-phase]').attributes('data-phase')).toBe('review')
    await wrapper.findAll('.lesson-ai-review button').find(button => button.text().includes('放弃'))!.trigger('click')
    await flushPromises()

    expect(store.resolveAiCandidate).toHaveBeenCalledWith('course-1', 'lesson-1', 'candidate-restored', false)
  })

  it('按课程、课次与稳定小节恢复未结束的对话', async () => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [structuredClone(lesson)]
    const first = mountWorkbench()

    await first.findAll('.document-actions button').find(button => button.text().includes('AI 修改'))!.trigger('click')
    await first.get('.lesson-ai-composer textarea').setValue('帮我改好一点')
    await first.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(first.text()).toContain('帮我改好一点')
    expect([...Array(window.localStorage.length)].map((_, index) => window.localStorage.key(index)))
      .toContain('teacher-course-workbench:ai-session:course-1:lesson:lesson-1:section-1')
    first.unmount()

    const second = mountWorkbench()
    await second.findAll('.document-actions button').find(button => button.text().includes('AI 修改'))!.trigger('click')
    await flushPromises()

    expect(second.text()).toContain('帮我改好一点')
    expect(second.text()).toContain('你希望优先调整哪一部分')
    expect(second.get('.lesson-ai-title [data-phase]').attributes('data-phase')).toBe('clarifying')
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

    await wrapper.findAll('.document-actions button').find(button => button.text().includes('AI 修改'))!.trigger('click')
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
    expect(wrapper.get('.lesson-ai-title [data-phase]').attributes('data-phase')).toBe('clarifying')
  })
})
