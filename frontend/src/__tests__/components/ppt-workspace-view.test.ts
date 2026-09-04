import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PptWorkspaceView from '@/views/PptWorkspaceView.vue'
import { useCourseStore } from '@/stores/course'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { useTeachingRepresentationsStore } from '@/stores/teachingRepresentations'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const routeState = vi.hoisted(() => ({ route: null as any }))
const routerMock = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  withApiBase: (path: string) => path,
  learnerIdentityHeaders: (initial: HeadersInit = {}) => new Headers(initial),
}))

vi.mock('vue-router', () => ({
  useRoute: () => (routeState.route ||= reactive({ params: { courseId: 'course-1' } })),
  useRouter: () => routerMock,
}))

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
  routerMock.push.mockReset()
  routerMock.replace.mockReset()
  routerMock.push.mockResolvedValue(undefined)
  routerMock.replace.mockResolvedValue(undefined)
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
  it('带课次参数时直接读取当前可用教案与讲义的 V6 源', async () => {
    routeState.route = reactive({
      params: { courseId: 'course-1' },
      query: { lesson: 'L1-1' },
      meta: { identityScope: 'teacher' },
    })
    const store = useTeachingRepresentationsStore()
    const ensure = vi.spyOn(store, 'ensure').mockImplementation(async () => {
      store.registry = { slide_deck_target_schema: 'slide_deck_v6', representations: [] }
    })

    mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    expect(store.teacherLessonId).toBe('L1-1')
    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/source',
    )
    expect(ensure).toHaveBeenCalledWith('course-1', {
      loadSelectedSpec: false,
      handleMissingRepresentations: false,
    })
  })

  it('一次性重建参数只打开真实生成设置，教师确认前不自动启动任务', async () => {
    routeState.route = reactive({
      params: { courseId: 'course-1' },
      query: { lesson: 'L1-1', regenerate: '1', returnTo: '/courses/course-1?stage=ppt' },
      path: '/course/course-1/ppt',
      hash: '',
      meta: { identityScope: 'teacher' },
    })
    httpMock.get.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/ppt-v6/manuscript')
        ? { ppt_manuscript_state: null }
        : courseEnvelope('canonical'),
    }))
    const store = useTeachingRepresentationsStore()
    vi.spyOn(store, 'ensure').mockImplementation(async () => {
      store.courseId = 'course-1'
      store.registry = { slide_deck_target_schema: 'slide_deck_v6', representations: [] }
    })
    vi.spyOn(store, 'recoverDurableBuild').mockResolvedValue(null as any)
    const build = vi.spyOn(store, 'buildSlideDeckVariant').mockResolvedValue(undefined as any)

    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    const generator = wrapper.getComponent({ name: 'SlideDeckGeneratorDialog' })
    expect(generator.props('open')).toBe(true)
    expect(build).not.toHaveBeenCalled()
    expect(routerMock.replace).toHaveBeenCalledWith({
      path: '/course/course-1/ppt',
      query: { lesson: 'L1-1', returnTo: '/courses/course-1?stage=ppt' },
      hash: '',
    })

    generator.vm.$emit('confirm', {
      mode: 'teaching',
      theme: 'academic-editorial',
      webImageRetrieval: { enabled: false, mode: 'wide_safe' },
    })
    await flushPromises()
    expect(build).toHaveBeenCalledWith('course-1', expect.objectContaining({
      forceRebuild: true,
      manuscriptOnly: true,
    }))
  })

  it('在独立 PPT 工作区把跨资产要求交给同一个整课修改方案', async () => {
    routeState.route = reactive({
      params: { courseId: 'course-1' },
      query: { lesson: 'L1-1' },
      meta: { identityScope: 'teacher', courseSurface: 'teacher' },
    })
    httpMock.get.mockImplementation((url: string) => {
      if (url.endsWith('/ppt-v6/manuscript')) return Promise.resolve({ data: { ppt_manuscript_state: null } })
      if (url.endsWith('/spec')) return Promise.resolve({ data: { ai_candidate: null } })
      return Promise.resolve({ data: courseEnvelope('canonical') })
    })
    const store = useTeachingRepresentationsStore()
    store.registry = {
      slide_deck_target_schema: 'slide_deck_v6',
      representations: [{
        representation_id: 'slides-v6', representation_type: 'slide_deck',
        variant_key: 'teaching:qizhi-classroom', spec_id: 'spec-v6',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      }],
    }
    store.selectedId = 'slides-v6'
    store.selectedSpec = {
      spec_id: 'spec-v6', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
      payload: { compiler_version: 'representation_compiler_v6:slide_deck_v6', content: {
        schema_version: 'slide_deck_v6', title: '微积分课件', pages: [{
          page_id: 'page-1', page_ordinal: 0, title: '导数的定义', resolved_layout: 'content-stack',
          source_block_ids: [], regions: [],
          speaker_notes: { source_document_revision: 'doc-1', teaching_unit_id: 'L1-1', source_blocks: [] },
        }],
      } },
    }
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    vi.spyOn(store, 'select').mockResolvedValue(undefined)
    const courseEvolutionStore = useCourseEvolutionStore()
    const createCoursePlan = vi.spyOn(courseEvolutionStore, 'createCoursePlan').mockImplementation(async input => ({
      course_evolution_plans: [{
        change_set_id: 'course-change-ppt',
        impact_summary: {
          request_id: input.requestId,
          affected_units: [{ asset_type: 'ppt' }, { asset_type: 'script' }],
        },
        teacher_change_planning: {
          status: 'impact_ready', structural_operations: [], intent: { blocking_questions: [] },
        },
      }],
    } as any))
    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    wrapper.getComponent({ name: 'SlideDeckWorkbench' }).vm.$emit('ask-ai', {
      text: '导数的定义', nodeId: 'page-1', anchor: { slide_unit_id: 'page-1' }, prefill: '',
    })
    await nextTick()
    await wrapper.get('.lesson-ai-composer textarea').setValue('统一修改讲稿和 PPT 中的导数定义')
    await wrapper.get('.lesson-ai-composer').trigger('submit')
    await flushPromises()

    expect(createCoursePlan).toHaveBeenCalledTimes(1)
    expect(createCoursePlan.mock.calls[0]![0]).toMatchObject({ courseId: 'course-1' })
    expect(wrapper.get('.lesson-ai-course-plan').text()).toContain('整课修改方案')
    expect(wrapper.get('.lesson-ai-course-plan').text()).toContain('PPT、讲义')
  })

  it('无原版 PPT 时先显示 PPT 文书步骤，不直接生成 PPT', async () => {
    routeState.route = reactive({
      params: { courseId: 'course-1' },
      query: { lesson: 'L1-1' },
      meta: { identityScope: 'teacher' },
    })
    httpMock.get.mockImplementation((url: string) => {
      if (url.endsWith('/ppt-v6/manuscript')) {
        return Promise.resolve({
          data: {
            ppt_manuscript_state: {
              generation_branch: 'manuscript_first',
              revision: '',
              status: 'not_generated',
              source_state: 'current',
              confirmable: false,
              can_generate_ppt: false,
              manuscript: null,
            },
          },
        })
      }
      return Promise.resolve({ data: courseEnvelope('canonical') })
    })
    const store = useTeachingRepresentationsStore()
    vi.spyOn(store, 'ensure').mockImplementation(async () => {
      store.registry = { slide_deck_target_schema: 'slide_deck_v6', representations: [] }
    })
    vi.spyOn(store, 'recoverDurableBuild').mockResolvedValue(null as any)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="ppt-manuscript-workflow"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="generate-ppt-manuscript"]').text()).toContain('生成页面内容稿')
    expect(wrapper.find('[data-testid="generate-ppt-from-manuscript"]').exists()).toBe(false)
  })

  it('文书确认后才解锁根据文书生成 PPT', async () => {
    routeState.route = reactive({
      params: { courseId: 'course-1' },
      query: { lesson: 'L1-1' },
      meta: { identityScope: 'teacher' },
    })
    const draftState = {
      generation_branch: 'manuscript_first',
      revision: 'pptman-1',
      status: 'draft',
      source_state: 'current',
      confirmable: true,
      can_generate_ppt: false,
      mode: 'teaching',
      theme: 'qizhi-classroom',
      manuscript: {
        schema_version: 'ppt_manuscript_v1',
        page_count: 1,
        pages: [{
          page_id: 'page-1',
          page_number: 1,
          page_type: 'concept',
          layout_id: 'L03',
          title: '函数复合的定义域',
          page_goal: '先确认内层函数输出可进入外层函数',
          primary_claim: '复合函数的定义域由两层约束共同决定',
          visible_copy: ['先求 g(x)', '再检查 f 的输入条件'],
        }],
      },
    }
    httpMock.get.mockImplementation((url: string) => (
      Promise.resolve({
        data: url.endsWith('/ppt-v6/manuscript')
          ? { ppt_manuscript_state: draftState }
          : courseEnvelope('canonical'),
      })
    ))
    httpMock.post.mockResolvedValue({
      data: {
        ppt_manuscript_state: {
          ...draftState,
          status: 'confirmed',
          confirmable: false,
          can_generate_ppt: true,
        },
      },
    })
    const store = useTeachingRepresentationsStore()
    vi.spyOn(store, 'ensure').mockImplementation(async () => {
      store.registry = { slide_deck_target_schema: 'slide_deck_v6', representations: [] }
    })
    vi.spyOn(store, 'recoverDurableBuild').mockResolvedValue(null as any)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('函数复合的定义域')
    expect(wrapper.find('[data-testid="generate-ppt-from-manuscript"]').exists()).toBe(false)
    await wrapper.get('[data-testid="confirm-ppt-manuscript"]').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/manuscript/confirm',
      { manuscript_revision: 'pptman-1' },
    )
    expect(wrapper.get('[data-testid="generate-ppt-from-manuscript"]').text()).toContain('根据已确认页面内容稿生成 PPT')
  })

  it('已有原版 PPT 时不进入文书两步生成链', async () => {
    routeState.route = reactive({
      params: { courseId: 'course-1' },
      query: { lesson: 'L1-1' },
      meta: { identityScope: 'teacher' },
    })
    httpMock.get.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/ppt-v6/manuscript')
        ? {
            ppt_manuscript_state: {
              generation_branch: 'original_ppt_review',
              revision: '',
              status: 'not_generated',
              source_state: 'current',
              confirmable: false,
              can_generate_ppt: false,
              manuscript: null,
            },
          }
        : courseEnvelope('canonical'),
    }))
    const store = useTeachingRepresentationsStore()
    vi.spyOn(store, 'ensure').mockImplementation(async () => {
      store.registry = { slide_deck_target_schema: 'slide_deck_v6', representations: [] }
    })
    vi.spyOn(store, 'recoverDurableBuild').mockResolvedValue(null as any)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('本讲已有原版 PPT')
    expect(wrapper.text()).toContain('继续原版 PPT 的审阅与确认')
    expect(wrapper.find('[data-testid="generate-ppt-manuscript"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="generate-ppt-from-manuscript"]').exists()).toBe(false)
  })

  it('loads the CourseDocument envelope and teaching registry in parallel', async () => {
    const calls: string[] = []
    let resolveDocument!: (value: { data: ReturnType<typeof courseEnvelope> }) => void
    httpMock.get.mockImplementation(() => {
      calls.push('document')
      return new Promise(resolve => { resolveDocument = resolve })
    })
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = { representations: [] }
    vi.spyOn(store, 'ensure').mockImplementation(async () => { calls.push('ensure') })

    mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await nextTick()

    expect(calls).toEqual(['document', 'ensure'])

    resolveDocument({ data: courseEnvelope('canonical') })
    await flushPromises()
  })

  it('loads registry summaries first and fetches the selected PPT spec only once', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    const representation = {
      representation_id: 'slides-v6',
      representation_type: 'slide_deck',
      variant_key: 'teaching:qizhi-classroom',
      spec_id: 'spec-v6',
      status: 'ready',
      stale_unit_ids: [],
      stale_reasons: [],
      revision: 'r1',
      updated_at: 'now',
    }
    const ensure = vi.spyOn(store, 'ensure').mockImplementation(async () => {
      store.registry = {
        slide_deck_target_schema: 'slide_deck_v6',
        representations: [representation],
        specs: [{
          spec_id: 'spec-v6',
          representation_type: 'slide_deck',
          payload: { content: { schema_version: 'slide_deck_v6' } },
        }],
      }
    })
    const select = vi.spyOn(store, 'select').mockResolvedValue(undefined)

    mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    expect(ensure).toHaveBeenCalledWith('course-1', {
      loadSelectedSpec: false,
      handleMissingRepresentations: false,
    })
    expect(select).toHaveBeenCalledTimes(1)
    expect(select).toHaveBeenCalledWith('slides-v6')
  })

  it('blocks a new PPT build when the course is not eligible for V4', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      representations: [],
      slide_deck_target_schema: 'blocked',
      slide_deck_v4_eligible: false,
      slide_deck_v4_blockers: ['course_knowledge_base'],
    }
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(
      wrapper.get('[data-testid="ppt-engine-status"]').attributes('data-engine-status'),
    ).toBe('blocked')
    expect(wrapper.find('.ppt-workspace-state__build').exists()).toBe(false)
    expect(
      wrapper.get('.ppt-workspace-state__upgrade-logic').attributes('disabled'),
    ).toBeUndefined()
  })

  it('repairs migrated course logic in place and unlocks the V4 generator', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      representations: [],
      slide_deck_target_schema: 'blocked',
      slide_deck_v4_eligible: false,
      slide_deck_v4_blockers: [
        'slide_deck_v4 requires a completed official course teaching plan',
      ],
    }
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    httpMock.post.mockResolvedValue({
      data: {
        status: 'success',
        already_ready: false,
        registry: {
          representations: [],
          slide_deck_target_schema: 'slide_deck_v4',
          slide_deck_v4_eligible: true,
          slide_deck_v4_blockers: [],
        },
      },
    })

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(wrapper.get('.ppt-workspace-state__upgrade-logic').text()).toContain(
      '补全课程逻辑',
    )
    await wrapper.get('.ppt-workspace-state__upgrade-logic').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/teaching-representations/course-logic/upgrade',
    )
    expect(store.registry?.slide_deck_target_schema).toBe('slide_deck_v4')
  })

  it('labels a current V5 course-logic deck in the workbench', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      slide_deck_target_schema: 'slide_deck_v5',
      slide_deck_v4_eligible: true,
      representations: [{
        representation_id: 'slides-v5',
        representation_type: 'slide_deck',
        variant_key: 'teaching:qizhi-classroom',
        spec_id: 'spec-v5',
        status: 'ready',
        stale_unit_ids: [],
        stale_reasons: [],
        revision: 'r1',
        updated_at: 'now',
      }],
    }
    store.selectedId = 'slides-v5'
    store.selectedSpec = {
      spec_id: 'spec-v5',
      representation_type: 'slide_deck',
      unit_bindings: {},
      revision: 'r1',
      payload: {
        compiler_version: 'same_source_compiler_v4',
        content: {
          schema_version: 'slide_deck_v5',
          title: 'V5 deck',
          deck_outline: { schema_version: 'deck_outline_v5' },
          slides: [{
            unit_id: 'slide:v5',
            layout: 'cover',
            slide_purpose: 'orientation',
            title: 'V5 cover',
            blocks: [],
          }],
        },
      },
    }
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    vi.spyOn(store, 'select').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(
      wrapper.get('.slide-workbench').attributes('data-engine-status'),
    ).toBe('slide_deck_v5')
  })

  it('does not select a legacy V3 deck when the course now targets V4', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      slide_deck_target_schema: 'slide_deck_v4',
      slide_deck_v4_eligible: true,
      representations: [{
        representation_id: 'slides-v3',
        representation_type: 'slide_deck',
        variant_key: 'teaching:qizhi-classroom',
        spec_id: 'spec-v3',
        status: 'ready',
        stale_unit_ids: [],
        stale_reasons: [],
        revision: 'r1',
        updated_at: 'now',
      }],
      specs: [{
        spec_id: 'spec-v3',
        representation_type: 'slide_deck',
        unit_bindings: {},
        revision: 'r1',
        payload: {
          compiler_version: 'same_source_compiler_v3',
          content: {
            schema_version: 'slide_deck_v3',
            title: 'Legacy V3 deck',
            slides: [{
              unit_id: 'slide:v3',
              layout: 'cover',
              slide_purpose: 'orientation',
              title: 'Legacy cover',
              blocks: [],
            }],
          },
        },
      }],
    }
    store.selectedId = 'slides-v3'
    store.selectedSpec = store.registry.specs[0] as any
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    vi.spyOn(store, 'select').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(wrapper.find('.slide-workbench').exists()).toBe(false)
    expect(
      wrapper.get('[data-testid="ppt-engine-status"]').attributes('data-engine-status'),
    ).toBe('slide_deck_v4')
    expect(
      wrapper.get('.ppt-workspace-state__build').attributes('disabled'),
    ).toBeUndefined()
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
    expect(ensure).toHaveBeenCalledWith('course-1', {
      loadSelectedSpec: false,
      handleMissingRepresentations: false,
    })

    await wrapper.get('.ppt-workspace-state__migrate').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/document/migrate',
      { confirm: true, source_checksum: 'checksum-legacy' },
    )
    expect(courseStore.currentCourseSourceFormat).toBe('canonical')
    expect(ensure).toHaveBeenLastCalledWith('course-1', { loadSelectedSpec: false })
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
    expect(ensure).toHaveBeenCalledOnce()
    expect(ensure).toHaveBeenCalledWith('course-1', {
      loadSelectedSpec: false,
      handleMissingRepresentations: false,
    })
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

  it('shows a Chinese recovery hint for a layout-capacity planner failure', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = { representations: [] }
    store.buildError = 'layout_capacity_failed'
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, {
      global: { stubs: { SideAIPanel: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('课程内容排版失败')
    expect(wrapper.text()).toContain('系统未发布不完整课件')
    expect(wrapper.text()).not.toContain('layout_capacity_failed')
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
    store.draftSlideQuality = {
      passed: false,
      blockers: [
        { severity: 'critical', code: 'body_density_overflow', page_id: 'slide:1' },
        { severity: 'critical', code: 'body_density_overflow', page_id: 'slide:2' },
      ],
    }
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    vi.spyOn(store, 'select').mockResolvedValue(undefined)

    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    expect(wrapper.find('.deck-canvas').text()).toContain('上一版本')
    expect(wrapper.text()).toContain('本次生成失败，当前展示上一可用版本')
    expect(wrapper.text()).toContain('质量检查阻断 · 2 项：正文过密 2')
    expect(wrapper.text()).toContain('body_density_overflow')
    expect(wrapper.text()).not.toContain('未发布问题预览')
    expect(wrapper.find('.slide-workbench__export').attributes('disabled')).toBeUndefined()
  })

  it('does not reselect the previous deck after a rebuild fails', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      slide_deck_target_schema: 'slide_deck_v5',
      slide_deck_v4_eligible: true,
      representations: [{
        representation_id: 'slides-v5', representation_type: 'slide_deck',
        variant_key: 'teaching:qizhi-classroom', spec_id: 'spec-v5',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      }],
    }
    store.selectedId = 'slides-v5'
    store.selectedSpec = {
      spec_id: 'spec-v5', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
      payload: { compiler_version: 'course_logic_slide_compiler_v5.5', content: {
        schema_version: 'slide_deck_v5', title: 'Previous deck',
        slides: [{
          unit_id: 'slide:published', layout: 'cover', slide_purpose: 'orientation',
          title: 'Previous published version', blocks: [],
        }],
      } },
    }
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    const select = vi.spyOn(store, 'select').mockResolvedValue(undefined)
    vi.spyOn(store, 'buildSlideDeckVariant').mockImplementation(async () => {
      store.buildError = 'quality_gate_failed'
      store.slidePreviewSource = 'published'
      throw new Error('quality_gate_failed')
    })

    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()
    select.mockClear()

    wrapper.getComponent({ name: 'SlideDeckWorkbench' }).vm.$emit('rebuild')
    await flushPromises()

    expect(select).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Previous published version')
  })

  it('resumes a saved failed PPT task instead of starting a fresh build', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    store.registry = {
      slide_deck_target_schema: 'slide_deck_v6',
      representations: [{
        representation_id: 'slides-v6', representation_type: 'slide_deck',
        variant_key: 'teaching:qizhi-classroom', spec_id: 'spec-v6',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      }],
    }
    store.selectedId = 'slides-v6'
    store.selectedSpec = {
      spec_id: 'spec-v6', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
      payload: { compiler_version: 'representation_compiler_v6:slide_deck_v6', content: {
        schema_version: 'slide_deck_v6', title: 'Saved deck', pages: [], slides: [],
      } },
    }
    store.buildTaskId = 'failed-v6-task'
    store.buildPaused = true
    store.buildFailure = {
      code: 'story_ai_batch_timeout', message: 'provider timed out', retryable: true,
    }
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    vi.spyOn(store, 'select').mockResolvedValue(undefined)
    const resume = vi.spyOn(store, 'resumeBuild').mockResolvedValue(undefined as any)
    const fresh = vi.spyOn(store, 'buildSlideDeckVariant').mockResolvedValue(undefined as any)

    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()
    wrapper.getComponent({ name: 'SlideDeckWorkbench' }).vm.$emit('rebuild')
    await flushPromises()

    expect(resume).toHaveBeenCalledTimes(1)
    expect(fresh).not.toHaveBeenCalled()
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

  it('switches between automatically generated PPT bundle parts', async () => {
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'course-1'
    const store = useTeachingRepresentationsStore()
    const representations = [
      {
        representation_id: 'slides-part-1', representation_type: 'slide_deck', spec_id: 'part-spec-1',
        variant_key: 'teaching:qizhi-classroom:part:01',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      },
      {
        representation_id: 'slides-part-2', representation_type: 'slide_deck', spec_id: 'part-spec-2',
        variant_key: 'teaching:qizhi-classroom:part:02',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      },
    ] as any
    const specs: Record<string, any> = {
      'slides-part-1': {
        spec_id: 'part-spec-1', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
        payload: { compiler_version: 'same_source_compiler_v4', content: {
          schema_version: 'slide_deck_v3', title: '第一分册',
          bundle_part: { part_index: 1, part_count: 2, title: '第 1 册' },
          slides: [{ unit_id: 'slide:part-1', layout: 'cover', slide_purpose: 'orientation', title: '第一分册页面', blocks: [] }],
        } },
      },
      'slides-part-2': {
        spec_id: 'part-spec-2', representation_type: 'slide_deck', unit_bindings: {}, revision: 'r1',
        payload: { compiler_version: 'same_source_compiler_v4', content: {
          schema_version: 'slide_deck_v3', title: '第二分册',
          bundle_part: { part_index: 2, part_count: 2, title: '第 2 册' },
          slides: [{ unit_id: 'slide:part-2', layout: 'cover', slide_purpose: 'orientation', title: '第二分册页面', blocks: [] }],
        } },
      },
    }
    store.registry = { representations }
    store.selectedId = 'slides-part-1'
    store.selectedSpec = specs['slides-part-1']
    vi.spyOn(store, 'ensure').mockResolvedValue(undefined)
    const select = vi.spyOn(store, 'select').mockImplementation(async (representationId: string) => {
      store.selectedId = representationId
      store.selectedSpec = specs[representationId]
    })

    const wrapper = mount(PptWorkspaceView, { global: { stubs: { SideAIPanel: true } } })
    await flushPromises()

    const partSelector = wrapper.get('select[aria-label="PPT 分册"]')
    expect(partSelector.findAll('option')).toHaveLength(2)
    await partSelector.setValue('slides-part-2')
    await flushPromises()

    expect(select).toHaveBeenLastCalledWith('slides-part-2')
    expect(wrapper.find('.deck-canvas').text()).toContain('第二分册页面')
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
    expect(ensure).toHaveBeenCalledTimes(2)
    expect(ensure).toHaveBeenLastCalledWith('course-2', {
      loadSelectedSpec: false,
      handleMissingRepresentations: false,
    })
  })
})
