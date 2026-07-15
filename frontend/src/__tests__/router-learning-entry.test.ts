import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('learning routes', () => {
  it('旧课程入口只重定向到唯一学习现场', async () => {
    await router.push('/course/course-1')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.fullPath).toBe('/course/course-1/learn')
    expect(router.getRoutes().map(route => route.name).filter(Boolean)).toEqual([
      'learning',
      'course-library',
    ])
  })
})
