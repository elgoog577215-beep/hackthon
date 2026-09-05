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
  arrangement: {
    schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'arrangement-1',
    lesson_unit_id: 'lesson-1', source_outline_revision_id: 'outline-1',
    lesson_type: 'theory', lesson_type_label: '理论讲授', blocks: [],
    source_state: 'current',
  },
  script: {
    current_revision_id: 'script-1',
    source_lesson_plan_revision_id: 'revision-1', source_state: 'current',
    ready: true,
    sections: [{ section_node_id: 'section-1', title: '1.1 爬虫的定义、原理与应用场景', content: '讲稿正文' }],
  },
  plan: {
    lesson_unit_id: 'lesson-1',
    working_revision_id: 'revision-1',
    source_state: 'current',
    current_revision: {
      revision_id: 'revision-1',
      lesson_unit_id: 'lesson-1',
      source_outline_revision_id: 'outline-1',
      generation_source: 'model',
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
            label: '爬虫工作流程建模',
            teaching_purpose: '建立核心概念',
            planned_minutes: 15,
            teacher_activity: '绘制爬虫工作流程图',
            student_activity: '记录并复述流程',
            expected_output: '一张完整流程图',
            check_method: '能说明四步之间的输入输出关系',
            feedback_strategy: '指出遗漏环节后重新说明',
            adaptation_options: ['达到后迁移', '部分达到时补提示', '未达到时回到示例'],
            access_support: '提供流程图模板',
            grouping: '同伴互查',
            transition: '转入边界判断',
            handout_ppt_mapping: '讲义第 2 页与 PPT 第 3 页',
          }, {
            module_id: 'feedback_check',
            label: '流程图纠错与复核',
            teaching_purpose: '检查学习结果',
            planned_minutes: 5,
            teacher_activity: '抽查流程图',
            student_activity: '根据反馈修正',
          }],
        }],
      },
      actor: 'teacher',
      created_at: '2026-08-24T10:00:00Z',
    },
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
    const saveDraft = vi.spyOn(store, 'saveDraft').mockResolvedValue(lesson)
    const wrapper = mount(TeacherLessonPlanDocument, {
      props: { courseId: 'course-1', courseTitle: '网络爬虫', lesson },
    })

    expect(wrapper.get('.document-title h3').text()).toBe('第1讲 爬虫概述与HTTP基础')
    expect(wrapper.find('.document-state').exists()).toBe(false)
    expect(wrapper.get('.lesson-document').text()).not.toContain('标准教案')
    expect(wrapper.find('.document-saved').exists()).toBe(false)
    for (const heading of [
      '知识目标', '能力目标', '育人目标',
      '教学重点与难点', '课堂教学过程',
      '课程总结', '课后作业', '拓展阅读', '教学活动照片',
    ]) expect(wrapper.text()).toContain(heading)
    expect(wrapper.find('.lesson-identity').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('课程名称')
    expect(wrapper.text()).not.toContain('课前准备（按需）')
    expect(wrapper.get('.lesson-theme-heading').text()).toContain('1.1 爬虫的定义、原理与应用场景')
    expect(wrapper.find('.document-title p').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('理论型')
    expect(wrapper.text()).not.toContain('实战型')
    expect(wrapper.get('.lesson-block-summary').text()).toContain('课堂活动')
    expect(wrapper.text()).toContain('环节 1：爬虫工作流程建模')
    expect(wrapper.text()).toContain('环节 2：流程图纠错与复核')
    expect(wrapper.get('.lesson-block-summary').text()).toContain('教师活动：绘制爬虫工作流程图')
    expect(wrapper.get('.lesson-block-summary').text()).toContain('学生活动：记录并复述流程')
    expect(wrapper.get('.lesson-block-summary').text()).toContain('达成判断')
    expect(wrapper.get('.lesson-block-summary').text()).toContain('课堂产出：一张完整流程图')
    expect(wrapper.get('.lesson-block-summary').text()).toContain('达成检查：能说明四步之间的输入输出关系')
    expect(wrapper.find('.block-contingency').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('进入支持')
    expect(wrapper.text()).not.toContain('分组方式')
    expect(wrapper.text()).not.toContain('讲义与 PPT 对应关系')

    await wrapper.findAll('.document-actions button').find(button => button.text().includes('编辑教案'))!.trigger('click')
    expect(wrapper.find('.lesson-document').exists()).toBe(true)
    expect(wrapper.findAll('.teaching-block')).toHaveLength(2)
    expect(wrapper.find('.lesson-block-summary').exists()).toBe(false)
    expect(wrapper.find('.block-contingency').exists()).toBe(true)
    await wrapper.get('.objective-section textarea').setValue('能独立说明爬虫的四步流程')
    await wrapper.findAll('.document-actions button').find(button => button.text().includes('完成编辑'))!.trigger('click')
    await flushPromises()

    expect(saveDraft).toHaveBeenCalledWith(
      'course-1',
      'lesson-1',
      expect.objectContaining({
        sections: [expect.objectContaining({
          knowledge_objectives: ['能独立说明爬虫的四步流程'],
          ability_objectives: ['记录并复述流程', '根据反馈修正'],
          education_objectives: [],
        })],
      }),
      'revision-1',
    )
    expect(wrapper.find('.objective-section textarea').exists()).toBe(false)
    expect(wrapper.find('.lesson-document').exists()).toBe(true)
  })

  it('单一内容主题与讲次同名时不重复展示标题', () => {
    const repeatedTitleLesson = structuredClone(lesson)
    repeatedTitleLesson.sections[0]!.title = '1.1 爬虫概述与HTTP基础'
    const wrapper = mount(TeacherLessonPlanDocument, {
      props: { courseId: 'course-1', lesson: repeatedTitleLesson, confirmed: true },
    })

    expect(wrapper.get('.document-title h3').text()).toBe('第1讲 爬虫概述与HTTP基础')
    expect(wrapper.find('.lesson-theme-heading').exists()).toBe(false)
    expect(wrapper.get('.objective-section').text()).toContain('教学目标')
  })

  it('正式教案的结构化字段统一渲染公式，编辑态保留 LaTeX 源码', async () => {
    const formulaLesson = structuredClone(lesson)
    const section = formulaLesson.plan.current_revision!.plan.sections[0]!
    section.learning_objective = String.raw`能计算 $\nabla^2(x^2y+z)$`
    section.teaching_modules![0]!.teacher_activity = String.raw`板书 $\varphi(0)=1$ 并说明边界条件`

    const wrapper = mount(TeacherLessonPlanDocument, {
      props: { courseId: 'course-1', lesson: formulaLesson },
    })

    expect(wrapper.findAll('.katex').length).toBeGreaterThanOrEqual(2)
    expect(wrapper.text()).not.toContain('\\nabla')
    expect(wrapper.text()).not.toContain('\\varphi')

    ;(wrapper.vm as any).beginEditing()
    await flushPromises()
    expect((wrapper.get('.objective-section textarea').element as HTMLTextAreaElement).value)
      .toContain(String.raw`\nabla^2`)
  })

  it('编辑多个字段时可以统一撤销和重做', async () => {
    const wrapper = mount(TeacherLessonPlanDocument, {
      props: { courseId: 'course-1', lesson },
    })
    ;(wrapper.vm as any).beginEditing()
    await flushPromises()

    const objective = wrapper.get('.objective-section textarea')
    await objective.setValue('第一次修改')
    await flushPromises()
    expect((wrapper.vm as any).canUndo).toBe(true)

    ;(wrapper.vm as any).undoEdit()
    await flushPromises()
    expect((wrapper.get('.objective-section textarea').element as HTMLTextAreaElement).value)
      .toBe('能解释爬虫的四步工作流程')

    ;(wrapper.vm as any).redoEdit()
    await flushPromises()
    expect((wrapper.get('.objective-section textarea').element as HTMLTextAreaElement).value)
      .toBe('第一次修改')
  })

  it('AI 候选在同一份教案中预览并采用', async () => {
    const store = useTeacherLessonAuthoringStore()
    const candidatePlan = JSON.parse(JSON.stringify(lesson.plan.current_revision!.plan))
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
    const resolveCandidate = vi.spyOn(store, 'resolveAiCandidate').mockResolvedValue(lesson)
    const wrapper = mount(TeacherLessonPlanDocument, {
      props: { courseId: 'course-1', lesson },
    })

    await flushPromises()
    await wrapper.findAll('.document-actions button').find(button => button.text().includes('AI 修改'))!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.text-selection-ai__composer').exists()).toBe(true)

    await (wrapper.vm as unknown as {
      requestAiCandidate: (instruction: string) => Promise<unknown>
      resolveAiCandidate: (accept: boolean) => Promise<boolean>
    }).requestAiCandidate('增加可观察目标')
    await flushPromises()

    expect(wrapper.text()).toContain('AI 候选已嵌入教案正文')
    expect(wrapper.text()).toContain('AI 优化后的可观察目标')
    expect(wrapper.get('[data-ai-field="knowledge_objectives"]').classes()).toContain('ai-change-target')
    await (wrapper.vm as unknown as { resolveAiCandidate: (accept: boolean) => Promise<boolean> }).resolveAiCandidate(true)
    await flushPromises()

    expect(resolveCandidate).toHaveBeenCalledWith('course-1', 'lesson-1', 'candidate-1', true)
    expect(wrapper.text()).not.toContain('AI 方案')
  })

  it('讲内主题目录只负责定位，教案始终连续展示全部主题', async () => {
    const multiSectionLesson = structuredClone(lesson)
    multiSectionLesson.sections.push({ section_node_id: 'section-2', title: '1.2 请求与响应' })
    multiSectionLesson.plan.current_revision!.plan.sections.push({
      node_id: 'section-2',
      learning_objective: '能判断一次请求与响应的边界',
      key_points: ['请求', '响应'],
      key_difficulties: [],
      in_class_checks: [],
      homework: [],
      teaching_notes: [],
      teaching_modules: [],
    })
    const wrapper = mount(TeacherLessonPlanDocument, {
      props: { courseId: 'course-1', lesson: multiSectionLesson, activeSectionId: 'section-2' },
    })

    expect(wrapper.find('.section-tabs').exists()).toBe(false)
    expect(wrapper.findAll('.lesson-theme')).toHaveLength(2)
    expect(wrapper.findAll('.lesson-theme-heading h4').map(node => node.text())).toEqual([
      '1.1 爬虫的定义、原理与应用场景',
      '1.2 请求与响应',
    ])
    expect(wrapper.get('.lesson-theme.active .objective-section').text()).toContain('能判断一次请求与响应的边界')

    await wrapper.setProps({ activeSectionId: 'section-1' })
    expect(wrapper.get('.lesson-theme.active .lesson-theme-heading h4').text()).toBe('1.1 爬虫的定义、原理与应用场景')
    expect(wrapper.findAll('.lesson-theme')).toHaveLength(2)
  })

  it('已有教案时不再在正文后重复生成依据，必要生成操作留在正文上方', () => {
    const workbenchSource = readFileSync(resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'), 'utf8')
    expect(workbenchSource).toContain("(!workingLessonRevision || lessonGenerationActive)")
    expect(workbenchSource.match(/<TeacherLessonArrangementSummary/g)).toHaveLength(1)
    expect(workbenchSource).not.toContain('lesson-arrangement-supporting')
    expect(workbenchSource).not.toContain(' supporting')
    expect(workbenchSource).not.toContain('data-testid="lesson-single-start"')
    expect(workbenchSource).not.toContain('data-testid="script-single-start"')
    expect(workbenchSource.indexOf('data-testid="lesson-batch-start"')).toBeLessThan(workbenchSource.indexOf('<TeacherLessonPlanDocument'))
    expect(workbenchSource).toContain(':lesson-types="outlineLessonTypeControls"')
    expect(workbenchSource).toContain('@lesson-type-change="updateOutlineLessonType"')
    expect(workbenchSource).not.toContain('class="outline-lesson-type-plan"')
    expect(workbenchSource).not.toContain('show-history')
    expect(workbenchSource).not.toContain("@history=\"toggleDocumentHistory('lesson')\"")
    expect(workbenchSource).not.toContain("historyOpen && historyDomain === 'lesson'")
    expect(workbenchSource).not.toContain(':selection-ai-enabled="false"')
    expect(workbenchSource).toContain('@open-ai-selection="openAiFromSelection(\'lesson\', $event)"')
    expect(workbenchSource).not.toContain('class="lesson-command-context"')
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
  it('无修改不写新版本，保存失败保留草稿并返回失败', async () => {
    const store = useTeacherLessonAuthoringStore()
    const save = vi.spyOn(store, 'saveDraft').mockRejectedValue(new Error('保存失败'))
    const wrapper = mount(TeacherLessonPlanDocument, { props: { courseId: 'course-1', lesson: structuredClone(lesson) } })
    const editor = wrapper.vm as any
    editor.beginEditing()
    expect(await editor.saveDraft()).toBe(true)
    expect(save).not.toHaveBeenCalled()
    editor.beginEditing()
    await flushPromises()
    await wrapper.findAll('textarea')[0]!.setValue('老师输入的新内容')
    expect(await editor.saveDraft()).toBe(false)
    expect(editor.editing).toBe(true)
    expect((wrapper.findAll('textarea')[0]!.element as HTMLTextAreaElement).value).toBe('老师输入的新内容')
    save.mockResolvedValue({} as any)
    expect(await editor.saveDraft()).toBe(true)
    expect(editor.editing).toBe(false)
    expect(JSON.stringify(save.mock.calls.at(-1))).toContain('老师输入的新内容')
    wrapper.unmount()
  })

})
