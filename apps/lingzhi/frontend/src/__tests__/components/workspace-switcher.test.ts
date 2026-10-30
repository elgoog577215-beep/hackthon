import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WorkspaceSwitcher from '@/components/WorkspaceSwitcher.vue'
import { activeLocale } from '@/shared/i18n'
import type { ProductSurface } from '@/shared/product-brand'

async function setup(surface: ProductSurface) {
  const router = createRouter({
    history: createMemoryHistory('/lingzhi/'),
    routes: [
      { path: '/courses', component: { template: '<div>Teacher</div>' } },
      { path: '/study', component: { template: '<div>Student</div>' } },
    ],
  })
  await router.push(surface === 'teacher' ? '/courses' : '/study')
  await router.isReady()
  return { router, wrapper: mount(WorkspaceSwitcher, { props: { surface }, global: { plugins: [router] } }) }
}

describe('shared workspace switching', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_APP_SURFACE', '')
    vi.stubEnv('VITE_STUDY_APP_URL', '')
    vi.stubEnv('VITE_TEACHER_APP_URL', '')
    activeLocale.value = 'zh'
  })
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); activeLocale.value = 'zh' })

  it.each(['teacher', 'student'] as const)('switches from %s in a shared deployment without reloading', async surface => {
    const { router, wrapper } = await setup(surface)
    const current = surface === 'teacher' ? 0 : 1
    expect(wrapper.findAll('button')[current]!.attributes('aria-pressed')).toBe('true')
    await wrapper.findAll('button')[1 - current]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(surface === 'teacher' ? '/study' : '/courses')
    wrapper.unmount()
  })

  it.each(['teacher', 'student'] as const)('uses the configured peer when leaving a separate %s instance', async surface => {
    const destination = surface === 'teacher' ? 'http://127.0.0.1:5274/study' : 'http://127.0.0.1:5273/courses'
    vi.stubEnv('VITE_APP_SURFACE', surface)
    vi.stubEnv(surface === 'teacher' ? 'VITE_STUDY_APP_URL' : 'VITE_TEACHER_APP_URL', destination)
    const assign = vi.fn()
    vi.stubGlobal('location', { assign })
    const { wrapper } = await setup(surface)
    await wrapper.findAll('button')[surface === 'teacher' ? 1 : 0]!.trigger('click')
    expect(assign).toHaveBeenCalledWith(destination)
    wrapper.unmount()
  })

  it.each(['', '/courses'])('does not expose a teacher route that the student-only router rejects (%s)', async teacherPortal => {
    vi.stubEnv('VITE_APP_SURFACE', 'student')
    vi.stubEnv('VITE_TEACHER_APP_URL', teacherPortal)
    const { wrapper } = await setup('student')
    expect(wrapper.find('.workspace-switcher').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps a configured internal path under the router base and translates both labels', async () => {
    vi.stubEnv('VITE_STUDY_APP_URL', '/study?view=courses')
    activeLocale.value = 'en'
    const { router, wrapper } = await setup('teacher')
    expect(wrapper.findAll('button').map(button => button.text())).toEqual(['Teacher', 'Student'])
    await wrapper.findAll('button')[1]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/study?view=courses')
    expect(router.resolve('/study').href).toBe('/lingzhi/study')
    wrapper.unmount()
  })
})
