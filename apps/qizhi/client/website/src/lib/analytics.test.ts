import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  EngagementTracker,
  AnalyticsClient,
  installAnalytics,
  normalizePagePath,
  sanitizeProperties,
  type AnalyticsEventDraft,
} from './analytics'

class MemoryStorage implements Storage {
  private values = new Map<string, string>()
  get length() { return this.values.size }
  clear() { this.values.clear() }
  getItem(key: string) { return this.values.get(key) ?? null }
  key(index: number) { return [...this.values.keys()][index] ?? null }
  removeItem(key: string) { this.values.delete(key) }
  setItem(key: string, value: string) { this.values.set(key, value) }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.stubGlobal('localStorage', new MemoryStorage())
  vi.stubGlobal('sessionStorage', new MemoryStorage())
  vi.stubGlobal('window', {
    setTimeout: vi.fn(() => 1),
    clearTimeout: vi.fn(),
    setInterval: vi.fn(() => 1),
    addEventListener: vi.fn(),
    innerHeight: 800,
    scrollY: 0,
  })
})

describe('analytics privacy helpers', () => {
  it('removes query strings and fragments from page paths', () => {
    expect(normalizePagePath('/document-analysis?recordId=secret#result')).toBe('/document-analysis')
  })

  it('keeps only approved low-risk properties', () => {
    expect(sanitizeProperties({
      feature: 'outline',
      task_type: 'resource_generation',
      file_name: 'private.docx',
      email: 'person@example.com',
    })).toEqual({ feature: 'outline', task_type: 'resource_generation' })
  })
})

describe('EngagementTracker', () => {
  it('records one page view, scroll milestones, and active time deltas', () => {
    let now = 0
    const emitted: AnalyticsEventDraft[] = []
    const tracker = new EngagementTracker({
      now: () => now,
      emit: (event) => emitted.push(event),
    })

    tracker.beginPage('/course/1?token=secret')
    tracker.recordScroll(80)
    now = 30_000
    tracker.heartbeat()
    now = 40_000
    tracker.setVisible(false)

    expect(emitted.map((event) => event.event_name)).toEqual([
      'page_view',
      'scroll_depth_reached',
      'scroll_depth_reached',
      'scroll_depth_reached',
      'page_engagement',
      'page_engagement',
    ])
    expect(emitted.filter((event) => event.event_name === 'scroll_depth_reached').map((event) => event.scroll_depth)).toEqual([25, 50, 75])
    expect(emitted.filter((event) => event.event_name === 'page_engagement').map((event) => event.duration_ms)).toEqual([30_000, 10_000])
    expect(emitted[0]?.page_path).toBe('/course/1')
  })

  it('does not count hidden time as engagement', () => {
    let now = 0
    const emit = vi.fn()
    const tracker = new EngagementTracker({ now: () => now, emit })

    tracker.beginPage('/my-courses')
    now = 5_000
    tracker.setVisible(false)
    now = 35_000
    tracker.heartbeat()

    const engagement = emit.mock.calls.map(([value]) => value).filter((value) => value.event_name === 'page_engagement')
    expect(engagement).toHaveLength(1)
    expect(engagement[0].duration_ms).toBe(5_000)
  })
})

describe('AnalyticsClient', () => {
  it('batches privacy-filtered events with an optional authorization header', async () => {
    localStorage.setItem('auth_token', 'token-value')
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => ({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new AnalyticsClient()

    client.emit({
      event_name: 'page_view',
      page_path: '/document-analysis?recordId=secret',
      properties: { feature: 'document_analysis', file_name: 'private.docx' } as Record<string, string>,
    })
    expect(client.pendingCount()).toBe(1)
    await client.flush()

    expect(client.pendingCount()).toBe(0)
    const request = fetchMock.mock.calls[0]![1]!
    const body = JSON.parse(String(request.body))
    expect(request.headers).toMatchObject({ Authorization: 'Bearer token-value' })
    expect(body.events[0].page_path).toBe('/document-analysis')
    expect(body.events[0].properties).toEqual({ feature: 'document_analysis' })
  })

  it('retains a failed batch and restores it for retry', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false })))
    const first = new AnalyticsClient()
    first.emit({ event_name: 'page_view', page_path: '/' })
    await first.flush()
    expect(first.pendingCount()).toBe(1)

    const restored = new AnalyticsClient()
    expect(restored.pendingCount()).toBe(1)
  })

  it('rotates the session after thirty minutes of inactivity', () => {
    const now = vi.spyOn(Date, 'now')
    now.mockReturnValue(1_000)
    const client = new AnalyticsClient()
    client.emit({ event_name: 'page_view', page_path: '/' })
    const first = JSON.parse(localStorage.getItem('qizhi_analytics_pending_v1') || '[]')[0].session_id
    now.mockReturnValue(30 * 60 * 1000 + 2_000)
    client.emit({ event_name: 'page_view', page_path: '/later' })
    const second = JSON.parse(localStorage.getItem('qizhi_analytics_pending_v1') || '[]')[1].session_id
    expect(second).not.toBe(first)
  })
})

describe('installAnalytics', () => {
  it('connects router, visibility, scroll, heartbeat and pagehide hooks', async () => {
    const documentHandlers: Record<string, () => void> = {}
    const windowHandlers: Record<string, () => void> = {}
    vi.stubGlobal('document', {
      visibilityState: 'visible',
      documentElement: { scrollHeight: 1600 },
      addEventListener: vi.fn((name: string, handler: () => void) => { documentHandlers[name] = handler }),
    })
    ;(window.addEventListener as ReturnType<typeof vi.fn>).mockImplementation((name: string, handler: () => void) => {
      windowHandlers[name] = handler
    })
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true })))
    let routeHook: ((to: { matched: { path: string }[]; path: string }) => void) | undefined
    const router = {
      currentRoute: { value: { matched: [{ path: '/home' }], path: '/' } },
      isReady: async () => undefined,
      afterEach: (hook: typeof routeHook) => { routeHook = hook },
    }

    installAnalytics(router as never)
    await Promise.resolve()
    routeHook?.({ matched: [{ path: '/course/:id' }], path: '/course/secret' })
    windowHandlers.scroll?.()
    documentHandlers.visibilitychange?.()
    windowHandlers.pagehide?.()

    expect(router.afterEach).toBeDefined()
    expect(window.addEventListener).toHaveBeenCalledWith('scroll', expect.any(Function), { passive: true })
    expect(window.setInterval).toHaveBeenCalled()
  })
})
