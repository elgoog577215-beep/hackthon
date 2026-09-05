import { createUuid } from './client-id'

export type UsageEventName =
  | 'session_started'
  | 'page_viewed'
  | 'api_action_completed'
  | 'api_action_failed'
  | 'client_error'

export type UsageSurface = 'teacher' | 'learner' | 'shared' | 'unknown'

export interface UsageContext {
  userId: string
  surface: UsageSurface
  routeName?: string
  courseId?: string
}

interface UsageEventInput {
  client_event_id: string
  event_name: UsageEventName
  session_id: string
  surface: UsageSurface
  route_name?: string
  course_id?: string
  properties: Record<string, string | number | boolean>
  client_occurred_at: string
}

interface QueuedUsageEvent extends UsageEventInput {
  owner_id: string
}

interface UsageTrackerOptions {
  endpoint: string
  identityProvider: () => string
  authorizationProvider?: () => string
  contextProvider: () => Omit<UsageContext, 'userId'>
}

const SESSION_KEY = 'lingzhi_usage_session_v1'
const QUEUE_KEY = 'lingzhi_usage_queue_v1'
const PREFERENCE_KEY = 'lingzhi_usage_tracking_v1'
const MAX_QUEUE_SIZE = 500
const BATCH_SIZE = 50
const FLUSH_DELAY_MS = 1200
const CONFIG_ENABLED = String(import.meta.env.VITE_USAGE_TRACKING_ENABLED ?? 'true').toLowerCase() !== 'false'
const SAFE_ID = /^[A-Za-z0-9_.:-]{1,160}$/

let options: UsageTrackerOptions | null = null
let flushTimer: ReturnType<typeof setTimeout> | null = null
let flushPromise: Promise<boolean> | null = null
let errorHandlersInstalled = false

const randomId = (prefix: string) => {
  return `${prefix}-${createUuid()}`
}

const safeGet = (storage: Storage | undefined, key: string) => {
  try {
    return storage?.getItem(key) || ''
  } catch {
    return ''
  }
}

const safeSet = (storage: Storage | undefined, key: string, value: string) => {
  try {
    storage?.setItem(key, value)
  } catch {
    // Usage collection must never make the product fail.
  }
}

const safeRemove = (storage: Storage | undefined, key: string) => {
  try {
    storage?.removeItem(key)
  } catch {
    // Best-effort local governance.
  }
}

const local = () => typeof localStorage === 'undefined' ? undefined : localStorage
const session = () => typeof sessionStorage === 'undefined' ? undefined : sessionStorage

export const isUsageTrackingEnabled = () => (
  CONFIG_ENABLED && safeGet(local(), PREFERENCE_KEY) !== 'off'
)

export const setUsageTrackingEnabled = (enabled: boolean) => {
  safeSet(local(), PREFERENCE_KEY, enabled ? 'on' : 'off')
  if (!enabled) {
    safeRemove(local(), QUEUE_KEY)
    if (flushTimer) clearTimeout(flushTimer)
    flushTimer = null
  }
}

const readQueue = (): QueuedUsageEvent[] => {
  try {
    const value = JSON.parse(safeGet(local(), QUEUE_KEY) || '[]')
    if (!Array.isArray(value)) return []
    return value.filter(item => (
      item && typeof item === 'object'
      && SAFE_ID.test(String(item.owner_id || ''))
      && SAFE_ID.test(String(item.client_event_id || ''))
    )).slice(-MAX_QUEUE_SIZE)
  } catch {
    return []
  }
}

const writeQueue = (value: QueuedUsageEvent[]) => {
  safeSet(local(), QUEUE_KEY, JSON.stringify(value.slice(-MAX_QUEUE_SIZE)))
}

const sessionId = () => {
  const current = safeGet(session(), SESSION_KEY)
  if (SAFE_ID.test(current)) return current
  const created = randomId('usage-session')
  safeSet(session(), SESSION_KEY, created)
  return created
}

