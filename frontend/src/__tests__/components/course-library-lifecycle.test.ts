import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessageBox } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import CourseLibraryView from '@/views/CourseLibraryView.vue'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/courses', name: 'course-library', component: CourseLibraryView },
    { path: '/teacher-course-space', name: 'teacher-course-space', component: { template: '<div />' } },
    { path: '/course/:courseId/workspace/:mode', name: 'course-workspace', component: { template: '<div />' } },
    { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: { template: '<div />' } },
  ],
})

const GenerationDialogStub = defineComponent({
  props: { modelValue: Boolean, busy: Boolean },
  emits: ['generate', 'update:modelValue'],
  template: '<button v-if="modelValue" class="generate-now" @click="$emit(\'generate\', { subject: \'微积分\', options: {} })">generate</button>',
})

describe('CourseLibraryView generation lifecycle', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    await router.push('/courses')
    await router.isReady()
  })

  it('零课程时保持一致的课程库框架并展示空状态', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = []
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.get('.library-header h1').text()).toBe('选择一门课程继续学习')
    expect(wrapper.get('.library-header p').text()).toBe('课程库')
    expect(wrapper.classes()).not.toContain('course-library--empty')
    expect(wrapper.find('.library-toolbar').exists()).toBe(true)
    expect(wrapper.get('.library-state').text()).toContain('还没有课程')
  })

  it('将继续学习入口合并进搜索工具栏并保留正确跳转', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{
      course_id: 'course-resume',
      course_name: 'Python 高级编程',
      node_count: 12,
      resume: {
        kind: 'practice',
        node_id: 'node-3-3',
        node_name: '3.3 默认参数与函数重载',
        activity_at: '2026-08-11T10:00:00Z',
      },
    } as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('.resume-card').exists()).toBe(false)
    expect(wrapper.get('input[type="search"]').attributes('aria-label')).toBe('搜索课程')
    expect(wrapper.get('.library-toolbar .library-resume__title').text()).toBe('《Python 高级编程》')
    expect(wrapper.get('.library-resume__location').text()).toBe('3.3 默认参数与函数重载')

    await wrapper.get('[data-testid="resume-course"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.courseId).toBe('course-resume')
  })

  it('已发布的质量建议不占用待处理任务角标', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-1', course_name: '世界模型', node_count: 20 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)
    const task = generation.createTask('job-1', 'course-1', '世界模型')
    task.status = 'completed_with_warnings'
    task.progress = 100
    task.publicationAllowed = true
    task.recovery = {
      state: 'completed', can_resume: false, reason_code: 'already_published', reason: 'done',
      checkpoint: { phase: 'completed', completed_nodes: 20, total_nodes: 20, draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [] },
    }

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('可以学习，有优化建议')
    expect(wrapper.text()).not.toContain('20 个学习节点')
    expect(wrapper.find('.action-count').exists()).toBe(false)
    expect(wrapper.find('.generation-progress').exists()).toBe(false)
  })

  it('把题库管理收进每门课程的更多操作菜单', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-review', course_name: '热力学', node_count: 12 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="open-question-bank-review-course-review"]').exists()).toBe(false)
    const menuTrigger = wrapper.get('[data-testid="course-actions-course-review"]')
    expect(menuTrigger.attributes('aria-expanded')).toBe('false')
    await menuTrigger.trigger('click')

    expect(menuTrigger.attributes('aria-expanded')).toBe('true')
    const reviewButton = wrapper.get('[data-testid="open-question-bank-review-course-review"]')
    expect(reviewButton.text()).toContain('题库管理')
    await reviewButton.trigger('click')
    await flushPromises()

    const workbench = wrapper.getComponent({ name: 'CourseWorkbench' })
    expect(workbench.props('modelValue')).toBe(true)
    expect(workbench.props('initialSection')).toBe('question-bank')
    expect(workbench.props('courseId')).toBe('course-review')
    expect(wrapper.find('[data-testid="course-menu-course-review"]').exists()).toBe(false)
  })

  it('把删除课程放在更多操作菜单的危险操作区', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-delete', course_name: '离散数学', node_count: 9 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    const deleteCourse = vi.spyOn(courses, 'deleteCourse').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="course-actions-course-delete"]').trigger('click')
    const deleteButton = wrapper.get('[data-testid="delete-course-course-delete"]')
    expect(deleteButton.text()).toContain('删除课程')
    await deleteButton.trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledOnce()
    expect(deleteCourse).toHaveBeenCalledWith('course-delete')
  })

  it('每页最多展示九门课程，并提供完整的翻页与跳转操作', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = Array.from({ length: 11 }, (_, index) => ({
      course_id: `course-${index + 1}`,
      course_name: `课程 ${index + 1}`,
      node_count: index + 1,
    }))
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.course-item')).toHaveLength(9)
    expect(wrapper.text()).toContain('课程 1')
    expect(wrapper.text()).not.toContain('课程 10')

    const pagination = wrapper.get('[aria-label="课程分页"]')
    expect(pagination.classes()).toContain('library-pagination-dock')
    expect((pagination.get('button[aria-label="上一页"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(pagination.get('button[aria-label="第 1 页"]').attributes('aria-current')).toBe('page')

    await pagination.get('button[aria-label="下一页"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.course-item')).toHaveLength(2)
    expect(wrapper.text()).toContain('课程 10')
    expect(wrapper.text()).toContain('课程 11')
    expect(wrapper.text()).not.toContain('课程 9')
    const secondPagePagination = wrapper.get('[aria-label="课程分页"]')
    expect((secondPagePagination.get('button[aria-label="下一页"]').element as HTMLButtonElement).disabled).toBe(true)

    await secondPagePagination.get('input[aria-label="跳转页码"]').setValue('1')
    await secondPagePagination.get('form.pagination-jump').trigger('submit')
    await flushPromises()

    expect(wrapper.findAll('.course-item')).toHaveLength(9)
    expect(wrapper.text()).toContain('课程 1')
    expect(wrapper.get('button[aria-label="第 1 页"]').attributes('aria-current')).toBe('page')
  })

  it('只有一页课程时隐藏分页，并保持单张课程卡片为两列网格中的固定列宽', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-only', course_name: '单门课程', node_count: 1 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.course-item')).toHaveLength(1)
    expect(wrapper.get('.course-grid').attributes('data-layout')).toBe('responsive-three-column')
    expect(wrapper.find('[aria-label="课程分页"]').exists()).toBe(false)
  })

  it('按课程类别展示预制教材封面，并统一课程名称书名号', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [
      {
        course_id: 'course-humanities',
        course_name: '辩论：逻辑构建与实战技巧',
        node_count: 10,
        resume: {
          kind: 'practice',
          status: 'in_progress',
          node_id: 'node-1',
          node_name: '论点组织',
          activity_at: '2026-08-10T09:00:00Z',
        },
      },
      { course_id: 'course-medicine', course_name: '局部解剖学', node_count: 8 },
      { course_id: 'course-engineering', course_name: '控制学：从原理到系统设计', node_count: 6 },
      { course_id: 'course-math', course_name: '线性代数：理论与应用', node_count: 6 },
      { course_id: 'course-programming', course_name: 'Java：从原理到工业级实践', node_count: 6 },
      { course_id: 'course-general', course_name: 'Test Basic Course：理论框架与实践', node_count: 6 },
    ]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.get('.library-toolbar .library-resume__title').text()).toBe('《辩论：逻辑构建与实战技巧》')
    expect(wrapper.findAll('.course-copy h2').map(title => title.text())).toEqual([
      '《辩论：逻辑构建与实战技巧》',
      '《局部解剖学》',
      '《控制学：从原理到系统设计》',
      '《线性代数：理论与应用》',
      '《Java：从原理到工业级实践》',
      '《Test Basic Course：理论框架与实践》',
    ])
    expect(wrapper.text()).not.toContain('《《')
    expect(wrapper.get('[data-testid="course-cover-course-humanities"]').attributes('data-cover-preset')).toBe('humanities')
    expect(wrapper.get('[data-testid="course-cover-course-medicine"]').attributes('data-cover-preset')).toBe('medicine')
    expect(wrapper.get('[data-testid="course-cover-course-engineering"]').attributes('data-cover-preset')).toBe('engineering')
    expect(wrapper.get('[data-testid="course-cover-course-math"]').attributes('data-cover-preset')).toBe('mathematics')
    expect(wrapper.get('[data-testid="course-cover-course-programming"]').attributes('data-cover-preset')).toBe('programming')
    expect(wrapper.get('[data-testid="course-cover-course-general"]').attributes('data-cover-preset')).toBe('general')
  })

  it('新建课程后直接进入同一门课程的生成现场', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(courses, 'generateCourse').mockResolvedValue({
      jobId: 'job-live',
      courseId: 'course-live',
      courseName: '微积分',
    })
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: GenerationDialogStub,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="create-course-menu-trigger"]').trigger('click')
    await wrapper.get('[data-testid="create-blank-course"]').trigger('click')
    await wrapper.get('.generate-now').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('course-workspace')
    expect(router.currentRoute.value.params.courseId).toBe('course-live')
    expect(router.currentRoute.value.params.mode).toBe('build')
    expect(router.currentRoute.value.query.section).toBe('outline')
    expect(wrapper.findComponent({ name: 'CourseWorkbench' }).props('modelValue')).toBe(false)
  })

  it('Markdown 导入创建后台任务后打开任务中心而不是提前进入空课程', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(courses, 'importMarkdown').mockResolvedValue({
      job_id: 'import-job-1', course_id: 'course-import-1',
    } as any)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()
    const input = wrapper.get('input[type="file"]')
    const inputClick = vi.spyOn(input.element as HTMLInputElement, 'click')
    await wrapper.get('[data-testid="create-course-menu-trigger"]').trigger('click')
    await wrapper.get('[data-testid="import-markdown-course"]').trigger('click')
    expect(inputClick).toHaveBeenCalledOnce()

    const file = new File(['# 线性代数\n\n向量有大小和方向。'], 'linear.md', { type: 'text/markdown' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await flushPromises()

    expect(courses.importMarkdown).toHaveBeenCalledWith(file)
    expect(router.currentRoute.value.name).toBe('course-library')
    const workbench = wrapper.getComponent({ name: 'CourseWorkbench' })
    expect(workbench.props('modelValue')).toBe(true)
    expect(workbench.props('initialSection')).toBe('tasks')
    expect(workbench.props('courseId')).toBe('course-import-1')
  })

  it('将跨课程入口移入全局顶栏，并在课程工具栏提供分段新建入口', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)
    const runningTask = generation.createTask('job-running', 'course-running', '进行中的课程')
    runningTask.status = 'running'
    const reviewTask = generation.createTask('job-needs-attention', 'course-review', '等待确认的课程')
    reviewTask.status = 'waiting_for_review'

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: GenerationDialogStub,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('.library-actions .task-center-button').exists()).toBe(false)
    expect(wrapper.find('.library-actions .import-button').exists()).toBe(false)
    expect(wrapper.find('.library-global-actions .task-center-button').exists()).toBe(true)
    expect(wrapper.get('[data-testid="open-course-workbench"]').text()).toContain('课程工作台')
    expect(wrapper.get('.library-global-actions .action-count').text()).toBe('1')
    expect(wrapper.find('.library-header [data-testid="create-course-menu-trigger"]').exists()).toBe(true)
    expect(wrapper.find('.library-header [data-testid="create-blank-course-trigger"]').exists()).toBe(true)
    expect(wrapper.find('.library-toolbar [data-testid="create-course-menu-trigger"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="create-course-menu-trigger"]').attributes('aria-expanded')).toBe('false')

    await wrapper.get('[data-testid="create-blank-course-trigger"]').trigger('click')
    expect(wrapper.find('.generate-now').exists()).toBe(true)

    await wrapper.get('[data-testid="create-course-menu-trigger"]').trigger('click')

    expect(wrapper.get('[data-testid="create-course-menu-trigger"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-testid="create-blank-course"]').text()).toContain('新建空白课程')
    expect(wrapper.get('[data-testid="import-markdown-course"]').text()).toContain('导入 Markdown')

    await wrapper.get('.library-global-actions .task-center-button').trigger('click')
    const workbench = wrapper.getComponent({ name: 'CourseWorkbench' })
    expect(workbench.props('modelValue')).toBe(true)
    expect(workbench.props('initialSection')).toBe('tasks')
  })

  it('移除全局教师文件空间并保留统一任务入口', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="open-teacher-course-space"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="switch-to-teacher-surface"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="open-course-workbench"]').exists()).toBe(true)
  })

  it('opens a published course in the unified setup workspace', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-ready', course_name: '矩阵与线性变换', node_count: 12 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    await router.push('/courses')
    const wrapper = mount(CourseLibraryView, {
      global: {
        plugins: [router],
        stubs: {
          CourseGenerationDialog: true,
          CourseWorkbench: true,
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('.course-main').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('course-workspace')
    expect(router.currentRoute.value.params.courseId).toBe('course-ready')
    expect(router.currentRoute.value.params.mode).toBe('setup')
    expect(router.currentRoute.value.query.section).toBe('basic')
    wrapper.unmount()
  })
})
