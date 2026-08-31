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

import { lessonJobsToObserve, useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('teacher lesson authoring store', () => {
  it('observes only the running job or the next queued job for one course', () => {
    const queued = [3, 1, 2].map(position => ({
      id: `job-${position}`,
      status: 'pending',
      batch_position: position,
      created_at: `2026-09-01T00:00:0${position}Z`,
    })) as any

    expect(lessonJobsToObserve(queued).map(job => job.id)).toEqual(['job-1'])
    expect(lessonJobsToObserve([
      ...queued,
      { id: 'job-running', status: 'running', batch_position: 2 },
    ] as any).map(job => job.id)).toEqual(['job-running'])
  })

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

  it('coalesces concurrent reads for the same course into one request', async () => {
    let resolveRequest!: (value: any) => void
    httpMock.get.mockReturnValue(new Promise(resolve => { resolveRequest = resolve }))
    const store = useTeacherLessonAuthoringStore()

    const first = store.load('course-1')
    const second = store.load('course-1')

    expect(httpMock.get).toHaveBeenCalledTimes(1)
    resolveRequest({
      data: {
        schema_version: 'teacher_lesson_authoring_view_v1',
        course_id: 'course-1',
        outline_revision_id: 'outline-1',
        lessons: [],
        jobs: [],
      },
    })
    await Promise.all([first, second])

    expect(store.loading).toBe(false)
    expect(store.loadedCourseId).toBe('course-1')
  })

  it('keeps the last successful lesson view visible when a background refresh times out', async () => {
    httpMock.get.mockResolvedValueOnce({
      data: {
        schema_version: 'teacher_lesson_authoring_view_v1',
        course_id: 'course-1',
        outline_revision_id: 'outline-1',
        lessons: [{ lesson_unit_id: 'lesson-1', title: '第一讲' }],
        jobs: [],
      },
    })
    const store = useTeacherLessonAuthoringStore()
    await store.load('course-1')
    httpMock.get.mockRejectedValueOnce(Object.assign(new Error('timeout of 10000ms exceeded'), { code: 'ECONNABORTED' }))

    const refresh = store.load('course-1')
    expect(store.loading).toBe(false)
    expect(store.refreshing).toBe(true)
    await expect(refresh).rejects.toThrow('timeout of 10000ms exceeded')

    expect(store.lessons).toEqual([{ lesson_unit_id: 'lesson-1', title: '第一讲' }])
    expect(store.error).toBe('')
    expect(store.refreshError).toBe('读取时间过长，请重新尝试。已生成的内容仍然保留。')
    expect(store.refreshing).toBe(false)
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
