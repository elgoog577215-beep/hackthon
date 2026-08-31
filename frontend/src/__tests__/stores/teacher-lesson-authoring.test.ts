import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  getTeacherIdentity: () => 'teacher-test',
  teacherReadRequestConfig: (config = {}) => config,
}))

import { useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
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

  it('starts lesson-plan generation when HTTP does not expose crypto.randomUUID', async () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (target: Uint8Array) => {
        target.fill(7)
        return target
      },
    })
    httpMock.post.mockResolvedValue({
      data: {
        job: {
          id: 'lesson-job-http',
          course_id: 'course-1',
          lesson_unit_id: 'lesson-1',
          type: 'teacher_lesson_plan_generation',
          status: 'pending',
          progress: 0,
        },
      },
    })
    const store = useTeacherLessonAuthoringStore()
    vi.spyOn(store, 'streamJob').mockResolvedValue(undefined)

    await store.generateLesson('course-1', 'lesson-1')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/teacher/courses/course-1/lessons/lesson-1/plan/generate',
      expect.objectContaining({
        request_id: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/),
      }),
      { headers: { 'X-User-Id': 'teacher-test' } },
    )
    expect(store.error).toBe('')
  })
})
