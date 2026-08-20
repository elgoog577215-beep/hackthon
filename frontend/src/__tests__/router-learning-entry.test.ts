import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('learning routes', () => {
  it('原课程入口进入统一课程工作区', () => {
    const legacyRoute = router.getRoutes().find(route => route.path === '/course/:courseId')
    expect(legacyRoute).toBeDefined()
    expect(typeof legacyRoute!.redirect).toBe('function')
    const redirect = (legacyRoute!.redirect as Function)({ params: { courseId: 'course-1' } })
    const resolved = router.resolve(redirect)

    expect(resolved.name).toBe('course-workspace')
    expect(resolved.fullPath).toBe('/course/course-1/workspace/setup')
    expect(router.getRoutes().map(route => route.name).filter(Boolean)).toEqual(
      expect.arrayContaining(['learning', 'course-library', 'course-workspace', 'ppt-workspace']),
    )
    expect(router.getRoutes().map(route => route.name)).not.toContain('course-workbench')
  })

  it('PPT 使用独立的课程级全屏路由', () => {
    const resolved = router.resolve('/course/course-1/ppt')
    expect(resolved.name).toBe('ppt-workspace')
    expect(resolved.params.courseId).toBe('course-1')
  })

  it('旧教师路由保留名称但只重定向到统一工作区', () => {
    expect(router.resolve('/teacher/courses').name).toBe('teacher-course-library')
    expect(router.resolve('/teacher/course/course-1/overview').name).toBe('teacher-course-overview')
    expect(router.resolve('/teacher/course/course-1/production').name).toBe('teacher-course-production')
    expect(router.resolve('/teacher/course/course-1/outline').name).toBe('teacher-course-outline')
    expect(router.resolve('/teacher/course/course-1/release').name).toBe('teacher-course-release')
    expect(router.resolve('/teacher/course/course-1/teaching-calendar').name).toBe('teacher-course-calendar')
    expect(router.resolve('/teacher/course/course-1/ppt').name).toBe('teacher-ppt-workspace')
    expect(router.resolve('/teacher/teaching-calendar').name).toBe('teacher-teaching-calendar')
    const filesRoute = router.getRoutes().find(route => route.name === 'teacher-course-files')
    const redirected = (filesRoute!.redirect as Function)({ params: { courseId: 'course-1' }, query: {} })
    expect(router.resolve(redirected).fullPath).toBe('/course/course-1/workspace/setup')
  })

  it('教师命名空间中的未知地址只能回教师工作台', () => {
    const rootFallback = router.getRoutes().find(route => route.path === '/teacher')
    const nestedFallback = router.getRoutes().find(route => route.path === '/teacher/:pathMatch(.*)*')

    expect(rootFallback?.redirect).toBe('/courses')
    expect(nestedFallback?.redirect).toBe('/courses')
    expect(router.resolve('/teacher/not-a-real-page').matched.at(-1)?.path).toBe('/teacher/:pathMatch(.*)*')
  })
})
