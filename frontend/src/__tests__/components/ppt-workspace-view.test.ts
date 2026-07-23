import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PptWorkspaceView from '@/views/PptWorkspaceView.vue'
import { useCourseStore } from '@/stores/course'
import { useTeachingRepresentationsStore } from '@/stores/teachingRepresentations'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const routeState = vi.hoisted(() => ({ route: null as any }))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  withApiBase: (path: string) => path,
  learnerIdentityHeaders: (initial: HeadersInit = {}) => new Headers(initial),
}))

vi.mock('vue-router', () => ({
  useRoute: () => (routeState.route ||= reactive({ params: { courseId: 'course-1' } })),
  useRouter: () => ({ push: vi.fn() }),
}))

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
  routeState.route = null
  httpMock.get.mockResolvedValue({ data: courseEnvelope('canonical') })
})

function courseEnvelope(
  sourceFormat: 'canonical' | 'legacy_projection',
  sourceChecksum = 'checksum-1',
) {
  return {
    course_id: 'course-1',
    course_name: '线性代数',
    current_course_version_id: 'version-1',
    source_format: sourceFormat,
    migration: { required: sourceFormat === 'legacy_projection', source_checksum: sourceChecksum },
    document: {
      schema_version: 'course_document_v1',
      course_id: 'course-1',
      title: '线性代数',
      document_revision: sourceFormat === 'canonical' ? 'cdr-2' : 'cdr-preview',
      sections: [],
      blocks: [],
    },
  }
}