const safeOptionalId = (value?: string) => {
  const normalized = String(value || '').trim()
  return SAFE_ID.test(normalized) ? normalized : undefined
}

const currentContext = (override?: Partial<UsageContext>): UsageContext | null => {
  if (!options) return null
  const base = options.contextProvider()
  const userId = safeOptionalId(override?.userId || options.identityProvider())
  if (!userId) return null
  return {
    userId,
    surface: override?.surface || base.surface || 'unknown',
    routeName: safeOptionalId(override?.routeName || base.routeName),
    courseId: safeOptionalId(override?.courseId || base.courseId),
  }
}

const scheduleFlush = () => {
  if (flushTimer || typeof window === 'undefined') return
  flushTimer = setTimeout(() => {
    flushTimer = null
    void flushUsageEvents()
  }, FLUSH_DELAY_MS)
}

const enqueue = (
  eventName: UsageEventName,
  properties: Record<string, string | number | boolean>,
  override?: Partial<UsageContext>,
) => {
  if (!options || !isUsageTrackingEnabled()) return
  const context = currentContext(override)
  if (!context) return
  const event: QueuedUsageEvent = {
    owner_id: context.userId,
    client_event_id: randomId('usage-event'),
    event_name: eventName,
    session_id: sessionId(),
    surface: context.surface,
    ...(context.routeName ? { route_name: context.routeName } : {}),
    ...(context.courseId ? { course_id: context.courseId } : {}),
    properties,
    client_occurred_at: new Date().toISOString(),
  }
  const queue = [...readQueue(), event].slice(-MAX_QUEUE_SIZE)
  writeQueue(queue)
  if (queue.length >= BATCH_SIZE) void flushUsageEvents()
  else scheduleFlush()
}

const navigationEntryKind = (): 'direct' | 'reload' | 'restore' | 'unknown' => {
  try {
    const entry = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    if (entry?.type === 'reload') return 'reload'
    if (entry?.type === 'back_forward') return 'restore'
    if (entry?.type === 'navigate') return 'direct'
  } catch {
    // The navigation timing API is optional.
  }
  return 'unknown'
}

const ensureSessionStarted = (context: Partial<UsageContext>) => {
  const marker = `${SESSION_KEY}:started`
  if (safeGet(session(), marker) === '1') return
  safeSet(session(), marker, '1')
  enqueue('session_started', { entry_kind: navigationEntryKind() }, context)
}

export const trackPageView = (
  context: Partial<UsageContext>,
  navigationKind: 'initial' | 'route' = 'route',
) => {
  ensureSessionStarted(context)
  enqueue('page_viewed', { navigation_kind: navigationKind }, context)
}

const RESOURCE_PARAMETERS: Record<string, string> = {
  courses: 'course_id',
  nodes: 'node_id',
  tasks: 'task_id',
  'generation-tasks': 'task_id',
  attempts: 'attempt_id',
  records: 'record_id',
  sessions: 'session_id',
  messages: 'message_id',
  proposals: 'proposal_id',
  versions: 'version_id',
  revisions: 'revision_id',
  materials: 'material_id',
  assets: 'asset_id',
  blocks: 'block_id',
  questions: 'question_id',
  templates: 'template_id',
  events: 'event_id',
  'course-evolution': 'course_id',
}

export const sanitizeApiRoute = (rawUrl: string): { routeTemplate: string; courseId?: string } | null => {
  try {
    const pathname = new URL(rawUrl, 'http://usage.local').pathname.replace(/\/+$/, '') || '/'
    const apiOffset = pathname.indexOf('/api/')
    const apiPath = apiOffset >= 0 ? pathname.slice(apiOffset) : pathname
    if (!apiPath.startsWith('/api/')) return null
    const segments = apiPath.split('/').filter(Boolean)
    let courseId: string | undefined
    for (let index = 1; index < segments.length; index += 1) {
      const parent = segments[index - 1] || ''
      const segment = segments[index] || ''
      const parameter = RESOURCE_PARAMETERS[parent]
      if (parameter) {
        if (parameter === 'course_id' && !courseId) courseId = safeOptionalId(segment)
        segments[index] = `:${parameter}`
      } else if (!/^[A-Za-z0-9_-]{1,80}$/.test(segment)) {
        segments[index] = ':id'
      }
    }
    const routeTemplate = `/${segments.join('/')}`
    if (routeTemplate.startsWith('/api/usage-events')) return null
    return { routeTemplate, ...(courseId ? { courseId } : {}) }
  } catch {
    return null
  }
}

