import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  getTeacherIdentity: () => 'teacher-test',
}))

import { useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
})

describe('teacher lesson authoring store', () => {
  it('loads an empty lesson view without publishing a duplicate global error', async () => {
    httpMock.get.mockResolvedValue({
      data: {
        schema_version: 'teacher_lesson_authoring_view_v1',
        course_id: 'course-1',
        outline_revision_id: '',
        lessons: [],
        jobs: [],
      },
    })
    const store = useTeacherLessonAuthoringStore()

    await store.load('course-1')

    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/teacher/courses/course-1/lesson-authoring',
      {
        headers: { 'X-User-Id': 'teacher-test' },
        silentError: true,
      },
    )
    expect(store.lessons).toEqual([])
    expect(store.error).toBe('')
  })
})
