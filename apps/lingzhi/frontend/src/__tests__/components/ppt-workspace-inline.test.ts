import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PptWorkspace from '@/components/PptWorkspace.vue'
import { useTeachingRepresentationsStore } from '@/stores/teachingRepresentations'
import { useCourseStore } from '@/stores/course'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http, withApiBase: (path: string) => path, learnerIdentityHeaders: () => ({}) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {}, query: {}, meta: {} }), useRouter: () => router }))
const source = { course_id: 'course-1', course_name: '整门课程', source_format: 'canonical', document: { schema_version: 'course_document_v1', course_id: 'course-1', title: '单讲来源', document_revision: 'doc-1', sections: [], blocks: [] } }
function manuscript(overrides: Record<string, any> = {}) {
  return { generation_branch: 'manuscript_first', revision: 'draft-1', status: 'draft', source_state: 'current', confirmable: true, can_generate_ppt: false, mode: 'teaching', theme: 'academic-editorial',
    manuscript: { schema_version: 'ppt_manuscript_v1', page_count: 1, pages: [{ page_id: 'p1', page_number: 1, page_type: 'concept', layout_id: 'L03', title: '比较两个方案', visible_copy: ['相同条件下比较'], page_goal: '能解释差异' }] }, ...overrides }
}
const deck = { representation_id: 'deck-1', representation_type: 'slide_deck', variant_key: 'teaching:academic-editorial', spec_id: 'spec-1', source_document_revision: 'doc-1', payload_schema: 'slide_deck_v6' }
let state: ReturnType<typeof manuscript> | null
let wrappers: ReturnType<typeof mount>[] = []
function setupStore(withDeck = false) {
  const store = useTeachingRepresentationsStore()
  vi.spyOn(store, 'load').mockImplementation(async courseId => {
    store.courseId = courseId
    store.registry = { slide_deck_target_schema: 'slide_deck_v6', representations: withDeck ? [deck] : [], specs: withDeck ? [{ spec_id: 'spec-1', payload: { content: { schema_version: 'slide_deck_v6' } } }] : [] } as any
    return store.registry
  })
  vi.spyOn(store, 'recoverDurableBuild').mockResolvedValue(null as any)
  vi.spyOn(store, 'select').mockImplementation(async id => {
    store.selectedId = id
    store.selectedSpec = { payload: { content: { schema_version: 'slide_deck_v6', title: '当前 PPT', pages: [], slides: [] } } } as any
  })
  return store
}
function open(props: Record<string, any> = {}) {
  const wrapper = mount(PptWorkspace, { props: { embedded: true, courseId: 'course-1', lessonId: 'L1-1', title: '第一讲', ...props }, global: { stubs: { SlideCanvas: true, PptTemplateCreatorDialog: true, SlideDeckWorkbench: { name: 'SlideDeckWorkbench', template: '<article data-testid="published-deck" />', setup(_p: unknown, { expose }: any) { expose({ prepareToLeave: () => true }); return {} } } } } })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  state = manuscript()
  http.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/manuscript') ? { ppt_manuscript_state: state } : source }))
  http.post.mockImplementation(async () => { state = manuscript({ revision: 'confirmed-1', status: 'confirmed', confirmable: false, can_generate_ppt: true }); return { data: { ppt_manuscript_state: state } } })
  http.patch.mockImplementation(async (_url, payload) => { state = manuscript({ revision: 'saved-2', manuscript: { ...state!.manuscript, pages: state!.manuscript.pages.map(page => ({ ...page, ...payload.page_updates.find((update: any) => update.page_id === page.page_id) })) } }); return { data: { ppt_manuscript_state: state } } })
})
afterEach(() => { wrappers.forEach(wrapper => wrapper.unmount()); wrappers = []; vi.restoreAllMocks() })

