import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherCourseWorkbench from '@/components/TeacherCourseWorkbench.vue'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'
import { lessonPlanStreamSegments, useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'
import { useTeachingRepresentationsStore } from '@/stores/teachingRepresentations'
import http from '@/utils/http'
import router from '@/router'

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
const outlineRequestAiCandidate = vi.fn(async () => null as Record<string, any> | null)
const outlineResolveAiCandidate = vi.fn(async (_accept: boolean) => true)
const outlineFocusQualityIssue = vi.fn(async () => true)
let outlineResolvedQualityReport: Record<string, any> | null = null

const mountWorkbench = (props: Record<string, unknown> = {}) => mount(TeacherCourseWorkbench, {
  props: {
    courseId: 'course-1',
    courseTitle: 'C 语言程序设计',
    generationOptions: {} as any,
    ...props,
  },
  global: {
    stubs: {
      'el-dialog': {
        props: ['modelValue'],
        template: '<section v-if="modelValue"><slot /></section>',
      },
      CourseReferenceTray: {
        name: 'CourseReferenceTray',
        props: ['modelValue', 'scopeTargetId', 'scopeTargetLabel', 'previousScopeTargetId', 'workflowState', 'workflowDetail', 'workflowProgress', 'workflowCanRetry', 'hideWorkflowStatus'],
        template: '<aside data-testid="reference-tray-stub"><span v-if="hideWorkflowStatus === undefined">{{ workflowDetail }}</span><i data-testid="workflow-progress">{{ workflowProgress }}</i><button data-testid="open-course-information" type="button" @click="$emit(\'open-course-information\')">课程信息</button><button v-if="workflowCanRetry && hideWorkflowStatus === undefined" data-testid="retry-workflow" type="button" @click="$emit(\'retry-workflow\')">重试生成</button><slot name="workflow-action" /></aside>',
        emits: ['open-course-information', 'retry-workflow', 'regenerate-workflow', 'source-state-change', 'update:modelValue'],
      },
      CompanionDocumentStudio: true,
      QuestionBankReviewPanel: true,
      TeacherScriptDocument: {
        name: 'TeacherScriptDocument',
        template: '<section data-testid="script-document-stub"><slot name="toolbar" /></section>',
      },
      MarkdownRenderer: true,
      CourseOutlineReview: {
        name: 'CourseOutlineReview',
        props: ['editable', 'variant', 'requiresConfirmation', 'lessonTypes', 'lessonTypeOptions', 'lessonTypeSavingId', 'lessonTypeError', 'lessonTypeErrorId'],
        template: '<section data-testid="inline-outline-editor" :data-mode="editable ? \'edit\' : \'view\'" :data-variant="variant"><label v-for="lesson in lessonTypes" :key="lesson.lessonUnitId" class="inline-lesson-type-control"><select :value="lesson.value" @change="$emit(\'lesson-type-change\', { lessonUnitId: lesson.lessonUnitId, lessonType: $event.target.value })"><option v-for="option in lessonTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></section>',
        emits: ['lesson-type-change', 'ai-resolved', 'quality-review-change'],
        setup(_props: unknown, { emit, expose }: any) {
          expose({
            finishEditing: outlineFinishEditing,
            requestAiCandidate: outlineRequestAiCandidate,
            requestQualityRepair: (issue: Record<string, any>) => String(issue.repair_instruction || ''),
            focusQualityIssueEditor: outlineFocusQualityIssue,
            resolveAiCandidate: async (accept: boolean) => {
              const resolved = await outlineResolveAiCandidate(accept)
              if (resolved) {
                if (accept && outlineResolvedQualityReport) emit('quality-review-change', outlineResolvedQualityReport)
                emit('ai-resolved', { accept })
              }
              return resolved
            },
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
    outlineRequestAiCandidate.mockReset()
    outlineRequestAiCandidate.mockResolvedValue(null)
    outlineResolveAiCandidate.mockReset()
    outlineResolveAiCandidate.mockResolvedValue(true)
    outlineFocusQualityIssue.mockReset()
    outlineFocusQualityIssue.mockResolvedValue(true)
    outlineResolvedQualityReport = null
    vi.spyOn(http, 'get').mockResolvedValue({ data: { total: 0 } })
    vi.spyOn(http, 'post').mockResolvedValue({ data: { status: 'resumed' } })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('侧栏只保留标题和导航名称，不再展示描述文本', () => {
    const wrapper = mountWorkbench()

    expect(wrapper.get('.stage-rail-title').text()).toBe('课程工作台')
    expect(wrapper.find('.stage-rail > header small').exists()).toBe(false)
    expect(wrapper.find('.stage-rail nav small').exists()).toBe(false)
    expect(wrapper.find('.companion-entry button small').exists()).toBe(false)
    expect(wrapper.findAll('.companion-entry button').map(button => button.text())).toEqual(['题库', '评分细则', '考试课程材料自查清单'])
    expect(wrapper.findAll('.companion-entry button').every(button => button.findAll('svg').length === 1)).toBe(true)
    expect(wrapper.find('.stage-rail > footer').exists()).toBe(false)
    expect(wrapper.findAll('.stage-state')).toHaveLength(4)
    expect(wrapper.findAll('.stage-state').every(state => state.attributes('data-state') === 'pending')).toBe(true)
    expect(wrapper.findAll('.stage-state').every(state => state.attributes('data-progress') === '0')).toBe(true)
  })

  it('侧栏用绿色圆形填充表示真实生成进度，不显示数字计数', () => {
    const task = useGenerationStore().createTask('job-progress', 'course-1', 'C 语言程序设计')
    task.status = 'running'
    task.progress = 40

    const wrapper = mountWorkbench()
    const outlineState = wrapper.findAll('.stage-state')[0]!

    expect(outlineState.attributes('data-state')).toBe('progress')
    expect(outlineState.attributes('data-progress')).toBe('40')
    expect(outlineState.attributes('style')).toContain('--stage-progress-angle: 144deg')
    expect(wrapper.find('.stage-rail > footer').exists()).toBe(false)
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

  it('旧检查点也只投影为讲次，不再回显章节与小节', () => {
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'running'
    task.currentStep = '正在展开各章小节'
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: growth }

    const wrapper = mountWorkbench()

    expect(wrapper.get('[data-testid="outline-growth-stream"]').attributes('data-structure')).toBe('lecture')
    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).toContain('第1讲 程序环境与基础语法')
    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).toContain('第2讲 流程控制结构')
    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).not.toContain('Hello World 与编译过程')
    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).not.toContain('1.1')
    expect(wrapper.get('[data-testid="outline-growth-stream"]').text()).not.toContain('小节')
    expect(wrapper.find('.stream-waiting').exists()).toBe(false)
    expect(wrapper.get('.generation-surface>header').text()).toContain('正在生成讲次方案')
    expect(wrapper.get('.generation-surface>header').text()).not.toContain('章')
    expect(wrapper.get('.generation-surface>header').text()).not.toContain('小节')
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

  it('完整大纲按讲显示真实进度并实时吐出当前文字', () => {
    const task = useGenerationStore().createTask('job-detail', 'course-1', '电动力学')
    task.status = 'running'
    task.currentPhase = 'outline_detail_generation'
    task.currentStep = '正在并发生成各讲完整内容'
    task.phaseDetail = {
      generation_step: 'outline_detail_generation',
      outline_growth: {
        ...growth,
        authoring_structure_version: 'lecture_v1',
        state: 'detailing',
        chapters: [
          { chapter_number: 1, title: '静电场', section_count: 1, completed_section_count: 1, status: 'completed', sections: [] },
          { chapter_number: 2, title: '稳恒磁场', section_count: 1, completed_section_count: 0, status: 'growing', sections: [] },
        ],
      },
      lesson_statuses: {
        'L1-1': { lesson_id: 'L1-1', status: 'completed', stage: 'outline_detail_completed', message: '第 1 讲已生成', progress: 100, stream_preview: '第 1 讲\n内容：静电场基本规律' },
        'L1-2': { lesson_id: 'L1-2', status: 'running', stage: 'outline_detail_generation', message: '第 2 讲正在生成', progress: 46, stream_preview: '第 2 讲\n内容：正在建立稳恒磁场分析方法' },
      },
    }

    const wrapper = mountWorkbench({ courseTitle: '电动力学' })
    const detail = wrapper.get('[data-testid="outline-detail-stream"]')

    expect(wrapper.findAll('[data-testid="outline-flow-steps"] button')[2]!.classes()).toContain('active')
    expect(wrapper.find('[data-testid="outline-growth-stream"]').exists()).toBe(false)
    expect(detail.text()).toContain('已完成 1/2 讲')
    expect(detail.text()).toContain('第1讲 静电场')
    expect(detail.text()).toContain('第2讲 稳恒磁场')
    expect(detail.text()).toContain('正在建立稳恒磁场分析方法')
    expect(detail.find('article[data-state="running"] .stream-caret').exists()).toBe(true)
  })

  it('新生成任务启动时不回显上一个任务的旧结构', async () => {
    const task = useGenerationStore().createTask('job-old', 'course-1', 'C 语言程序设计')
    task.status = 'completed'
    task.currentPhase = 'teacher_outline_ready'
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: growth }
    const wrapper = mountWorkbench()

    await wrapper.get('form.stage-form').trigger('submit')
    await flushPromises()

    expect(wrapper.emitted('generateOutline')).toHaveLength(1)
    expect(wrapper.find('.generation-surface').exists()).toBe(true)
    expect(wrapper.find('[data-testid="outline-growth-stream"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Hello World 与编译过程')
    expect(wrapper.text()).not.toContain('1.1')
    expect(wrapper.get('.stream-waiting').text()).toContain('AI 正在建立课程结构')
  })

  it('切换课程或任务时不复用其他任务的大纲快照', async () => {
    const generation = useGenerationStore()
    const firstTask = generation.createTask('job-first', 'course-1', 'C 语言程序设计')
    firstTask.status = 'running'
    firstTask.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: growth }
    const wrapper = mountWorkbench()
    expect(wrapper.find('[data-testid="outline-growth-stream"]').exists()).toBe(true)

    const secondTask = generation.createTask('job-second', 'course-2', '电动力学')
    secondTask.status = 'running'
    secondTask.phaseDetail = {}
    await wrapper.setProps({ courseId: 'course-2', courseTitle: '电动力学' })
    await flushPromises()

    expect(wrapper.find('[data-testid="outline-growth-stream"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('程序环境与基础语法')
    expect(wrapper.find('.stream-waiting').exists()).toBe(true)
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

  it('大纲生成完成后直接展示文档，由老师主动进入编辑', async () => {
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
    task.status = 'completed'
    task.currentPhase = 'teacher_outline_ready'
    task.progress = 35
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: { ...growth, state: 'completed' } }

    const wrapper = mountWorkbench()

    expect(wrapper.find('.generation-surface').exists()).toBe(false)
    expect(wrapper.get('[data-testid="outline-workspace"]').text()).not.toContain('课程大纲已生成')
    expect(wrapper.get('[data-testid="outline-workspace"]').text()).not.toContain('已保存完整章节结构')
    expect(wrapper.find('[data-testid="outline-confirm-action"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="inline-outline-editor"]').attributes('data-mode')).toBe('view')
    expect(wrapper.get('.center-heading h2').text()).toBe('大纲')
    expect(wrapper.find('[data-testid="outline-ai-action"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="outline-manual-action"]').text()).toContain('编辑大纲')
    const completedState = wrapper.findAll('.stage-state')[0]!
    expect(completedState.attributes('data-state')).toBe('complete')
    expect(completedState.attributes('data-progress')).toBe('100')
    expect(completedState.find('svg').exists()).toBe(true)
    await wrapper.get('[data-testid="outline-manual-action"]').trigger('click')
    expect(wrapper.emitted('update:outlineEditing')?.[0]).toEqual([true])
  })

  it('讲次方案生成后退出转圈并提供编辑与继续入口', () => {
    useCourseStore().nodes = [{
      node_id: 'L1-1', parent_node_id: 'root', node_name: '第1讲 设计导论', node_level: 1,
      node_content: '', node_type: 'original', generation_status: 'completed', generated_chars: 0,
    }] as any
    const task = useGenerationStore().createTask('job-waiting', 'course-1', 'UI 设计')
    task.status = 'waiting_for_input'
    task.currentPhase = 'outline_shape_ready'
    task.progress = 35

    const wrapper = mountWorkbench({ courseTitle: 'UI 设计' })

    expect(wrapper.find('.generation-surface').exists()).toBe(false)
    expect(wrapper.find('[data-testid="outline-workspace"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="outline-continue-action"]').text()).toContain('生成完整大纲')
    expect(wrapper.get('[data-testid="outline-manual-action"]').text()).toContain('编辑大纲')
    expect(wrapper.find('.spin').exists()).toBe(false)
  })

  it('等待继续状态先于讲次投影到达时不回退课程表单', async () => {
    const courses = useCourseStore()
    courses.nodes = []
    const task = useGenerationStore().createTask('job-waiting-race', 'course-1', 'UI 设计')
    task.taskType = 'teacher_outline_generation'
    task.status = 'waiting_for_input'
    task.currentPhase = 'outline_framework_ready'
    task.progress = 32

    const wrapper = mountWorkbench({ courseTitle: 'UI 设计' })

    expect(wrapper.find('form.stage-form').exists()).toBe(false)
    expect(wrapper.find('[data-testid="outline-workspace"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="outline-workspace-loading"]').text()).toContain('正在载入可编辑讲次方案')
    expect(wrapper.get('[data-testid="outline-continue-action"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="outline-manual-action"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="inline-outline-editor"]').exists()).toBe(false)

    courses.nodes = [{
      node_id: 'L1-1', parent_node_id: 'root', node_name: '第1讲 设计导论', node_level: 1,
      node_content: '', node_type: 'original', generation_status: 'completed', generated_chars: 0,
    }] as any
    await flushPromises()

    expect(wrapper.find('[data-testid="outline-workspace-loading"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="inline-outline-editor"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="outline-continue-action"]').attributes('disabled')).toBeUndefined()
  })

  it('正式大纲不再重复完成步骤，右栏只显示一次结果状态', async () => {
    useCourseStore().nodes = [
      {
        node_id: 'L1-1', parent_node_id: 'root', node_name: '第1章 程序环境与基础语法', node_level: 1,
        node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
      },
    ] as any

    const wrapper = mountWorkbench()
    await flushPromises()

    expect(wrapper.find('[data-testid="outline-flow-steps"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="outline-ai-action"]').exists()).toBe(false)
    expect(wrapper.find('.context-pane-tabs').exists()).toBe(false)
    expect(wrapper.find('.ai-workspace-panel').exists()).toBe(false)
    expect(wrapper.find('[data-testid="teacher-ai-dialog"]').exists()).toBe(false)
    expect(wrapper.get('.context-pane-heading').attributes('data-phase')).toBe('after')
    expect(wrapper.get('.context-pane-heading').text()).toContain('内容已就绪')
    expect(wrapper.get('.context-pane-heading').text()).toContain('完整大纲')
    expect(wrapper.get('.context-pane-heading').text()).not.toContain('C 语言程序设计')
    expect(wrapper.getComponent({ name: 'CourseReferenceTray' }).props('hideWorkflowStatus')).toBe('')
    expect(wrapper.get('.teacher-workbench').classes()).not.toContain('is-ai-collaboration')
    expect(wrapper.get('.stage-rail').attributes('style')).toBeUndefined()
  })

  it('右侧审阅建议进入统一 AI 候选链，采用后重新审读并移除已解决问题', async () => {
    useCourseStore().nodes = [
      {
        node_id: 'L1-1', parent_node_id: 'root', node_name: '第1讲 统计思维', node_level: 1,
        node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
      },
    ] as any
    const issues = [
      {
        code: 'outline_editorial:missing_outcome_alignment',
        message: '有 1 项可测量成果尚未建立完整关联。',
        node_ids: [],
        repair_instruction: '补齐成果与目标、讲次和评价证据的关联。',
      },
      {
        code: 'outline_editorial:unverified_extension_resources',
        message: '有 1 讲的拓展资源尚未核验。',
        node_ids: ['L1-1'],
        repair_instruction: '为拓展资源补齐真实来源。',
      },
    ]
    outlineRequestAiCandidate.mockResolvedValue({
      proposal_id: 'proposal-outline-review',
      can_apply: true,
      diff: { course_updated: [{ field: 'outcome_alignment' }] },
    })
    outlineResolvedQualityReport = {
      schema_version: 'course_outline_editorial_review_v6',
      status: 'ready',
      summary: '整篇大纲未发现高频专业表达问题。',
      issues: [],
      blocking_issues: [],
      can_confirm: true,
    }
    const wrapper = mountWorkbench()
    await flushPromises()
    wrapper.getComponent({ name: 'CourseOutlineReview' }).vm.$emit('quality-review-change', {
      schema_version: 'course_outline_editorial_review_v6',
      status: 'review_suggested',
      summary: '大纲已生成；发现 2 类改进建议，不影响后续生成。',
      issues,
      blocking_issues: [],
      can_confirm: true,
    })
    await flushPromises()

    const review = wrapper.get('[data-testid="outline-quality-review"]')
    expect(review.text()).toContain('查看大纲审阅')
    expect(review.text()).toContain('2')
    expect(review.text()).not.toContain('2 项改进建议')
    expect(review.text()).not.toContain('AI 优化')
    await review.get('[data-testid="outline-quality-review-open"]').trigger('click')
    const reviewDialog = wrapper.get('[data-testid="outline-quality-review-dialog"]')
    expect(reviewDialog.text()).toContain('仅供参考，不影响后续生成')
    expect(reviewDialog.text()).toContain('AI 优化')
    expect(reviewDialog.text()).toContain('手动补充')

    const issueActions = reviewDialog.findAll('.outline-quality-review-dialog__body li button')
    await issueActions[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:outlineEditing')?.at(-1)).toEqual([true])
    expect(outlineFocusQualityIssue).toHaveBeenCalledWith(issues[1])
    expect(outlineRequestAiCandidate).not.toHaveBeenCalled()

    await issueActions[0]!.trigger('click')
    await flushPromises()
    expect(outlineRequestAiCandidate).toHaveBeenCalledWith(
      '补齐成果与目标、讲次和评价证据的关联。',
      'outline_editorial:missing_outcome_alignment',
    )
    expect(wrapper.find('[data-testid="outline-quality-review-dialog"]').exists()).toBe(false)
    expect(wrapper.find('.ai-workspace-panel').exists()).toBe(false)
    expect(wrapper.find('.teacher-ai-dialog__workspace').exists()).toBe(false)
    expect(wrapper.find('.lesson-ai-review').exists()).toBe(false)

    await (wrapper.getComponent({ name: 'CourseOutlineReview' }).vm as any).resolveAiCandidate(true)
    await flushPromises()
    expect(outlineResolveAiCandidate).toHaveBeenCalledWith(true)
    const resolvedReview = wrapper.get('[data-testid="outline-quality-review"]')
    expect(resolvedReview.find('small').exists()).toBe(false)
    await resolvedReview.get('[data-testid="outline-quality-review-open"]').trigger('click')
    expect(wrapper.get('[data-testid="outline-quality-review-dialog"]').text()).toContain('暂无改进建议')
  })

  it('目标问题未解决时保留阻断候选，且不再打开旧 AI 弹窗', async () => {
    useCourseStore().nodes = [
      {
        node_id: 'L1-1', parent_node_id: 'root', node_name: '第1讲 统计思维', node_level: 1,
        node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
      },
    ] as any
    const issue = {
      code: 'outline_editorial:hour_total_mismatch',
      message: '各讲学时合计与课程总学时不一致。',
      node_ids: [],
      repair_instruction: '调整各讲分项学时，使合计等于课程总学时。',
    }
    outlineRequestAiCandidate.mockResolvedValue({
      proposal_id: 'proposal-outline-review-blocked',
      can_apply: false,
      diff: { updated: [{ node_name: '第1讲' }] },
      blocking_issues: [{
        code: 'outline_quality_issue_unresolved',
        message: '这版 AI 候选仍未解决目标审阅问题，已暂停采用。',
      }],
    })
    const wrapper = mountWorkbench()
    await flushPromises()
    wrapper.getComponent({ name: 'CourseOutlineReview' }).vm.$emit('quality-review-change', {
      schema_version: 'course_outline_editorial_review_v6',
      status: 'review_suggested',
      issues: [issue],
      blocking_issues: [],
      can_confirm: true,
    })
    await flushPromises()

    await wrapper.get('[data-testid="outline-quality-review-open"]').trigger('click')
    await wrapper.get('.outline-quality-review-dialog__body li button').trigger('click')
    await flushPromises()

    const candidate = await outlineRequestAiCandidate.mock.results[0]!.value
    expect(candidate?.can_apply).toBe(false)
    expect(candidate?.blocking_issues?.[0]?.message).toContain('仍未解决目标审阅问题')
    expect(candidate?.blocking_issues?.[0]?.message).toContain('已暂停采用')
    expect(wrapper.find('.teacher-ai-dialog__workspace').exists()).toBe(false)
    expect(wrapper.find('.lesson-ai-review').exists()).toBe(false)
    expect(outlineResolveAiCandidate).not.toHaveBeenCalledWith(true)
  })

  it('在大纲中展示并调整每一讲的课型', async () => {
    useCourseStore().nodes = [{
      node_id: 'L1-1', parent_node_id: 'root', node_name: '第一讲', node_level: 1,
      node_content: '', node_type: 'original', generation_status: 'pending', generated_chars: 0,
    }] as any
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', number: 1, title: '第一讲', duration_minutes: 45, sections: [],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: '', lesson_unit_id: 'L1-1',
        source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授',
        status: 'suggested', confirmed: false, source_state: 'current', blocks: [{
          block_id: 'block-1', module_id: 'core_explanation', section_node_id: 'L2-1-1',
          section_title: '基础概念', name: '概念讲解', role: 'concept', purpose: '建立概念',
          content_summary: '讲清概念边界', planned_minutes: 45, teacher_activity: '',
          student_activity: '', expected_output: '', required: true,
        }],
      },
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }] as any
    const updateLessonType = vi.spyOn(lessonStore, 'updateLessonType').mockResolvedValue(lessonStore.lessons[0]!)

    const wrapper = mountWorkbench()
    const selector = wrapper.get('.inline-lesson-type-control select')
    expect(wrapper.find('.outline-lesson-type-plan').exists()).toBe(false)
    expect((selector.element as HTMLSelectElement).value).toBe('theory')

    await selector.setValue('project_workshop')
    await flushPromises()

    expect(updateLessonType).toHaveBeenCalledWith('course-1', 'L1-1', 'project_workshop')
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

  it('后端没有大纲投影时不伪装成已生成文档', () => {
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'completed'
    task.currentPhase = 'teacher_outline_ready'
    task.phaseDetail = {}

    const wrapper = mountWorkbench()

    expect(wrapper.find('[data-testid="outline-workspace"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="inline-outline-editor"]').exists()).toBe(false)
    expect(wrapper.find('form.stage-form').exists()).toBe(true)
  })

  it('任务完成且后端存在大纲时直接展示当前文档', async () => {
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'running'
    task.phaseDetail = { artifact_type: 'course_outline_growth', outline_growth: growth }
    const wrapper = mountWorkbench()

    useCourseStore().nodes = [{
      node_id: 'L1-1', parent_node_id: 'root', node_name: '第1讲 程序环境', node_level: 1,
      node_content: '', node_type: 'original', generation_status: 'completed', generated_chars: 0,
    }] as any
    const reactiveTask = useGenerationStore().getTask('course-1')!
    reactiveTask.status = 'completed'
    reactiveTask.currentPhase = 'teacher_outline_ready'
    reactiveTask.phaseDetail = { artifact_type: 'course_outline_ready' }
    await flushPromises()

    expect(wrapper.get('[data-testid="inline-outline-editor"]').attributes('data-mode')).toBe('view')
    expect(wrapper.find('form.stage-form').exists()).toBe(false)
  })

  it('后台状态刷新不得自动关闭大纲编辑', async () => {
    useCourseStore().nodes = [{
      node_id: 'L1-1', parent_node_id: 'root', node_name: '第1讲 程序环境', node_level: 1,
      node_content: '', node_type: 'original', generation_status: 'completed', generated_chars: 0,
    }] as any
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'completed'
    task.currentPhase = 'teacher_outline_ready'

    const wrapper = mountWorkbench({ outlineEditing: true })
    expect(wrapper.get('[data-testid="inline-outline-editor"]').attributes('data-mode')).toBe('edit')

    task.phaseDetail = { artifact_type: 'course_outline_ready', refreshed_at: '2026-09-04T00:00:00Z' }
    useTeacherLessonAuthoringStore().lessons = [{
      lesson_unit_id: 'L1-1', number: 1, title: '第1讲 程序环境', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }] as any
    await flushPromises()

    expect(wrapper.get('[data-testid="inline-outline-editor"]').attributes('data-mode')).toBe('edit')
    expect(wrapper.emitted('update:outlineEditing')).toBeUndefined()
  })

  it('把大纲编辑器放在工作台中央而不是右侧抽屉', async () => {
    const wrapper = mountWorkbench({ outlineEditing: true })

    expect(wrapper.find('.workbench-center [data-testid="inline-outline-editor"]').exists()).toBe(true)
    expect(wrapper.find('.stage-rail').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'CourseReferenceTray' }).exists()).toBe(true)
    expect(wrapper.find('[data-testid="outline-confirm-action"]').exists()).toBe(false)
    expect(wrapper.emitted('outlineConfirmed')).toBeUndefined()
    await wrapper.get('[data-testid="outline-manual-action"]').trigger('click')
    expect(wrapper.emitted('update:outlineEditing')?.at(-1)).toEqual([false])
  })

  it('旧大纲检查点不再触发隐藏确认请求', async () => {
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
    expect(wrapper.find('.generation-surface').exists()).toBe(false)
    expect(wrapper.find('[data-testid="outline-shape-review"]').exists()).toBe(false)
    expect(wrapper.find('form.stage-form').exists()).toBe(true)
    expect(vi.mocked(http.post).mock.calls.some(call => String(call[0]).includes('outline-shape/confirm'))).toBe(false)
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

  it('大纲与讲次投影完成后可直接进入教案', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }] as any
    const task = useGenerationStore().createTask('job-1', 'course-1', 'C 语言程序设计')
    task.status = 'completed'
    task.currentPhase = 'teacher_outline_ready'

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.find('.lesson-selector').exists()).toBe(false)
    expect(wrapper.find('.prerequisite').exists()).toBe(false)
    expect(wrapper.find('[data-testid="lesson-outline-fixed"]').exists()).toBe(false)
    expect(wrapper.get('.lesson-current-title').text()).toContain('第一讲')
    expect(wrapper.get('.lesson-empty-canvas').text()).toContain('教案尚未生成')
    expect(wrapper.text()).not.toContain('查看并确认大纲')
    expect(wrapper.text()).not.toContain('确认教案')
    expect(wrapper.get('.context-pane-heading').attributes('data-phase')).toBe('before')
  })

  it('系统无法自动恢复时显示真实错误，只保留普通重试动作', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.courseId = 'course-1'
    lessonStore.error = '分讲教案状态读取失败'
    const reload = vi.spyOn(lessonStore, 'load').mockResolvedValue({} as any)

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    const notice = wrapper.get('.prerequisite-error')
    expect(notice.text()).toContain('教案读取失败')
    expect(notice.text()).toContain('分讲教案状态读取失败')
    expect(notice.get('details code').text()).toContain('原始反馈')
    expect(notice.get('button').text()).toBe('重试')
    await notice.get('button').trigger('click')
    expect(reload).toHaveBeenCalledWith('course-1')
  })

  it('大纲已经存在时自动重试同步课次，不要求教师重复操作', async () => {
    vi.useFakeTimers()
    useCourseStore().nodes = [{
      node_id: 'L1-1', node_level: 1, node_name: '第一讲', node_content: '基础概念',
    }] as any
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.courseId = 'course-1'
    lessonStore.error = '分讲教案状态读取失败'
    const reload = vi.spyOn(lessonStore, 'load').mockImplementation(async () => {
      if (reload.mock.calls.length < 3) throw new Error('暂时读取失败')
      lessonStore.error = ''
      lessonStore.lessons = [{
        lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
        title: '第一讲', duration_minutes: 45, sections: [],
        plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
      }] as any
      return {} as any
    })

    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    expect(wrapper.get('.prerequisite').text()).toContain('正在准备教案')
    expect(wrapper.get('.prerequisite').text()).toContain('无需重复操作')
    expect(wrapper.find('.prerequisite button').exists()).toBe(false)

    await vi.runAllTimersAsync()
    await flushPromises()

    expect(reload).toHaveBeenCalledTimes(3)
    expect(wrapper.get('.lesson-current-title').text()).toContain('第一讲')
    expect(wrapper.text()).not.toContain('重新读取课次')
  })

  it('未生成教案时先平铺全课预览，只突出一次生成全部', async () => {
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
    const preview = wrapper.get('[data-testid="lesson-course-preview"]')
    const generationButton = wrapper.get('[data-testid="lesson-course-preview-generate"]')
    expect(wrapper.find('[data-testid="lesson-arrangement-editor"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="lesson-generation-form"]').exists()).toBe(false)
    expect(preview.text()).toContain('整门课程教案预览')
    expect(preview.text()).toContain('第1讲')
    expect(preview.text()).toContain('理论讲授')
    expect(preview.text()).toContain('概念讲解')
    expect(wrapper.find('[data-testid="lesson-outline-fixed"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="lesson-single-start"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="lesson-batch-start"]').exists()).toBe(false)
    expect(generationButton.text()).toBe('生成全部教案')
    expect(wrapper.text()).not.toContain('统一生成要求')
    expect(wrapper.find('.lesson-batch-panel').exists()).toBe(false)

    await generationButton.trigger('click')
    await flushPromises()

    expect(generateAllLessons).toHaveBeenCalledWith('course-1', undefined, '', [])
  })

  it('教案批量生成只承诺教学结构已就绪的讲次', () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45,
      sections: [{ section_node_id: `L2-${number}-1`, title: `${number}.1 核心内容` }],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: '', lesson_unit_id: `L1-${number}`,
        source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授',
        status: 'suggested', confirmed: false, source_state: 'current',
        blocks: number === 1 ? [{ block_id: 'block-1', name: '概念讲解' }] : [],
      },
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: {
        lesson_unit_id: `L1-${number}`, working_revision_id: '', confirmed_revision_id: '', source_state: 'current',
        ready: false, can_generate: number === 1,
        generation_unavailable_reason: number === 1 ? '' : 'lesson_arrangement:blocks_empty',
        revisions: [], ppt_assets: [],
      },
    })) as any

    const wrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(wrapper.get('[data-testid="lesson-course-preview-generate"]').text()).toBe('生成已具备教学结构的教案（1讲）')
  })

  it('已有部分教案时仍可只生成当前讲，课型在标题中显示', async () => {
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
    }, {
      lesson_unit_id: 'L1-2', source_outline_revision_id: 'outline-1', number: 2,
      title: '第二讲', duration_minutes: 45, sections: [],
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: 'L1-2', working_revision_id: 'plan-2', confirmed_revision_id: '', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
    }] as any
    const generateLesson = vi.spyOn(lessonStore, 'generateLesson').mockResolvedValue({ id: 'lesson-job-1' } as any)
    const generateAllLessons = vi.spyOn(lessonStore, 'generateAllLessons')
    const saveRelationships = vi.spyOn(http, 'put').mockResolvedValue({ data: { relationships: [] } } as any)

    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    wrapper.findComponent({ name: 'CourseReferenceTray' }).vm.$emit('update:modelValue', [{
      package_id: 'package-1', asset_id: 'asset-3', material_asset_id: 'mat-3',
      filename: '第一讲主教材.docx', relative_path: '生成资料/第一讲主教材.docx',
      size_bytes: 1800, role: 'primary',
    }])
    await flushPromises()
    const singleButton = wrapper.get('[data-testid="lesson-single-start"]')
    expect(wrapper.get('.lesson-type-context').text()).toContain('讲练结合')
    expect(wrapper.find('[data-testid="lesson-course-preview"]').exists()).toBe(false)
    expect(wrapper.find('.lesson-command-bar select').exists()).toBe(false)
    expect(wrapper.find('.lesson-command-bar [aria-label="历史版本"]').exists()).toBe(false)
    expect(wrapper.findAll('.lesson-command-bar button').some(button => button.text().includes('AI 修改'))).toBe(false)
    expect(singleButton.text()).toBe('只生成本讲')
    await singleButton.trigger('click')
    await flushPromises()

    expect(saveRelationships).toHaveBeenCalledWith(
      '/api/teacher-course-spaces/package-1/relationships',
      expect.objectContaining({
        target_id: 'lesson-plan:L1-1',
        sources: [{ source_asset_id: 'asset-3', role: 'primary' }],
      }),
      expect.any(Object),
    )
    expect(generateLesson).toHaveBeenCalledWith(
      'course-1', 'L1-1', { packageId: 'package-1', assetId: 'asset-3' }, '', ['mat-3'], '',
    )
    expect(saveRelationships.mock.invocationCallOrder[0]).toBeLessThan(generateLesson.mock.invocationCallOrder[0]!)
    expect(generateAllLessons).not.toHaveBeenCalled()
  })

  it('默认先定位最近失败讲次，其次定位受影响讲次', () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2, 3].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45, sections: [],
      script: { current_revision_id: 'script-1', confirmed_revision_id: 'script-1', source_lesson_plan_revision_id: 'plan-1', source_state: number === 2 ? 'stale' : 'current', ready: true, confirmed: true, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: number === 2 ? 'stale' : 'current', ready: number !== 2, revisions: [], ppt_assets: [{ source_state: 'current', ppt_manuscript_status: 'confirmed' }] },
    })) as any
    lessonStore.jobs = [{
      id: 'failed-job', course_id: 'course-1', lesson_unit_id: 'L1-3', type: 'teacher_lesson_plan_generation',
      status: 'failed', progress: 30, phase: 'lesson_plan_failed', message: '生成失败', warnings: [], updated_at: '2026-09-02T09:00:00Z',
    }] as any

    const failedFirst = mountWorkbench({ initialStage: 'lesson' })
    expect(failedFirst.get('.lesson-current-title').text()).toContain('第3讲')
    failedFirst.unmount()

    lessonStore.jobs = []
    const affectedNext = mountWorkbench({ initialStage: 'lesson' })
    expect(affectedNext.get('.lesson-current-title').text()).toContain('第2讲')
  })

  it('讲次目录使用生成、更新和失败状态', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2, 3, 4, 5, 6].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45, sections: [],
      plan: {
        lesson_unit_id: `L1-${number}`,
        working_revision_id: [3, 4, 5].includes(number) ? `plan-${number}` : '',
        confirmed_revision_id: [4, 5].includes(number) ? `plan-${number}` : '',
        source_state: number === 5 ? 'stale' : 'current', ready: [3, 4].includes(number), revisions: [], ppt_assets: [],
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
    const buttons = wrapper.findAll('.lesson-outline-chapter-button')
    expect(buttons.map(button => button.attributes('aria-label'))).toEqual([
      '第1讲，未生成', '第2讲，正在生成', '第3讲，已生成',
      '第4讲，已生成', '第5讲，需更新', '第6讲，失败',
    ])
    expect(buttons[1]!.find('.lesson-outline-status').attributes('data-state')).toBe('generating')
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

    expect(wrapper.find('[data-testid="lesson-outline-fixed"]').exists()).toBe(true)
    expect(wrapper.get('.lesson-generation-status').text()).toContain('正在生成第一讲')
    expect(wrapper.get('.lesson-generation-status').text()).toContain('正在确定各节教学重点')
    expect(wrapper.get('.lesson-stream-document').text()).toContain('AI 工作稿')
    expect(wrapper.get('.lesson-stream-document').text()).toContain('学生能够解释爬虫的工作流程')
    expect(wrapper.find('.lesson-stream-document .stream-caret').exists()).toBe(true)
    expect(wrapper.find('button[type="submit"]').exists()).toBe(false)
    expect(wrapper.get('.context-pane-heading').attributes('data-phase')).toBe('during')
  })

  it('批量任务在固定目录中独立显示运行与排队状态', async () => {
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
    const chapterButtons = wrapper.findAll('.lesson-outline-chapter-button')
    expect(chapterButtons[0]!.find('.lesson-outline-status').attributes('data-state')).toBe('generating')
    expect(chapterButtons[0]!.find('small').text()).toContain('正在生成')
    expect(chapterButtons[1]!.find('.lesson-outline-status').attributes('data-state')).toBe('queued')
    expect(chapterButtons[1]!.find('small').text()).toContain('等待')
    expect(wrapper.findAll('.lesson-outline-status .spin')).toHaveLength(1)

    await chapterButtons[1]!.trigger('click')
    expect(wrapper.get('.lesson-current-title').text()).toContain('第2讲')
    expect(wrapper.find('.lesson-queue-state').exists()).toBe(true)
    expect(wrapper.find('.lesson-queue-state button').exists()).toBe(false)
  })

  it('教案任务失败后只在右侧显示真实原因和整课重试动作', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', can_generate: true, revisions: [], ppt_assets: [] },
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

    expect(wrapper.get('.context-pane-heading').text()).toContain('生成未完成')
    expect(wrapper.get('.context-pane-heading').text()).toContain('知识骨架汇编失败')
    expect(wrapper.get('[data-testid="reference-tray-stub"]').text()).not.toContain('知识骨架汇编失败')
    expect(wrapper.get('.primary-status-action').text()).toBe('重试')
    expect(wrapper.get('.lesson-empty-canvas').text()).toBe('教案尚未生成')
    await wrapper.get('.primary-status-action').trigger('click')
    await flushPromises()
    expect(generateAllLessons).toHaveBeenCalledWith('course-1', undefined, '', [])
    expect(wrapper.text()).not.toContain('重新生成本讲教案')
  })

  it('教案已生成但讲义未生成时仍可上传自有 PPT，但不能使用 AI 生成', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [{ section_node_id: 'L2-1-1', title: '1.1 程序运行过程' }],
      plan: {
        lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: '', source_state: 'current', ready: true, ppt_assets: [],
        revisions: [{ revision_id: 'plan-1', lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', generation_source: 'model', status: 'draft', warnings: [], plan: { sections: [{ node_id: 'L2-1-1', key_points: ['编译', '运行'], teaching_modules: [{ module_id: 'core_explanation', planned_minutes: 15, teacher_activity: '演示源码如何编译运行', student_activity: '跟随完成首次运行' }] }] }, actor: 'teacher', created_at: '' }],
      },
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
    }] as any
    const lessonWrapper = mountWorkbench({ initialStage: 'lesson' })

    expect(lessonWrapper.get('.lesson-outline-chapter-button').attributes('aria-label')).toContain('已生成')
    expect(lessonWrapper.text()).toContain('1.1 程序运行过程')
    expect(lessonWrapper.text()).toContain('演示源码如何编译运行')
    expect(lessonWrapper.find('.lesson-toolbar-status').exists()).toBe(false)
    expect(lessonWrapper.find('.teacher-document-command-bar__status').exists()).toBe(false)
    expect(lessonWrapper.find('.lesson-document-toolbar .primary-action').exists()).toBe(false)
    expect(lessonWrapper.find('.lesson-section-tabs').exists()).toBe(false)

    const scriptWrapper = mountWorkbench({ initialStage: 'script' })
    expect(scriptWrapper.find('[data-testid="lesson-outline-fixed"]').exists()).toBe(false)
    scriptWrapper.unmount()

    const pptWrapper = mountWorkbench({ initialStage: 'ppt' })
    await flushPromises()
    expect(pptWrapper.get('.lesson-navigator').text()).toContain('第一讲')
    expect(pptWrapper.find('.lesson-toolbar-status').exists()).toBe(false)
    expect(pptWrapper.get('.context-pane-heading').text()).toContain('准备资料')
    expect(pptWrapper.get('.context-pane-heading').text()).toContain('待生成')
    expect(pptWrapper.get('.ppt-upload-secondary').attributes('disabled')).toBeUndefined()
    expect(pptWrapper.get('.ppt-generate-primary').attributes('disabled')).toBeDefined()
  })

  it('讲义生成完成后停留当前阶段，由左侧四步流程负责切换', async () => {
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
        lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: 'current', ready: true, ppt_assets: [],
        revisions: [{ revision_id: 'plan-1', lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', generation_source: 'model', status: 'confirmed', warnings: [], plan: {}, actor: 'teacher', created_at: '' }],
      },
    }] as any
    const wrapper = mountWorkbench({ initialStage: 'script' })

    expect(wrapper.find('[data-testid="lesson-outline-fixed"]').exists()).toBe(true)
    expect(wrapper.find('.center-heading').exists()).toBe(false)
    expect(wrapper.get('.lesson-current-title').text()).toContain('第一讲')
    expect(wrapper.find('.lesson-toolbar-status').exists()).toBe(false)
    expect(wrapper.get('.context-pane-heading').text()).toContain('内容已就绪')
    expect(wrapper.get('.context-pane-heading').text()).toContain('已生成')
    expect(wrapper.find('.lesson-document-toolbar .primary-action').exists()).toBe(false)
    expect(wrapper.get('.stage-rail button.active').text()).toContain('讲义')
  })

  it('讲义未生成时先平铺全课教案映射，再一次提交全部讲义', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45,
      sections: [{ section_node_id: `L2-${number}-1`, title: `${number}.1 核心内容` }],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: `arrangement-${number}`, lesson_unit_id: `L1-${number}`,
        source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授',
        status: 'confirmed', confirmed: true, source_state: 'current', blocks: [],
      },
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: `plan-${number}`, source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: {
        lesson_unit_id: `L1-${number}`, working_revision_id: `plan-${number}`, confirmed_revision_id: '', source_state: 'current', ready: true, ppt_assets: [],
        revisions: [{
          revision_id: `plan-${number}`, lesson_unit_id: `L1-${number}`, source_outline_revision_id: 'outline-1',
          generation_source: 'model', status: 'draft', warnings: [], actor: 'teacher', created_at: '',
          plan: { sections: [{ node_id: `L2-${number}-1`, teaching_modules: [{ module_id: 'core_explanation', label: '核心教学', planned_minutes: 20, teacher_activity: `讲清第${number}讲的核心概念` }] }] },
        }],
      },
    })) as any
    const generateAll = vi.spyOn(lessonStore, 'generateAllScripts').mockResolvedValue({
      parent_job: { id: 'script-batch-1' }, jobs: [],
    } as any)

    const wrapper = mountWorkbench({ initialStage: 'script' })

    expect(wrapper.find('[data-testid="lesson-outline-fixed"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="script-course-preview"]').text()).not.toContain('检查教案映射')
    expect(wrapper.get('[data-testid="script-course-preview"]').text()).toContain('整门课程教案映射')
    expect(wrapper.get('[data-testid="script-course-preview"]').text()).toContain('核心教学')
    expect(wrapper.get('[data-testid="script-course-preview"]').text()).toContain('讲清第1讲的核心概念')
    expect(wrapper.get('[data-testid="script-course-preview"]').text()).not.toContain('填写讲义生成要求')
    expect(wrapper.get('[data-testid="script-course-preview-generate"]').text()).toBe('生成全部讲义')

    await wrapper.get('[data-testid="script-course-preview-generate"]').trigger('click')
    await flushPromises()

    expect(generateAll).toHaveBeenCalledWith('course-1', '')
  })

  it('讲义批量生成只承诺有当前教案的讲次', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45,
      sections: [{ section_node_id: `L2-${number}-1`, title: `${number}.1 核心内容` }],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: `arrangement-${number}`, lesson_unit_id: `L1-${number}`,
        source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授',
        status: 'confirmed', confirmed: true, source_state: 'current', blocks: [],
      },
      script: {
        current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: number === 1 ? 'plan-1' : '',
        source_state: 'current', ready: false, can_generate: number === 1,
        generation_unavailable_reason: number === 1 ? '' : 'revision_missing',
        confirmed: false, confirmed_at: '', sections: [],
      },
      plan: {
        lesson_unit_id: `L1-${number}`, working_revision_id: number === 1 ? 'plan-1' : '', confirmed_revision_id: '',
        source_state: 'current', ready: number === 1, revisions: [], ppt_assets: [],
      },
    })) as any
    const generateAll = vi.spyOn(lessonStore, 'generateAllScripts').mockResolvedValue({
      parent_job: { id: 'script-batch-1' }, jobs: [],
    } as any)

    const wrapper = mountWorkbench({ initialStage: 'script' })
    const preview = wrapper.get('[data-testid="script-course-preview"]')
    const button = wrapper.get('[data-testid="script-course-preview-generate"]')

    expect(preview.text()).toContain('教案待生成')
    expect(preview.text()).not.toContain('会自动跳过')
    expect(button.text()).toBe('生成已具备教案的讲义（1讲）')

    await button.trigger('click')
    await flushPromises()

    expect(generateAll).toHaveBeenCalledWith('course-1', '')
  })

  it('讲义批量启动失败在当前预览内反馈', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', number: 1, title: '第一讲', duration_minutes: 45, sections: [],
      arrangement: { source_state: 'current', blocks: [] },
      script: {
        current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1',
        source_state: 'current', ready: false, can_generate: true, confirmed: false, confirmed_at: '', sections: [],
      },
      plan: { lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: '', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
    }] as any
    vi.spyOn(lessonStore, 'generateAllScripts').mockImplementation(async () => {
      lessonStore.error = '生成条件已变化，请重试。'
      throw new Error('conflict')
    })

    const wrapper = mountWorkbench({ initialStage: 'script' })
    await wrapper.get('[data-testid="script-course-preview-generate"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('.workbench-error').text()).toContain('讲义生成未开始')
    expect(wrapper.get('.workbench-error').text()).toContain('生成条件已变化')
  })

  it('资料未就绪时讲义批量按钮显示禁用原因且不发起请求', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', number: 1, title: '第一讲', duration_minutes: 45, sections: [],
      arrangement: { source_state: 'current', blocks: [] },
      script: {
        current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1',
        source_state: 'current', ready: false, can_generate: true, confirmed: false, confirmed_at: '', sections: [],
      },
      plan: { lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: '', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
    }] as any
    const generateAll = vi.spyOn(lessonStore, 'generateAllScripts')
    const wrapper = mountWorkbench({ initialStage: 'script' })
    wrapper.findComponent({ name: 'CourseReferenceTray' }).vm.$emit('source-state-change', {
      busy: false, blocked: true, reason: '资料正在解析，完成后即可生成。',
    })
    await flushPromises()

    const button = wrapper.get('[data-testid="script-course-preview-generate"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('title')).toContain('资料正在解析')
    await button.trigger('click')
    expect(generateAll).not.toHaveBeenCalled()
  })

  it('旧讲义批次失败但当前无可生成讲次时不显示无效重试', () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', number: 1, title: '第一讲', duration_minutes: 45, sections: [],
      arrangement: { source_state: 'current', blocks: [] },
      script: {
        current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '',
        source_state: 'current', ready: false, can_generate: false, confirmed: false, confirmed_at: '', sections: [],
      },
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', ready: false, revisions: [], ppt_assets: [] },
    }] as any
    lessonStore.jobs = [{
      id: 'script-job-1', course_id: 'course-1', lesson_unit_id: 'L1-1', type: 'teacher_lesson_script_generation',
      status: 'failed', progress: 20, phase: 'lesson_script_failed', message: '本讲讲义生成失败', warnings: [],
      parent_job_id: 'script-batch-1', error: { code: 'lesson_script_generation_failed', message: '上游教案已变化', retryable: true },
    }] as any

    const wrapper = mountWorkbench({ initialStage: 'script' })

    expect(wrapper.get('.context-pane-heading').text()).toContain('上游教案已变化')
    expect(wrapper.find('.context-pane-heading .primary-status-action').exists()).toBe(false)
  })

  it('仅把真实可用的讲义计入完成，遗留修订标识不再显示勾选', () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45, sections: [],
      arrangement: { schema_version: 'teacher_lesson_arrangement_v1', revision_id: `arrangement-${number}`, lesson_unit_id: `L1-${number}`, source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授', status: 'confirmed', confirmed: true, source_state: 'current', blocks: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: `plan-${number}`, confirmed_revision_id: '', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
      script: {
        current_revision_id: number === 1 ? 'script-1' : 'legacy-fingerprint',
        confirmed_revision_id: '', source_lesson_plan_revision_id: `plan-${number}`, source_state: 'current',
        ready: number === 1, confirmed: false, confirmed_at: '', sections: [],
      },
    })) as any

    const wrapper = mountWorkbench({ initialStage: 'script' })
    const outline = wrapper.get('[data-testid="lesson-outline-fixed"]')
    const lessons = outline.findAll('.lesson-outline-chapter-button')

    expect(outline.get('header').text()).toContain('已完成 1/2')
    expect(lessons[0]!.find('.lesson-outline-status').attributes('data-state')).toBe('ready')
    expect(lessons[1]!.find('.lesson-outline-status').attributes('data-state')).toBe('pending')
    expect(lessons[1]!.text()).toContain('未生成')
    expect(lessons[1]!.find('.lesson-outline-status svg').exists()).toBe(false)
  })

  it('讲义批次同时显示逐讲状态与全课总进度', () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45, sections: [],
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: `plan-${number}`, source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: `plan-${number}`, confirmed_revision_id: '', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
    })) as any
    lessonStore.jobs = [{
      id: 'script-job-1', course_id: 'course-1', lesson_unit_id: 'L1-1', type: 'teacher_lesson_script_generation',
      status: 'running', progress: 50, phase: 'lesson_script_generation', message: '正在生成：概念讲解', warnings: [],
      parent_job_id: 'script-batch-1', batch_position: 1, batch_size: 2,
    }, {
      id: 'script-job-2', course_id: 'course-1', lesson_unit_id: 'L1-2', type: 'teacher_lesson_script_generation',
      status: 'pending', progress: 0, phase: 'queued', message: '等待生成', warnings: [],
      parent_job_id: 'script-batch-1', batch_position: 2, batch_size: 2,
    }] as any

    const wrapper = mountWorkbench({ initialStage: 'script' })
    const chapters = wrapper.findAll('.lesson-outline-chapter-button')

    expect(chapters[0]!.find('.lesson-outline-status').attributes('data-state')).toBe('generating')
    expect(chapters[0]!.find('small').text()).toContain('正在生成：概念讲解')
    expect(chapters[1]!.find('.lesson-outline-status').attributes('data-state')).toBe('queued')
    expect(wrapper.get('.context-pane-heading').text()).toContain('已完成 0/2 讲 · 正在并行生成 1 讲')
    expect(wrapper.get('.context-pane-heading__progress').attributes('aria-valuenow')).toBe('25')
    expect(wrapper.get('[data-testid="workflow-progress"]').text()).toBe('25')
  })

  it('旧质量报告只提供建议，不阻断从当前讲义进入 PPT', async () => {
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
        lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: 'current', ready: true, ppt_assets: [],
        revisions: [{ revision_id: 'plan-1', lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', generation_source: 'model', status: 'confirmed', warnings: [], plan: {}, actor: 'teacher', created_at: '' }],
      },
    }] as any

    const wrapper = mountWorkbench({ initialStage: 'ppt' })
    await flushPromises()
    expect(wrapper.get('.ppt-generate-primary').attributes('disabled')).toBeUndefined()
  })

  it('教案、讲义和 PPT 开始生成后显示双行讲次目录，正文不再出现小节 Tab', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45,
      sections: [1, 2].map(section => ({ section_node_id: `L2-${number}-${section}`, title: `${number}.${section} 小节${section}` })),
      script: { current_revision_id: number === 1 ? 'script-1' : '', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1', source_state: 'current', ready: number === 1, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: `plan-${number}`, confirmed_revision_id: number === 2 ? 'plan-2' : '', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
    })) as any
    for (const stage of ['lesson', 'script', 'ppt']) {
      const wrapper = mountWorkbench({ initialStage: stage })
      const outline = wrapper.get('[data-testid="lesson-outline-fixed"]')
      const chapterButtons = outline.findAll('.lesson-outline-chapter-button')

      expect(chapterButtons).toHaveLength(2)
      expect(chapterButtons.every(button => button.find('strong').exists() && button.find('small').exists())).toBe(true)
      expect(chapterButtons[0]!.find('strong').text()).toContain('第1讲')
      expect(chapterButtons.every(button => Boolean(button.find('small').text()))).toBe(true)
      expect(wrapper.find('.lesson-title-trigger').exists()).toBe(false)
      expect(wrapper.find('.lesson-outline-popover').exists()).toBe(false)
      expect(wrapper.find('.lesson-outline-sections').exists()).toBe(false)
      expect(wrapper.find('.lesson-selector').exists()).toBe(false)
      expect(wrapper.find('.lesson-section-tabs').exists()).toBe(false)
      expect(wrapper.find('.lesson-navigator .lesson-switch-actions').exists()).toBe(false)
      expect(wrapper.get('.lesson-switch-actions').text()).toContain('上一讲')
      expect(wrapper.get('.lesson-switch-actions').text()).toContain('下一讲')

      await chapterButtons[1]!.trigger('click')
      expect(wrapper.get('.lesson-current-title').text()).toContain('第2讲')
      expect(wrapper.get('.lesson-current-title').text()).toContain('2/2')
      if (stage === 'script') {
        expect(wrapper.get('[data-testid="script-single-start"]').text()).toContain('生成本讲讲义')
        expect(wrapper.get('[data-testid="script-batch-start"]').text()).toContain('生成剩余讲义')
      }
      wrapper.unmount()
    }
  })

  it('右侧资料随当前讲次切换且不会串到其他讲次', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45,
      sections: [{ section_node_id: `L2-${number}-1`, title: `${number}.1 小节` }],
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: `L1-${number}`, working_revision_id: number === 1 ? 'plan-1' : '', confirmed_revision_id: '', source_state: 'current', ready: number === 1, revisions: [], ppt_assets: [] },
    })) as any
    const wrapper = mountWorkbench({ initialStage: 'lesson' })
    const firstReference = { package_id: 'package-1', asset_id: 'asset-1', material_asset_id: 'mat-1', filename: '第一讲.docx', relative_path: '', size_bytes: 100, role: 'primary' }
    const secondReference = { package_id: 'package-1', asset_id: 'asset-2', material_asset_id: 'mat-2', filename: '第二讲.pdf', relative_path: '', size_bytes: 100, role: 'reference' }

    let tray = wrapper.findComponent({ name: 'CourseReferenceTray' })
    expect(tray.props('scopeTargetId')).toBe('lesson-plan:L1-1')
    expect(tray.props('scopeTargetLabel')).toBe('第1讲')
    tray.vm.$emit('update:modelValue', [firstReference])
    await flushPromises()

    await wrapper.findAll('.lesson-outline-chapter-button')[1]!.trigger('click')
    tray = wrapper.findComponent({ name: 'CourseReferenceTray' })
    expect(tray.props('scopeTargetId')).toBe('lesson-plan:L1-2')
    expect(tray.props('previousScopeTargetId')).toBe('lesson-plan:L1-1')
    expect(tray.props('modelValue')).toEqual([])
    tray.vm.$emit('update:modelValue', [secondReference])
    await flushPromises()

    await wrapper.findAll('.lesson-outline-chapter-button')[0]!.trigger('click')
    tray = wrapper.findComponent({ name: 'CourseReferenceTray' })
    expect(tray.props('scopeTargetId')).toBe('lesson-plan:L1-1')
    expect(tray.props('modelValue')).toEqual([firstReference])
  })

  it('资料未就绪时同时禁用教案与 PPT 生成，事件也不能绕过阻断', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'arrangement-1', lesson_unit_id: 'L1-1',
        source_outline_revision_id: 'outline-1', lesson_type: 'theory', lesson_type_label: '理论讲授',
        status: 'confirmed', confirmed: true, source_state: 'current',
        blocks: [{ block_id: 'block-1', module_id: 'core_explanation', section_node_id: 'L2-1-1', section_title: '基础概念', name: '概念讲解', role: 'concept', purpose: '建立概念', content_summary: '讲清边界', planned_minutes: 45, teacher_activity: '', student_activity: '', expected_output: '', required: true }],
      },
      script: { current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '', source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [] },
      plan: { lesson_unit_id: 'L1-1', working_revision_id: '', confirmed_revision_id: '', source_state: 'current', revisions: [], ppt_assets: [] },
    }, {
      lesson_unit_id: 'L1-2', source_outline_revision_id: 'outline-1', number: 2,
      title: '第二讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-2', working_revision_id: 'plan-2', confirmed_revision_id: '', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
    }] as any
    const generateLesson = vi.spyOn(lessonStore, 'generateLesson')
    const lessonWrapper = mountWorkbench({ initialStage: 'lesson' })
    lessonWrapper.findComponent({ name: 'CourseReferenceTray' }).vm.$emit('source-state-change', {
      busy: false, blocked: true, reason: '资料正在解析，完成后即可生成。',
    })
    await flushPromises()

    const lessonButton = lessonWrapper.get('[data-testid="lesson-single-start"]')
    expect(lessonButton.attributes('disabled')).toBeDefined()
    expect(lessonButton.attributes('title')).toContain('资料正在解析')
    await lessonButton.trigger('click')
    expect(generateLesson).not.toHaveBeenCalled()
    lessonWrapper.unmount()

    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', source_outline_revision_id: 'outline-1', number: 1,
      title: '第一讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
      script: { current_revision_id: 'script-1', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1', source_state: 'current', ready: true, confirmed: false, confirmed_at: '', sections: [] },
    }] as any
    const routePush = vi.spyOn(router, 'push').mockResolvedValue(undefined as any)
    const pptWrapper = mountWorkbench({ initialStage: 'ppt' })
    pptWrapper.findComponent({ name: 'CourseReferenceTray' }).vm.$emit('source-state-change', {
      busy: true, blocked: true, reason: '正在更新资料…',
    })
    await flushPromises()

    expect(pptWrapper.get('.ppt-generate-primary').attributes('disabled')).toBeDefined()
    pptWrapper.findComponent({ name: 'CourseReferenceTray' }).vm.$emit('regenerate-workflow')
    await flushPromises()
    expect(routePush).not.toHaveBeenCalled()
  })

  it('PPT 任务状态只投影到同一课程的当前讲次', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', number: 1, title: '第一讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
      script: { current_revision_id: 'script-1', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1', source_state: 'current', ready: true, confirmed: false, confirmed_at: '', sections: [] },
    }] as any
    const pptStore = useTeachingRepresentationsStore()
    pptStore.courseId = 'course-1'
    pptStore.teacherLessonId = 'L1-2'
    pptStore.building = true
    pptStore.buildProgress = 47

    const wrapper = mountWorkbench({ initialStage: 'ppt' })
    let tray = wrapper.findComponent({ name: 'CourseReferenceTray' })
    expect(tray.props('workflowState')).not.toBe('generating')

    pptStore.teacherLessonId = 'L1-1'
    await flushPromises()
    tray = wrapper.findComponent({ name: 'CourseReferenceTray' })
    expect(tray.props('workflowState')).toBe('generating')
    expect(tray.props('workflowProgress')).toBe(47)
  })

  it('从资料栏重新生成时经 SPA 返回 PPT 工作台，并携带一次性重建意图', async () => {
    const lessonStore = useTeacherLessonAuthoringStore()
    lessonStore.lessons = [{
      lesson_unit_id: 'L1-1', number: 1, title: '第一讲', duration_minutes: 45, sections: [],
      plan: { lesson_unit_id: 'L1-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: 'current', ready: true, revisions: [], ppt_assets: [] },
      script: { current_revision_id: 'script-1', confirmed_revision_id: '', source_lesson_plan_revision_id: 'plan-1', source_state: 'current', ready: true, confirmed: false, confirmed_at: '', sections: [] },
    }] as any
    const routePush = vi.spyOn(router, 'push').mockResolvedValue(undefined as any)
    const wrapper = mountWorkbench({ initialStage: 'ppt' })

    wrapper.findComponent({ name: 'CourseReferenceTray' }).vm.$emit('regenerate-workflow')
    await flushPromises()

    expect(routePush).toHaveBeenCalledWith({
      name: 'ppt-workspace',
      params: { courseId: 'course-1' },
      query: expect.objectContaining({
        lesson: 'L1-1',
        returnTo: expect.any(String),
        regenerate: '1',
      }),
    })
  })
})
