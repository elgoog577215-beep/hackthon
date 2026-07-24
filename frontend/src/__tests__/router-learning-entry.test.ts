import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('learning routes', () => {
  it('旧课程入口直接进入当前课程学习工作区', () => {
    const legacyRoute = router.getRoutes().find(route => route.path === '/course/:courseId')
    expect(legacyRoute).toBeDefined()
    expect(typeof legacyRoute!.redirect).toBe('function')
    const redirect = (legacyRoute!.redirect as Function)({ params: { courseId: 'course-1' } })
    const resolved = router.resolve(redirect)

    expect(resolved.name).toBe('learning')
    expect(resolved.fullPath).toBe('/course/course-1/learn')
    expect(router.getRoutes().map(route => route.name).filter(Boolean)).toEqual(
      expect.arrayContaining(['learning', 'course-library', 'ppt-workspace']),
    )
    expect(router.getRoutes().map(route => route.name)).not.toContain('course-workbench')
  })

  it('PPT 使用独立的课程级全屏路由', () => {
    const resolved = router.resolve('/course/course-1/ppt')
    expect(resolved.name).toBe('ppt-workspace')
    expect(resolved.params.courseId).toBe('course-1')
  })
})
