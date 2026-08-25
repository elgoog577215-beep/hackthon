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

const mountWorkbench = (props: Record<string, unknown> = {}) => mount(TeacherCourseWorkbench, {
  props: {
    courseId: 'course-1',
    courseTitle: 'C 语言程序设计',
    generationOptions: {} as any,
    ...props,
  },
  global: {
    stubs: {
      CourseReferenceTray: true,
      CompanionDocumentStudio: true,
      QuestionBankReviewPanel: true,
      TeacherScriptDocument: true,
      MarkdownRenderer: true,
      CourseOutlineReview: {
        props: ['editable', 'variant', 'requiresConfirmation'],
        template: '<section data-testid="inline-outline-editor" :data-mode="editable ? \'edit\' : \'view\'" :data-variant="variant"><button type="button" @click="$emit(\'confirmed\')">确认</button></section>',
        emits: ['confirmed'],
      },
    },
  },
})

describe('teacher course workbench outline streaming', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.spyOn(http, 'get').mockResolvedValue({ data: { total: 0 } })
    vi.spyOn(http, 'post').mockResolvedValue({ data: { status: 'resumed' } })
  })

  it('侧栏只保留标题和导航名称，不再展示描述文本', () => {
    const wrapper = mountWorkbench()

    expect(wrapper.get('.stage-rail-title').text()).toBe('课程工作台')
    expect(wrapper.find('.stage-rail > header small').exists()).toBe(false)
    expect(wrapper.find('.stage-rail nav small').exists()).toBe(false)
    expect(wrapper.find('.companion-entry button small').exists()).toBe(false)
    expect(wrapper.get('.companion-entry button').text()).toBe('配套文档')
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

  it('大纲进入待确认后保留同一展示区并原地解锁编辑', async () => {
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
    expect(wrapper.get('.center-heading h2').text()).toBe('课程基础')
    expect(wrapper.get('.center-heading>button').text()).toContain('编辑大纲')
    const outlineElement = wrapper.get('[data-testid="inline-outline-editor"]').element
    await wrapper.get('.center-heading>button').trigger('click')
    expect(wrapper.emitted('update:outlineEditing')).toEqual([[true]])

    await wrapper.setProps({ outlineEditing: true })
    expect(wrapper.get('[data-testid="inline-outline-editor"]').element).toBe(outlineElement)
    expect(wrapper.get('[data-testid="inline-outline-editor"]').attributes('data-mode')).toBe('edit')
    expect(wrapper.get('.center-heading h2').text()).toBe('课程基础')
    expect(wrapper.get('.center-heading>button').text()).toContain('完成编辑')
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
    expect(wrapper.emitted('update:outlineEditing')).toContainEqual([false])
  })

  it('先展示真实大章节，再由老师确认每章小节数并继续同一任务', async () => {
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
    const sectionInputs = wrapper.findAll('.shape-chapter-list input')

    expect(wrapper.find('.generation-surface').exists()).toBe(false)
    expect(wrapper.find('.shape-chapter-index').exists()).toBe(false)
    expect(wrapper.get('[data-testid="outline-shape-review"]').text()).toContain('程序环境与基础语法')
    expect(wrapper.get('[data-testid="outline-shape-review"]').text()).toContain('流程控制结构')
    expect(sectionInputs).toHaveLength(2)
    await sectionInputs[0]!.setValue(3)
    await sectionInputs[1]!.setValue(5)
    await wrapper.get('.outline-shape-review>footer button').trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith(
      '/api/courses/course-1/generation/outline-shape/confirm',
      { chapter_section_counts: [3, 5] },
      expect.any(Object),
    )
  })

  it('生成前只展示业务输入和操作，不展示内部流程解释', async () => {
    const wrapper = mountWorkbench()

    expect(wrapper.find('.chapter-shape-editor').exists()).toBe(false)
    expect(wrapper.find('.course-shape-summary').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('大纲生成顺序')
    expect(wrapper.text()).not.toContain('学时不自动换算小节')
    expect(wrapper.text()).not.toContain('右侧资料会与这些信息一起交给 AI')
    expect(wrapper.get('form.stage-form button.primary').text()).toContain('生成大章节')
    await wrapper.get('.form-field input[type="number"]').setValue(12)
    await wrapper.get('form.stage-form').trigger('submit')
    await flushPromises()

    const emitted = wrapper.emitted('generateOutline')?.[0]?.[0] as any
    expect(emitted.options.teacher_course_brief).toEqual(expect.objectContaining({
      total_class_hours: 12,
    }))
    expect(emitted.options.teacher_course_brief).not.toHaveProperty('chapter_count')
    expect(emitted.options.teacher_course_brief).not.toHaveProperty('section_count')
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
    expect(wrapper.get('.center-heading h2').text()).toBe('课程基础')
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

  it('页面不展示教学块编辑器并自动采用本讲编排生成教案', async () => {
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
    const confirmArrangement = vi.spyOn(lessonStore, 'confirmArrangement').mockResolvedValue(lessonStore.lessons[0]!)
    const generateLesson = vi.spyOn(lessonStore, 'generateLesson').mockResolvedValue({ id: 'job-1' } as any)

    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    const generationForm = wrapper.get('[data-testid="lesson-generation-form"]')
    expect(wrapper.find('[data-testid="lesson-arrangement-editor"]').exists()).toBe(false)
    expect(generationForm.get('label').text()).toBe('请补充本讲的重难点、教学方法或课堂活动要求（选填）。')
    expect(generationForm.find('.lesson-generation-copy').exists()).toBe(false)
    expect(generationForm.get('textarea').attributes('placeholder')).toBeUndefined()
    expect(generationForm.get('textarea').attributes('aria-label')).toBe('教案生成要求')

    await generationForm.trigger('submit')
    await flushPromises()

    expect(confirmArrangement).toHaveBeenCalledWith(
      'course-1',
      'L1-1',
      expect.objectContaining({ lesson_type: 'theory', blocks: [expect.objectContaining({ block_id: 'block-1' })] }),
    )
    expect(generateLesson).toHaveBeenCalledWith('course-1', 'L1-1', undefined, '', [])
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
      status: 'running', progress: 36, phase: 'course_teaching_plan_skeleton', message: '正在冻结知识职责', warnings: [],
      stream_batches: {
        'TP-B01': '{"sections":[{"learning_objective":"学生能够解释爬虫的工作流程',
      },
    }] as any

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.get('.lesson-generation-surface').text()).toContain('正在冻结知识职责')
    expect(wrapper.get('.lesson-stream-document').text()).toContain('AI 工作稿')
    expect(wrapper.get('.lesson-stream-document').text()).toContain('学生能够解释爬虫的工作流程')
    expect(wrapper.find('.lesson-stream-document .stream-caret').exists()).toBe(true)
    expect(wrapper.find('button[type="submit"]').exists()).toBe(false)
  })

  it('教案任务失败后显示真实原因并提供单一重试动作', () => {
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

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.get('.lesson-generation-error').text()).toContain('知识骨架汇编失败')
    expect(wrapper.get('button[type="submit"]').text()).toContain('重新生成本讲教案')
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
    expect(lessonWrapper.get('.document-footer button').text()).toContain('确认并进入题库')
    await lessonWrapper.get('.document-footer button').trigger('click')
    expect(confirm).toHaveBeenCalledWith('course-1', 'L1-1', 'plan-1')
    expect(lessonWrapper.get('.center-heading h2').text()).toBe('题库')

    const pptWrapper = mountWorkbench({ initialStage: 'ppt' })
    await flushPromises()
    expect(pptWrapper.get('.ppt-upload-primary').attributes('disabled')).toBeUndefined()
    expect(pptWrapper.get('.ppt-generate-secondary').attributes('disabled')).toBeDefined()
  })

  it('讲稿确认成功后原位进入 PPT，不要求老师再次寻找下一步', async () => {
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

    wrapper.findComponent({ name: 'TeacherScriptDocument' }).vm.$emit('confirm')
    await flushPromises()

    expect(confirmScript).toHaveBeenCalledWith('course-1', 'L1-1', 'script-1')
    expect(wrapper.get('.center-heading h2').text()).toBe('PPT')
  })

  it('大章目录以浮层按需展开，小节在正文顶部横向切换', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}章`, duration_minutes: 45,
      sections: [1, 2].map(section => ({ section_node_id: `L2-${number}-${section}`, title: `${number}.${section} 小节${section}` })),
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: number === 1 ? 'plan-1' : '', confirmed_revision_id: number === 2 ? 'plan-2' : '', source_state: 'current', revisions: [], ppt_assets: [] },
    })) as any
    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.get('.lesson-title-trigger').text()).toContain('第1章')
    expect(wrapper.get('.lesson-title-trigger').text()).toContain('1/2')
    expect(wrapper.get('.lesson-title-trigger').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.lesson-outline-popover').exists()).toBe(false)
    const currentLessonGroup = wrapper.get('.lesson-current-group')
    expect(currentLessonGroup.element.children[0]?.classList.contains('lesson-outline-control')).toBe(true)
    expect(currentLessonGroup.element.children).toHaveLength(1)
    expect(wrapper.find('.lesson-selector').exists()).toBe(false)
    expect(wrapper.findAll('.lesson-section-tabs button')).toHaveLength(2)
    expect(wrapper.get('.lesson-section-tabs button.active').text()).toBe('1.1 小节1')
    expect(wrapper.get('.lesson-navigator').text()).toContain('上一讲')
    expect(wrapper.get('.lesson-navigator').text()).toContain('下一讲')

    await wrapper.get('.lesson-title-trigger').trigger('click')
    expect(wrapper.get('.lesson-title-trigger').attributes('aria-expanded')).toBe('true')
    const chapterButtons = wrapper.findAll('.lesson-outline-chapter-button')
    expect(chapterButtons).toHaveLength(2)
    expect(chapterButtons[0]!.text()).toBe('第1章')
    expect(chapterButtons[0]!.attributes('aria-label')).toContain('待确认')
    expect(chapterButtons[1]!.attributes('aria-label')).toContain('已确认')
    expect(wrapper.find('.lesson-outline-sections').exists()).toBe(false)

    await chapterButtons[1]!.trigger('click')
    expect(wrapper.find('.lesson-outline-popover').exists()).toBe(false)
    expect(wrapper.get('.lesson-title-trigger').text()).toContain('第2章')
    expect(wrapper.get('.lesson-title-trigger').text()).toContain('2/2')
    expect(wrapper.get('.lesson-section-tabs button.active').text()).toBe('2.1 小节1')
    const secondSection = wrapper.findAll('.lesson-section-tabs button')[1]!
    await secondSection.trigger('click')
    expect(secondSection.classes()).toContain('active')

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
