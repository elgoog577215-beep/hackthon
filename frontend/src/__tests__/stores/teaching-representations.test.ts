import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  withApiBase: (path: string) => path,
  learnerIdentityHeaders: (initial: HeadersInit = {}) => new Headers(initial),
  identityScopeHeaders: (scope: 'teacher' | 'learner', initial: HeadersInit = {}) => {
    const headers = new Headers(initial)
    headers.set('X-User-Id', scope === 'teacher' ? 'teacher-local-workbench-v1' : 'learner-local-preview-v1')
    return headers
  },
}))

import {
  consumeTeachingRepresentationStream,
  normalizedBuildFailure,
  preferredRepresentationForType,
  type TeachingRepresentation,
  useTeachingRepresentationsStore,
} from '@/stores/teachingRepresentations'

function streamResponse(events: Array<Record<string, unknown>>) {
  const text = events.map((event, index) => (
    `id: ${index + 1}\nevent: ${event.event}\ndata: ${JSON.stringify(event)}\n\n`
  )).join('')
  return new Response(text, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(next => { resolve = next })
  return { promise, resolve }
}

function slideRegistry(id: string, revision: string) {
  return {
    representations: [{
      representation_id: id, representation_type: 'slide_deck', spec_id: `spec-${id}`,
      status: 'ready', stale_unit_ids: [], stale_reasons: [], revision, updated_at: 'now',
    }],
    specs: [],
  }
}

function slideSpec(id: string, title: string) {
  return {
    spec_id: `spec-${id}`, representation_type: 'slide_deck', revision: 'r1', unit_bindings: {},
    payload: { compiler_version: 'same_source_compiler_v2', content: {
      schema_version: 'slide_deck_v2', title, slides: [], quality_summary: { passed: true },
    } },
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
  httpMock.delete.mockReset()
  vi.unstubAllGlobals()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('preferredRepresentationForType', () => {
  it('selects the registry target schema instead of a retained legacy PPT', () => {
    const legacy: TeachingRepresentation = {
      representation_id: 'legacy-v2', representation_type: 'slide_deck', spec_id: 'spec-v2',
      status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: '2026-08-03',
    }
    const current: TeachingRepresentation = {
      representation_id: 'current-v5', representation_type: 'slide_deck', spec_id: 'spec-v5',
      variant_key: 'teaching:qizhi-classroom', status: 'ready', stale_unit_ids: [], stale_reasons: [],
      revision: 'r2', updated_at: '2026-08-05',
    }
    const registry = {
      slide_deck_target_schema: 'slide_deck_v5',
      specs: [
        { spec_id: 'spec-v2', payload: { content: { schema_version: 'slide_deck_v2' } } },
        { spec_id: 'spec-v5', payload: { content: { schema_version: 'slide_deck_v5' } } },
      ],
    }

    expect(preferredRepresentationForType(
      [legacy, current],
      'slide_deck',
      registry,
    )?.representation_id).toBe('current-v5')
  })

  it('does not surface a legacy PPT when the current slide engine is blocked', () => {
    const legacy: TeachingRepresentation = {
      representation_id: 'legacy-v2', representation_type: 'slide_deck', spec_id: 'spec-v2',
      status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: '2026-08-03',
    }

    expect(preferredRepresentationForType(
      [legacy],
      'slide_deck',
      { slide_deck_target_schema: 'blocked' },
    )).toBeUndefined()
  })
})

describe('teaching representation progressive build', () => {
  it('can load compact registry state without eagerly fetching a selected spec', async () => {
    const registry: any = slideRegistry('slides-v6', 'r1')
    registry.specs = [{
      spec_id: 'spec-slides-v6',
      representation_type: 'slide_deck',
      revision: 'r1',
      payload: {
        compiler_version: 'same_source_compiler_v6',
        content: { schema_version: 'slide_deck_v6' },
      },
    }]
    httpMock.get.mockResolvedValueOnce({ data: { registry } })
    const store = useTeachingRepresentationsStore()

    await store.ensure('course-1', { loadSelectedSpec: false })

    expect(httpMock.get).toHaveBeenCalledTimes(1)
    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/courses/course-1/teaching-representations',
    )
    expect(store.selectedId).toBe('slides-v6')
    expect(store.selectedSpec).toBeNull()
  })

  it('can preload an empty registry without recovering or starting a build', async () => {
    httpMock.get.mockResolvedValueOnce({
      data: { registry: { representations: [], specs: [] } },
    })
    const store = useTeachingRepresentationsStore()
    const recover = vi.spyOn(store, 'recoverDurableBuild').mockResolvedValue(null)
    const build = vi.spyOn(store, 'buildProgressive').mockResolvedValue(undefined)

    await store.ensure('course-1', {
      loadSelectedSpec: false,
      handleMissingRepresentations: false,
    })

    expect(recover).not.toHaveBeenCalled()
    expect(build).not.toHaveBeenCalled()
  })

  it('rebuilds the material suite and then regenerates PPT through the scoped V5 route', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(streamResponse([{
        event: 'build_complete', progress: 100,
        registry: { representations: [], specs: [] }, quality: { passed: true },
      }]))
      .mockResolvedValueOnce(streamResponse([{
        event: 'build_complete', progress: 100,
        registry: { representations: [], specs: [] }, quality: { passed: true },
      }]))
    vi.stubGlobal('fetch', fetchMock)
    const store = useTeachingRepresentationsStore()

    await store.rebuildCurrentRepresentations('course-1')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/courses/course-1/teaching-representations/build/stream',
      '/api/courses/course-1/teaching-representations/slide-decks/build/stream',
    ])
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      mode: 'teaching',
      theme: 'academic-editorial',
      force_rebuild: true,
    })
  })

  it('replaces intermediate quality when the final V5 payload fails schema validation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      {
        event: 'slide_quality',
        quality: {
          passed: false,
          blockers: [{ severity: 'critical', code: 'concept_card_overflow' }],
        },
      },
      {
        event: 'build_failed',
        message: '15 validation errors for SlideDeckContent: narrative_role extra_forbidden',
      },
      {
        event: 'error',
        message: 'slide_deck_variant_quality_gate_failed',
      },
    ])))
    const store = useTeachingRepresentationsStore()

    await expect(store.buildProgressive('course-1')).rejects.toThrow('quality_gate_failed')

    expect(store.draftSlideQuality?.blockers?.[0]?.code).toBe('slide_variant_rebuild_failed')
    expect(store.draftSlideQuality?.blockers?.[0]?.code).not.toBe('concept_card_overflow')
  })

  it('retains compact step detail from streamed layout and page events', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      {
        event: 'layout_plan',
        stage: 'layout_plan',
        progress: 20,
        allocation_plan: {
          pages: [
            { page_id: 'slide:1' },
            { page_id: 'slide:2' },
            { page_id: 'slide:3' },
          ],
        },
      },
      {
        event: 'slide_upsert',
        progress: 48,
        slide: { unit_id: 'slide:1', title: '向量的定义', blocks: [] },
      },
      {
        event: 'build_complete',
        progress: 100,
        registry: { representations: [], specs: [] },
        quality: { passed: true },
      },
    ])))
    const store = useTeachingRepresentationsStore()

    await store.buildSlideDeckVariant('course-1', {
      mode: 'teaching',
      theme: 'qizhi-classroom',
    })

    expect(store.buildEstimatedSlideCount).toBe(3)
    expect(store.buildCompletedUnitCount).toBe(1)
    expect(store.buildDetail).toEqual(expect.objectContaining({
      event: 'build_complete',
      completed: 1,
      total: 3,
    }))
    expect(store.buildDetail).not.toHaveProperty('allocation_plan')
    expect(store.buildDetail).not.toHaveProperty('slide')
  })

  it('posts mode and theme to the scoped slide variant stream', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      {
        event: 'build_complete',
        progress: 100,
        registry: { representations: [], specs: [] },
        quality: { passed: true },
      },
    ]))
    vi.stubGlobal('fetch', fetchMock)
    const store = useTeachingRepresentationsStore()

    await store.buildSlideDeckVariant('course-1', {
      mode: 'teaching',
      theme: 'grid-notebook',
      engineVersion: 'v6',
      templatePackId: 'pptp-generic',
      templatePackVersion: 4,
      forceRebuild: true,
      webImageRetrieval: {
        enabled: true,
        mode: 'wide_safe',
        targetCount: 7,
      },
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/courses/course-1/teaching-representations/slide-decks/build/stream')
    expect(JSON.parse(String(init.body))).toEqual({
      mode: 'teaching',
      theme: 'grid-notebook',
      engine_version: 'v6',
      template_pack_id: 'pptp-generic',
      template_version: 4,
      force_rebuild: true,
      web_image_retrieval: {
        enabled: true,
        mode: 'wide_safe',
        target_count: 7,
      },
    })
  })

  it('uses the independent teacher manuscript stream without requiring a deck registry', async () => {
    const manuscriptState = {
      generation_branch: 'manuscript_first',
      revision: 'pptman-1',
      status: 'draft',
      source_state: 'current',
      confirmable: true,
      can_generate_ppt: false,
      manuscript: { schema_version: 'ppt_manuscript_v1', page_count: 1, pages: [] },
    }
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([{
      event: 'build_complete',
      progress: 100,
      stage: 'manuscript_complete',
      ppt_manuscript_state: manuscriptState,
      build: { status: 'manuscript_ready' },
    }]))
    vi.stubGlobal('fetch', fetchMock)
    const store = useTeachingRepresentationsStore()
    store.setTeacherLessonScope('L1-1')

    const completed = await store.buildSlideDeckVariant('course-1', {
      mode: 'teaching',
      theme: 'qizhi-classroom',
      manuscriptOnly: true,
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe(
      '/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/manuscript/build/stream',
    )
    expect(JSON.parse(String(init.body))).toEqual({
      mode: 'teaching',
      theme: 'qizhi-classroom',
      force_rebuild: false,
    })
    expect((init.headers as Headers).get('X-User-Id')).toBe(
      'teacher-local-workbench-v1',
    )
    expect(completed?.ppt_manuscript_state).toEqual(manuscriptState)
    expect(store.buildStage).toBe('manuscript_complete')
  })

  it('queues a durable repair for degraded V6 visual pages without rebuilding the deck', async () => {
    vi.useFakeTimers()
    httpMock.post.mockResolvedValueOnce({ data: {
      status: 'accepted',
      task_id: 'visual-repair-task',
      target_page_ids: ['page-field-feedback'],
    } })
    const store = useTeachingRepresentationsStore()

    const result = await store.repairDegradedVisuals(
      'course-1',
      'slides-v6',
      ['page-field-feedback'],
    )

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/teaching-representations/slides-v6/slide-decks/visual-repair',
      { page_ids: ['page-field-feedback'] },
    )
    expect(result).toEqual({
      status: 'accepted',
      task_id: 'visual-repair-task',
      target_page_ids: ['page-field-feedback'],
    })
    expect(store.buildTaskId).toBe('visual-repair-task')
    expect(store.building).toBe(true)
    expect(store.buildStage).toBe('visual_repair')
  })

  it('preserves an actionable course-logic blocker from a 409 preflight response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: {
        code: 'course_teaching_plan_not_ready',
        message: '当前课程尚未完成正式教学计划，请先补全课程逻辑。',
        action: 'upgrade_course_logic',
        retryable: false,
      },
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    })))
    const store = useTeachingRepresentationsStore()

    await expect(store.buildSlideDeckVariant('course-1', {
      mode: 'teaching',
      theme: 'qizhi-classroom',
      forceRebuild: true,
    })).rejects.toThrow('当前课程尚未完成正式教学计划')

    expect(store.buildError).toBe('course_teaching_plan_not_ready')
    expect(store.buildFailure).toEqual({
      code: 'course_teaching_plan_not_ready',
      message: '当前课程尚未完成正式教学计划，请先补全课程逻辑。',
      action: 'upgrade_course_logic',
      retryable: false,
    })
    expect(store.liveSlides).toEqual([])
    expect(store.slidePreviewSource).toBe('published')
  })

  it('selects the first generated bundle part for the requested mode and theme', async () => {
    const registry = {
      representations: [
        {
          representation_id: 'outline-1', representation_type: 'outline', spec_id: 'outline-spec',
          status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
        },
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
      ],
      specs: [],
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([{
      event: 'build_complete',
      progress: 100,
      registry,
      quality: { passed: true },
    }])))
    httpMock.get.mockResolvedValue({ data: { spec: slideSpec('slides-part-1', '第一分册') } })
    const store = useTeachingRepresentationsStore()

    await store.buildSlideDeckVariant('course-1', {
      mode: 'teaching',
      theme: 'qizhi-classroom',
    })

    expect(store.selectedId).toBe('slides-part-1')
  })

  it('resets all course-scoped state as soon as a different course starts loading', async () => {
    const pending = deferred<{ data: { registry: { representations: never[] } } }>()
    httpMock.get.mockReturnValueOnce(pending.promise)
    const store = useTeachingRepresentationsStore()
    store.courseId = 'course-1'
    store.registry = slideRegistry('slides-old', 'r1')
    store.selectedId = 'slides-old'
    store.selectedSpec = slideSpec('slides-old', '旧课件') as any
    store.quality = { passed: true }
    store.slideQuality = { passed: false }
    store.publishedSlideQuality = { passed: true }
    store.draftSlideQuality = { passed: false }
    store.slidePreviewSource = 'draft'
    store.liveSlides = [{ unit_id: 'slide:old' }]
    store.buildProgress = 72
    store.buildStage = 'quality'
    store.buildError = 'quality_gate_failed'
    store.building = true

    const loading = store.load('course-2')

    expect(store.courseId).toBe('course-2')
    expect(store.registry).toBeNull()
    expect(store.selectedId).toBe('')
    expect(store.selectedSpec).toBeNull()
    expect(store.quality).toBeNull()
    expect(store.slideQuality).toBeNull()
    expect(store.publishedSlideQuality).toBeNull()
    expect(store.draftSlideQuality).toBeNull()
    expect(store.slidePreviewSource).toBe('published')
    expect(store.liveSlides).toEqual([])
    expect(store.buildProgress).toBe(0)
    expect(store.buildStage).toBe('')
    expect(store.buildDisplayStep).toBe(0)
    expect(store.buildError).toBe('')
    expect(store.building).toBe(false)

    pending.resolve({ data: { registry: { representations: [] } } })
    await loading
  })

  it('ignores a stale load response and keeps loading owned by the latest request', async () => {
    const staleRegistry = { representations: [], specs: [{ marker: 'stale' }] }
    const staleResponse = deferred<{ data: { registry: typeof staleRegistry } }>()
    const latestRegistry = { representations: [], specs: [] }
    const latestResponse = deferred<{ data: { registry: typeof latestRegistry } }>()
    httpMock.get
      .mockReturnValueOnce(staleResponse.promise)
      .mockReturnValueOnce(latestResponse.promise)
    const store = useTeachingRepresentationsStore()

    const staleLoad = store.load('course-old')
    const latestLoad = store.load('course-latest')
    staleResponse.resolve({ data: { registry: staleRegistry } })
    await staleLoad

    expect(store.courseId).toBe('course-latest')
    expect(store.registry).toBeNull()
    expect(store.loading).toBe(true)

    latestResponse.resolve({ data: { registry: latestRegistry } })
    await latestLoad

    expect(store.registry).toEqual(latestRegistry)
    expect(store.loading).toBe(false)
  })

  it('ignores a same-course load response after a progressive build starts', async () => {
    const loadResponse = deferred<{ data: { registry: { representations: never[]; specs: Array<{ marker: string }> } } }>()
    const builtRegistry = { representations: [], specs: [{ marker: 'built' }] }
    const staleRegistry = { representations: [], specs: [{ marker: 'stale-load' }] }
    httpMock.get.mockReturnValueOnce(loadResponse.promise)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'build_complete', progress: 100, registry: builtRegistry, quality: { passed: true } },
    ])))
    const store = useTeachingRepresentationsStore()

    const loading = store.load('course-1')
    await store.buildProgressive('course-1')
    loadResponse.resolve({ data: { registry: staleRegistry } })
    await loading

    expect(store.registry).toEqual(builtRegistry)
    expect(store.loading).toBe(false)
  })

  it('does not let a stale ensure restart work for a superseded course', async () => {
    const staleResponse = deferred<{ data: { registry: { representations: never[] } } }>()
    const latestRegistry = { representations: [], specs: [] }
    const latestResponse = deferred<{ data: { registry: typeof latestRegistry } }>()
    httpMock.get
      .mockReturnValueOnce(staleResponse.promise)
      .mockReturnValueOnce(latestResponse.promise)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'build_complete', progress: 100, registry: latestRegistry },
    ])))
    const store = useTeachingRepresentationsStore()

    const staleEnsure = store.ensure('course-old')
    const latestLoad = store.load('course-latest')
    staleResponse.resolve({ data: { registry: { representations: [] } } })
    await staleEnsure

    expect(store.courseId).toBe('course-latest')
    expect(fetch).not.toHaveBeenCalled()

    latestResponse.resolve({ data: { registry: latestRegistry } })
    await latestLoad
  })

  it('ignores a loadSpec response after its course is superseded', async () => {
    const staleSpecResponse = deferred<{ data: { spec: ReturnType<typeof slideSpec> } }>()
    const latestRegistry = { representations: [], specs: [] }
    const latestLoadResponse = deferred<{ data: { registry: typeof latestRegistry } }>()
    httpMock.get
      .mockReturnValueOnce(staleSpecResponse.promise)
      .mockReturnValueOnce(latestLoadResponse.promise)
    const store = useTeachingRepresentationsStore()
    store.courseId = 'course-old'

    const staleSpecLoad = store.loadSpec('slides-old')
    const latestLoad = store.load('course-latest')
    staleSpecResponse.resolve({ data: { spec: slideSpec('slides-old', 'stale deck') } })
    await staleSpecLoad

    expect(store.courseId).toBe('course-latest')
    expect(store.selectedSpec).toBeNull()
    expect(store.publishedSlideQuality).toBeNull()

    latestLoadResponse.resolve({ data: { registry: latestRegistry } })
    await latestLoad
  })

  it('ignores an older select response after a newer selection resolves', async () => {
    const staleResponse = deferred<{ data: { spec: ReturnType<typeof slideSpec> } }>()
    const latestResponse = deferred<{ data: { spec: ReturnType<typeof slideSpec> } }>()
    httpMock.get
      .mockReturnValueOnce(staleResponse.promise)
      .mockReturnValueOnce(latestResponse.promise)
    const store = useTeachingRepresentationsStore()
    store.courseId = 'course-1'

    const staleSelect = store.select('slides-old')
    const latestSelect = store.select('slides-latest')
    latestResponse.resolve({ data: { spec: slideSpec('slides-latest', 'latest deck') } })
    await latestSelect
    staleResponse.resolve({ data: { spec: slideSpec('slides-old', 'stale deck') } })
    await staleSelect

    expect(store.selectedId).toBe('slides-latest')
    expect(store.selectedSpec?.payload.content.title).toBe('latest deck')
  })

  it('ignores a superseded build attempt that returns after the latest attempt', async () => {
    const firstResponse = deferred<Response>()
    const latestRegistry = slideRegistry('slides-latest', 'r2')
    const staleRegistry = slideRegistry('slides-stale', 'r1')
    vi.stubGlobal('fetch', vi.fn()
      .mockReturnValueOnce(firstResponse.promise)
      .mockResolvedValueOnce(streamResponse([
        { event: 'slide_upsert', progress: 40, slide: { unit_id: 'slide:latest', title: '最新页面' } },
        { event: 'build_complete', progress: 100, registry: latestRegistry, quality: { passed: true } },
      ])))
    httpMock.get.mockImplementation((url: string) => Promise.resolve({
      data: { spec: url.includes('slides-latest')
        ? slideSpec('slides-latest', '最新课件')
        : slideSpec('slides-stale', '过期课件') },
    }))
    const store = useTeachingRepresentationsStore()

    const staleBuild = store.buildProgressive('course-1')
    const latestBuild = store.buildProgressive('course-1')
    await latestBuild
    firstResponse.resolve(streamResponse([
      { event: 'slide_upsert', progress: 25, slide: { unit_id: 'slide:stale', title: '过期页面' } },
      { event: 'build_complete', progress: 100, registry: staleRegistry, quality: { passed: true } },
    ]))
    await staleBuild

    expect(store.registry).toEqual(latestRegistry)
    expect(store.selectedId).toBe('slides-latest')
    expect(store.selectedSpec?.payload.content.title).toBe('最新课件')
    expect(store.liveSlides.map(slide => slide.unit_id)).toEqual(['slide:latest'])
    expect(store.buildError).toBe('')
  })

  it('ignores an old-course build response after switching courses', async () => {
    const oldCourseResponse = deferred<Response>()
    const newRegistry = slideRegistry('slides-new-course', 'r2')
    vi.stubGlobal('fetch', vi.fn()
      .mockReturnValueOnce(oldCourseResponse.promise)
      .mockResolvedValueOnce(streamResponse([
        { event: 'slide_upsert', progress: 35, slide: { unit_id: 'slide:new-course', title: '新课程' } },
        { event: 'build_complete', progress: 100, registry: newRegistry, quality: { passed: true } },
      ])))
    httpMock.get.mockResolvedValue({ data: { spec: slideSpec('slides-new-course', '新课程课件') } })
    const store = useTeachingRepresentationsStore()

    const oldBuild = store.buildProgressive('course-1')
    await store.buildProgressive('course-2')
    oldCourseResponse.resolve(streamResponse([
      { event: 'slide_upsert', progress: 90, slide: { unit_id: 'slide:old-course', title: '旧课程' } },
      { event: 'build_complete', progress: 100, registry: slideRegistry('slides-old-course', 'r1') },
    ]))
    await oldBuild

    expect(store.courseId).toBe('course-2')
    expect(store.registry).toEqual(newRegistry)
    expect(store.liveSlides.map(slide => slide.unit_id)).toEqual(['slide:new-course'])
    expect(store.building).toBe(false)
  })

  it('does not let a superseded attempt catch or finally clear the latest build state', async () => {
    const staleResponse = deferred<Response>()
    const latestResponse = deferred<Response>()
    const registry = { representations: [], specs: [] }
    vi.stubGlobal('fetch', vi.fn()
      .mockReturnValueOnce(staleResponse.promise)
      .mockReturnValueOnce(latestResponse.promise))
    const store = useTeachingRepresentationsStore()

    const staleBuild = store.buildProgressive('course-1')
    const latestBuild = store.buildProgressive('course-1')
    staleResponse.resolve(new Response('stale failure', { status: 500 }))
    await expect(staleBuild).rejects.toThrow('stale failure')

    expect(store.building).toBe(true)
    expect(store.buildError).toBe('')
    expect(store.buildStage).toBe('planning')

    latestResponse.resolve(streamResponse([
      { event: 'build_complete', progress: 100, registry, quality: { passed: true } },
    ]))
    await latestBuild

    expect(store.building).toBe(false)
    expect(store.buildError).toBe('')
    expect(store.registry).toEqual(registry)
  })

  it('parses named SSE events in sequence', async () => {
    const received: string[] = []
    await consumeTeachingRepresentationStream(streamResponse([
      { event: 'deck_plan', progress: 4 },
      { event: 'slide_upsert', progress: 22, slide: { unit_id: 'slide:1' } },
      { event: 'build_complete', progress: 100, registry: {} },
    ]), event => received.push(event.event))

    expect(received).toEqual(['deck_plan', 'slide_upsert', 'build_complete'])
  })

  it('keeps the main milestone monotonic through quality repairs and V5 candidate replays', async () => {
    const encoder = new TextEncoder()
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const response = new Response(new ReadableStream<Uint8Array>({
      start(nextController) {
        controller = nextController
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    const store = useTeachingRepresentationsStore()
    const building = store.buildProgressive('course-1')

    const push = async (event: Record<string, unknown>) => {
      controller.enqueue(encoder.encode(
        `event: ${event.event}\ndata: ${JSON.stringify(event)}\n\n`,
      ))
      await vi.waitFor(() => expect(store.buildDetail?.event).toBe(event.event))
    }

    await push({ event: 'slide_quality', progress: 96, quality: { passed: false } })
    expect(store.buildStage).toBe('quality')
    expect(store.buildDisplayStep).toBe(8)

    await push({ event: 'semantic_repair', stage: 'semantic_repair', progress: 97, repair_attempts: 1 })
    expect(store.buildStage).toBe('semantic_repair')
    expect(store.buildDisplayStep).toBe(8)

    await push({
      event: 'slide_reset', stage: 'v5_candidate', progress: 97,
      engine_schema: 'slide_deck_v5', candidate_stage: 'final_contract',
    })
    await push({
      event: 'slide_upsert', stage: 'v5_candidate', progress: 97,
      engine_schema: 'slide_deck_v5', candidate_stage: 'final_contract',
      slide: { unit_id: 'slide:final', title: '最终候选页面' },
    })
    expect(store.buildStage).toBe('semantic_repair')
    expect(store.buildDisplayStep).toBe(8)
    expect(store.buildDetail).toEqual(expect.objectContaining({
      event: 'slide_upsert',
      candidateStage: 'final_contract',
    }))

    await push({ event: 'render_review', stage: 'render_review', progress: 98 })
    expect(store.buildStage).toBe('render_review')
    expect(store.buildDisplayStep).toBe(9)

    await push({
      event: 'slide_reset', stage: 'v5_candidate', progress: 99,
      engine_schema: 'slide_deck_v5', candidate_stage: 'render_verified',
    })
    await push({
      event: 'slide_upsert', stage: 'v5_candidate', progress: 99,
      engine_schema: 'slide_deck_v5', candidate_stage: 'render_verified',
      slide: { unit_id: 'slide:final', title: '渲染确认页面' },
    })
    expect(store.buildStage).toBe('render_review')
    expect(store.buildDisplayStep).toBe(9)

    await push({
      event: 'build_complete', progress: 100,
      registry: { representations: [], specs: [] }, quality: { passed: true },
    })
    controller.close()
    await building
    expect(store.buildDisplayStep).toBe(9)
  })

  it('uses the persisted V6 work manifest instead of legacy stage inference', async () => {
    const encoder = new TextEncoder()
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const response = new Response(new ReadableStream<Uint8Array>({
      start(nextController) {
        controller = nextController
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    const store = useTeachingRepresentationsStore()
    const building = store.buildProgressive('generic-course', {
      mode: 'teaching', theme: 'qizhi-classroom', engineVersion: 'v6',
    })

    const push = async (payload: Record<string, unknown>) => {
      controller.enqueue(encoder.encode(
        `event: slide_build_progress_v2\ndata: ${JSON.stringify({
          event: 'slide_build_progress_v2',
          progress: payload.percent,
          stage: payload.stage,
          slide_build_progress_v2: payload,
        })}\n\n`,
      ))
      await vi.waitFor(() => expect(store.slideBuildProgressV2?.stage).toBe(payload.stage))
    }

    await push({
      schema_version: 'slide_build_progress_v2', event_type: 'heartbeat', task_id: 'v6-task',
      status: 'active', percent: 35, published: false, stage: 'story', step_index: 4,
      step_count: 12, current_chapter_id: 'chapter-a', current_batch_id: 'story-2',
      current_page_id: '', completed_items: 3, total_items: 12, completed_weight: 21,
      total_weight: 60, elapsed_seconds: 14, provider_wait: true, retry_attempt: 1,
      newly_discovered_work: 2, estimated_remaining_seconds: 26, failure: null,
      items: [
        { item_id: 'story-1', kind: 'ai_batch', stage: 'story', label: '故事批次 1', status: 'completed' },
        { item_id: 'story-2', kind: 'ai_batch', stage: 'story', label: '故事批次 2', status: 'running' },
      ],
    })

    expect(store.buildProgress).toBe(35)
    expect(store.buildDisplayStep).toBe(3)
    expect(store.buildDetail).toEqual(expect.objectContaining({
      event: 'slide_build_progress_v2', completed: 3, total: 12,
      itemId: 'story-2', retryAttempt: 1,
    }))

    await push({
      ...store.slideBuildProgressV2,
      event_type: 'update', percent: 28, stage: 'visual', step_index: 7, step_count: 15,
      completed_items: 5, total_items: 15, provider_wait: false, retry_attempt: 0,
      newly_discovered_work: 3, current_batch_id: 'visual-1',
    })

    expect(store.buildProgress).toBe(35)
    expect(store.buildDisplayStep).toBe(6)
    expect(store.slideBuildProgressV2?.total_items).toBe(15)

    controller.enqueue(encoder.encode(
      'event: build_complete\ndata: {"event":"build_complete","progress":100,"registry":{"representations":[],"specs":[]},"quality":{"passed":true}}\n\n',
    ))
    controller.close()
    await building
  })

  it('restores V6 progress from the durable task snapshot after refresh', () => {
    const store = useTeachingRepresentationsStore()
    store.applyDurableBuildTask({
      id: 'v6-recovery-task', status: 'running', progress: 18, phase: 'legacy-phase',
      slide_build_progress_v2: {
        schema_version: 'slide_build_progress_v2', event_type: 'heartbeat',
        task_id: 'v6-recovery-task', status: 'active', percent: 44, published: false,
        stage: 'render', step_index: 9, step_count: 14, current_chapter_id: 'chapter-b',
        current_batch_id: '', current_page_id: 'page-3', completed_items: 8,
        total_items: 14, completed_weight: 42, total_weight: 80, elapsed_seconds: 31,
        provider_wait: false, retry_attempt: 0, newly_discovered_work: 0,
        estimated_remaining_seconds: 28, failure: null, items: [],
      },
    })

    expect(store.building).toBe(true)
    expect(store.buildProgress).toBe(44)
    expect(store.buildStage).toBe('render')
    expect(store.buildDisplayStep).toBe(8)
    expect(store.slideBuildProgressV2?.current_page_id).toBe('page-3')
  })

  it('does not let durable polling overwrite a newer active streamed stage', async () => {
    vi.useFakeTimers()
    const encoder = new TextEncoder()
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const response = new Response(new ReadableStream<Uint8Array>({
      start(nextController) {
        controller = nextController
        controller.enqueue(encoder.encode(
          'event: planner_started\ndata: {"event":"planner_started","progress":1,"task_id":"representation-job-live"}\n\n'
          + 'event: visual_quality\ndata: {"event":"visual_quality","stage":"visual_quality","progress":96,"quality":{"passed":true}}\n\n',
        ))
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    httpMock.get.mockResolvedValue({ data: {
      id: 'representation-job-live',
      status: 'running',
      progress: 96,
      phase: 'slide_plan',
    } })
    const store = useTeachingRepresentationsStore()

    const building = store.buildProgressive('course-1')
    await vi.advanceTimersByTimeAsync(0)
    expect(store.buildStage).toBe('visual_quality')

    await vi.advanceTimersByTimeAsync(1_000)

    expect(httpMock.get).toHaveBeenCalledWith('/api/tasks/representation-job-live')
    expect(store.buildStage).toBe('visual_quality')
    expect(store.buildDisplayStep).toBe(8)

    controller.enqueue(encoder.encode(
      'event: build_complete\ndata: {"event":"build_complete","progress":100,"registry":{"representations":[],"specs":[]},"quality":{"passed":true}}\n\n',
    ))
    controller.close()
    await building
    vi.useRealTimers()
  })

  it('keeps the durable task id and exposes pause and cancel controls', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'planner_started', progress: 1, task_id: 'representation-job-1' },
      { event: 'paused', progress: 36, task_id: 'representation-job-1' },
    ])))
    httpMock.delete.mockResolvedValue({ data: { status: 'deleted' } })
    const store = useTeachingRepresentationsStore()

    await store.buildProgressive('course-1')

    expect(store.buildTaskId).toBe('representation-job-1')
    expect(store.buildPaused).toBe(true)
    expect(store.building).toBe(false)
    await store.cancelBuild()
    expect(httpMock.delete).toHaveBeenCalledWith('/api/tasks/representation-job-1')
    expect(store.buildTaskId).toBe('')
    expect(store.buildStage).toBe('cancelled')
  })

  it('reconciles a failed durable task when its SSE stream never reaches a terminal event', async () => {
    vi.useFakeTimers()
    const encoder = new TextEncoder()
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const response = new Response(new ReadableStream<Uint8Array>({
      start(nextController) {
        controller = nextController
        controller.enqueue(encoder.encode(
          'event: planner_started\ndata: {"event":"planner_started","progress":1,"task_id":"representation-job-stuck"}\n\n',
        ))
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    httpMock.get.mockResolvedValue({ data: {
      id: 'representation-job-stuck',
      type: 'slide_deck_variant_build',
      status: 'failed',
      progress: 100,
      phase: 'build_blocked',
      error: 'slide_deck_variant_quality_gate_failed',
    } })
    const store = useTeachingRepresentationsStore()

    const building = store.buildProgressive('course-1')
    await vi.advanceTimersByTimeAsync(0)
    expect(store.buildTaskId).toBe('representation-job-stuck')

    await vi.advanceTimersByTimeAsync(1_000)

    expect(httpMock.get).toHaveBeenCalledWith('/api/tasks/representation-job-stuck')
    expect(store.building).toBe(false)
    expect(store.buildProgress).toBe(100)
    expect(store.buildStage).toBe('build_blocked')
    expect(store.buildError).toBe('quality_gate_failed')

    controller.close()
    await building
    vi.useRealTimers()
  })

  it('atomically publishes a completed durable build when its SSE stream is still open', async () => {
    vi.useFakeTimers()
    const encoder = new TextEncoder()
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const response = new Response(new ReadableStream<Uint8Array>({
      start(nextController) {
        controller = nextController
        controller.enqueue(encoder.encode(
          'event: planner_started\ndata: {"event":"planner_started","progress":1,"task_id":"representation-job-complete"}\n\n'
          + 'event: slide_upsert\ndata: {"event":"slide_upsert","progress":40,"slide":{"unit_id":"slide:draft","title":"Draft","layout":"concept"}}\n\n',
        ))
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))

    const registry = slideRegistry('slides-published', 'r2')
    const publishedSpec = slideSpec('slides-published', 'Published')
    const publishedQuality = { passed: true, score: 96, total_slide_count: 91 }
    publishedSpec.payload.content.schema_version = 'slide_deck_v5'
    publishedSpec.payload.content.quality_summary = publishedQuality
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/tasks/representation-job-complete') {
        return Promise.resolve({ data: {
          id: 'representation-job-complete',
          type: 'slide_deck_variant_build',
          status: 'completed',
          progress: 100,
          phase: 'build_complete',
        } })
      }
      if (url === '/api/courses/course-1/teaching-representations') {
        return Promise.resolve({ data: { registry } })
      }
      if (url === '/api/courses/course-1/teaching-representations/slides-published/spec') {
        return Promise.resolve({ data: { spec: publishedSpec } })
      }
      throw new Error(`Unexpected GET ${url}`)
    })
    const store = useTeachingRepresentationsStore()

    const building = store.buildProgressive('course-1')
    await vi.advanceTimersByTimeAsync(0)
    expect(store.slidePreviewSource).toBe('draft')
    expect(store.liveSlides).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(1_000)

    expect(store.slidePreviewSource).toBe('published')
    expect(store.liveSlides).toEqual([])
    expect(store.draftSlideQuality).toBeNull()
    expect(store.publishedSlideQuality).toEqual(publishedQuality)
    expect(store.slideQuality).toEqual(publishedQuality)
    expect(store.selectedSpec?.payload.content.schema_version).toBe('slide_deck_v5')

    controller.close()
    await building
    vi.useRealTimers()
  })

  it('restores a failed PPT build terminal state after reopening the workspace', async () => {
    httpMock.get.mockResolvedValue({ data: {
      id: 'representation-job-failed',
      type: 'slide_deck_variant_build',
      status: 'failed',
      progress: 100,
      phase: 'build_blocked',
      error: 'slide_deck_variant_split_required',
    } })
    const store = useTeachingRepresentationsStore()

    await store.recoverDurableBuild('course-1')

    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/task')
    expect(store.buildTaskId).toBe('representation-job-failed')
    expect(store.building).toBe(false)
    expect(store.buildProgress).toBe(100)
    expect(store.buildStage).toBe('build_blocked')
    expect(store.buildError).toBe('deck_split_required')
  })

  it('exposes a retryable failed PPT task as resumable from its saved checkpoint', () => {
    const store = useTeachingRepresentationsStore()

    store.applyDurableBuildTask({
      id: 'representation-job-resumable',
      type: 'slide_deck_variant_build',
      status: 'failed',
      progress: 41,
      phase: 'story',
      error_detail: {
        stage: 'story',
        code: 'story_ai_batch_timeout',
        message: 'provider timed out',
        retryable: true,
        batch_id: 'story-2',
      },
      recovery: {
        state: 'manual_resume',
        can_resume: true,
        reason_code: 'checkpoint_available',
        checkpoint: { progress: 41 },
      },
    })

    expect(store.buildPaused).toBe(true)
    expect(store.buildProgress).toBe(41)
    expect(store.buildFailure?.code).toBe('story_ai_batch_timeout')
  })

  it('replaces an earlier quality failure with the latest durable terminal failure', () => {
    const store = useTeachingRepresentationsStore()
    store.draftSlideQuality = {
      passed: false,
      blockers: [{
        severity: 'critical',
        code: 'story_unsupported_fact',
        message: 'Earlier story attempt failed.',
      }],
    }

    store.applySlideBuildProgressV2({
      schema_version: 'slide_build_progress_v2',
      event_type: 'failed',
      task_id: 'v6-template-failure',
      status: 'failed',
      percent: 66,
      published: false,
      stage: 'template',
      step_index: 6,
      step_count: 10,
      current_chapter_id: '',
      current_batch_id: '',
      current_page_id: 'page-5',
      completed_items: 6,
      total_items: 10,
      completed_weight: 60,
      total_weight: 100,
      elapsed_seconds: 12,
      provider_wait: false,
      retry_attempt: 1,
      newly_discovered_work: 0,
      estimated_remaining_seconds: 0,
      items: [],
      failure: {
        stage: 'template',
        code: 'template_required_slot_unfilled',
        message: 'Required template slot annotation has no source-backed content',
        retryable: false,
        page_id: 'page-5',
      },
    })

    expect(store.buildFailure?.code).toBe('template_required_slot_unfilled')
    expect(store.draftSlideQuality?.blockers?.[0]?.code).toBe(
      'template_required_slot_unfilled',
    )
    expect(store.draftSlideQuality?.blockers?.[0]?.message).toContain(
      'annotation',
    )
  })

  it('normalizes a layout-capacity planner failure after reopening the workspace', async () => {
    httpMock.get.mockResolvedValue({ data: {
      id: 'representation-job-layout-capacity',
      type: 'slide_deck_variant_build',
      status: 'failed',
      progress: 3,
      phase: 'fragmenting',
      error: (
        "No capacity-safe layout for scene=concept, characters=1100, "
        + "items=10, evidence=['code', 'formula', 'list', 'text']"
      ),
    } })
    const store = useTeachingRepresentationsStore()

    await store.recoverDurableBuild('course-1')

    expect(store.buildError).toBe('layout_capacity_failed')
  })

  it('keeps an in-flight cancellation from being overwritten by the old SSE stream', async () => {
    const encoder = new TextEncoder()
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const response = new Response(new ReadableStream<Uint8Array>({
      start(nextController) {
        controller = nextController
        controller.enqueue(encoder.encode(
          'event: planner_started\ndata: {"event":"planner_started","progress":1,"task_id":"representation-job-1"}\n\n',
        ))
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    httpMock.delete.mockResolvedValue({ data: { status: 'deleted' } })
    const store = useTeachingRepresentationsStore()

    const building = store.buildProgressive('course-1')
    await vi.waitFor(() => expect(store.buildTaskId).toBe('representation-job-1'))
    await store.cancelBuild()
    controller.enqueue(encoder.encode(
      'event: error\ndata: {"event":"error","message":"task removed"}\n\n',
    ))
    controller.close()
    await building

    expect(store.buildStage).toBe('cancelled')
    expect(store.buildError).toBe('')
    expect(store.building).toBe(false)
  })

  it('shows generated slides before publishing the final registry', async () => {
    const registry = {
      representations: [{
        representation_id: 'slides-1', representation_type: 'slide_deck', spec_id: 'spec-1',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      }],
      specs: [],
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'deck_plan', progress: 4 },
      { event: 'slide_upsert', progress: 18, slide: { unit_id: 'slide:title', title: '数据结构', layout: 'cover' } },
      { event: 'slide_upsert', progress: 30, slide: { unit_id: 'slide:roadmap', title: '课程路线', layout: 'roadmap' } },
      { event: 'slide_quality', progress: 97, quality: { passed: true, score: 1 } },
      { event: 'build_complete', progress: 100, registry, quality: { passed: true } },
    ])))
    httpMock.get.mockResolvedValue({ data: { spec: {
      spec_id: 'spec-1', representation_type: 'slide_deck', revision: 'r1', unit_bindings: {},
      payload: { compiler_version: 'same_source_compiler_v2', content: { schema_version: 'slide_deck_v2', slides: [] } },
    } } })

    const store = useTeachingRepresentationsStore()
    await store.buildProgressive('course-1')

    expect(store.liveSlides.map(slide => slide.unit_id)).toEqual(['slide:title', 'slide:roadmap'])
    expect(store.slideQuality?.passed).toBe(true)
    expect(store.buildProgress).toBe(100)
    expect(store.buildStage).toBe('complete')
    expect(store.registry).toEqual(registry)
    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/teaching-representations/slides-1/spec')
  })

  it('keeps legacy materializer slides private during a V5 build', async () => {
    const registry = {
      ...slideRegistry('slides-v5', 'r5'),
      slide_deck_target_schema: 'slide_deck_v5',
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'build_started', progress: 1, target_schema: 'slide_deck_v5' },
      {
        event: 'slide_upsert', progress: 30,
        slide: { unit_id: 'slide:legacy-base', title: '旧版基础页', layout: 'concept' },
      },
      {
        event: 'slide_reset', progress: 96, stage: 'v5_candidate',
        engine_schema: 'slide_deck_v5', candidate_stage: 'final_contract',
      },
      {
        event: 'slide_upsert', progress: 97,
        engine_schema: 'slide_deck_v5', candidate_stage: 'final_contract',
        slide: {
          unit_id: 'slide:v5:final', title: '最终 V5 页面', layout: 'editorial-body',
          quality: { resolved_layout: 'editorial-body' },
        },
      },
      {
        event: 'build_complete', progress: 100, registry,
        build: { candidate_status: 'v5_ready' }, quality: { passed: true },
      },
    ])))
    httpMock.get.mockResolvedValue({ data: { spec: {
      ...slideSpec('slides-v5', '最终 V5 页面'),
      payload: { compiler_version: 'same_source_compiler_v2:v5', content: {
        schema_version: 'slide_deck_v5', title: '最终 V5 页面', slides: [],
        candidate_status: 'v5_ready', quality_summary: { passed: true },
      } },
    } } })

    const store = useTeachingRepresentationsStore()
    await store.buildProgressive('course-1')

    expect(store.liveSlides.map(slide => slide.unit_id)).toEqual(['slide:v5:final'])
    expect(store.slideCandidateStatus).toBe('v5_ready')
  })

  it('preserves the complete structured V5 failure envelope', () => {
    expect(normalizedBuildFailure({
      stage: 'source_commit',
      code: 'v5_source_revision_conflict',
      message: '课程内容在 PPT 生成期间发生变化。',
      retryable: true,
      source_revision: 'doc-r1',
      page_id: 'slide:v5:12',
    })).toEqual({
      stage: 'source_commit',
      code: 'v5_source_revision_conflict',
      message: '课程内容在 PPT 生成期间发生变化。',
      retryable: true,
      source_revision: 'doc-r1',
      page_id: 'slide:v5:12',
    })
  })

  it('keeps a quality-blocked build unpublished and exposes a useful error state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'deck_plan', progress: 4 },
      { event: 'slide_upsert', progress: 30, slide: { unit_id: 'slide:title', title: '数据结构', layout: 'cover' } },
      { event: 'build_blocked', progress: 100, quality: { passed: false, issues: [{
        severity: 'critical', code: 'slide_item_overflow', message: '页面要点数量超过版式容量。',
        suggestion: '将可见要点压缩到版式允许的数量。', slide_id: 'slide:title', layout: 'cover',
      }] } },
      { event: 'build_complete', progress: 100, build: { status: 'failed_using_last_available' }, registry: { representations: [] } },
    ])))

    const store = useTeachingRepresentationsStore()
    await expect(store.buildProgressive('course-1')).rejects.toThrow('quality_gate_failed')
    expect(store.buildError).toBe('quality_gate_failed')
    expect(store.registry).toBeNull()
    expect(store.liveSlides).toHaveLength(1)
    expect(store.slideQuality?.issues?.[0]?.suggestion).toBe('将可见要点压缩到版式允许的数量。')
  })

  it('clears the rejected AI draft before a deterministic quality fallback is streamed', async () => {
    const registry = slideRegistry('slides-deterministic', 'r2')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'slide_upsert', progress: 45, slide: { unit_id: 'slide:ai', title: 'Rejected AI', layout: 'concept' } },
      { event: 'quality_fallback', progress: 85, initial_blocker_count: 99, initial_score: 23 },
      { event: 'slide_upsert', progress: 88, slide: { unit_id: 'slide:deterministic', title: 'Accepted fallback', layout: 'cover' } },
      { event: 'build_complete', progress: 100, build: { status: 'ready' }, registry, quality: { passed: true, score: 98 } },
    ])))
    httpMock.get.mockResolvedValue({ data: { spec: slideSpec('slides-deterministic', 'Accepted fallback') } })

    const store = useTeachingRepresentationsStore()
    await store.buildProgressive('course-1')

    expect(store.liveSlides.map(slide => slide.unit_id)).toEqual(['slide:deterministic'])
    expect(store.buildError).toBe('')
    expect(store.buildFailure).toBeNull()
    expect(store.slideQuality?.passed).toBe(true)
  })

  it('keeps the published deck visible when a rebuild fails before the first slide', async () => {
    const registry = slideRegistry('slides-published', 'r1')
    const publishedQuality = { passed: true, score: 0.9, issues: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'deck_plan', progress: 4 },
      { event: 'slide_quality', progress: 97, quality: { passed: false, issues: [] } },
      { event: 'build_blocked', progress: 100, quality: { passed: false, issues: [] } },
      { event: 'build_complete', progress: 100, build: { status: 'failed_using_last_available' }, registry },
    ])))
    const store = useTeachingRepresentationsStore()
    store.courseId = 'course-1'
    store.registry = registry
    store.selectedId = 'slides-published'
    store.selectedSpec = slideSpec('slides-published', '上一可用版本') as any
    store.publishedSlideQuality = publishedQuality
    store.slideQuality = publishedQuality

    await expect(store.buildProgressive('course-1')).rejects.toThrow('quality_gate_failed')

    expect(store.registry).toEqual(registry)
    expect(store.selectedSpec?.payload.content.title).toBe('上一可用版本')
    expect(store.liveSlides).toEqual([])
    expect(store.slidePreviewSource).toBe('published')
    expect(store.slideQuality).toEqual(publishedQuality)
    expect(store.draftSlideQuality).toEqual({ passed: false, issues: [] })
  })

  it('keeps failed draft quality across a real old-spec selection and publishes a later successful rebuild', async () => {
    const registry = {
      representations: [{
        representation_id: 'slides-1', representation_type: 'slide_deck', spec_id: 'spec-1',
        status: 'ready', stale_unit_ids: [], stale_reasons: [], revision: 'r1', updated_at: 'now',
      }],
      specs: [],
    }
    const oldPublishedQuality = { passed: true, score: 0.82, issues: [] }
    const failedDraftQuality = { passed: false, issues: [{
      severity: 'major', code: 'draft_overflow', message: '本次草稿超出版式容量。',
      suggestion: '精简本次草稿要点。', slide_id: 'slide:draft', layout: 'concept',
    }] }
    const successfulQuality = { passed: true, score: 0.97, issues: [] }
    let selectedQuality = oldPublishedQuality
    httpMock.get.mockImplementation(() => Promise.resolve({ data: { spec: {
      spec_id: 'spec-1', representation_type: 'slide_deck', revision: 'r1', unit_bindings: {},
      payload: { compiler_version: 'same_source_compiler_v2', content: {
        schema_version: 'slide_deck_v2', title: '已发布课件', slides: [], quality_summary: selectedQuality,
      } },
    } } }))

    const store = useTeachingRepresentationsStore()
    store.courseId = 'course-1'
    store.registry = registry
    await store.select('slides-1')
    expect(store.slidePreviewSource).toBe('published')
    expect(store.slideQuality).toEqual(oldPublishedQuality)
    expect(store.publishedSlideQuality).toEqual(oldPublishedQuality)

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'deck_plan', progress: 4 },
      { event: 'slide_upsert', progress: 45, slide: { unit_id: 'slide:draft', title: '失败草稿', layout: 'concept' } },
      { event: 'build_blocked', progress: 99, quality: failedDraftQuality },
      { event: 'build_complete', progress: 100, build: { status: 'failed_using_last_available' }, registry },
    ])))

    await expect(store.buildProgressive('course-1')).rejects.toThrow('quality_gate_failed')
    await store.select('slides-1')

    expect(store.selectedSpec?.payload.content.title).toBe('已发布课件')
    expect(store.liveSlides).toEqual([])
    expect(store.slidePreviewSource).toBe('published')
    expect(store.slideQuality).toEqual(oldPublishedQuality)
    expect(store.draftSlideQuality).toEqual(failedDraftQuality)
    expect(store.publishedSlideQuality).toEqual(oldPublishedQuality)

    selectedQuality = successfulQuality
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'deck_plan', progress: 4 },
      { event: 'slide_upsert', progress: 45, slide: { unit_id: 'slide:published', title: '成功课件', layout: 'cover' } },
      { event: 'slide_quality', progress: 97, quality: successfulQuality },
      { event: 'build_complete', progress: 100, build: { status: 'ready' }, registry, quality: successfulQuality },
    ])))

    await store.buildProgressive('course-1')

    expect(store.slidePreviewSource).toBe('published')
    expect(store.slideQuality).toEqual(successfulQuality)
    expect(store.draftSlideQuality).toBeNull()
    expect(store.publishedSlideQuality).toEqual(successfulQuality)
    expect(store.buildError).toBe('')
  })

  it('keeps every unpublished failed draft slide available for diagnosis', async () => {
    const draftSlides = Array.from({ length: 12 }, (_, index) => ({
      event: 'slide_upsert',
      progress: 10 + index,
      slide: { unit_id: `slide:draft:${index}`, title: `Draft ${index}`, layout: 'concept' },
    }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'deck_plan', progress: 4 },
      ...draftSlides,
      { event: 'build_blocked', progress: 99, quality: { passed: false, issues: [] } },
      { event: 'build_complete', progress: 100, build: { status: 'failed' } },
    ])))

    const store = useTeachingRepresentationsStore()
    await expect(store.buildProgressive('course-1')).rejects.toThrow('quality_gate_failed')

    expect(store.slidePreviewSource).toBe('draft')
    expect(store.liveSlides).toHaveLength(12)
    expect(store.liveSlides.map(slide => slide.unit_id)).toEqual(
      Array.from({ length: 12 }, (_, index) => `slide:draft:${index}`),
    )
  })

  it('exports pptx with the selected rendering theme query', async () => {
    httpMock.get.mockResolvedValue({ data: new Blob(['pptx']) })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:pptx'),
      revokeObjectURL: vi.fn(),
    })

    const store = useTeachingRepresentationsStore()
    store.courseId = 'course-1'
    await store.downloadSlides('slides-1', '数据结构', 'academic-bluegray')

    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/courses/course-1/teaching-representations/slides-1/export.pptx',
      { params: { theme: 'academic-bluegray' }, responseType: 'blob' },
    )
  })
})
