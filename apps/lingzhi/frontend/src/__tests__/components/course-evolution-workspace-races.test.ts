import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CourseEvolutionWorkspace from '@/components/CourseEvolutionWorkspace.vue'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { setLocale } from '@/shared/i18n'
import messages from '../../../public/locales/zh/translation.json'

function deferred() {
  let resolve!: (value?: any) => void
  let reject!: (error: Error) => void
  const promise = new Promise<any>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

function setup() {
  const pinia = createPinia()
  const store = useCourseEvolutionStore(pinia)
  store.selectCourse('course-1')
  store.courseContext = { course_id: 'course-1', ready: true, assets: [], outline: [] } as any
  store.plans = [{
    change_set_id: 'plan-1', status: 'pending', operations: [],
    impact_summary: { affected_units: [{ migration_id: 'm1', operation_id: 'op1', asset_type: 'script', disposition: 'rewrite_partial', title: '正文', section_ids: [] }] },
    teacher_change_planning: { structural_operations: [], execution_strategies: ['semantic_impact'], intent: {}, status: 'impact_ready' },
  }] as any
  vi.spyOn(store, 'refreshProgress').mockResolvedValue({})
  vi.spyOn(store, 'loadCourseContext').mockResolvedValue(store.courseContext)
  const wrapper = mount(CourseEvolutionWorkspace, {
    props: { modelValue: true, courseId: 'course-1' },
    global: { plugins: [pinia], stubs: { Teleport: true, Transition: false } },
  })
  return { wrapper, store, actions: (wrapper.vm as any).$.setupState }
}

beforeEach(async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => messages })))
  await setLocale('zh')
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('course change workspace request isolation', () => {
  it('reloads an open workspace for the new course and does not continue an old review there', async () => {
    const { wrapper, store, actions } = setup()
    await flushPromises()
    const review = deferred()
    const reviewing = vi.spyOn(store, 'reviewCoursePlan').mockReturnValue(review.promise)
    const generate = vi.spyOn(store, 'generateSuggested').mockResolvedValue({})
    const pending = actions.saveScopeReview()
    await wrapper.setProps({ courseId: 'course-2' })
    expect(store.refreshProgress).toHaveBeenLastCalledWith('course-2')
    expect(store.loadCourseContext).toHaveBeenLastCalledWith('course-2')
    review.resolve({})
    await pending
    expect(reviewing).toHaveBeenCalledTimes(1)
    expect(generate).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('blocks duplicate applications and ignores a late completion after course switching', async () => {
    const { wrapper, store, actions } = setup()
    await flushPromises()
    const application = deferred()
    const accept = vi.spyOn(store, 'accept').mockReturnValue(application.promise)
    const pending = actions.applyCourseChange()
    await actions.applyCourseChange()
    expect(accept).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ courseId: 'course-2' })
    application.resolve({})
    await pending
    expect(wrapper.emitted('courseApplied')).toBeUndefined()
    wrapper.unmount()
  })

  it('does not show an old request error in a reopened workspace and allows a fresh retry', async () => {
    const { wrapper, store, actions } = setup()
    await flushPromises()
    const oldRequest = deferred()
    const generate = vi.spyOn(store, 'generateSuggested').mockReturnValueOnce(oldRequest.promise).mockResolvedValue({})
    const pending = actions.generateReviewedCandidates()
    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    oldRequest.reject(new Error('old generation failed'))
    await pending
    expect(wrapper.text()).not.toContain('old generation failed')
    await actions.generateReviewedCandidates()
    expect(generate).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
