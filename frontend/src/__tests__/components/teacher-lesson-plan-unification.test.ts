import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherLessonPlanDocument from '@/components/TeacherLessonPlanDocument.vue'
import { setLocale } from '@/shared/i18n'
import { useTeacherLessonAuthoringStore, type TeacherLessonProjection } from '@/stores/teacherLessonAuthoring'
import zhMessages from '../../../public/locales/zh/translation.json'

const lesson: TeacherLessonProjection = {
  lesson_unit_id: 'lesson-1',
  number: 1,
  title: '第1讲 爬虫概述与HTTP基础',
  duration_minutes: 45,
  sections: [{ section_node_id: 'section-1', title: '1.1 爬虫的定义、原理与应用场景' }],
  script: {
    current_revision_id: 'script-1', confirmed_revision_id: 'script-1',
    source_lesson_plan_revision_id: 'revision-1', source_state: 'current',
    ready: true, confirmed: true, confirmed_at: '2026-08-24T10:00:00Z',
    sections: [{ section_node_id: 'section-1', title: '1.1 爬虫的定义、原理与应用场景', content: '讲稿正文' }],
  },
  plan: {
    lesson_unit_id: 'lesson-1',
    working_revision_id: 'revision-1',
    confirmed_revision_id: 'revision-1',
    source_state: 'current',
    revisions: [{
      revision_id: 'revision-1',
      lesson_unit_id: 'lesson-1',
      source_outline_revision_id: 'outline-1',
      generation_source: 'model',
      status: 'confirmed',
      warnings: [],
      plan: {
        schema_version: 'course_teaching_plan_v3',
        sections: [{
          node_id: 'section-1',
          learning_objective: '能解释爬虫的四步工作流程',
          key_points: ['爬虫定义', '工作流程'],
          key_difficulties: ['爬虫与 API 调用的边界'],
          in_class_checks: ['完成流程图并说明每一步'],
          homework: ['查阅一个网站的 robots.txt'],
          teaching_notes: ['课堂以概念框架为主'],
          teaching_modules: [{
            module_id: 'core_explanation',
            teaching_purpose: '建立核心概念',
            planned_minutes: 15,
            teacher_activity: '绘制爬虫工作流程图',
            student_activity: '记录并复述流程',
          }, {
            module_id: 'feedback_check',
            teaching_purpose: '检查学习结果',
            planned_minutes: 5,
            teacher_activity: '抽查流程图',
            student_activity: '根据反馈修正',
          }],
        }],
      },
      actor: 'teacher',
      created_at: '2026-08-24T10:00:00Z',
    }],
    ppt_assets: [],
  },
}

describe('统一教案页面', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    await setLocale('zh')
  })

  it('用同一份标准模板展示并原位编辑', async () => {
    const store = useTeacherLessonAuthoringStore()
    const saveDraft = vi.spyOn(store, 'saveDraft').mockResolvedValue(lesson.plan)
    const wrapper = mount(TeacherLessonPlanDocument, {
      props: { courseId: 'course-1', lesson, confirmed: true },
    })

    expect(wrapper.get('.lesson-document').text()).toContain('标准教案')
    expect(wrapper.text()).toContain('教学目标')
    expect(wrapper.text()).toContain('教学重点')
    expect(wrapper.text()).toContain('教学流程')
    expect(wrapper.text()).toContain('课后作业')
    expect(wrapper.text()).not.toContain('理论型')
    expect(wrapper.text()).not.toContain('实战型')

    await wrapper.findAll('.document-actions button').find(button => button.text().includes('编辑教案'))!.trigger('click')
    expect(wrapper.find('.lesson-document').exists()).toBe(true)
    expect(wrapper.findAll('.flow-row')).toHaveLength(3)
    await wrapper.get('.objective-section textarea').setValue('能独立说明爬虫的四步流程')
    await wrapper.findAll('.document-actions button').find(button => button.text().includes('完成编辑'))!.trigger('click')
    await flushPromises()

    expect(saveDraft).toHaveBeenCalledWith(
      'course-1',
      'lesson-1',
      expect.objectContaining({
        sections: [expect.objectContaining({ learning_objective: '能独立说明爬虫的四步流程' })],
      }),
    )
    expect(wrapper.find('.objective-section textarea').exists()).toBe(false)
    expect(wrapper.find('.lesson-document').exists()).toBe(true)
  })

  it('AI 候选在同一份教案中预览并采用', async () => {
    const store = useTeacherLessonAuthoringStore()
    const candidatePlan = JSON.parse(JSON.stringify(lesson.plan.revisions[0]!.plan))
    candidatePlan.sections[0].learning_objective = 'AI 优化后的可观察目标'
    vi.spyOn(store, 'createAiCandidate').mockResolvedValue({
      candidate_id: 'candidate-1',
      lesson_unit_id: 'lesson-1',
      base_revision_id: 'revision-1',
      instruction: '增加可观察目标',
      section_node_id: 'section-1',
      plan: candidatePlan,
      status: 'pending',
      created_at: '2026-08-24T10:00:00Z',
    })
    const resolveCandidate = vi.spyOn(store, 'resolveAiCandidate').mockResolvedValue(lesson.plan)
    const wrapper = mount(TeacherLessonPlanDocument, {
      props: { courseId: 'course-1', lesson, confirmed: true },
    })

    await wrapper.findAll('.document-actions button').find(button => button.text().includes('AI 优化'))!.trigger('click')
    await wrapper.get('.ai-command textarea').setValue('增加可观察目标')
    await wrapper.get('.ai-command').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('AI 方案')
    expect(wrapper.text()).toContain('AI 优化后的可观察目标')
    await wrapper.findAll('.document-actions button').find(button => button.text().includes('采用'))!.trigger('click')
    await flushPromises()

    expect(resolveCandidate).toHaveBeenCalledWith('course-1', 'lesson-1', 'candidate-1', true)
    expect(wrapper.text()).not.toContain('AI 方案')
  })

  it('课程文件入口回到同一教案工作区，不再打开第二套抽屉', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/CourseWorkspaceView.vue'), 'utf8')
    const fileSource = readFileSync(resolve(process.cwd(), 'src/views/TeacherCourseSpaceView.vue'), 'utf8')
    const workbenchSource = readFileSync(resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'), 'utf8')
    expect(source).not.toContain('<GenerationLessonPlan')
    expect(source).not.toContain('lessonOpen')
    expect(source).toContain("requestedWorkbenchStage.value = 'lesson'")
    expect(source).toContain("requestedWorkbenchStage.value = 'script'")
    expect(source).toContain("requestedWorkbenchStage.value = 'ppt'")
    expect(source).toContain('requestedLessonId.value = lessonId')
    expect(source).toContain("workspaceView.value = 'categories'")
    expect(fileSource).toContain("emit('openScript', node.lessonId || '')")
    expect(fileSource).not.toContain('lessonStore.generatePpt')
    expect(workbenchSource).toContain('<TeacherScriptDocument')
    expect(workbenchSource).not.toContain("emit('openScript'")
    expect(workbenchSource).not.toContain('lessonStore.generatePpt')
  })
})
