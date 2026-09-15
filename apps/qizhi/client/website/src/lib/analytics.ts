import type { Router } from 'vue-router'

import { buildAuthorizationHeader } from '../api/authToken'
import { buildApiFullUrl } from '../api/request'

export type AnalyticsEventName =
  | 'page_view'
  | 'page_engagement'
  | 'scroll_depth_reached'
  | 'feature_used'

export interface AnalyticsEventDraft {
  event_name: AnalyticsEventName
  page_path?: string
  page_instance_id?: string
  workflow_id?: string
  outcome?: 'success' | 'failed' | 'cancelled'
  duration_ms?: number
  scroll_depth?: number
  properties?: Record<string, string | number | boolean>
}

interface AnalyticsEvent extends AnalyticsEventDraft {
  event_id: string
  anonymous_id: string
  session_id: string
  occurred_at: string
  schema_version: 1
  source: 'web'
  client_version?: string
}

const ALLOWED_PROPERTIES = new Set([
  'feature',
  'task_type',
  'source',
  'mode',
  'error_code',
  'result_category',
  'trigger',
])
const PENDING_KEY = 'qizhi_analytics_pending_v1'
const ANONYMOUS_KEY = 'qizhi_analytics_anonymous_v1'
const SESSION_KEY = 'qizhi_analytics_session_v1'
const MAX_PENDING = 200
const SESSION_IDLE_MS = 30 * 60 * 1000
const SESSION_LAST_KEY = 'qizhi_analytics_session_last_v1'

function randomId(prefix: string): string {
  const uuid = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
  return `${prefix}-${uuid}`
}

function storageId(storage: Storage, key: string, prefix: string): string {
  try {
    const existing = storage.getItem(key)
    if (existing) return existing
    const created = randomId(prefix)
    storage.setItem(key, created)
    return created
  } catch {
    return randomId(prefix)
  }
}

