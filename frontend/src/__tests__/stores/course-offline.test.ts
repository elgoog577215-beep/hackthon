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
    expect(store.loading).toBe(false)
  })

  it('教师首页的后台刷新继续读取教师课程摘要', async () => {
    window.history.replaceState({}, '', '/courses?view=courses')
    const store = useCourseStore()
    vi.spyOn(http, 'get').mockResolvedValue({ data: [] } as any)

    await store.fetchCourseList({ surface: 'teacher' })

    expect(http.get).toHaveBeenCalledWith('/api/teacher/courses', expect.any(Object))
  })
})
