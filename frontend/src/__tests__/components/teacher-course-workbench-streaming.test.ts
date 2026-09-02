import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherCourseWorkbench from '@/components/TeacherCourseWorkbench.vue'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'
import { lessonPlanStreamSegments, useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'
import http from '@/utils/http'

const growth = {
  schema_version: 'course_outline_growth_v1',
  state: 'growing',
  active_chapter_number: 2,
  completed_batches: 1,
  total_batches: 3,
  completed_sections: 2,
  total_sections: 6,
  chapters: [
    {
      chapter_number: 1,
      title: '程序环境与基础语法',
      learning_focus: '建立可运行的程序心智模型',
      section_count: 2,
      completed_section_count: 2,
      status: 'completed',
      sections: [
        { node_id: 'L2-1-1', section_number: '1.1', title: 'Hello World 与编译过程', learning_objective: '能解释源码如何变成可执行程序' },
        { node_id: 'L2-1-2', section_number: '1.2', title: '变量与基本数据类型', learning_objective: '能选择合适数据类型' },
      ],
    },
    {
      chapter_number: 2,
      title: '流程控制结构',
      learning_focus: '用条件和循环表达算法',
      section_count: 2,
      completed_section_count: 0,
      status: 'growing',
      sections: [],
    },
  ],
}

const outlineFinishEditing = vi.fn(async () => true)

const mountWorkbench = (props: Record<string, unknown> = {}) => mount(TeacherCourseWorkbench, {
  props: {
    courseId: 'course-1',
    courseTitle: 'C 语言程序设计',
    generationOptions: {} as any,
    ...props,
  },
  global: {
    stubs: {
      CourseReferenceTray: {
        name: 'CourseReferenceTray',
        props: ['modelValue', 'scopeTargetId', 'scopeTargetLabel', 'previousScopeTargetId', 'workflowState', 'workflowDetail', 'workflowCanRetry'],
        template: '<aside data-testid="reference-tray-stub"><span>{{ workflowDetail }}</span><button data-testid="open-course-information" type="button" @click="$emit(\'open-course-information\')">课程信息</button><button v-if="workflowCanRetry" data-testid="retry-workflow" type="button" @click="$emit(\'retry-workflow\')">重试生成</button><slot name="workflow-action" /></aside>',
        emits: ['open-course-information', 'retry-workflow', 'update:modelValue'],
      },
      CompanionDocumentStudio: true,
      QuestionBankReviewPanel: true,
      TeacherScriptDocument: {
        name: 'TeacherScriptDocument',
        template: '<section data-testid="script-document-stub"><slot name="toolbar" /></section>',
        emits: ['confirm'],
      },
      MarkdownRenderer: true,
      CourseOutlineReview: {
        props: ['editable', 'variant', 'requiresConfirmation'],
        template: '<section data-testid="inline-outline-editor" :data-mode="editable ? \'edit\' : \'view\'" :data-variant="variant"><button type="button" @click="$emit(\'confirmed\')">确认</button></section>',
        emits: ['confirmed'],
        setup(_props: unknown, { expose }: any) {
          expose({
            finishEditing: outlineFinishEditing,
            confirmOutline: vi.fn(async () => true),
            requestAiCandidate: vi.fn(async () => null),
            resolveAiCandidate: vi.fn(async () => true),
            focusAiCandidate: vi.fn(async () => undefined),
          })
          return {}
        },
      },
    },
  },
})

describe('teacher course workbench outline streaming', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    outlineFinishEditing.mockReset()
    outlineFinishEditing.mockResolvedValue(true)
    vi.spyOn(http, 'get').mockResolvedValue({ data: { total: 0 } })
    vi.spyOn(http, 'post').mockResolvedValue({ data: { status: 'resumed' } })
  })

  it('侧栏只保留标题和导航名称，不再展示描述文本', () => {
    const wrapper = mountWorkbench()

    expect(wrapper.get('.stage-rail-title').text()).toBe('课程工作台')
    expect(wrapper.find('.stage-rail > header small').exists()).toBe(false)
    expect(wrapper.find('.stage-rail nav small').exists()).toBe(false)
    expect(wrapper.find('.companion-entry button small').exists()).toBe(false)
    expect(wrapper.findAll('.companion-entry button').map(button => button.text())).toEqual(['题库', '评分细则', '考试课程材料自查清单'])
  })

  it('把课程信息入口事件交给课程工作区打开弹窗', async () => {
    const wrapper = mountWorkbench()

    await wrapper.get('[data-testid="open-course-information"]').trigger('click')

    expect(wrapper.emitted('open-course-information')).toHaveLength(1)
  })

  it('能从尚未闭合的 JSON 增量中提前显示教案正文', () => {
    expect(lessonPlanStreamSegments({
      'TP-B01': '{"sections":[{"learning_objective":"学生能够解释爬虫的工作流程',
    })).toContain('学生能够解释爬虫的工作流程')
  })

  it('用后端大纲检查点持续吐出已形成的章节文字', () => {
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'running'
    task.currentStep = '正在展开各章小节'
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: growth }

    const wrapper = mountWorkbench()

    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).toContain('Hello World 与编译过程')
    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).toContain('流程控制结构')
    expect(wrapper.find('.stream-waiting').exists()).toBe(false)
    expect(wrapper.get('.generation-surface>header').text()).toContain('正在展开各章小节')
  })

  it('教师课程生成过程只显示讲次，不暴露内部 1.1 编号', () => {
    const lectureGrowth = {
      ...growth,
      authoring_structure_version: 'lecture_v1',
      completed_sections: 1,
      total_sections: 2,
      chapters: [
        {
          chapter_number: 1,
          title: '第1章 静电场与边值问题',
          learning_focus: '建立静电场边值问题的分析方法',
          section_count: 1,
          completed_section_count: 1,
          status: 'completed',
          sections: [
            { node_id: 'L2-1-1', section_number: '1.1', title: '1.1 静电场基本方程', learning_objective: '能建立典型边值问题' },
          ],
        },
        {
          chapter_number: 2,
          title: '第2章 稳恒磁场',
          learning_focus: '分析稳恒电流产生的磁场',
          section_count: 1,
          completed_section_count: 0,
          status: 'growing',
          sections: [],
        },
      ],
    }
    const task = useGenerationStore().createTask('job-lecture', 'course-1', '电动力学')
    task.status = 'running'
    task.currentStep = '正在生成全课讲次大纲'
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: lectureGrowth }

    const wrapper = mountWorkbench({ courseTitle: '电动力学' })
    const stream = wrapper.get('[data-testid="outline-growth-stream"]')

    expect(stream.attributes('data-structure')).toBe('lecture')
    expect(stream.text()).toContain('第1讲 静电场与边值问题')
    expect(stream.text()).toContain('第2讲 稳恒磁场')
    expect(stream.text()).not.toContain('第1章')
    expect(stream.text()).not.toContain('1.1')
    expect(stream.text()).not.toContain('小节')
  })

  it('大纲失败后的重试沿用原任务检查点，不新建重复课程', async () => {
    const generation = useGenerationStore()
    const task = generation.createTask('job-failed', 'course-1', 'C 语言程序设计')
    task.status = 'error'
    task.error = 'AI provider unavailable: authentication_failed'
    const resume = vi.spyOn(generation, 'resumeTask').mockResolvedValue(undefined)

    const wrapper = mountWorkbench()
    await wrapper.get('.workbench-error button').trigger('click')
    await flushPromises()

    expect(resume).toHaveBeenCalledWith('course-1', 'job-failed')
    expect(wrapper.emitted('generateOutline')).toBeUndefined()
  })

  it('大纲进入待确认后先展示正式文档，由老师主动进入编辑', async () => {
    useCourseStore().nodes = [
      {
        node_id: 'L1-1', parent_node_id: 'root', node_name: '第1章 程序环境与基础语法', node_level: 1,
        node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
      },
      {
        node_id: 'L2-1-1', parent_node_id: 'L1-1', node_name: '1.1 Hello World 与编译过程', node_level: 2,
        node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
      },
    ] as any
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'waiting_for_review'
    task.progress = 35
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: { ...growth, state: 'completed' } }

    const wrapper = mountWorkbench()

    expect(wrapper.find('.generation-surface').exists()).toBe(false)
    expect(wrapper.get('[data-testid="outline-workspace"]').text()).not.toContain('课程大纲已生成')
    expect(wrapper.get('[data-testid="outline-workspace"]').text()).not.toContain('已保存完整章节结构')
    expect(wrapper.get('[data-testid="inline-outline-editor"]').attributes('data-mode')).toBe('view')
    expect(wrapper.get('.center-heading h2').text()).toBe('大纲')
    expect(wrapper.find('[data-testid="outline-ai-action"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="outline-manual-action"]').text()).toContain('编辑大纲')
    await wrapper.get('[data-testid="outline-manual-action"]').trigger('click')
    expect(wrapper.emitted('update:outlineEditing')?.[0]).toEqual([true])
  })

  it('正式大纲只保留稳定右栏的 AI 入口', async () => {
    useCourseStore().nodes = [
      {
        node_id: 'L1-1', parent_node_id: 'root', node_name: '第1章 程序环境与基础语法', node_level: 1,
        node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
      },
    ] as any

    const wrapper = mountWorkbench()
    await flushPromises()

    expect(wrapper.find('[data-testid="outline-ai-action"]').exists()).toBe(false)
    const aiAction = wrapper.get('.context-pane-tabs button:first-child')
    expect(aiAction.text()).toContain('AI 助手')
    await aiAction.trigger('click')

    expect(wrapper.get('.teacher-workbench').classes()).not.toContain('is-ai-collaboration')
    expect(wrapper.get('.stage-rail').attributes('style')).toBeUndefined()
    expect(wrapper.find('.ai-workspace-panel').exists()).toBe(true)
  })

  it('离开大纲阶段前保存编辑，保存失败则停留原页', async () => {
    useCourseStore().nodes = [{
      node_id: 'L1-1', parent_node_id: 'root', node_name: '第1章 基础', node_level: 1,
      node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
    }] as any
    outlineFinishEditing.mockResolvedValueOnce(false)
    const wrapper = mountWorkbench()

    await wrapper.get('.stage-rail nav button:nth-child(2)').trigger('click')
    await flushPromises()

    expect(outlineFinishEditing).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.stage-rail nav button.active').text()).toContain('大纲')
  })

  it('最终检查点暂时没有投影时保留审阅状态而不退回初始表单', () => {
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'waiting_for_review'
    task.currentPhase = 'outline_ready'
    task.phaseDetail = {}

    const wrapper = mountWorkbench()

    expect(wrapper.find('[data-testid="outline-workspace"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="inline-outline-editor"]').attributes('data-mode')).toBe('view')
    expect(wrapper.find('form.stage-form').exists()).toBe(false)
  })

  it('任务切换为最终审阅时保留最后一次小章节生成结果', async () => {
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'running'
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: growth }
    const wrapper = mountWorkbench()

    const reactiveTask = useGenerationStore().getTask('course-1')!
    reactiveTask.status = 'waiting_for_review'
    reactiveTask.currentPhase = 'outline_ready'
    reactiveTask.phaseDetail = { artifact_type: 'course_outline_ready' }
    await flushPromises()

    expect(wrapper.get('[data-testid="inline-outline-editor"]').attributes('data-mode')).toBe('view')
    expect(wrapper.find('form.stage-form').exists()).toBe(false)
  })

  it('把大纲编辑器放在工作台中央而不是右侧抽屉', async () => {
    const wrapper = mountWorkbench({ outlineEditing: true })

    expect(wrapper.find('.workbench-center [data-testid="inline-outline-editor"]').exists()).toBe(true)
    expect(wrapper.find('.stage-rail').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(true)
    await wrapper.get('[data-testid="inline-outline-editor"] button').trigger('click')
    expect(wrapper.emitted('outlineConfirmed')).toHaveLength(1)
    expect(wrapper.emitted('update:outlineEditing')).toBeUndefined()
  })

  it('讲数已由老师确认时自动继续同一大纲任务，不再要求章和小节确认', async () => {
    const generation = useGenerationStore()
    const task = generation.createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'waiting_for_review'
    task.currentPhase = 'outline_shape_ready'
    task.phaseDetail = {
      artifact_type: 'course_outline_skeleton',
      skeleton_revision_id: 'skeleton-1',
      outline_growth: { ...growth, state: 'shape_review', completed_sections: 0 },
    }
    generation.generationStatus = 'error'

    const wrapper = mountWorkbench()
    await flushPromises()
    const sectionInputs = wrapper.findAll('.shape-chapter-list input')

    expect(wrapper.find('.generation-surface').exists()).toBe(false)
    expect(wrapper.find('.shape-chapter-index').exists()).toBe(false)
    expect(wrapper.get('[data-testid="outline-shape-review"]').text()).toContain('讲数已经确认')
    expect(wrapper.get('[data-testid="outline-shape-review"]').text()).not.toContain('程序环境与基础语法')
    expect(sectionInputs).toHaveLength(0)

    expect(http.post).toHaveBeenCalledWith(
      '/api/courses/course-1/generation/outline-shape/confirm',
      { chapter_section_counts: expect.any(Array) },
      expect.any(Object),
    )
    const shapePayload = vi.mocked(http.post).mock.calls.find(call => String(call[0]).includes('outline-shape/confirm'))?.[1] as any
    expect(shapePayload.chapter_section_counts.every((count: number) => count === 1)).toBe(true)
  })

  it('生成前只展示业务输入和操作，不展示内部流程解释', async () => {
    const wrapper = mountWorkbench({
      generationOptions: {
        course_type: 'systematic',
        composition_style: 'balanced',
        course_purpose: 'systematic',
      } as any,
    })

    expect(wrapper.get('.foundation-semantics').text()).toContain('教学编排')
    expect(wrapper.get('.foundation-semantics').text()).toContain('学习目的')
    expect(wrapper.get('.foundation-semantics').text()).toContain('学科类型')
    expect(wrapper.get('.foundation-semantics').text()).toContain('课程教学类型')
    expect(wrapper.get('.foundation-semantics').text()).toContain('系统学习')
    expect(wrapper.get('.foundation-semantics').text()).toContain('综合课')
    expect(wrapper.find('.chapter-shape-editor').exists()).toBe(false)
    expect(wrapper.find('.course-shape-summary').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('大纲生成顺序')
    expect(wrapper.text()).not.toContain('学时不自动换算小节')
    expect(wrapper.text()).not.toContain('右侧资料会与这些信息一起交给 AI')
    expect(wrapper.get('form.stage-form button.primary').text()).toContain('生成课程大纲')
    await wrapper.get('.form-field input[type="number"]').setValue(12)
    await wrapper.get('form.stage-form').trigger('submit')
    await flushPromises()

    const emitted = wrapper.emitted('generateOutline')?.[0]?.[0] as any
    expect(emitted.options.teacher_course_brief).toEqual(expect.objectContaining({
      total_class_hours: 12,
      additional_requirements: expect.stringContaining('学习目的：系统学习'),
    }))
    expect(emitted.options).toEqual(expect.objectContaining({
      learning_purpose: 'systematic',
      course_teaching_type: 'comprehensive',
      pedagogy_mode: 'auto',
    }))
    expect(emitted.options).not.toHaveProperty('course_type')
    expect(emitted.options).not.toHaveProperty('composition_style')
    expect(emitted.options).not.toHaveProperty('course_purpose')
    expect(emitted.options.requirements).toContain('学科类型：自动判断')
    expect(emitted.options.requirements).toContain('课程教学类型：综合课')
    expect(emitted.options.teacher_course_brief).not.toHaveProperty('chapter_count')
    expect(emitted.options.teacher_course_brief).not.toHaveProperty('section_count')
  })

  it('项目实战与项目课分别写入学习目的和课程教学类型', async () => {
    const wrapper = mountWorkbench()
    const projectPurpose = wrapper.findAll('.foundation-semantic-options button').find(button => button.text().includes('项目实战'))
    expect(projectPurpose).toBeTruthy()
    await projectPurpose!.trigger('click')
    await wrapper.get('.foundation-purpose-fields input').setValue('可运行原型与设计说明')
    await wrapper.get('form.stage-form').trigger('submit')
    await flushPromises()

    const emitted = wrapper.emitted('generateOutline')?.[0]?.[0] as any
    expect(emitted.options).not.toHaveProperty('course_type')
    expect(emitted.options.learning_purpose).toBe('project')
    expect(emitted.options.course_teaching_type).toBe('project')
    expect(emitted.options.course_intent).toEqual(expect.objectContaining({
      type: 'project',
      expected_deliverable: '可运行原型与设计说明',
    }))
  })

  it('大纲已生成待确认时阻断教案生成并恢复原有确认入口', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }] as any
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'waiting_for_review'
    task.currentPhase = 'outline_ready'

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.find('.lesson-selector').exists()).toBe(false)
    expect(wrapper.get('.prerequisite').text()).toContain('课程大纲已生成，等待确认')
    expect(wrapper.get('.prerequisite button').text()).toBe('查看并确认大纲')
    await wrapper.get('.prerequisite button').trigger('click')

    expect(wrapper.emitted('update:outlineEditing')).toBeUndefined()
    expect(wrapper.get('.center-heading h2').text()).toBe('大纲')
  })

  it('课次投影读取失败时显示真实错误并复用现有重载动作', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.courseId = 'course-1'
    lessonStore.error = '分讲教案状态读取失败'
    const reload = vi.spyOn(lessonStore, 'load').mockResolvedValue({} as any)

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    const notice = wrapper.get('.prerequisite-error')
    expect(notice.text()).toContain('课次读取失败')
    expect(notice.text()).toContain('分讲教案状态读取失败')
    expect(notice.get('details code').text()).toContain('原始反馈')
    await notice.get('button').trigger('click')
    expect(reload).toHaveBeenCalledWith('course-1')
  })

  it('把唯一的整课生成入口放在右侧资料栏，中栏保持空白', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45,
      sections: [{ section_node_id: 'L2-1-1', title: '1.1 基础概念' }],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: '', lesson_unit_id: 'L1-1',
        source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授',
        status: 'suggested', confirmed: false, source_state: 'current',
        blocks: [{
          block_id: 'block-1', module_id: 'core_explanation', section_node_id: 'L2-1-1',
          section_title: '1.1 基础概念', name: '概念讲解', role: 'concept', purpose: '建立概念',
          content_summary: '用正反例讲清概念边界', planned_minutes: 45,
          teacher_activity: '', student_activity: '', expected_output: '', required: true,
        }],
      },
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }] as any
    const generateAllLessons = vi.spyOn(lessonStore, 'generateAllLessons').mockResolvedValue({
      parent_job: { id: 'batch-1' }, jobs: [],
    } as any)

    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    const generationButton = wrapper.get('[data-testid="lesson-batch-start"]')
    expect(wrapper.find('[data-testid="lesson-arrangement-editor"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="lesson-generation-form"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="lesson-arrangement-summary"]').exists()).toBe(false)
    expect(wrapper.get('.lesson-empty-canvas').text()).toBe('教案尚未生成')
    expect(wrapper.get('[data-testid="lesson-batch-launch"]').text()).toContain('剩余 1 讲，将按顺序逐讲生成')
    expect(generationButton.text()).toBe('生成全部教案')
    expect(wrapper.text()).not.toContain('生成本讲教案')
    expect(wrapper.text()).not.toContain('统一生成要求')
    expect(wrapper.find('.lesson-batch-panel').exists()).toBe(false)

    await generationButton.trigger('click')
    await flushPromises()

    expect(generateAllLessons).toHaveBeenCalledWith('course-1', undefined, '', [])
  })

  it('确认本讲课型后可以只生成当前讲，不启动整课任务', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45,
      sections: [{ section_node_id: 'L2-1-1', title: '变化率' }],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'arrangement-1', lesson_unit_id: 'L1-1',
        source_outline_revision_id: 'outline-1', lesson_type: 'theory_practice', lesson_type_label: '讲练结合',
        lesson_type_recommendation_reason: '需要把概念讲解和即时练习连续组织起来。',
        status: 'confirmed', confirmed: true, source_state: 'current',
        blocks: [{
          block_id: 'block-1', module_id: 'core_explanation', section_node_id: 'L2-1-1',
          section_title: '变化率', name: '建立概念', role: 'concept', purpose: '建立变化率概念',
          content_summary: '从平均变化率进入瞬时变化率', planned_minutes: 45,
          teacher_activity: '示范', student_activity: '解释', expected_output: '概念图', required: true,
        }],
      },
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }] as any
    const generateLesson = vi.spyOn(lessonStore, 'generateLesson').mockResolvedValue({ id: 'lesson-job-1' } as any)
    const generateAllLessons = vi.spyOn(lessonStore, 'generateAllLessons')

    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    const singleButton = wrapper.findAll('.arrangement-actions button').find(button => button.text().includes('只生成本讲'))
    expect(singleButton).toBeTruthy()
    await singleButton!.trigger('click')
    await flushPromises()

    expect(generateLesson).toHaveBeenCalledWith('course-1', 'L1-1', undefined, '', [], '')
    expect(generateAllLessons).not.toHaveBeenCalled()
  })

  it('默认先定位最近失败讲次，其次定位受影响讲次', () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2, 3].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45, sections: [],
      script: { current_revision_id: 'script-1', confirmed_revision_id: 'script-1', source_lesson_plan_revision_id: 'plan-1', source_state: number === 2 ? 'stale' : 'current', ready: true, confirmed: true, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: number === 2 ? 'stale' : 'current', revisions: [], ppt_assets: [{ source_state: 'current', ppt_manuscript_status: 'confirmed' }] },
    })) as any
    lessonStore.jobs = [{
      id: 'failed-job', course_id: 'course-1', lesson_unit_id: 'L1-3', type: 'teacher_lesson_plan_generation',
      status: 'failed', progress: 30, phase: 'lesson_plan_failed', message: '生成失败', warnings: [], updated_at: '2026-09-02T09:00:00Z',
    }] as any

    const failedFirst = mountWorkbench({ initialStage: 'lesson' })
    expect(failedFirst.get('.lesson-title-trigger').text()).toContain('第3讲')
    failedFirst.unmount()

    lessonStore.jobs = []
    const affectedNext = mountWorkbench({ initialStage: 'lesson' })
    expect(affectedNext.get('.lesson-title-trigger').text()).toContain('第2讲')
  })

  it('讲次目录只使用六类可行动状态', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2, 3, 4, 5, 6].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45, sections: [],
      plan: {
        lesson_unit_id: `L1-${number}`,
        working_revision_id: [3, 4, 5].includes(number) ? `plan-${number}` : '',
        confirmed_revision_id: [4, 5].includes(number) ? `plan-${number}` : '',
        source_state: number === 5 ? 'stale' : 'current', revisions: [], ppt_assets: [],
      },
    })) as any
    lessonStore.jobs = [{
      id: 'running-job', course_id: 'course-1', lesson_unit_id: 'L1-2', type: 'teacher_lesson_plan_generation',
      status: 'running', progress: 40, phase: 'lesson_plan_generation', message: '正在生成', warnings: [],
    }, {
      id: 'failed-job', course_id: 'course-1', lesson_unit_id: 'L1-6', type: 'teacher_lesson_plan_generation',
      status: 'failed', progress: 40, phase: 'lesson_plan_failed', message: '生成失败', warnings: [],
    }] as any

    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    await wrapper.get('.lesson-title-trigger').trigger('click')
    const labels = wrapper.findAll('.lesson-outline-chapter-button').map(button => button.attributes('aria-label'))
    expect(labels).toEqual([
      '第1讲，未生成', '第2讲，生成中', '第3讲，待确认',
      '第4讲，已确认', '第5讲，需复核', '第6讲，失败',
    ])
  })

  it('教案任务开始后原位显示真实进度并隐藏重复提交按钮', () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }] as any
    lessonStore.jobs = [{
      id: 'lesson-job-1', course_id: 'course-1', lesson_unit_id: 'L1-1', type: 'teacher_lesson_plan_generation',
      status: 'running', progress: 36, phase: 'course_teaching_plan_skeleton', message: '正在确定各节教学重点', warnings: [],
      stream_batches: {
        'TP-B01': '{"sections":[{"learning_objective":"学生能够解释爬虫的工作流程',
      },
    }] as any

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.get('.lesson-generation-status').text()).toContain('正在生成第一讲')
    expect(wrapper.get('.lesson-generation-status').text()).toContain('正在确定各节教学重点')
    expect(wrapper.get('.lesson-stream-document').text()).toContain('AI 工作稿')
    expect(wrapper.get('.lesson-stream-document').text()).toContain('学生能够解释爬虫的工作流程')
    expect(wrapper.find('.lesson-stream-document .stream-caret').exists()).toBe(true)
    expect(wrapper.find('button[type="submit"]').exists()).toBe(false)
  })

  it('批量任务只让当前讲显示生成中，其余讲次显示等待队列', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, source_outline_revision_id: 'outline-1', number,
      title: `第${number}讲`, duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    })) as any
    lessonStore.jobs = [
      {
        id: 'lesson-job-1', course_id: 'course-1', lesson_unit_id: 'L1-1', type: 'teacher_lesson_plan_generation',
        status: 'running', progress: 42, phase: 'lesson_plan_generation', message: '正在生成第一讲', warnings: [],
        parent_job_id: 'batch-1', batch_position: 1, batch_size: 2,
      },
      {
        id: 'lesson-job-2', course_id: 'course-1', lesson_unit_id: 'L1-2', type: 'teacher_lesson_plan_generation',
        status: 'pending', progress: 0, phase: 'waiting_for_previous_lesson', message: '等待上一讲生成完成', warnings: [],
        parent_job_id: 'batch-1', batch_position: 2, batch_size: 2,
      },
    ] as any

    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    await wrapper.get('.lesson-title-trigger').trigger('click')
    const chapterButtons = wrapper.findAll('.lesson-outline-chapter-button')
    expect(chapterButtons[0]!.attributes('aria-label')).toContain('生成中')
    expect(chapterButtons[1]!.attributes('aria-label')).toContain('生成中')
    expect(wrapper.findAll('.lesson-outline-status .spin')).toHaveLength(1)

    await chapterButtons[1]!.trigger('click')
    expect(wrapper.get('.lesson-queue-state').text()).toContain('等待按顺序生成')
    expect(wrapper.get('.lesson-queue-state').text()).toContain('不需要再次操作')
    expect(wrapper.find('.lesson-queue-state button').exists()).toBe(false)
  })

  it('教案任务失败后只在右侧显示真实原因和整课重试动作', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }] as any
    lessonStore.jobs = [{
      id: 'lesson-job-1', course_id: 'course-1', lesson_unit_id: 'L1-1', type: 'teacher_lesson_plan_generation',
      status: 'failed', progress: 36, phase: 'lesson_plan_failed', message: '本讲教案生成失败', warnings: [],
      error: { code: 'lesson_plan_generation_failed', message: '知识骨架汇编失败', retryable: true },
    }] as any
    const generateAllLessons = vi.spyOn(lessonStore, 'generateAllLessons').mockResolvedValue({
      parent_job: { id: 'batch-2' }, jobs: [],
    } as any)

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.get('[data-testid="reference-tray-stub"]').text()).toContain('知识骨架汇编失败')
    expect(wrapper.get('[data-testid="retry-workflow"]').text()).toBe('重试生成')
    expect(wrapper.get('.lesson-empty-canvas').text()).toBe('教案尚未生成')
    await wrapper.get('[data-testid="retry-workflow"]').trigger('click')
    await flushPromises()
    expect(generateAllLessons).toHaveBeenCalledWith('course-1', undefined, '', [])
    expect(wrapper.text()).not.toContain('重新生成本讲教案')
  })

  it('教案未确认时仍可上传自有 PPT，但不能使用 AI 生成', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [{ section_node_id: 'L2-1-1', title: '1.1 程序运行过程' }],
      plan: {
        lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: '', source_state: 'current', ppt_assets: [],
        revisions: [{ revision_id: 'plan-1', lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', generation_source: 'model', status: 'draft', warnings: [], plan: { sections: [{ node_id: 'L2-1-1', key_points: ['编译', '运行'], teaching_modules: [{ module_id: 'core_explanation', planned_minutes: 15, teacher_activity: '演示源码如何编译运行', student_activity: '跟随完成首次运行' }] }] }, actor: 'teacher', created_at: '' }],
      },
    }] as any
    const confirm = vi.spyOn(lessonStore, 'confirm').mockResolvedValue({} as any)
    const lessonWrapper = mountWorkbench({ initialStage: 'lesson' })

    await lessonWrapper.get('.lesson-title-trigger').trigger('click')
    expect(lessonWrapper.get('.lesson-outline-chapter-button').attributes('aria-label')).toContain('待确认')
    expect(lessonWrapper.text()).toContain('1.1 程序运行过程')
    expect(lessonWrapper.text()).toContain('演示源码如何编译运行')
    expect(lessonWrapper.find('.lesson-toolbar-status').exists()).toBe(false)
    expect(lessonWrapper.get('.teacher-document-command-bar__status').text()).toContain('待确认')
    expect(lessonWrapper.get('.lesson-document-toolbar .primary-action').text()).toContain('确认本讲教案')
    await lessonWrapper.get('.lesson-document-toolbar .primary-action').trigger('click')
    expect(confirm).toHaveBeenCalledWith('course-1', 'L1-1', 'plan-1')
    expect(lessonWrapper.find('.lesson-section-tabs').exists()).toBe(false)

    const pptWrapper = mountWorkbench({ initialStage: 'ppt' })
    await flushPromises()
    expect(pptWrapper.get('.lesson-navigator').text()).toContain('第一讲')
    expect(pptWrapper.get('.lesson-toolbar-status').text()).toContain('待生成')
    expect(pptWrapper.get('.ppt-upload-secondary').attributes('disabled')).toBeUndefined()
    expect(pptWrapper.get('.ppt-generate-primary').attributes('disabled')).toBeDefined()
  })

  it('讲义确认成功后停留当前阶段，由左侧四步流程负责切换', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45,
      sections: [{ section_node_id: 'L2-1-1', title: '1.1 程序运行过程' }],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'arrangement-1', lesson_unit_id: 'L1-1',
        source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授',
        status: 'confirmed', confirmed: true, source_state: 'current', blocks: [],
      },
      script: {
        current_revision_id: 'script-1', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1',
        source_state: 'current', ready: true, confirmed: false, confirmed_at: '',
        sections: [{ section_node_id: 'L2-1-1', title: '1.1 程序运行过程', content: '讲稿正文' }],
      },
      plan: {
        lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: 'current', ppt_assets: [],
        revisions: [{ revision_id: 'plan-1', lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', generation_source: 'model', status: 'confirmed', warnings: [], plan: {}, actor: 'teacher', created_at: '' }],
      },
    }] as any
    const confirmScript = vi.spyOn(lessonStore, 'confirmScript').mockResolvedValue({} as any)
    const wrapper = mountWorkbench({ initialStage: 'script' })

    expect(wrapper.find('.center-heading').exists()).toBe(false)
    expect(wrapper.get('.lesson-title-trigger').text()).toContain('第一讲')
    expect(wrapper.get('.lesson-toolbar-status').text()).toContain('待确认')
    expect(wrapper.find('.lesson-toolbar-status button').exists()).toBe(false)
    expect(wrapper.get('.lesson-document-toolbar .primary-action').text()).toContain('确认本讲讲义')
    await wrapper.get('.lesson-document-toolbar .primary-action').trigger('click')
    await flushPromises()

    expect(confirmScript).toHaveBeenCalledWith('course-1', 'L1-1', 'script-1')
    expect(wrapper.get('.stage-rail button.active').text()).toContain('讲义')
  })

  it('旧质量规则阻断讲义确认时提供重新生成入口', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45,
      sections: [{ section_node_id: 'L2-1-1', title: '1.1 程序运行过程' }],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'arrangement-1', lesson_unit_id: 'L1-1',
        source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授',
        status: 'confirmed', confirmed: true, source_state: 'current', blocks: [],
      },
      script: {
        current_revision_id: 'script-old', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1',
        source_state: 'current', ready: true, confirmed: false, confirmed_at: '', publication_eligible: false,
        quality_report: { blocking_issues: [{ code: 'quality_contract_stale', message: '旧质量规则' }] },
        sections: [{ section_node_id: 'L2-1-1', title: '1.1 程序运行过程', content: '旧讲稿正文' }],
      },
      plan: {
        lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: 'current', ppt_assets: [],
        revisions: [{ revision_id: 'plan-1', lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', generation_source: 'model', status: 'confirmed', warnings: [], plan: {}, actor: 'teacher', created_at: '' }],
      },
    }] as any

    const generateScript = vi.spyOn(lessonStore, 'generateScript').mockResolvedValue({ id: 'script-job-new' } as any)
    const wrapper = mountWorkbench({ initialStage: 'script' })

    expect(wrapper.get('.lesson-document-toolbar .primary-action').text()).toContain('重新生成本讲讲义')
    expect(wrapper.get('.lesson-document-toolbar .primary-action').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('.lesson-document-toolbar .primary-action').attributes('title')).toContain('旧质量规则')
    await wrapper.get('.lesson-document-toolbar .primary-action').trigger('click')
    await flushPromises()
    expect(generateScript).toHaveBeenCalledWith('course-1', 'L1-1', '', [], '')
  })

  it('讲次目录以浮层按需展开，教案正文不再出现小节 Tab', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45,
      sections: [1, 2].map(section => ({ section_node_id: `L2-${number}-${section}`, title: `${number}.${section} 小节${section}` })),
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: number === 1 ? 'plan-1' : '', confirmed_revision_id: number === 2 ? 'plan-2' : '', source_state: 'current', revisions: [], ppt_assets: [] },
    })) as any
    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.get('.lesson-title-trigger').text()).toContain('第1讲')
    expect(wrapper.get('.lesson-title-trigger').text()).toContain('1/2')
    expect(wrapper.get('.lesson-title-trigger').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.lesson-outline-popover').exists()).toBe(false)
    const currentLessonGroup = wrapper.get('.lesson-current-group')
    expect(currentLessonGroup.element.children[0]?.classList.contains('lesson-outline-control')).toBe(true)
    expect(currentLessonGroup.element.children).toHaveLength(1)
    expect(wrapper.get('.lesson-heading-cluster').element.firstElementChild).toBe(currentLessonGroup.element)
    expect(wrapper.find('.lesson-selector').exists()).toBe(false)
    expect(wrapper.find('.lesson-section-tabs').exists()).toBe(false)
    expect(wrapper.get('.lesson-navigator').text()).toContain('上一讲')
    expect(wrapper.get('.lesson-navigator').text()).toContain('下一讲')

    await wrapper.get('.lesson-title-trigger').trigger('click')
    expect(wrapper.get('.lesson-title-trigger').attributes('aria-expanded')).toBe('true')
    const chapterButtons = wrapper.findAll('.lesson-outline-chapter-button')
    expect(chapterButtons).toHaveLength(2)
    expect(chapterButtons[0]!.text()).toBe('第1讲')
    expect(chapterButtons[0]!.attributes('aria-label')).toContain('待确认')
    expect(chapterButtons[1]!.attributes('aria-label')).toContain('已确认')
    expect(wrapper.find('.lesson-outline-sections').exists()).toBe(false)

    await chapterButtons[1]!.trigger('click')
    expect(wrapper.find('.lesson-outline-popover').exists()).toBe(false)
    expect(wrapper.get('.lesson-title-trigger').text()).toContain('第2讲')
    expect(wrapper.get('.lesson-title-trigger').text()).toContain('2/2')
    expect(wrapper.find('.lesson-section-tabs').exists()).toBe(false)

    await wrapper.get('.lesson-title-trigger').trigger('click')
    expect(wrapper.get('.lesson-title-trigger').attributes('aria-expanded')).toBe('true')
  })

  it('右侧资料随当前讲次切换且不会串到其他讲次', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45,
      sections: [{ section_node_id: `L2-${number}-1`, title: `${number}.1 小节` }],
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    })) as any
    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    const firstReference = { package_id: 'package-1', asset_id: 'asset-1', material_asset_id: 'mat-1', filename: '第一讲.docx', relative_path: '', size_bytes: 100, role: 'primary' }
    const secondReference = { package_id: 'package-1', asset_id: 'asset-2', material_asset_id: 'mat-2', filename: '第二讲.pdf', relative_path: '', size_bytes: 100, role: 'reference' }

    let tray = wrapper.findComponent({ name: 'CourseReferenceTray' })
    expect(tray.props('scopeTargetId')).toBe('lesson-plan:L1-1')
    expect(tray.props('scopeTargetLabel')).toBe('第1讲')
    tray.vm.$emit('update:modelValue', [firstReference])
    await flushPromises()

    await wrapper.get('.lesson-title-trigger').trigger('click')
    await wrapper.findAll('.lesson-outline-chapter-button')[1]!.trigger('click')
    tray = wrapper.findComponent({ name: 'CourseReferenceTray' })
    expect(tray.props('scopeTargetId')).toBe('lesson-plan:L1-2')
    expect(tray.props('previousScopeTargetId')).toBe('lesson-plan:L1-1')
    expect(tray.props('modelValue')).toEqual([])
    tray.vm.$emit('update:modelValue', [secondReference])
    await flushPromises()

    await wrapper.get('.lesson-title-trigger').trigger('click')
    await wrapper.findAll('.lesson-outline-chapter-button')[0]!.trigger('click')
    tray = wrapper.findComponent({ name: 'CourseReferenceTray' })
    expect(tray.props('scopeTargetId')).toBe('lesson-plan:L1-1')
    expect(tray.props('modelValue')).toEqual([firstReference])
  })
})
