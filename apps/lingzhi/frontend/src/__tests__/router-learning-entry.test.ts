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

  it('不再注册已退役的教师页面路由', () => {
    const routeNames = router.getRoutes().map(route => route.name)
    expect(routeNames.some(name => String(name || '').startsWith('teacher-course-'))).toBe(false)
    expect(routeNames).not.toContain('teacher-ppt-workspace')
    expect(routeNames).not.toContain('teacher-teaching-calendar')
  })
})
