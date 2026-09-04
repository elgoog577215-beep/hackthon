import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/http', () => ({
  default: httpMock,
  teacherRequestConfig: (config = {}) => config,
}))

import TeacherTeachingCalendarView from '@/views/TeacherTeachingCalendarView.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'
import { useTeachingCalendarStore } from '@/stores/teachingCalendar'
import zhMessages from '../../../public/locales/zh/translation.json'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/courses', name: 'course-library', component: TeacherTeachingCalendarView },
    { path: '/course/:courseId/workspace/:mode', name: 'course-workspace', component: { template: '<div />' } },
    { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: { template: '<div />' } },
  ],
})
let pinia: ReturnType<typeof createPinia>

describe('TeacherTeachingCalendarView production state', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    httpMock.get.mockReset()
    pinia = createPinia()
    setActivePinia(pinia)
    const today = new Date()
    const date = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
    const courses = useCourseStore()
    courses.courseList = [{ course_id: 'course-1', course_name: '数据结构', node_count: 1 }] as any
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(useGenerationStore(), 'fetchGlobalTasks').mockResolvedValue(undefined)
    const calendar = useTeachingCalendarStore()
    calendar.totalSessions = [{
      session_id: 'session-1', course_id: 'course-1', course_title: '数据结构', lesson_unit_id: 'L1-1', sequence: 1,
      date, start_time: '08:00:00', end_time: '08:45:00', content_summary: '线性表', status: 'scheduled',
    }] as any
    vi.spyOn(calendar, 'loadTotal').mockResolvedValue([])
    await router.replace('/courses?view=calendar')
    await router.isReady()
    await setLocale('zh')
  })

  it('authoring 投影成功时不受 calendar 请求失败覆盖，并且不越过大纲直接阻断', async () => {
    const stage = (overrides: Record<string, unknown> = {}) => ({
      display_state: 'not_generated', task_state: 'idle', availability: 'missing', source_state: 'missing',
      latest_attempt_failed: false, update_required: false, task_ids: [], allowed_actions: [],
      counts: { total: 1, available: 0, generating: 0, failed: 0, stale: 0 }, issues: [], ...overrides,
    })
    const productionState = {
      schema_version: 'course_production_state_v1', course_id: 'course-1', preparation_state: 'preparing',
      stages: {
        outline: stage({ display_state: 'available', availability: 'usable', source_state: 'current', latest_attempt_failed: true, counts: { total: 1, available: 1, generating: 0, failed: 1, stale: 0 } }),
        lesson_plan: stage(), script: stage(), ppt: stage(),
      },
      lessons: [], issues: [],
    }
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher/courses/course-1/lesson-authoring') return Promise.resolve({ data: {
        schema_version: 'teacher_lesson_authoring_view_v1', course_id: 'course-1', outline_revision_id: '', lessons: [], jobs: [], course_production_state: productionState,
      } })
      if (url === '/api/courses/course-1/teaching-calendar') return Promise.reject(new Error('calendar unavailable'))
      return Promise.resolve({ data: {} })
    })
    const wrapper = mount(TeacherTeachingCalendarView, {
      global: { plugins: [pinia, router], stubs: { Teleport: true, TeacherCourseLibraryView: true, TeacherCourseCreateView: true, TeachingCalendarMonthGrid: true } },
    })
    await flushPromises()

    await wrapper.get('.week-session').trigger('click')
    await flushPromises()
    const outline = wrapper.findAll('.preparation-list article')[0]!
    expect(outline.text()).toContain('可使用')
    expect(outline.text()).toContain('最近一次生成失败')

    await wrapper.get('.inspector-actions .primary').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.stage).toBe('foundation')
    wrapper.unmount()
  })
})
