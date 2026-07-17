import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

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

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
  vi.unstubAllGlobals()
})

describe('teaching representation progressive build', () => {
  it('parses named SSE events in sequence', async () => {
    const received: string[] = []
    await consumeTeachingRepresentationStream(streamResponse([
      { event: 'deck_plan', progress: 4 },
      { event: 'slide_upsert', progress: 22, slide: { unit_id: 'slide:1' } },
      { event: 'build_complete', progress: 100, registry: {} },
    ]), event => received.push(event.event))

    expect(received).toEqual(['deck_plan', 'slide_upsert', 'build_complete'])
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
      { event: 'slide_quality', progress: 97, quality: { passed: false, issues: [{ code: 'slide_item_overflow' }] } },
      { event: 'build_blocked', progress: 100, quality: { passed: false } },
      { event: 'build_complete', progress: 100, build: { status: 'failed_using_last_available' }, registry: { representations: [] } },
    ])))

    const store = useTeachingRepresentationsStore()
    await expect(store.buildProgressive('course-1')).rejects.toThrow('quality_gate_failed')
    expect(store.buildError).toBe('quality_gate_failed')
    expect(store.registry).toBeNull()
  })
})
