import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  withApiBase: (path: string) => path,
  learnerIdentityHeaders: (initial: HeadersInit = {}) => new Headers(initial),
}))

import {
  consumeTeachingRepresentationStream,
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

describe('teaching representation progressive build', () => {
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
    expect(store.liveSlides[0]?.title).toBe('失败草稿')
    expect(store.slidePreviewSource).toBe('draft')
    expect(store.slideQuality).toEqual(failedDraftQuality)
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
