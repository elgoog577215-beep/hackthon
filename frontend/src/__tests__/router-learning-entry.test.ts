import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('learning routes', () => {
  it('旧课程入口进入当前课程的教师概览', () => {
    const legacyRoute = router.getRoutes().find(route => route.path === '/course/:courseId')
    expect(legacyRoute).toBeDefined()
    expect(typeof legacyRoute!.redirect).toBe('function')
    const redirect = (legacyRoute!.redirect as Function)({ params: { courseId: 'course-1' } })
    const resolved = router.resolve(redirect)

    expect(resolved.name).toBe('teacher-course-overview')
    expect(resolved.fullPath).toBe('/course/course-1/overview')
    expect(router.getRoutes().map(route => route.name).filter(Boolean)).toEqual(
      expect.arrayContaining(['learning', 'course-library', 'teacher-course-create', 'teacher-course-overview', 'ppt-workspace', 'teacher-course-production', 'teacher-course-outline', 'teacher-course-release', 'teacher-course-files', 'teacher-course-calendar', 'teacher-teaching-calendar']),
    )
    expect(router.getRoutes().map(route => route.name)).not.toContain('course-workbench')
  })

  it('PPT 使用独立的课程级全屏路由', () => {
    const resolved = router.resolve('/course/course-1/ppt')
    expect(resolved.name).toBe('ppt-workspace')
    expect(resolved.params.courseId).toBe('course-1')
  })

  it('教师大纲、生产、发布、单课程教学日历与教学总日历使用独立真实路由', () => {
    expect(router.resolve('/course/course-1/production').name).toBe('teacher-course-production')
    expect(router.resolve('/course/course-1/outline').name).toBe('teacher-course-outline')
    expect(router.resolve('/course/course-1/release').name).toBe('teacher-course-release')
    expect(router.resolve('/course/course-1/teaching-calendar').name).toBe('teacher-course-calendar')
    expect(router.resolve('/teacher/teaching-calendar').name).toBe('teacher-teaching-calendar')
  })
})
