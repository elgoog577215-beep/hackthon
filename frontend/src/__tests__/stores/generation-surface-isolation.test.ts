import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import http, { setActiveRequestIdentityScope } from '../../utils/http'
import {
  globalTaskRetryDelayMs,
  isCourseLifecycleBackendTask,
  useGenerationStore,
} from '../../stores/generation'
import { useCourseStore } from '../../stores/course'
import { teacherPptRoute } from '../../features/teacher-course/useTeacherCourseRuntime'

describe('teacher/student shared capability isolation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setActiveRequestIdentityScope('learner')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('keeps representation builds out of course lifecycle projection', () => {
    expect(isCourseLifecycleBackendTask({ type: 'course_generation' })).toBe(true)
    expect(isCourseLifecycleBackendTask({ type: 'course_import' })).toBe(true)
    expect(isCourseLifecycleBackendTask({})).toBe(true)
    expect(isCourseLifecycleBackendTask({ type: 'slide_deck_variant_build' })).toBe(false)
    expect(isCourseLifecycleBackendTask({ type: 'teaching_representation_build' })).toBe(false)
    expect(isCourseLifecycleBackendTask({ type: 'teacher_outline_generation' })).toBe(true)
    expect(isCourseLifecycleBackendTask({ type: 'teacher_lesson_plan_generation' })).toBe(false)
    expect(isCourseLifecycleBackendTask({ type: 'teacher_lesson_ppt_generation' })).toBe(false)
  })

  it('opens the shared PPT capability through a teacher-owned route', () => {
    expect(teacherPptRoute('course-1', {
      nodeId: 'lesson-2',
      returnTo: '/course/course-1/workspace/build?stage=ppt',
    })).toEqual({
      name: 'ppt-workspace',
      params: { courseId: 'course-1' },
      query: {
        lesson: 'lesson-2',
        returnTo: '/course/course-1/workspace/build?stage=ppt',
      },
    })
  })

  it('coalesces concurrent global task refreshes', async () => {
    const generation = useGenerationStore()
    let resolveRequest!: (value: { data: never[] }) => void
    const request = new Promise<{ data: never[] }>(resolve => {
      resolveRequest = resolve
    })
    const get = vi.spyOn(http, 'get').mockReturnValue(request as never)

    const first = generation.fetchGlobalTasks()
    const second = generation.fetchGlobalTasks()

    expect(get).toHaveBeenCalledTimes(1)
    resolveRequest({ data: [] })
    await Promise.all([first, second])
    expect(generation.globalTasksLoading).toBe(false)
  })

  it('keeps a background task discovery inside the active teacher course library', async () => {
    setActiveRequestIdentityScope('teacher')
    const generation = useGenerationStore()
    const courses = useCourseStore()
    vi.spyOn(http, 'get').mockResolvedValue({
      data: [{
        id: 'legacy-job',
        course_id: 'legacy-course',
        course_name: '历史课程',
        type: 'course_generation',
        status: 'running',
        progress: 10,
      }],
    })
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.fetchGlobalTasks()

    expect(refreshList).toHaveBeenCalledWith({ surface: 'teacher' })
  })

  it('backs off global task refresh after a 429 response', async () => {
    const generation = useGenerationStore()
    const get = vi.spyOn(http, 'get').mockRejectedValue({
      response: { status: 429, headers: { 'retry-after': '2' } },
    })

    await generation.fetchGlobalTasks()
    await generation.fetchGlobalTasks()

    expect(get).toHaveBeenCalledTimes(1)
    expect(generation.globalTasksBackoffUntil).toBeGreaterThan(Date.now())
    expect(globalTaskRetryDelayMs({ response: { status: 429, headers: {} } })).toBe(60_000)
  })

  it('does not poll global tasks while the page is hidden', () => {
    vi.useFakeTimers()
    const generation = useGenerationStore()
    const fetchGlobalTasks = vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')

    generation.startGlobalMonitor()
    vi.advanceTimersByTime(15_000)

    expect(fetchGlobalTasks).not.toHaveBeenCalled()
    generation.stopGlobalMonitor()
  })
})
