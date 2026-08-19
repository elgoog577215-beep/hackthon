import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'
import CourseModeTabs from '@/components/CourseModeTabs.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/course/:courseId/workspace/:mode', name: 'course-workspace', component: { template: '<div />' } },
    { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: { template: '<div />' } },
  ],
})
describe('CourseModeTabs', () => {
  beforeEach(async () => {
    await router.push('/course/course-1/workspace/setup')
    await router.isReady()
  })

  it('shows the three confirmed course modes without a teacher surface', () => {
    const wrapper = mount(CourseModeTabs, {
      props: { active: 'setup', courseId: 'course-1' },
      global: { plugins: [router] },
    })

    expect(wrapper.findAll('button')).toHaveLength(3)
    expect(wrapper.text()).toContain('课程设置')
    expect(wrapper.text()).toContain('备课制作')
    expect(wrapper.text()).toContain('正式课程')
    expect(wrapper.text()).not.toContain('信息、资料与排课')
    expect(wrapper.text()).not.toContain('大纲、讲次与课件')
    expect(wrapper.text()).not.toContain('上课与学习现场')
    expect(wrapper.text()).not.toContain('教师端')
  })

  it('uses the flat topbar treatment when promoted to the global header', () => {
    const wrapper = mount(CourseModeTabs, {
      props: { active: 'build', courseId: 'course-1', topbar: true },
      global: { plugins: [router] },
    })

    expect(wrapper.classes()).toContain('is-topbar')
    expect(wrapper.get('[data-testid="course-mode-build"]').classes()).toContain('is-active')
  })

  it('routes preparation and formal use to the same course', async () => {
    const wrapper = mount(CourseModeTabs, {
      props: { active: 'setup', courseId: 'course-1' },
      global: { plugins: [router] },
    })

    await wrapper.get('[data-testid="course-mode-build"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/course/course-1/workspace/build?section=outline')

    await wrapper.setProps({ active: 'build' })
    await wrapper.get('[data-testid="course-mode-formal"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/course/course-1/learn')
  })
})