export function normalizePagePath(value: string): string {
  const path = value.split(/[?#]/, 1)[0] || '/'
  return path.startsWith('/') ? path.slice(0, 512) : '/'
}

export function sanitizeProperties(
  properties: Record<string, unknown> | undefined,
): Record<string, string | number | boolean> {
  const clean: Record<string, string | number | boolean> = {}
  if (!properties) return clean
  for (const [key, value] of Object.entries(properties)) {
    if (!ALLOWED_PROPERTIES.has(key)) continue
    if ((typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') && String(value).length <= 200) {
      clean[key] = value
    }
  }
  return clean
}

export class EngagementTracker {
  private readonly now: () => number
  private readonly emit: (event: AnalyticsEventDraft) => void
  private pagePath: string | null = null
  private pageInstanceId: string | null = null
  private activeStartedAt: number | null = null
  private visible = true
  private scrollMilestones = new Set<number>()

  constructor(options: { now: () => number; emit: (event: AnalyticsEventDraft) => void }) {
    this.now = options.now
    this.emit = options.emit
  }

  beginPage(pagePath: string): void {
    this.endPage()
    this.pagePath = normalizePagePath(pagePath)
    this.pageInstanceId = randomId('page')
    this.scrollMilestones.clear()
    this.activeStartedAt = this.visible ? this.now() : null
    this.emit({
      event_name: 'page_view',
      page_path: this.pagePath,
      page_instance_id: this.pageInstanceId,
    })
  }

  recordScroll(percent: number): void {
    if (!this.pageInstanceId) return
    const bounded = Math.max(0, Math.min(100, Math.floor(percent)))
    for (const milestone of [25, 50, 75, 100]) {
      if (bounded >= milestone && !this.scrollMilestones.has(milestone)) {
        this.scrollMilestones.add(milestone)
        this.emit({
          event_name: 'scroll_depth_reached',
          page_path: this.pagePath ?? undefined,
          page_instance_id: this.pageInstanceId,
          scroll_depth: milestone,
        })
      }
    }
  }

  heartbeat(): void {
    if (this.visible) this.flushEngagement()
  }

  setVisible(visible: boolean): void {
    if (this.visible === visible) return
    if (!visible) this.flushEngagement()
    this.visible = visible
    this.activeStartedAt = visible && this.pageInstanceId ? this.now() : null
  }

  endPage(): void {
    if (!this.pageInstanceId) return
    if (this.visible) this.flushEngagement()
    this.pagePath = null
    this.pageInstanceId = null
    this.activeStartedAt = null
    this.scrollMilestones.clear()
  }

  private flushEngagement(): void {
    if (this.activeStartedAt === null || !this.pageInstanceId) return
    const now = this.now()
    const duration = Math.max(0, Math.min(3_600_000, Math.round(now - this.activeStartedAt)))
    this.activeStartedAt = now
    if (duration <= 0) return
    this.emit({
      event_name: 'page_engagement',
      page_path: this.pagePath ?? undefined,
      page_instance_id: this.pageInstanceId,
      duration_ms: duration,
    })
  }
}

export class AnalyticsClient {
  private readonly anonymousId = storageId(localStorage, ANONYMOUS_KEY, 'anon')
  private sessionId = storageId(sessionStorage, SESSION_KEY, 'session')
  private queue: AnalyticsEvent[] = []
  private flushTimer: number | undefined

  constructor() {
    try {
      const stored = JSON.parse(localStorage.getItem(PENDING_KEY) || '[]')
      if (Array.isArray(stored)) this.queue = stored.slice(-MAX_PENDING)
    } catch {
      this.queue = []
    }
  }

  emit = (draft: AnalyticsEventDraft): void => {
    const event: AnalyticsEvent = {
      ...draft,
      page_path: draft.page_path ? normalizePagePath(draft.page_path) : undefined,
      properties: sanitizeProperties(draft.properties),
      event_id: randomId('evt'),
      anonymous_id: this.anonymousId,
      session_id: this.currentSessionId(),
      occurred_at: new Date().toISOString(),
      schema_version: 1,
      source: 'web',
      client_version: import.meta.env.VITE_APP_VERSION as string | undefined,
    }
    this.queue.push(event)
    this.queue = this.queue.slice(-MAX_PENDING)
    this.persist()
    if (this.flushTimer === undefined) {
      this.flushTimer = window.setTimeout(() => void this.flush(), 1_000)
    }
  }

  async flush(keepalive = false): Promise<void> {
    if (this.flushTimer !== undefined) {
      window.clearTimeout(this.flushTimer)
      this.flushTimer = undefined
    }
    if (!this.queue.length) return
    const batch = this.queue.slice(0, 50)
    const authorization = buildAuthorizationHeader()
    try {
      const response = await fetch(buildApiFullUrl('/analytics/events'), {
        method: 'POST',
        keepalive,
        headers: {
          'Content-Type': 'application/json',
          ...(authorization ? { Authorization: authorization } : {}),
        },
        body: JSON.stringify({ events: batch }),
      })
      if (!response.ok) return
      this.queue.splice(0, batch.length)
      this.persist()
      if (this.queue.length && !keepalive) void this.flush()
    } catch {
      // Keep the privacy-filtered batch for a later retry.
    }
  }

  pendingCount(): number {
    return this.queue.length
  }

  private currentSessionId(): string {
    const now = Date.now()
    try {
      const last = Number(sessionStorage.getItem(SESSION_LAST_KEY) || 0)
      if (last > 0 && now - last > SESSION_IDLE_MS) {
        this.sessionId = randomId('session')
        sessionStorage.setItem(SESSION_KEY, this.sessionId)
      }
      sessionStorage.setItem(SESSION_LAST_KEY, String(now))
    } catch {
      // Keep the in-memory session when storage is unavailable.
    }
    return this.sessionId
  }

  private persist(): void {
    try {
      localStorage.setItem(PENDING_KEY, JSON.stringify(this.queue))
    } catch {
      // Storage may be disabled; in-memory delivery still works.
    }
  }
}

let installed = false

export function installAnalytics(router: Router): void {
  if (installed || typeof window === 'undefined') return
  installed = true
  const client = new AnalyticsClient()
  const tracker = new EngagementTracker({ now: () => performance.now(), emit: client.emit })

  const routePattern = () => {
    const route = router.currentRoute.value
    return route.matched[route.matched.length - 1]?.path || route.path
  }
  let navigationTracked = false
  void router.isReady().then(() => {
    if (!navigationTracked) tracker.beginPage(routePattern())
  })
  router.afterEach((to) => {
    navigationTracked = true
    tracker.beginPage(to.matched[to.matched.length - 1]?.path || to.path)
  })

  const onVisibility = () => tracker.setVisible(document.visibilityState === 'visible')
  const onScroll = () => {
    const root = document.documentElement
    const maximum = Math.max(0, root.scrollHeight - window.innerHeight)
    tracker.recordScroll(maximum === 0 ? 100 : window.scrollY / maximum * 100)
  }
  const onPageHide = () => {
    tracker.endPage()
    void client.flush(true)
  }
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('pagehide', onPageHide)
  window.setInterval(() => {
    tracker.heartbeat()
    void client.flush()
  }, 30_000)
}
