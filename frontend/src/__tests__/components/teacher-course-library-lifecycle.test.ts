import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessageBox } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import CourseLibraryView from '@/views/TeacherCourseLibraryView.vue'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'
import { setLocale } from '@/shared/i18n'
import zhMessages from '../../../public/locales/zh/translation.json'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/teacher/courses', name: 'teacher-course-library', component: CourseLibraryView },
    { path: '/teacher-course-space', name: 'teacher-course-space', component: { template: '<div />' } },
    { path: '/teacher/teaching-calendar', name: 'teacher-teaching-calendar', component: { template: '<div />' } },
    { path: '/teacher/courses/new', name: 'teacher-course-create', component: { template: '<div />' } },
    { path: '/teacher/course/:courseId/overview', name: 'teacher-course-overview', component: { template: '<div />' } },
    { path: '/teacher/course/:courseId/production', name: 'teacher-course-production', component: { template: '<div />' } },
    { path: '/course/:courseId/workspace/:mode', name: 'course-workspace', component: { template: '<div />' } },
    { path: '/course/:courseId/learn', name: 'learning', component: { template: '<div />' } },
  ],
})

describe('CourseLibraryView generation lifecycle', () => {
  beforeAll(async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => zhMessages }))
    await setLocale('zh')
  })

  afterAll(() => {
    vi.unstubAllGlobals()
  })

  beforeEach(async () => {
    setActivePinia(createPinia())
    localStorage.removeItem('teacher_course_library_view')
    await router.push('/teacher/courses')
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

    expect(wrapper.find('.library-header').exists()).toBe(false)
    expect(wrapper.classes()).not.toContain('course-library--empty')
    expect(wrapper.find('.library-toolbar').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="按备课状态筛选课程"]').exists()).toBe(true)
    expect(wrapper.find('.library-status-filters').exists()).toBe(false)
    expect(wrapper.get('.library-state').text()).toContain('还没有课程')
  })

  it('不再把学生继续学习入口放进教师课程工作台，并从课程卡进入课程概览', async () => {
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
    expect(wrapper.get('input[type="search"]').attributes('aria-label')).toBe('搜索课程名称或代码')
    expect(wrapper.find('.library-resume').exists()).toBe(false)
    expect(wrapper.find('.teacher-asset-summary').exists()).toBe(false)

    await wrapper.get('.course-main').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('course-workspace')
    expect(router.currentRoute.value.params.courseId).toBe('course-resume')
    expect(router.currentRoute.value.query.returnTo).toBe('/courses?view=courses')
  })

  it('把新建空课程归入正在备课，并提供开始备课入口', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{
      course_id: 'course-draft',
      course_name: '空白课程',
      node_count: 0,
      course_status: 'draft',
      authoring_surface: 'teacher',
      is_published: false,
      updated_at: '2026-08-22T10:00:00Z',
    }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: { plugins: [router], stubs: { CourseGenerationDialog: true, CourseWorkbench: true, Teleport: true } },
    })
    await flushPromises()

    expect(wrapper.get('.course-status').text()).toContain('正在备课')
    expect(wrapper.find('.teacher-asset-summary').exists()).toBe(false)
    expect(wrapper.get('.course-primary-action').text()).toContain('开始备课')
    const statusMenu = wrapper.get('[data-testid="course-status-filter"]')
    expect(statusMenu.text()).toContain('状态全部课程1')
    await statusMenu.get('.ui-select-menu__trigger').trigger('click')
    expect(statusMenu.findAll('[role="option"]').map(option => option.text())).toEqual([
      '全部课程1', '待处理0', '备课中1', '备课完成0',
    ])

    await statusMenu.get('[data-option-value="prepared"]').trigger('click')
    expect(wrapper.find('.course-item').exists()).toBe(false)
    expect(wrapper.get('.library-state').text()).toContain('调整搜索词、学期或课程状态')
  })

  it('课程卡片只保留备课状态、上课时间和地点', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{
      course_id: 'course-scheduled',
      course_name: '矩阵与线性变换',
      node_count: 12,
      academic_year: '2026-2027',
      term: '秋季',
      course_code: 'MATH-221',
      is_published: true,
      next_session: {
        session_id: 'session-7',
        sequence: 7,
        date: '2026-08-25',
        start_time: '14:00:00',
        end_time: '15:35:00',
        content_summary: '特征向量：变换中不转向的方向',
        location: '理科楼 A108',
      },
    }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: { plugins: [router], stubs: { CourseGenerationDialog: true, CourseWorkbench: true, Teleport: true } },
    })
    await flushPromises()

    expect(wrapper.get('.course-grid').attributes('data-view')).toBe('grid')
    expect(wrapper.find('.course-list-columns').exists()).toBe(false)
    expect(wrapper.get('.course-identity__meta').text()).toContain('MATH-221')
    expect(wrapper.get('.course-status').text()).toContain('备课完成')
    expect(wrapper.get('.course-time').text()).toContain('14:00')
    expect(wrapper.get('.course-location').text()).toContain('理科楼 A108')
    expect(wrapper.find('.course-readiness').exists()).toBe(false)
    expect(wrapper.find('.course-updated').exists()).toBe(false)
    expect(wrapper.find('.teacher-asset-summary').exists()).toBe(false)
    expect(wrapper.get('.course-primary-action').text()).toContain('准备下次课')
  })

  it('列表模式展示学期、版本、上课时间和地点，并可按代码和学期筛选', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [
      {
        course_id: 'course-math', course_name: '矩阵与线性变换', node_count: 12,
        academic_year: '2026-2027', term: '秋季', course_code: 'MATH-221', is_published: true,
        updated_at: '2026-08-24T10:00:00Z', current_course_version_id: 'cv3',
        next_session: {
          session_id: 'session-math', sequence: 3, date: '2026-09-02', start_time: '10:00', end_time: '11:35',
          content_summary: '特征向量', location: '理科楼 A108',
        },
      },
      {
        course_id: 'course-ai', course_name: '人工智能导论', node_count: 16,
        academic_year: '2025-2026', term: '春夏', course_code: 'AI-101', is_published: true,
        updated_at: '2026-06-10T10:00:00Z',
      },
    ]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    const wrapper = mount(CourseLibraryView, {
      global: { plugins: [router], stubs: { CourseWorkbench: true, Teleport: true } },
    })
    await flushPromises()

    await wrapper.get('button[title="列表"]').trigger('click')
    expect(wrapper.get('.course-list-columns').text()).toContain('课程版本')
    expect(wrapper.get('.course-list-columns').text()).toContain('上课地点')
    expect(wrapper.get('.course-grid').attributes('data-view')).toBe('list')
    expect(wrapper.findAll('.course-item')).toHaveLength(2)
    expect(wrapper.findAll('.course-version')[0]!.text()).toContain('V3')
    expect(wrapper.findAll('.course-location')[0]!.text()).toContain('理科楼 A108')

    await wrapper.get('input[type="search"]').setValue('AI-101')
    expect(wrapper.findAll('.course-item')).toHaveLength(1)
    expect(wrapper.get('.course-identity h2').text()).toContain('人工智能导论')

    await wrapper.get('input[type="search"]').setValue('')
    const termMenu = wrapper.get('[data-testid="course-term-filter"]')
    await termMenu.get('.ui-select-menu__trigger').trigger('click')
    const targetOption = termMenu.findAll('[role="option"]').find(option => option.text() === '2026-2027 秋季')
    expect(targetOption).toBeTruthy()
    await targetOption!.trigger('click')
    expect(wrapper.findAll('.course-item')).toHaveLength(1)
    expect(wrapper.get('.course-identity h2').text()).toContain('矩阵与线性变换')
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

    expect(wrapper.text()).toContain('备课完成')
    expect(wrapper.text()).not.toContain('20 个学习节点')
    expect(wrapper.find('.action-count').exists()).toBe(false)
    expect(wrapper.find('.generation-progress').exists()).toBe(false)
  })

  it('课程更多操作不再暴露独立题库管理页', async () => {
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
    expect(wrapper.find('[data-testid="open-question-bank-review-course-review"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="course-menu-course-review"]').text()).not.toContain('题库管理')
  })

  it('主操作直接进入课程工作台，更多菜单只保留低频危险操作', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-authoring', course_name: '设计思维', node_count: 18 }]
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
          Teleport: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="course-actions-course-authoring"]').trigger('click')
    expect(wrapper.find('[data-testid="open-course-production-course-authoring"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="course-menu-course-authoring"]').text()).toContain('删除课程')

    await wrapper.get('.course-primary-action').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('course-workspace')
    expect(router.currentRoute.value.params.courseId).toBe('course-authoring')
    expect(router.currentRoute.value.query.returnTo).toBe('/courses?view=courses')
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

  it('每页最多展示九门课程，并提供简洁的翻页操作', async () => {
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

    expect(secondPagePagination.find('input[aria-label="跳转页码"]').exists()).toBe(false)
    await secondPagePagination.get('button[aria-label="第 1 页"]').trigger('click')
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

    expect(wrapper.find('.library-resume').exists()).toBe(false)
    expect(wrapper.findAll('.course-identity h2').map(title => title.text())).toEqual([
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

  it('opens a published course in the unified course workbench', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    courses.courseList = [{ course_id: 'course-ready', course_name: '矩阵与线性变换', node_count: 12 }]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)

    await router.push('/teacher/courses')
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
    expect(router.currentRoute.value.query.returnTo).toBe('/courses?view=courses')
    wrapper.unmount()
  })
})
