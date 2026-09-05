import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  flushUsageEvents,
  initializeUsageTracking,
  resetUsageTrackingForTests,
  sanitizeApiRoute,
  setUsageTrackingEnabled,
  trackApiAction,
  trackPageView,
} from '@/utils/usage-tracker'

const initialize = (identityProvider = () => 'learner-usage-test') => {
  initializeUsageTracking({
    endpoint: '/api/usage-events/batch',
    identityProvider,
    contextProvider: () => ({
      surface: 'learner',
      routeName: 'learning',
      courseId: 'course-1',
    }),
  })
}

const requestBody = (callIndex = 0) => JSON.parse(
  String((vi.mocked(fetch).mock.calls[callIndex]?.[1] as RequestInit)?.body || '{}'),
)

beforeEach(() => {
  resetUsageTrackingForTests()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
})
afterEach(() => {
  resetUsageTrackingForTests()
  vi.unstubAllGlobals()
})

describe('usage tracker privacy and delivery', () => {
  it('records one session and stable route name without URL content', async () => {
    initialize()

    trackPageView({
      userId: 'learner-usage-test',
      surface: 'learner',
      routeName: 'learning',
      courseId: 'course-1',
    }, 'initial')
    await flushUsageEvents()

    expect(fetch).toHaveBeenCalledTimes(1)
    const body = requestBody()
    expect(body.events.map((item: any) => item.event_name)).toEqual([
      'session_started',
      'page_viewed',
    ])
    expect(body.events[1]).toMatchObject({
      route_name: 'learning',
      course_id: 'course-1',
      properties: { navigation_kind: 'initial' },
    })
    expect(JSON.stringify(body)).not.toContain('teacherPreview')
    expect((vi.mocked(fetch).mock.calls[0]?.[1] as RequestInit).headers).toMatchObject({
      'X-User-Id': 'learner-usage-test',
    })
  })

  it('sanitizes API IDs and strips query strings before tracking mutations', async () => {
    initialize()

    expect(sanitizeApiRoute(
      '/api/courses/course-1/learning-progress/nodes/node-private?answer=secret#fragment',
    )).toEqual({
      routeTemplate: '/api/courses/:course_id/learning-progress/nodes/:node_id',
      courseId: 'course-1',
    })

    trackApiAction({
      method: 'post',
      url: '/api/courses/course-1/learning-progress/nodes/node-private?answer=secret',
      statusCode: 200,
      durationMs: 32.4,
      userId: 'learner-usage-test',
    })
    await flushUsageEvents()

    const serialized = JSON.stringify(requestBody())
    expect(serialized).toContain('/api/courses/:course_id/learning-progress/nodes/:node_id')
    expect(serialized).not.toContain('node-private')
    expect(serialized).not.toContain('answer')
    expect(serialized).not.toContain('secret')
  })

  it('keeps failed batches for a later retry', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response('{}', { status: 503 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
    initialize()
    trackPageView({ routeName: 'course-library' }, 'initial')

    expect(await flushUsageEvents()).toBe(false)
    expect(await flushUsageEvents()).toBe(true)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(requestBody(1).events).toHaveLength(2)
  })

  it('sends mixed-surface queues under the identity captured with each event', async () => {
    initialize()
    trackPageView({ userId: 'learner-one', routeName: 'learning' }, 'initial')
    trackPageView({ userId: 'teacher-two', surface: 'teacher', routeName: 'course-workspace' })

    await flushUsageEvents()

    const headers = vi.mocked(fetch).mock.calls.map(call => (
      (call[1] as RequestInit).headers as Record<string, string>
    )['X-User-Id'])
    expect(headers).toEqual(['learner-one', 'teacher-two'])
  })

  it('supports a complete client-side off switch and clears queued events', async () => {
    initialize()
    trackPageView({ routeName: 'learning' }, 'initial')
    setUsageTrackingEnabled(false)
    trackApiAction({
      method: 'POST',
      url: '/api/courses/course-1',
      statusCode: 200,
    })

    expect(await flushUsageEvents()).toBe(false)
    expect(fetch).not.toHaveBeenCalled()
  })
})
