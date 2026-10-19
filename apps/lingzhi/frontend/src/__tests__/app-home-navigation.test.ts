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
    vi.stubEnv('VITE_STUDY_APP_URL', '')
    vi.stubEnv('VITE_APP_SURFACE', '')
  })

  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs() })

  it.each([false, true])('keeps home navigation correct across routes (school deployment: %s)', async (schoolDeployment) => {
    vi.spyOn(http, 'isQizhiAuthRequired').mockReturnValue(schoolDeployment)
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/study/:materialId?', name: 'study', component: { template: '<div>Personal study</div>' } },
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

    const homeLink = wrapper.get(schoolDeployment ? 'a.qizhi-home-link' : 'a.product-brand')
    expect(homeLink.attributes('href')).toBe(schoolDeployment ? '/' : '/courses')
    expect(wrapper.find('a.qizhi-home-link').exists()).toBe(schoolDeployment)
    await router.push('/study')
    await flushPromises()
    expect(wrapper.find('.app-header').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'KnowledgeLibrary' }).exists()).toBe(false)
    expect(generationStore.stopGlobalMonitor).toHaveBeenCalled()
    await router.push('/courses')
    await flushPromises()
    expect(wrapper.find('a[href="/study"]').exists()).toBe(true)
    expect(generationStore.startGlobalMonitor).toHaveBeenCalled()
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
      expect(wrapper.get('a.product-brand').isVisible()).toBe(true)
      expect(wrapper.get('a.product-brand').attributes('data-product-surface')).toBe('teacher')
    }
    expect(wrapper.classes()).toContain('is-course-workspace-route')

    await router.push('/course/course-1/learn?teacherPreview=1')
    await flushPromises()
    expect(wrapper.findComponent({name:'KnowledgeLibrary'}).exists()).toBe(false)
    expect(wrapper.find('.header-search').exists()).toBe(true)
    expect(wrapper.find('a.qizhi-home-link').exists()).toBe(schoolDeployment)
    expect(wrapper.get('a.product-brand').text()).toBe('启智教师端')
    expect(document.title).toBe('启智 · 教师端')
    wrapper.unmount()
  })
})
