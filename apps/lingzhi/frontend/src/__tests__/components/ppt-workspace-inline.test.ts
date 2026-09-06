import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PptWorkspace from '@/components/PptWorkspace.vue'
import { setLocale } from '@/shared/i18n'
import messages from '../../../public/locales/zh/translation.json'
import { useTeachingRepresentationsStore } from '@/stores/teachingRepresentations'
import { useCourseStore } from '@/stores/course'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http, withApiBase: (path: string) => path, learnerIdentityHeaders: () => ({}), identityScopeHeaders: (_scope: string, headers: Record<string, string>) => headers }))
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
beforeEach(async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, json: async () => messages } as Response); await setLocale('zh')
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
    expect(steps).toHaveLength(2)
    expect(steps[1]!.attributes('disabled')).toBeDefined()
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
  it('keeps saved content readable and assigns export failures to rendering', async () => {
    state = manuscript({ status: 'confirmed', can_generate_ppt: true })
    const store = setupStore()
    vi.mocked(store.recoverDurableBuild).mockImplementation(async () => {
      store.buildResumeOptions = { mode: 'teaching', theme: 'academic-editorial', manuscriptOnly: false }
      store.buildFailure = { code: 'quality_gate_failed', message: 'exported_text_frame_overflow', retryable: true }
      store.buildError = 'quality_gate_failed'
      return null as any
    })
    const wrapper = open()
    await flushPromises()
    expect(wrapper.find('[data-testid="ppt-render-failure"]').exists()).toBe(false)
    await wrapper.get('[data-testid="ppt-flow-steps"]').findAll('button')[0]!.trigger('click')
    expect(wrapper.find('[data-testid="ppt-manuscript-failure"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ppt-render-failure-link"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="ppt-page-reading"]').text()).toContain('相同条件下比较')
    expect(wrapper.text()).not.toContain('exported_text_frame_overflow')
    expect(wrapper.text()).not.toContain('页面内容稿未生成')
    await wrapper.get('[data-testid="edit-ppt-manuscript"]').trigger('click')
    await wrapper.get('.ppt-manuscript-workflow__title-field input').setValue('修订后待确认')
    await wrapper.get('[data-testid="save-ppt-manuscript"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="ppt-flow-steps"]').findAll('button')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="ppt-flow-steps"]').findAll('button')[1]!.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="render-confirmed-ppt"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ppt-render-failure"]').exists()).toBe(false)
  })
  it('assigns a direct render failure to rendering without a refresh', async () => {
    state = manuscript({ status: 'confirmed', can_generate_ppt: true })
    const store = setupStore()
    const wrapper = open()
    await flushPromises()
    vi.mocked(fetch).mockRejectedValueOnce({ code: 'quality_gate_failed', message: 'exported_text_frame_overflow' })
    await wrapper.get('[data-testid="render-confirmed-ppt"]').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenCalledWith('/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/build/stream', expect.objectContaining({ method: 'POST' }))
    expect(store.buildResumeOptions?.manuscriptOnly).toBe(false)
    expect(wrapper.find('[data-testid="ppt-render-failure"]').exists()).toBe(false)
    await wrapper.get('[data-testid="ppt-flow-steps"]').findAll('button')[0]!.trigger('click')
    expect(wrapper.find('[data-testid="ppt-manuscript-failure"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="ppt-page-reading"]').text()).toContain('相同条件下比较')
    expect(wrapper.find('[data-testid="ppt-render-failure-link"]').exists()).toBe(false)
  })
  it('hides teacher render errors in the standalone workspace', async () => {
    state = manuscript({ status: 'confirmed', can_generate_ppt: true })
    setupStore()
    const wrapper = open({ embedded: false })
    await flushPromises()
    vi.mocked(fetch).mockRejectedValueOnce({ code: 'quality_gate_failed', message: 'exported_text_frame_overflow' })
    await wrapper.get('[data-testid="generate-ppt-from-manuscript"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ppt-render-failure"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ppt-manuscript-failure"]').exists()).toBe(false)
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
    await wrapper.get('[data-testid="edit-ppt-manuscript"]').trigger('click')
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
    await wrapper.get('[data-testid="edit-ppt-manuscript"]').trigger('click')
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

  it('uses sidebar commands while the center remains readable and rendering stays explicit', async () => {
    const store = setupStore()
    const build = vi.spyOn(store, 'buildSlideDeckVariant').mockResolvedValue(undefined as any)
    const wrapper = open({ externalControls: true })
    await flushPromises()
    expect(wrapper.find('[data-testid="confirm-ppt-manuscript"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="ppt-page-reading"]').text()).toContain('相同条件下比较')
    expect(wrapper.vm.context.actions.map(action => action.id)).toContain('confirm')
    await wrapper.get('[data-testid="edit-ppt-manuscript"]').trigger('click')
    await wrapper.vm.runContextAction('confirm')
    await flushPromises()
    expect(build).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="ppt-render-step"]').exists()).toBe(false)
    expect(wrapper.find('.ppt-manuscript-workflow__title-field').exists()).toBe(false)
    expect(wrapper.get('[data-testid="ppt-page-reading"]').text()).toContain('相同条件下比较')
    expect(wrapper.get('[data-testid="ppt-flow-steps"]').findAll('button')).toHaveLength(2)
    await wrapper.vm.runContextAction('render')
    expect(build).toHaveBeenCalledWith('course-1', expect.objectContaining({ manuscriptOnly: false }))
  })
  it('keeps the current save error above an earlier render failure and blocks confirmation of unsaved edits', async () => {
    const store = setupStore()
    store.buildResumeOptions = { manuscriptOnly: false } as any
    store.buildFailure = { code: 'quality_gate_failed', message: 'exported_text_frame_overflow' } as any
    const wrapper = open({ externalControls: true })
    await flushPromises()
    await wrapper.get('[data-testid="edit-ppt-manuscript"]').trigger('click')
    await wrapper.get('.ppt-manuscript-workflow__title-field input').setValue('尚未保存')
    await wrapper.vm.runContextAction('confirm')
    expect(http.post).not.toHaveBeenCalled()
    http.patch.mockRejectedValueOnce({ response: { data: { detail: { message: '修订已变化，请重新加载。' } } } })
    await wrapper.get('[data-testid="save-ppt-manuscript"]').trigger('click')
    await flushPromises()
    expect(wrapper.vm.context.error?.summary).toContain('修订已变化')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect((wrapper.get('.ppt-manuscript-workflow__title-field input').element as HTMLInputElement).value).toBe('尚未保存')
  })
  it('keeps edits across compact pagination and reveals selection only on request', async () => {
    state = manuscript({ manuscript: { page_count: 2, pages: [
      { page_id: 'p1', page_number: 1, title: '第一页', visible_copy: ['甲'] },
      { page_id: 'p2', page_number: 2, title: '第二页', visible_copy: ['乙'] },
    ] } })
    setupStore()
    const wrapper = open({ externalControls: true })
    await flushPromises()
    expect(wrapper.find('.ppt-manuscript-workflow__page-list').exists()).toBe(false)
    await wrapper.get('[data-testid="select-ppt-pages"]').trigger('click')
    expect(wrapper.findAll('[data-testid="select-ppt-pages"]')).toHaveLength(1)
    await wrapper.get('[data-testid="select-ppt-pages"]').trigger('click')
    await wrapper.get('[data-testid="edit-ppt-manuscript"]').trigger('click')
    await wrapper.get('.ppt-manuscript-workflow__title-field input').setValue('修改第一页')
    await wrapper.get('[data-testid="ppt-manuscript-page-next"]').trigger('click')
    await wrapper.get('[data-testid="ppt-manuscript-page-prev"]').trigger('click')
    expect((wrapper.get('.ppt-manuscript-workflow__title-field input').element as HTMLInputElement).value).toBe('修改第一页')
    await wrapper.get('[data-testid="cancel-ppt-edit"]').trigger('click')
    expect(http.patch).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="ppt-page-reading"]').text()).toContain('第一页')
  })

})
