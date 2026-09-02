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
    { path: '/teacher/courses', name: 'teacher-course-library', component: CourseLibraryView },
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
    await router.replace('/teacher/courses')
    await router.isReady()
  })

  it('用单一数据表直接呈现课程管理信息，不再保留卡片、视图切换和三点菜单', async () => {
    const courses = useCourseStore()
    courses.courseList = [course('math', {
      course_name: '矩阵与线性变换',
      course_code: 'MATH-221',
      preparation_state: 'prepared',
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
    expect(wrapper.get('tbody').text()).toContain('备课完成')
    expect(wrapper.get('tbody').text()).toContain('14:00')
    expect(wrapper.get('tbody').text()).toContain('理科楼 A108')
    expect(wrapper.get('tbody').text()).toContain('2026-2027 秋季')
    expect(wrapper.get('[data-testid="delete-course-math"]').attributes('title')).toBe('删除课程')
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
    expect(router.currentRoute.value.query.returnTo).toBe('/teacher/courses?view=courses&sort=name&dir=ascending')
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
