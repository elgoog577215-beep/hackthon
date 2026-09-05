import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
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
    { path: '/courses', name: 'course-library', component: CourseLibraryView },
    { path: '/course/:courseId/workspace/:mode', name: 'course-workspace', component: { template: '<div />' } },
  ],
})

const course = (id: string, overrides: Record<string, unknown> = {}) => ({
  course_id: id,
  course_name: `课程 ${id}`,
  node_count: 8,
  academic_year: '2026-2027',
  term: '秋季',
  course_code: `CODE-${id}`,
  preparation_state: 'preparing',
  updated_at: '2026-09-01T10:00:00Z',
  ...overrides,
})

function mountLibrary(): VueWrapper {
  const generation = useGenerationStore()
  vi.spyOn(generation, 'restoreGenerationState').mockReturnValue(null)
  return mount(CourseLibraryView, {
    global: { plugins: [router], stubs: { Teleport: true } },
  })
}

describe('teacher course library management', () => {
  beforeAll(async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => zhMessages }))
    await setLocale('zh')
  })

  afterAll(() => vi.unstubAllGlobals())

  beforeEach(async () => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
    await router.replace('/courses')
    await router.isReady()
  })

  it('用单一数据表直接呈现课程管理信息，不再保留卡片、视图切换和三点菜单', async () => {
    const courses = useCourseStore()
    courses.courseList = [course('math', {
      course_name: '矩阵与线性变换',
      course_code: 'MATH-221',
      preparation_state: 'prepared',
      preparation_summary: {
        planned_lessons: 8,
        outline_ready: true,
        ready_lesson_plans: 8,
        ready_handouts: 8,
        ready_ppts: 8,
      },
      next_session: {
        session_id: 'session-7', sequence: 7, date: '2026-09-08', start_time: '14:00:00',
        end_time: '15:35:00', content_summary: '特征向量', location: '理科楼 A108',
      },
    }) as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()

    expect(wrapper.find('table.course-table').exists()).toBe(true)
    expect(wrapper.find('.course-grid').exists()).toBe(false)
    expect(wrapper.find('.library-view-control').exists()).toBe(false)
    expect(wrapper.find('[aria-haspopup="menu"]').exists()).toBe(false)
    expect(wrapper.get('thead').text()).toContain('课程')
    expect(wrapper.get('thead').text()).toContain('备课状态')
    expect(wrapper.get('thead').text()).toContain('上课时间')
    expect(wrapper.get('thead').text()).toContain('学年学期')
    expect(wrapper.get('thead').text()).toContain('最后编辑')
    expect(wrapper.findAll('.column-sort').map(node => node.attributes('aria-label'))).toEqual([
      '按课程排序', '按备课状态排序', '按上课时间排序', '按学年学期排序', '按最后编辑排序',
    ])
    expect(wrapper.get('tbody').text()).toContain('《矩阵与线性变换》')
    expect(wrapper.get('.course-production-summary').text()).toBe('备课完成')
    expect(wrapper.find('.asset-progress').exists()).toBe(false)
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    expect(wrapper.get('tbody').text()).toContain('备课完成')
    expect(wrapper.get('tbody').text()).toContain('14:00')
    expect(wrapper.get('tbody').text()).toContain('理科楼 A108')
    expect(wrapper.get('tbody').text()).toContain('2026-2027 秋季')
    expect(wrapper.get('[data-testid="delete-course-math"]').attributes('title')).toBe('删除课程')
  })

  it('课程行只显示备课两态，并直接进入对应生产阶段', async () => {
    const courses = useCourseStore()
    courses.courseList = [course('active', {
      course_name: '线性代数',
      preparation_summary: {
        planned_lessons: 3,
        outline_ready: true,
        ready_lesson_plans: 1,
        ready_handouts: 0,
        ready_ppts: 0,
        current_production: {
          target: 'lesson_plan',
          status: 'running',
          completed: 1,
          total: 3,
          failed: 0,
          progress: 50,
          message: '正在生成第 2 讲教案',
        },
      },
    }) as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()

    expect(wrapper.get('.course-production-summary').text()).toBe('备课中')
    expect(wrapper.find('.course-production-detail').exists()).toBe(false)
    expect(wrapper.find('.course-task').exists()).toBe(false)
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    expect(wrapper.get('.course-action').text()).toContain('查看进度')

    await wrapper.get('.course-action').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('course-workspace')
    expect(router.currentRoute.value.params.courseId).toBe('active')
    expect(router.currentRoute.value.query.stage).toBe('lesson')
  })

  it('大纲暂停时仍保持课程两态并进入大纲阶段', async () => {
    const courses = useCourseStore()
    courses.courseList = [course('outline-waiting', { course_name: 'UI 设计' }) as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    const task = useGenerationStore().createTask('job-outline-waiting', 'outline-waiting', 'UI 设计')
    task.taskType = 'teacher_outline_generation'
    task.status = 'waiting_for_input'
    task.currentPhase = 'outline_shape_ready'

    const wrapper = mountLibrary()
    await flushPromises()

    expect(wrapper.get('.course-production-summary').text()).toBe('备课中')
    expect(wrapper.find('.course-production-detail').exists()).toBe(false)
    expect(wrapper.get('.course-action').text()).toContain('查看进度')
    await wrapper.get('.course-action').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.stage).toBe('foundation')
  })

  it('课程汇总中的大纲等待状态不扩张课程主状态', async () => {
    const courses = useCourseStore()
    courses.courseList = [course('outline-summary-waiting', {
      course_name: 'UI 设计',
      preparation_summary: {
        planned_lessons: 16,
        current_production: {
          target: 'outline',
          status: 'waiting_for_input',
          completed: 16,
          total: 16,
          failed: 0,
          progress: 35,
          message: '轻量讲次方案已生成',
        },
      },
    }) as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()

    expect(wrapper.get('.course-production-summary').text()).toBe('备课中')
    expect(wrapper.find('.course-production-detail').exists()).toBe(false)
    expect(wrapper.get('.course-action').text()).toContain('查看进度')
    await wrapper.get('.course-action').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.stage).toBe('foundation')
  })

  it.each([
    ['waiting_for_input', 'provide_input'],
    ['waiting_for_review', 'review_generation'],
  ] as const)('优先定位保留 last-good 的 %s 阶段', async (taskState, action) => {
    const courses = useCourseStore()
    const stage = (overrides: Record<string, unknown> = {}) => ({
      display_state: 'available', task_state: 'completed', availability: 'usable', source_state: 'current',
      latest_attempt_failed: false, update_required: false, task_ids: [], action_targets: {}, allowed_actions: [],
      counts: { total: 2, available: 2, generating: 0, failed: 0, stale: 0 }, issues: [],
      ...overrides,
    })
    courses.courseList = [course(`script-${taskState}`, {
      course_production_state: {
        schema_version: 'course_production_state_v1', course_id: `script-${taskState}`, preparation_state: 'preparing',
        stages: {
          outline: stage({ counts: { total: 1, available: 1, generating: 0, failed: 0, stale: 0 } }),
          lesson_plan: stage(),
          script: stage({
            task_state: taskState,
            task_ids: ['script-waiting'],
            action_targets: { [action]: ['script-waiting'] },
            allowed_actions: [action],
          }),
          ppt: stage({ display_state: 'not_generated', task_state: 'idle', availability: 'missing', source_state: 'missing', counts: { total: 2, available: 0, generating: 0, failed: 0, stale: 0 } }),
        },
        lessons: [], issues: [],
      },
    }) as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()

    expect(wrapper.find('.course-production-detail').exists()).toBe(false)
    expect(wrapper.get('.course-action').text()).toContain('查看进度')
    await wrapper.get('.course-action').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.stage).toBe('script')
  })

  it('新投影优先保留整课 15/16，last-good 失败只导航定位且不发写请求', async () => {
    const courses = useCourseStore()
    const stage = (display_state: string, total: number, available: number, extra: Record<string, unknown> = {}) => ({
      display_state,
      task_state: 'idle',
      availability: available > 0 ? 'usable' : 'missing',
      source_state: 'current',
      latest_attempt_failed: false,
      update_required: false,
      counts: { total, available, generating: 0, failed: 0, stale: 0 },
      issues: [],
      ...extra,
    })
    const issue = {
      issue_id: 'lesson-plan-L1-16-task-16',
      stage: 'lesson_plan',
      lesson_unit_id: 'L1-16',
      block_id: 'block-3',
      task_id: 'task-16',
      code: 'generation_failed',
      summary: '第 16 讲知识骨架生成失败，请检查来源后重试。',
      recovery: { action: 'retry_generation', automatic: false, requires_confirmation: true },
    }
    courses.courseList = [course('projection', {
      preparation_summary: {
        planned_lessons: 16,
        current_production: { target: 'lesson_plan', status: 'failed', completed: 0, total: 1, failed: 1 },
      },
      course_production_state: {
        schema_version: 'course_production_state_v1',
        course_id: 'projection',
        preparation_state: 'preparing',
        stages: {
          outline: stage('available', 1, 1),
          lesson_plan: stage('available', 16, 15, { latest_attempt_failed: true, issues: [issue] }),
          script: stage('not_generated', 16, 0),
          ppt: stage('not_generated', 16, 0),
        },
        lessons: [],
        issues: [issue],
      },
    }) as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockClear()

    expect(wrapper.get('.course-production-summary').text()).toBe('备课中')
    expect(wrapper.find('.course-production-detail').exists()).toBe(false)
    expect(wrapper.get('.course-action').text()).toContain('处理问题')
    await wrapper.get('.course-action').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toMatchObject({
      stage: 'lesson', lesson: 'L1-16', block: 'block-3', task: 'task-16',
      issue: 'lesson-plan-L1-16-task-16', expandIssue: '1',
    })
    const writeMethods = fetchMock.mock.calls
      .map(([, options]) => String(options?.method || 'GET').toUpperCase())
      .filter(method => ['POST', 'PATCH', 'PUT', 'DELETE'].includes(method))
    expect(writeMethods).toEqual([])
  })

  it('不把 issues 数组顺序当优先级，优先定位可重试问题', async () => {
    const courses = useCourseStore()
    const stage = (display_state: string, total: number, available: number, issues: any[] = []) => ({
      display_state, task_state: 'idle', availability: available > 0 ? 'usable' : 'missing', source_state: 'current',
      latest_attempt_failed: false, update_required: false,
      counts: { total, available, generating: 0, failed: 0, stale: 0 }, issues,
    })
    const inspectIssue = {
      issue_id: 'inspect-first', stage: 'outline', lesson_unit_id: '', blocking: false, code: 'review_source', summary: '先检查来源',
      recovery: { action: 'inspect_failure', automatic: false, requires_confirmation: true },
    }
    const retryIssue = {
      issue_id: 'retry-second', stage: 'lesson_plan', lesson_unit_id: 'L1-2', task_id: 'task-2', blocking: true, code: 'generation_failed', summary: '第 2 讲可重试',
      recovery: { action: 'retry_generation', automatic: false, requires_confirmation: true },
    }
    courses.courseList = [course('priority', {
      course_production_state: {
        schema_version: 'course_production_state_v1', course_id: 'priority', preparation_state: 'preparing',
        stages: {
          outline: stage('available', 1, 1, [inspectIssue]),
          lesson_plan: stage('available', 2, 1, [retryIssue]),
          script: stage('not_generated', 2, 0),
          ppt: stage('not_generated', 2, 0),
        },
        lessons: [], issues: [inspectIssue, retryIssue],
      },
    }) as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()
    await wrapper.get('.course-action').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toMatchObject({
      stage: 'lesson', lesson: 'L1-2', task: 'task-2', issue: 'retry-second', expandIssue: '1',
    })
  })

  it('停留在我的课程时静默刷新生成进度，离开页面后停止', async () => {
    vi.useFakeTimers()
    let wrapper: VueWrapper | null = null
    try {
      vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
      const courses = useCourseStore()
      courses.courseList = [course('active') as any]
      const fetchCourses = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
      wrapper = mountLibrary()
      await flushPromises()

      expect(fetchCourses).toHaveBeenCalledWith({ surface: 'teacher' })
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(fetchCourses).toHaveBeenLastCalledWith({ surface: 'teacher', background: true })

      wrapper.unmount()
      wrapper = null
      const callsAfterUnmount = fetchCourses.mock.calls.length
      await vi.advanceTimersByTimeAsync(5000)
      expect(fetchCourses).toHaveBeenCalledTimes(callsAfterUnmount)
    } finally {
      wrapper?.unmount()
      vi.useRealTimers()
    }
  })

  it('支持搜索、表头排序，并把当前筛选和排序带回课程入口', async () => {
    const courses = useCourseStore()
    courses.courseList = [
      course('z', { course_name: '线性代数', course_code: 'MATH-2', updated_at: '2026-09-02T10:00:00Z' }) as any,
      course('a', { course_name: '人工智能导论', course_code: 'AI-101', updated_at: '2026-08-02T10:00:00Z' }) as any,
    ]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()

    await wrapper.get('input[type="search"]').setValue('AI-101')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.get('tbody').text()).toContain('人工智能导论')

    await wrapper.get('input[type="search"]').setValue('')
    await wrapper.findAll('.column-sort')[0]!.trigger('click')
    expect(wrapper.findAll('.course-identity strong').map(node => node.text())).toEqual([
      '《人工智能导论》', '《线性代数》',
    ])

    await wrapper.findAll('.course-main')[0]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('course-workspace')
    expect(router.currentRoute.value.params.courseId).toBe('a')
    expect(router.currentRoute.value.query.returnTo).toBe('/courses?view=courses&sort=name&dir=ascending')
  })

  it('支持逐门选择、全选和部分选中，并可明确取消选择', async () => {
    const courses = useCourseStore()
    courses.courseList = [course('1') as any, course('2') as any, course('3') as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()
    const headerCheckbox = wrapper.get('thead input[type="checkbox"]')
    const rowCheckboxes = wrapper.findAll('tbody input[type="checkbox"]')

    await rowCheckboxes[0]!.setValue(true)
    expect((headerCheckbox.element as HTMLInputElement).indeterminate).toBe(true)
    expect(wrapper.get('.selection-summary').text()).toBe('已选 1 门课程')

    await headerCheckbox.setValue(true)
    expect(wrapper.findAll('tbody input[type="checkbox"]').every(node => (node.element as HTMLInputElement).checked)).toBe(true)
    expect(wrapper.get('.selection-summary').text()).toBe('已选 3 门课程')

    await wrapper.get('.toolbar-button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.selection-summary').exists()).toBe(false)
    expect((wrapper.get('thead input[type="checkbox"]').element as HTMLInputElement).checked).toBe(false)
  })

  it('单门删除使用行内直接按钮，确认后按教师身份删除并刷新教师课程', async () => {
    const courses = useCourseStore()
    courses.courseList = [course('delete', { course_name: '离散数学' }) as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    const deleteCourse = vi.spyOn(courses, 'deleteCourse').mockResolvedValue(undefined)
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)

    const wrapper = mountLibrary()
    await flushPromises()
    await wrapper.get('[data-testid="delete-course-delete"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(
      '确定删除《离散数学》吗？课程、备课内容和相关任务都将删除，且无法恢复。',
      '删除课程',
      expect.any(Object),
    )
    expect(deleteCourse).toHaveBeenCalledWith('delete', { surface: 'teacher' })
  })

  it('批量删除只确认一次，部分失败时保留失败课程的选择以便重试', async () => {
    const courses = useCourseStore()
    courses.courseList = [course('ok') as any, course('failed') as any]
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    const deleteCourses = vi.spyOn(courses, 'deleteCourses').mockResolvedValue({ deleted: ['ok'], failed: ['failed'] })
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)

    const wrapper = mountLibrary()
    await flushPromises()
    await wrapper.get('thead input[type="checkbox"]').setValue(true)
    await wrapper.get('[data-testid="delete-selected-courses"]').trigger('click')
    await flushPromises()

    expect(deleteCourses).toHaveBeenCalledWith(['ok', 'failed'], { surface: 'teacher' })
    expect(wrapper.get('.selection-summary').text()).toBe('已选 1 门课程')
    const selectedRows = wrapper.findAll('tbody tr.selected')
    expect(selectedRows).toHaveLength(1)
    expect(selectedRows[0]!.text()).toContain('课程 failed')
  })

  it('每页展示九门课程，翻页时清空本页选择且分页位于表格底部', async () => {
    const courses = useCourseStore()
    courses.courseList = Array.from({ length: 11 }, (_, index) => course(String(index + 1), {
      updated_at: `2026-09-${String(index + 1).padStart(2, '0')}T10:00:00Z`,
    })) as any
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()
    expect(wrapper.findAll('tbody tr')).toHaveLength(9)
    expect(wrapper.find('.course-table-region > .library-pagination').exists()).toBe(true)

    await wrapper.findAll('tbody input[type="checkbox"]')[0]!.setValue(true)
    await wrapper.get('button[aria-label="下一页"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.find('.selection-summary').exists()).toBe(false)
  })

  it('区分首次加载失败和已有列表刷新失败，并提供重试入口', async () => {
    const courses = useCourseStore()
    courses.courseListError = 'offline'
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const wrapper = mountLibrary()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('课程读取失败')
    expect(wrapper.get('[role="alert"] button').text()).toBe('重试')

    courses.courseList = [course('cached') as any]
    await flushPromises()
    expect(wrapper.get('.library-inline-error').text()).toContain('当前显示的是上次读取结果')
    expect(wrapper.find('tbody').exists()).toBe(true)
  })
})
