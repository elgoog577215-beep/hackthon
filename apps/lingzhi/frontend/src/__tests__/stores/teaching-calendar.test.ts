import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
  getTeacherIdentity: vi.fn(() => 'teacher-calendar-test'),
}))

import http from '@/utils/http'
import { TEACHING_CALENDAR_SAVED_EVENT, TEACHING_CALENDAR_SAVED_STORAGE_KEY, useTeachingCalendarStore, type TeachingCalendar } from '@/stores/teachingCalendar'

const calendar: TeachingCalendar = {
  schema_version: 'teaching_calendar_v1',
  course_id: 'course-1',
  course_title: '设计思维',
  academic_year: '2025-2026',
  term: '春夏',
  timezone: 'Asia/Shanghai',
  status: 'draft',
  source_outline_revision: 'outline-r2',
  revision: 2,
  sessions: [{
    session_id: 'session-1', sequence: 1, date: '2026-03-02', start_time: '08:00:00', end_time: '09:50:00',
    content_summary: '第一讲', requirements: '', location: '紫金港', teacher_name: '张老师', teaching_type: '理论课',
    group_code: '', credit_hours: 2, notes: '', status: 'scheduled', source: 'manual',
  }],
  created_at: '', updated_at: '',
}

describe('teaching calendar store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads a course calendar and submits its optimistic base revision', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: calendar } as any)
    vi.mocked(http.put).mockResolvedValue({ data: { ...calendar, revision: 3 } } as any)
    const store = useTeachingCalendarStore()

    await store.loadCourse('course-1')
    await store.saveCourse('course-1', calendar)

    expect(http.get).toHaveBeenCalledWith('/api/courses/course-1/teaching-calendar', {
      headers: { 'X-User-Id': 'teacher-calendar-test' },
    })
    expect(http.put).toHaveBeenCalledWith(
      '/api/courses/course-1/teaching-calendar',
      expect.objectContaining({ base_revision: 2 }),
      { headers: { 'X-User-Id': 'teacher-calendar-test' } },
    )
    expect(store.calendar?.revision).toBe(3)
  })

  it('announces a successful save so total-calendar views can refresh', async () => {
    const saved = { ...calendar, revision: 3, updated_at: '2026-08-13T10:00:00Z' }
    vi.mocked(http.put).mockResolvedValue({ data: saved } as any)
    const listener = vi.fn()
    window.addEventListener(TEACHING_CALENDAR_SAVED_EVENT, listener)
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem')

    await useTeachingCalendarStore().saveCourse('course-1', calendar)

    expect(listener).toHaveBeenCalledOnce()
    expect((listener.mock.calls[0]?.[0] as CustomEvent).detail).toMatchObject({ courseId: 'course-1', revision: 3 })
    expect(storageSpy).toHaveBeenCalledWith(TEACHING_CALENDAR_SAVED_STORAGE_KEY, expect.stringContaining('"revision":3'))
    window.removeEventListener(TEACHING_CALENDAR_SAVED_EVENT, listener)
    storageSpy.mockRestore()
  })

  it('preserves the conflict revision returned by the backend', async () => {
    vi.mocked(http.put).mockRejectedValue({ response: { status: 409, data: { detail: { code: 'teaching_calendar_revision_conflict', message: '已更新', current_revision: 6 } } } })
    const store = useTeachingCalendarStore()

    await expect(store.saveCourse('course-1', calendar)).rejects.toBeTruthy()

    expect(store.conflictRevision).toBe(6)
    expect(store.error).toBe('已更新')
  })

  it('derives candidates without saving them', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: { candidate: calendar, candidate_count: 1, retained_count: 0, new_count: 1, current_revision: 0 } } as any)
    const store = useTeachingCalendarStore()

    const result = await store.deriveFromOutline('course-1')

    expect(result.new_count).toBe(1)
    expect(http.post).toHaveBeenCalledWith(
      '/api/courses/course-1/teaching-calendar/derive-from-outline',
      undefined,
      { headers: { 'X-User-Id': 'teacher-calendar-test' } },
    )
    expect(http.put).not.toHaveBeenCalled()
  })

  it('loads the total calendar with the same teacher identity', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { count: 1, sessions: calendar.sessions } } as any)
    const store = useTeachingCalendarStore()

    await store.loadTotal('2026-08-01', '2026-08-31')

    // include_incomplete 是后加的能力，默认不带出未排完的课次，
    // 断言必须跟着走——漏掉它等于没在检查真正发出去的请求。
    expect(http.get).toHaveBeenCalledWith('/api/teachers/me/teaching-calendar', {
      params: { date_from: '2026-08-01', date_to: '2026-08-31', include_incomplete: false },
      headers: { 'X-User-Id': 'teacher-calendar-test' },
    })
  })

  it('opts into incomplete sessions only when asked', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { count: 1, sessions: calendar.sessions } } as any)
    const store = useTeachingCalendarStore()

    await store.loadTotal('2026-08-01', '2026-08-31', true)

    expect(http.get).toHaveBeenCalledWith('/api/teachers/me/teaching-calendar', {
      params: { date_from: '2026-08-01', date_to: '2026-08-31', include_incomplete: true },
      headers: { 'X-User-Id': 'teacher-calendar-test' },
    })
  })
})
