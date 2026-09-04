import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCourseStore } from '@/stores/course'
import http from '@/utils/http'


describe('course list offline continuity', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    window.history.replaceState({}, '', '/')
  })

  it('刷新失败时保留最后一次成功课程列表', async () => {
    const store = useCourseStore()
    store.courseList = [{ course_id: 'course-1', course_name: '线性代数', node_count: 4 }]
    vi.spyOn(http, 'get').mockRejectedValue(new Error('offline'))

    await store.fetchCourseList()

    expect(store.courseList).toEqual([
      { course_id: 'course-1', course_name: '线性代数', node_count: 4 },
    ])
    expect(store.courseListError).toBe('offline')
    expect(store.loading).toBe(false)
  })

  it('下一次读取成功后清除旧错误', async () => {
    const store = useCourseStore()
    store.courseListError = 'offline'
    vi.spyOn(http, 'get').mockResolvedValue({ data: [] } as any)

    await store.fetchCourseList({ surface: 'teacher' })

    expect(store.courseListError).toBeNull()
  })

  it('教师首页的后台刷新继续读取教师课程摘要', async () => {
    window.history.replaceState({}, '', '/courses?view=courses')
    const store = useCourseStore()
    vi.spyOn(http, 'get').mockResolvedValue({ data: [] } as any)

    await store.fetchCourseList({ surface: 'teacher' })

    expect(http.get).toHaveBeenCalledWith('/api/teacher/courses', expect.any(Object))
  })

  it('任务事件后只读刷新服务端生产投影，不创建新任务', async () => {
    const store = useCourseStore()
    store.courseList = [{ course_id: 'course-1', course_name: '线性代数', node_count: 16 }]
    const emptyStage = {
      display_state: 'not_generated', task_state: 'idle', availability: 'missing', source_state: 'missing',
      latest_attempt_failed: false, update_required: false,
      counts: { total: 16, available: 0, generating: 0, failed: 0, stale: 0 }, issues: [],
    }
    const production = {
      schema_version: 'course_production_state_v1', course_id: 'course-1', preparation_state: 'preparing',
      stages: { outline: { ...emptyStage, counts: { ...emptyStage.counts, total: 1 } }, lesson_plan: emptyStage, script: emptyStage, ppt: emptyStage },
      lessons: [], issues: [],
    }
    const get = vi.spyOn(http, 'get').mockResolvedValue({ data: { course_id: 'course-1', course_production_state: production } } as any)
    const post = vi.spyOn(http, 'post')
    const put = vi.spyOn(http, 'put')
    const patch = vi.spyOn(http, 'patch')
    const remove = vi.spyOn(http, 'delete')

    await store.fetchTeacherCourseProductionState('course-1')

    expect(get).toHaveBeenCalledOnce()
    expect(get).toHaveBeenCalledWith('/api/courses/course-1', expect.any(Object))
    expect(store.teacherProductionStates['course-1']).toMatchObject({ schema_version: 'course_production_state_v1', course_id: 'course-1' })
    expect(store.courseList[0]?.course_production_state).toMatchObject({ course_id: 'course-1' })
    expect(post).not.toHaveBeenCalled()
    expect(put).not.toHaveBeenCalled()
    expect(patch).not.toHaveBeenCalled()
    expect(remove).not.toHaveBeenCalled()
  })

  it('批量删除并行执行、只刷新一次，并保留失败课程', async () => {
    const store = useCourseStore()
    store.courseList = [
      { course_id: 'course-ok', course_name: '成功课程', node_count: 4 },
      { course_id: 'course-failed', course_name: '失败课程', node_count: 4 },
    ]
    const remove = vi.spyOn(http, 'delete').mockImplementation(async (url: string) => {
      if (url.endsWith('course-failed')) throw new Error('busy')
      return { data: { status: 'success' } } as any
    })
    const refresh = vi.spyOn(store, 'fetchCourseList').mockResolvedValue(undefined)

    const result = await store.deleteCourses(['course-ok', 'course-failed'], { surface: 'teacher' })

    expect(remove).toHaveBeenCalledTimes(2)
    expect(remove).toHaveBeenCalledWith('/api/courses/course-ok', expect.objectContaining({ identityScope: 'teacher' }))
    expect(result).toEqual({ deleted: ['course-ok'], failed: ['course-failed'] })
    expect(store.courseList.map(course => course.course_id)).toEqual(['course-failed'])
    expect(refresh).toHaveBeenCalledOnce()
    expect(refresh).toHaveBeenCalledWith({ surface: 'teacher' })
  })
})