describe('PptWorkspaceView', () => {
  it('reads the CourseDocument envelope before ensuring teaching representations', async () => {
    const calls: string[] = []
    httpMock.get.mockImplementation(async () => {
      calls.push('document')
      return { data: courseEnvelope('canonical') }
    })
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = { representations: [] }
    vi.spyOn(store, 'ensure').mockImplementation(async () => { calls.push('ensure') })

    mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    expect(calls).toEqual(['document', 'ensure'])
  })

  it('requires an explicit legacy-course migration before building, then continues automatically', async () => {
    httpMock.get.mockResolvedValue({ data: courseEnvelope('legacy_projection', 'checksum-legacy') })
    httpMock.post.mockResolvedValue({ data: courseEnvelope('canonical') })
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    const ensure = vi.spyOn(store, 'ensure').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('旧课程需要先升级')
    expect(wrapper.get('.ppt-workspace-state__migrate').text()).toContain('升级课程后生成PPT')
    expect(ensure).not.toHaveBeenCalled()

    await wrapper.get('.ppt-workspace-state__migrate').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/document/migrate',
      { confirm: true, source_checksum: 'checksum-legacy' },
    )
    expect(courseStore.currentCourseSourceFormat).toBe('canonical')
    expect(ensure).toHaveBeenCalledWith('course-1')
  })

  it('reloads the migration preview after a 409 and shows an actionable retry hint', async () => {
    httpMock.get
      .mockResolvedValueOnce({ data: courseEnvelope('legacy_projection', 'checksum-old') })
      .mockResolvedValueOnce({ data: courseEnvelope('legacy_projection', 'checksum-new') })
    httpMock.post.mockRejectedValue({ response: { status: 409 } })
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    const ensure = vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    await wrapper.get('.ppt-workspace-state__migrate').trigger('click')
    await flushPromises()

    expect(httpMock.get).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('课程源已变化，迁移预览已刷新，请确认后重试')
    expect(ensure).not.toHaveBeenCalled()
  })

  it('shows a failed live preview even when no deck has ever been published', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = { representations: [] }
    store.liveSlides = [{
      unit_id: 'slide:first-failed-preview', layout: 'cover', slide_purpose: 'orientation',
      title: '首次构建问题预览', blocks: [], quality: { passed: false },
    }]
    store.slideQuality = { passed: false, issues: [] }
    store.slidePreviewSource = 'draft'
    store.buildError = 'quality_gate_failed'
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(wrapper.find('.deck-canvas').text()).toContain('首次构建问题预览')
    expect(wrapper.text()).toContain('未发布问题预览')
  })

  it('keeps failed live slides visible instead of covering them with the published deck', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      representations: [{
        representation_id: 'slides-1', representation_type: 'slide_deck', spec_id: 'spec-1',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      }],
    }
    store.selectedSpec = {
      spec_id: 'spec-1', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
      payload: { compiler_version: 'same_source_compiler_v2', content: {
        schema_version: 'slide_deck_v2', title: '旧已发布课件',
        slides: [{ unit_id: 'slide:old', layout: 'cover', slide_purpose: 'orientation', title: '旧版本', blocks: [] }],
      } },
    }
    store.liveSlides = [{
      unit_id: 'slide:failed-preview', layout: 'concept', slide_purpose: 'concept',
      title: '本次失败预览', blocks: [], quality: { passed: false },
    }]
    store.slideQuality = { passed: false, issues: [] }
    store.slidePreviewSource = 'draft'
    store.buildError = 'quality_gate_failed'
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    vi.spyOn(store, 'select').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(wrapper.find('.deck-canvas').text()).toContain('本次失败预览')
    expect(wrapper.find('.deck-canvas').text()).not.toContain('旧版本')
    expect(wrapper.text()).toContain('未发布问题预览')
    expect(wrapper.find('.slide-workbench').attributes('data-preview-source')).toBe('draft')
    expect(wrapper.find('.slide-workbench__export').attributes('disabled')).toBeDefined()
  })

  it('keeps the last published deck and labels it when a rebuild fails before creating a draft', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      representations: [{
        representation_id: 'slides-1', representation_type: 'slide_deck', spec_id: 'spec-1',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      }],
    }
    store.selectedSpec = {
      spec_id: 'spec-1', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
      payload: { compiler_version: 'same_source_compiler_v2', content: {
        schema_version: 'slide_deck_v2', title: '上一可用课件',
        slides: [{ unit_id: 'slide:published', layout: 'cover', slide_purpose: 'orientation', title: '上一版本', blocks: [] }],
      } },
    }
    store.liveSlides = []
    store.slidePreviewSource = 'published'
    store.buildError = 'quality_gate_failed'
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    vi.spyOn(store, 'select').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    expect(wrapper.find('.deck-canvas').text()).toContain('上一版本')
    expect(wrapper.text()).toContain('本次生成失败，当前展示上一可用版本')
    expect(wrapper.text()).not.toContain('未发布问题预览')
    expect(wrapper.find('.slide-workbench__export').attributes('disabled')).toBeUndefined()
  })

  it('keeps the published deck when an errored build leaves residual live slides', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      representations: [{
        representation_id: 'slides-1', representation_type: 'slide_deck', spec_id: 'spec-1',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      }],
    }
    store.selectedSpec = {
      spec_id: 'spec-1', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
      payload: { compiler_version: 'same_source_compiler_v2', content: {
        schema_version: 'slide_deck_v2', title: '已发布课件',
        slides: [{ unit_id: 'slide:published', layout: 'cover', slide_purpose: 'orientation', title: '已发布版本', blocks: [] }],
      } },
    }
    store.liveSlides = [{
      unit_id: 'slide:residual', layout: 'concept', slide_purpose: 'concept', title: '残留失败预览', blocks: [],
    }]
    store.slidePreviewSource = 'published'
    store.buildError = 'quality_gate_failed'
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    vi.spyOn(store, 'select').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    expect(wrapper.find('.deck-canvas').text()).toContain('已发布版本')
    expect(wrapper.find('.deck-canvas').text()).not.toContain('残留失败预览')
  })

  it('restores the slide representation after closing the teaching-material overview', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      representations: [
        {
          representation_id: 'outline-1', representation_type: 'outline', spec_id: 'outline-spec',
          status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
        },
        {
          representation_id: 'slides-1', representation_type: 'slide_deck', spec_id: 'slides-spec',
          status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
        },
      ],
    }
    store.selectedId = 'slides-1'
    store.selectedSpec = {
      spec_id: 'slides-spec', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
      payload: { compiler_version: 'same_source_compiler_v2', content: {
        title: '同源课件',
        slides: [{ unit_id: 'slide:1', layout: 'cover', slide_purpose: 'orientation', title: '正式课件', blocks: [] }],
      } },
    }
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    const select = vi.spyOn(store, 'select').mockImplementation(async (representationId: string) => {
      store.selectedId = representationId
    })

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true, TeachingRepresentationsOverlay: true } },
    })
    await flushPromises()

    const workbench = wrapper.getComponent({ name: 'SlideDeckWorkbench' })
    workbench.vm.$emit('open-materials')
    await nextTick()
    const overlay = wrapper.getComponent({ name: 'TeachingRepresentationsOverlay' })
    expect(overlay.props('visible')).toBe(true)

    overlay.vm.$emit('close')
    await flushPromises()
    expect(overlay.props('visible')).toBe(false)
    expect(select).toHaveBeenLastCalledWith('slides-1')
  })

  it('clears legacy migration state when a switched course document fails to load', async () => {
    httpMock.get.mockResolvedValueOnce({ data: courseEnvelope('legacy_projection', 'checksum-legacy') })
    const store = useTeachingRepresentationsStore()
    const ensure = vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    expect(wrapper.find('.ppt-workspace-state__migrate').exists()).toBe(true)

    httpMock.get.mockRejectedValueOnce(new Error('network'))
    routeState.route.params.courseId = 'course-2'
    await nextTick()
    await flushPromises()

    expect(wrapper.find('.ppt-workspace-state__migrate').exists()).toBe(false)
    expect(wrapper.text()).toContain('加载课程源失败，请重试')
    expect(ensure).not.toHaveBeenCalled()
  })
})
