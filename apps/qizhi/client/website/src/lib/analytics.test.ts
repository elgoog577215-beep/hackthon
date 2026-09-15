import { describe, expect, it, vi } from 'vitest'

import {
  EngagementTracker,
  normalizePagePath,
  sanitizeProperties,
  type AnalyticsEventDraft,
} from './analytics'

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
    expect(emitted[0].page_path).toBe('/course/1')
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
