import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCourseStore } from '@/stores/course'
import http from '@/utils/http'


const deferred = <T>() => {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}


describe('course list offline continuity', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
  })

  it('刷新失败时保留最后一次成功课程列表', async () => {
    const store = useCourseStore()
    store.courseList = [{ course_id: 'course-1', course_name: '线性代数', node_count: 4 }]
    vi.spyOn(http, 'get').mockRejectedValue(new Error('offline'))

    await store.fetchCourseList()

    expect(store.courseList).toEqual([
      { course_id: 'course-1', course_name: '线性代数', node_count: 4 },
    ])
    expect(store.loading).toBe(false)
  })

  it('课程列表刷新使用独立状态和短请求超时，不阻塞课程内容', async () => {
    const store = useCourseStore()
    const response = deferred<{ data: Array<{ course_id: string; course_name: string; node_count: number }> }>()
    const get = vi.spyOn(http, 'get').mockReturnValue(response.promise as any)

    const refresh = store.fetchCourseList()

    expect(store.courseListLoading).toBe(true)
    expect(store.loading).toBe(false)
    expect(get).toHaveBeenCalledWith('/api/courses', { timeout: 15000 })

    response.resolve({ data: [{ course_id: 'course-2', course_name: '数据结构', node_count: 8 }] })
    await refresh

    expect(store.courseListLoading).toBe(false)
    expect(store.courseList).toHaveLength(1)
  })

  it('合并并发课程列表刷新，避免重复读取同一批课程', async () => {
    const store = useCourseStore()
    const response = deferred<{ data: Array<{ course_id: string; course_name: string; node_count: number }> }>()
    const get = vi.spyOn(http, 'get').mockReturnValue(response.promise as any)

    const first = store.fetchCourseList()
    const second = store.fetchCourseList()

    expect(get).toHaveBeenCalledTimes(1)

    response.resolve({ data: [] })
    await Promise.all([first, second])
    expect(store.courseListLoading).toBe(false)
  })
})
