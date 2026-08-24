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
    vi.spyOn(http, 'get').mockResolvedValue({ data: { total: 0 } })
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
    expect(wrapper.text()).toContain('当前小节')
    expect(wrapper.text()).toContain('1.1 爬虫的定义与流程')

    await wrapper.get('.lesson-ai-composer textarea').setValue('把教学目标改成可观察行为')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(createCandidate).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('能用流程图准确解释爬虫四步流程')
    expect(wrapper.get('.objective-section').classes()).toContain('ai-change-target')
    expect(wrapper.text()).toContain('修改候选已生成')

    await wrapper.get('.lesson-ai-composer textarea').setValue('同时增加课堂检查')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(resolveCandidate).toHaveBeenCalledWith('course-1', 'lesson-1', 'candidate-1', false)
    expect(createCandidate).toHaveBeenCalledTimes(2)
    expect(createCandidate.mock.calls[1]![3]).toContain('把教学目标改成可观察行为')
    expect(createCandidate.mock.calls[1]![3]).toContain('同时增加课堂检查')
    expect(wrapper.text()).toContain('上一版候选已被本轮补充要求替换')

    await wrapper.get('.lesson-ai-candidate-card button.primary').trigger('click')
    await flushPromises()

    expect(resolveCandidate).toHaveBeenLastCalledWith('course-1', 'lesson-1', 'candidate-2', true)
    expect(wrapper.text()).toContain('候选已采用，并形成新的教案工作修订')
  })
})
