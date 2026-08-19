import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'

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

  it('returns to the course-library home when the brand link is clicked', async () => {
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
      ],
    })

    await router.push('/course/course-1/learn/node-1')
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

    const homeLink = wrapper.get('a.brand-button')
    expect(homeLink.attributes('href')).toBe('/courses')
    expect(wrapper.get('.app-course-modes').classes()).toContain('is-topbar')
    expect(wrapper.get('[data-testid="course-mode-formal"]').classes()).toContain('is-active')

    await homeLink.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('course-library')
  })
})
