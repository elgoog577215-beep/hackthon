import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import http from '@/utils/http'
import { useTeachingCalendarStore, type TeachingCalendar } from '@/stores/teachingCalendar'

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

    expect(http.get).toHaveBeenCalledWith('/api/courses/course-1/teaching-calendar')
    expect(http.put).toHaveBeenCalledWith('/api/courses/course-1/teaching-calendar', expect.objectContaining({ base_revision: 2 }))
    expect(store.calendar?.revision).toBe(3)
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
    expect(http.put).not.toHaveBeenCalled()
  })
})