export const trackApiAction = (input: {
  method?: string
  url?: string
  statusCode?: number
  durationMs?: number
  userId?: string
}) => {
  const method = String(input.method || '').toUpperCase()
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) return
  const route = sanitizeApiRoute(String(input.url || ''))
  if (!route) return
  const statusCode = Math.max(0, Math.min(599, Number(input.statusCode) || 0))
  const completed = statusCode >= 200 && statusCode < 400
  enqueue(completed ? 'api_action_completed' : 'api_action_failed', {
    method,
    route_template: route.routeTemplate,
    status_code: statusCode,
    duration_ms: Math.max(0, Math.min(3_600_000, Math.round(Number(input.durationMs) || 0))),
  }, {
    ...(input.userId ? { userId: input.userId } : {}),
    ...(route.courseId ? { courseId: route.courseId } : {}),
  })
}

export const trackClientError = (errorKind: 'window_error' | 'unhandled_rejection' | 'router_error') => {
  enqueue('client_error', { error_kind: errorKind })
}

const installErrorHandlers = () => {
  if (errorHandlersInstalled || typeof window === 'undefined') return
  window.addEventListener('error', onWindowError)
  window.addEventListener('unhandledrejection', onUnhandledRejection)
  errorHandlersInstalled = true
}

const onWindowError = () => trackClientError('window_error')
const onUnhandledRejection = () => trackClientError('unhandled_rejection')

export const initializeUsageTracking = (value: UsageTrackerOptions) => {
  options = value
  installErrorHandlers()
  if (isUsageTrackingEnabled() && readQueue().length) scheduleFlush()
}

const flushQueuedEvents = async (): Promise<boolean> => {
  if (!options || !isUsageTrackingEnabled() || typeof fetch !== 'function') return false
  for (let pass = 0; pass < 20; pass += 1) {
    const queue = readQueue()
    if (!queue.length) return true
    const ownerId = queue[0]!.owner_id
    const batch = queue.filter(item => item.owner_id === ownerId).slice(0, BATCH_SIZE)
    const ids = new Set(batch.map(item => item.client_event_id))
    let response: Response
    try {
      const token = options.authorizationProvider?.() || ''
      response = await fetch(options.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': ownerId,
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          events: batch.map(({ owner_id: _ownerId, ...event }) => event),
        }),
        keepalive: true,
      })
    } catch {
      return false
    }
    if (!response.ok) {
      if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) {
        writeQueue(queue.filter(item => !ids.has(item.client_event_id)))
      }
      return false
    }
    writeQueue(queue.filter(item => !ids.has(item.client_event_id)))
  }
  return readQueue().length === 0
}

export const flushUsageEvents = (): Promise<boolean> => {
  if (flushPromise) return flushPromise
  flushPromise = flushQueuedEvents().finally(() => {
    flushPromise = null
  })
  return flushPromise
}

export const resetUsageTrackingForTests = () => {
  if (flushTimer) clearTimeout(flushTimer)
  flushTimer = null
  flushPromise = null
  options = null
  safeRemove(local(), QUEUE_KEY)
  safeRemove(local(), PREFERENCE_KEY)
  safeRemove(session(), SESSION_KEY)
  safeRemove(session(), `${SESSION_KEY}:started`)
  if (errorHandlersInstalled && typeof window !== 'undefined') {
    window.removeEventListener('error', onWindowError)
    window.removeEventListener('unhandledrejection', onUnhandledRejection)
  }
  errorHandlersInstalled = false
}
