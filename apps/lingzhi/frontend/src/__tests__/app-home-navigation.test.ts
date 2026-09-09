import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'
import * as http from '@/utils/http'

const generationStore = {
  restoreGenerationState: vi.fn(),
  startGlobalMonitor: vi.fn(),
  stopGlobalMonitor: vi.fn(),
  fetchGlobalTasks: vi.fn().mockResolvedValue(undefined),
}

vi.mock('@/stores/generation', () => ({
  GENERATION_STATE_KEY: 'qizhi-generation-state',
  useGenerationStore: () => generationStore,
}))

describe('App home navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => vi.restoreAllMocks())

  it.each([false, true])('keeps home navigation correct across routes (school deployment: %s)', async (schoolDeployment) => {
    vi.spyOn(http, 'isQizhiAuthRequired').mockReturnValue(schoolDeployment)
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/courses',
          name: 'course-library',
          component: { template: '<div>Course library</div>' },
        },
        {
          path: '/course/:courseId/learn/:nodeId?',
          name: 'learning',
          component: { template: '<div>Learning workspace</div>' },
        },
        {
          path: '/course/:courseId/workspace/:mode?',
          name: 'course-workspace',
          component: { template: '<div>Course workspace</div>' },
        },
      ],
    })

    await router.push('/courses')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [pinia, router],
        stubs: {
          KnowledgeLibrary: true,
          'el-dropdown': true,
          'el-dropdown-item': true,
          'el-dropdown-menu': true,
          'el-popover': true,
        },
      },
    })

    const homeLink = wrapper.get(schoolDeployment ? 'a.qizhi-home-link' : 'a.brand-button')
    expect(homeLink.attributes('href')).toBe(schoolDeployment ? '/' : '/courses')
    expect(wrapper.find('a.qizhi-home-link').exists()).toBe(schoolDeployment)
    expect(homeLink.attributes('target')).toBeUndefined()
    expect(wrapper.find('.app-course-stages').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'CourseStageTabs' }).exists()).toBe(false)

    await router.push('/course/course-1/workspace/setup')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('course-workspace')
    if (schoolDeployment) {
      expect(wrapper.get('a.qizhi-home-link').isVisible()).toBe(true)
      expect(wrapper.get('a.qizhi-home-link').attributes('href')).toBe('/')
    } else {
      expect(wrapper.get('a.brand-button').classes()).toContain('is-route-hidden')
    }
    expect(wrapper.classes()).toContain('is-course-workspace-route')

    await router.push('/course/course-1/learn?teacherPreview=1')
    await flushPromises()
    expect(wrapper.findComponent({name:'KnowledgeLibrary'}).exists()).toBe(true)
    expect(wrapper.findComponent({name:'KnowledgeLibrary'}).props('learningMode')).toBe(true)
    expect(wrapper.find('.header-search').exists()).toBe(true)
    expect(wrapper.find('a.qizhi-home-link').exists()).toBe(schoolDeployment)
    wrapper.unmount()
  })
})
