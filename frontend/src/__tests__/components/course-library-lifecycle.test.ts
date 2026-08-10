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
    { path: '/course/:courseId/learn', name: 'learning', component: { template: '<div />' } },
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

    const reviewCenter = wrapper.getComponent({ name: 'QuestionBankReviewCenter' })
    expect(reviewCenter.props('modelValue')).toBe(true)
    expect(reviewCenter.props('courseId')).toBe('course-review')
    const taskCenter = wrapper.getComponent({ name: 'CourseTaskCenter' })
    expect(taskCenter.props('modelValue')).toBe(false)
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

  it('每页最多展示六门课程，并提供完整的翻页与跳转操作', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = Array.from({ length: 8 }, (_, index) => ({
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
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.course-item')).toHaveLength(6)
    expect(wrapper.text()).toContain('课程 1')
    expect(wrapper.text()).not.toContain('课程 7')

    const pagination = wrapper.get('[aria-label="课程分页"]')
    expect(pagination.classes()).toContain('library-pagination-dock')
    expect(pagination.get('button[aria-label="上一页"]').attributes('disabled')).toBeDefined()
    expect(pagination.get('button[aria-label="第 1 页"]').attributes('aria-current')).toBe('page')

    await pagination.get('button[aria-label="下一页"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.course-item')).toHaveLength(2)
    expect(wrapper.text()).toContain('课程 7')
    expect(wrapper.text()).toContain('课程 8')
    expect(wrapper.text()).not.toContain('课程 1')
    expect(pagination.get('button[aria-label="下一页"]').attributes('disabled')).toBeDefined()

    await pagination.get('input[aria-label="跳转页码"]').setValue('1')
    await pagination.get('button[aria-label="跳转"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.course-item')).toHaveLength(6)
    expect(wrapper.text()).toContain('课程 1')
    expect(pagination.get('button[aria-label="第 1 页"]').attributes('aria-current')).toBe('page')
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
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.course-item')).toHaveLength(1)
    expect(wrapper.get('.course-grid').attributes('data-layout')).toBe('two-column')
    expect(wrapper.find('[aria-label="课程分页"]').exists()).toBe(false)
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

    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.params.courseId).toBe('course-live')
    expect(wrapper.findComponent({ name: 'CourseTaskCenter' }).props('modelValue')).toBe(false)
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
    const taskCenter = wrapper.getComponent({ name: 'CourseTaskCenter' })
    expect(taskCenter.props('modelValue')).toBe(true)
    expect(taskCenter.props('courseId')).toBe('course-import-1')
  })

  it('将跨课程入口移入全局顶栏，并只在页面标题区保留新建课程菜单', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)
    const task = generation.createTask('job-needs-attention', 'course-running', '进行中的课程')
    task.status = 'running'

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

    expect(wrapper.find('.library-actions .task-center-button').exists()).toBe(false)
    expect(wrapper.find('.library-actions .import-button').exists()).toBe(false)
    expect(wrapper.find('.library-global-actions .task-center-button').exists()).toBe(true)
    expect(wrapper.get('.library-global-actions .action-count').text()).toBe('1')
    expect(wrapper.get('[data-testid="create-course-menu-trigger"]').attributes('aria-expanded')).toBe('false')

    await wrapper.get('[data-testid="create-course-menu-trigger"]').trigger('click')

    expect(wrapper.get('[data-testid="create-course-menu-trigger"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-testid="create-blank-course"]').text()).toContain('新建空白课程')
    expect(wrapper.get('[data-testid="import-markdown-course"]').text()).toContain('导入 Markdown')

    await wrapper.get('.library-global-actions .task-center-button').trigger('click')
    expect(wrapper.getComponent({ name: 'CourseTaskCenter' }).props('modelValue')).toBe(true)
  })

  it('从全局顶栏进入教师文件空间', async () => {
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
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="open-teacher-course-space"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('teacher-course-space')
  })

  it('opens a published course directly in the learning workspace', async () => {
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
          CourseTaskCenter: true,
          QuestionBankReviewCenter: true,
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('.course-main').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.params.courseId).toBe('course-ready')
    wrapper.unmount()
  })
})
