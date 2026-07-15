import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('learning routes', () => {
  it('旧课程入口只重定向到唯一学习现场', async () => {
    await router.push('/course/course-1')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.fullPath).toBe('/course/course-1/learn')
    expect(router.getRoutes().map(route => route.name).filter(Boolean)).toEqual(expect.arrayContaining([
      'learning',
      'course-library',
      'presentation-entry',
      'presentation-studio',
    ]))
  }, 15000)

  it('课件入口和具体草稿使用独立 workbench shell', async () => {
    await router.push('/course/course-1/deck?nodeId=node-2')
    expect(router.currentRoute.value.name).toBe('presentation-entry')
    expect(router.currentRoute.value.query.nodeId).toBe('node-2')
    expect(router.currentRoute.value.meta.shell).toBe('workbench')

    await router.push('/course/course-1/deck/deck-1')
    expect(router.currentRoute.value.name).toBe('presentation-studio')
    expect(router.currentRoute.value.params.deckId).toBe('deck-1')
  }, 15000)
})