describe('PPT inside the course workbench', () => {
  it('preserves the whole-course source; confirming waits for an explicit render action', async () => {
    const store = setupStore()
    const applySource = vi.spyOn(useCourseStore(), 'applyCourseDocumentEnvelope')
    const build = vi.spyOn(store, 'buildSlideDeckVariant').mockResolvedValue(undefined as any)
    const wrapper = open()
    await flushPromises()
    const steps = wrapper.get('[data-testid="ppt-flow-steps"]').findAll('button')
    expect(steps).toHaveLength(3)
    expect(steps[1]!.attributes('disabled')).toBeDefined()
    expect(steps[2]!.attributes('disabled')).toBeDefined()
    expect(applySource).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="confirm-ppt-manuscript"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ppt-render-step"]').exists()).toBe(true)
    expect(build).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="render-confirmed-ppt"]').trigger('click')
    await flushPromises()
    expect(build).toHaveBeenCalledOnce()
    expect(build).toHaveBeenCalledWith('course-1', expect.objectContaining({ engineVersion: 'v6' }))
    expect(router.push).not.toHaveBeenCalled()
  })
  it('reads the last available deck when upstream sources are unavailable', async () => {
    state = manuscript({ status: 'confirmed', source_state: 'stale', can_generate_ppt: false, generated_representation_id: 'deck-1' })
    setupStore(true)
    const wrapper = open({ sourceReady: false })
    await flushPromises()
    expect(wrapper.find('[data-testid="published-deck"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ppt-source-required"]').exists()).toBe(false)
    expect(wrapper.find('.ppt-workspace-source-notice').exists()).toBe(true)
    expect(http.get).not.toHaveBeenCalledWith(expect.stringMatching(/\/source$/))
  })
  it('source readiness updates never erase an unsaved draft', async () => {
    setupStore()
    const wrapper = open()
    await flushPromises()
    await wrapper.get('.ppt-manuscript-workflow__title-field input').setValue('教师正在编辑的标题')
    await wrapper.setProps({ sourceReady: false })
    await flushPromises()
    expect((wrapper.get('.ppt-manuscript-workflow__title-field input').element as HTMLInputElement).value).toBe('教师正在编辑的标题')
    expect(await wrapper.vm.prepareToLeave()).toBe(true)
    expect(http.patch).toHaveBeenCalledWith(expect.stringContaining('/lessons/L1-1/'), expect.objectContaining({ page_updates: [expect.objectContaining({ title: '教师正在编辑的标题' })] }))
  })
  it('a failed save keeps the input in the same lesson and allows retry', async () => {
    setupStore()
    const wrapper = open()
    await flushPromises()
    await wrapper.get('.ppt-manuscript-workflow__title-field input').setValue('必须保留的修改')
    http.patch.mockRejectedValueOnce({ response: { data: { detail: { message: '保存冲突，请重试' } } } })
    expect(await wrapper.vm.prepareToLeave()).toBe(false)
    expect((wrapper.get('.ppt-manuscript-workflow__title-field input').element as HTMLInputElement).value).toBe('必须保留的修改')
    expect(wrapper.text()).toContain('保存冲突，请重试')
    expect(await wrapper.vm.prepareToLeave()).toBe(true)
  })
  it('does not report stale sources before the first draft exists', async () => {
    state = manuscript({ status: 'not_generated', source_state: 'stale', manuscript: null }) as any
    setupStore()
    const wrapper = open()
    await flushPromises()
    expect(wrapper.find('.ppt-manuscript-workflow__warning').exists()).toBe(false)
    expect(wrapper.find('.deck-generator.is-inline').exists()).toBe(true)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
  it('checks generation permission even if an event bypasses the disabled button', async () => {
    state = null
    const store = setupStore()
    const build = vi.spyOn(store, 'buildSlideDeckVariant').mockResolvedValue(undefined as any)
    const wrapper = open({ canGenerate: false })
    await flushPromises()
    wrapper.getComponent({ name: 'SlideDeckGeneratorDialog' }).vm.$emit('confirm', { mode: 'teaching', theme: 'academic-editorial', webImageRetrieval: { enabled: false, mode: 'wide_safe' } })
    await flushPromises()
    expect(build).not.toHaveBeenCalled()
  })
  it('requires the exact recovered task before retrying', async () => {
    const store = setupStore()
    const resume = vi.spyOn(store, 'resumeBuild').mockResolvedValue(undefined as any)
    const wrapper = open()
    await flushPromises()
    vi.mocked(store.recoverDurableBuild).mockImplementation(async () => { store.buildPaused = true; store.buildTaskId = 'different-task'; return { id: 'different-task' } as any })
    await wrapper.vm.requestGeneration('retry_generation', 'requested-task')
    expect(store.recoverDurableBuild).toHaveBeenLastCalledWith('course-1', 'requested-task')
    expect(resume).not.toHaveBeenCalled()
  })
  it('checks for an active task even when a previous deck is available', async () => {
    const store = setupStore(true)
    const wrapper = open()
    await flushPromises()
    expect(store.recoverDurableBuild).toHaveBeenCalledWith('course-1')
    expect(wrapper.find('[data-testid="ppt-flow-steps"]').exists()).toBe(true)
  })
  it('a resume finishing after a lesson switch cannot restore the previous lesson scope', async () => {
    const store = setupStore()
    let finish!: () => void
    const resumed = new Promise<void>(resolve => { finish = resolve })
    const resume = vi.spyOn(store, 'resumeBuild').mockReturnValue(resumed)
    const wrapper = open()
    await flushPromises()
    vi.mocked(store.recoverDurableBuild).mockImplementation(async (_courseId, id) => {
      if (!id) return null as any
      store.buildTaskId = id; store.buildPaused = true
      return { id } as any
    })
    const pending = wrapper.vm.requestGeneration('retry_generation', 'exact-task')
    await flushPromises()
    expect(resume).toHaveBeenCalledOnce()
    await wrapper.setProps({ lessonId: 'L1-2' })
    await flushPromises()
    expect(store.teacherLessonId).toBe('L1-2')
    finish()
    await pending
    expect(store.teacherLessonId).toBe('L1-2')
  })
  it('uploading disables generation and prevents leaving the workspace', async () => {
    state = null
    const store = setupStore()
    const build = vi.spyOn(store, 'buildSlideDeckVariant').mockResolvedValue(undefined as any)
    const wrapper = open({ externalBusy: true })
    await flushPromises()
    expect(wrapper.get('.ppt-workspace-body').attributes('inert')).toBeDefined()
    wrapper.getComponent({ name: 'SlideDeckGeneratorDialog' }).vm.$emit('confirm', { mode: 'teaching', theme: 'academic-editorial', webImageRetrieval: { enabled: false, mode: 'wide_safe' } })
    await flushPromises()
    expect(build).not.toHaveBeenCalled()
    expect(await wrapper.vm.prepareToLeave()).toBe(false)
  })

})
