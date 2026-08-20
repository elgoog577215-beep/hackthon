import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'
import CourseStageTabs from '@/components/CourseStageTabs.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/course/:courseId/workspace/:mode', name: 'course-workspace', component: { template: '<div />' } },
    { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: { template: '<div />' } },
    { path: '/course/:courseId/ppt', name: 'ppt-workspace', component: { template: '<div />' } },
  ],
})

describe('CourseStageTabs', () => {
  beforeEach(async () => {
    await router.push('/course/course-1/workspace/setup')
    await router.isReady()
  })

  it('shows the four course production stages in their real order', () => {
    const wrapper = mount(CourseStageTabs, {
      props: { active: 'course', courseId: 'course-1' },
      global: { plugins: [router] },
    })

    expect(wrapper.findAll('button').map(button => button.text().replace(/\d/g, ''))).toEqual(['课程', '大纲', '正文', 'PPT'])
    expect(wrapper.get('[data-testid="course-stage-course"]').attributes('aria-current')).toBe('step')
  })

  it('marks exactly one active stage', () => {
    const wrapper = mount(CourseStageTabs, {
      props: { active: 'outline', courseId: 'course-1' },
      global: { plugins: [router] },
    })

    expect(wrapper.get('[data-testid="course-stage-outline"]').classes()).toContain('is-active')
    expect(wrapper.findAll('button.is-active')).toHaveLength(1)
  })

  it('routes outline, content and PPT to the same course', async () => {
    const wrapper = mount(CourseStageTabs, {
      props: { active: 'course', courseId: 'course-1' },
      global: { plugins: [router] },
    })

    await wrapper.get('[data-testid="course-stage-outline"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/course/course-1/workspace/build?section=outline')

    await wrapper.setProps({ active: 'outline' })
    await wrapper.get('[data-testid="course-stage-content"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/course/course-1/learn')

    await wrapper.setProps({ active: 'content' })
    await wrapper.get('[data-testid="course-stage-ppt"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/course/course-1/ppt')
  })
})
