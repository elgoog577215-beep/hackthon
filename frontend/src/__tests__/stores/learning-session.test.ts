import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useLearningSessionStore, type LearningSnapshot } from '@/stores/learningSession'

const snapshot = (overrides: Partial<LearningSnapshot> = {}): LearningSnapshot => ({
  snapshot_id: 'ls_1',
  revision: 1,
  course_id: 'course-1',
  course_version_id: 'cv1',
  node_id: 'node-1',
  node_name: '第一节',
  content_anchor: null,
  session: { session_id: 'session-1', device_id: 'device-1', started_at: '2026-07-11T09:00:00Z' },
  task_state: {
    kind: 'reading', object_id: 'node-1', task_revision_id: '', status: 'active',
    context: { course_id: 'course-1', course_version_id: 'cv1', node_id: 'node-1' },
    return_node_id: 'node-1', draft_revision: 0, metadata: {},
  },
  interaction_state: { conversation_id: '', issue_id: '', remediation_session_id: '' },
  fallback_scroll_top: 120,
  activity_at: '2026-07-11T10:00:00Z',
  source: 'live',
  ...overrides,
})

const response = (body: unknown, status = 200) => Promise.resolve({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
} as Response)

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('learning session store', () => {
  it('优先加载服务端快照并写入本地缓存', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ snapshot: snapshot(), resolution: { status: 'exact', resolved_anchor: null, content_changed: false } })))
    const store = useLearningSessionStore()

    await store.load('course-1')

    expect(store.snapshot?.revision).toBe(1)
    expect(store.status).toBe('synced')
    expect(localStorage.getItem('learning_snapshot_v1:course-1')).toContain('"pending":false')
  })

  it('语义位置先落本地，再成功同步到服务端', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ snapshot: snapshot({ revision: 1 }), resolution: null })))
    const store = useLearningSessionStore()
    store.updatePosition({
      courseId: 'course-1',
      courseVersionId: 'cv1',
      nodeId: 'node-1',
      nodeName: '第一节',
      anchor: { block_id: 'b1', block_revision_id: 'r1', content_fingerprint: 'f1', block_type: 'concept', title: '概念', progress: 0.4, text_quote: '概念' },
      fallbackScrollTop: 320,
    })

    expect(store.status).toBe('pending')
    expect(localStorage.getItem('learning_snapshot_v1:course-1')).toContain('"pending":true')
    expect(await store.flush()).toBe(true)
    expect(store.status).toBe('synced')
  })

  it('网络失败时保留本地待同步快照', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const store = useLearningSessionStore()
    store.updatePosition({
      courseId: 'course-1', courseVersionId: 'cv1', nodeId: 'node-1', nodeName: '第一节', anchor: null, fallbackScrollTop: 200,
    })

    expect(await store.flush()).toBe(false)
    expect(store.status).toBe('offline')
    expect(localStorage.getItem('learning_snapshot_v1:course-1')).toContain('"pending":true')
  })

  it('远端更新较新时不覆盖并进入冲突状态', async () => {
    const remote = snapshot({ revision: 2, node_id: 'node-2', activity_at: '2026-07-11T12:00:00Z' })
    vi.stubGlobal('fetch', vi.fn(() => response({ detail: { current_snapshot: remote } }, 409)))
    const store = useLearningSessionStore()
    store.snapshot = snapshot({ revision: 1, activity_at: '2026-07-11T11:00:00Z' })
    store.courseId = 'course-1'

    expect(await store.flush()).toBe(false)
    expect(store.snapshot.node_id).toBe('node-2')
    expect(store.status).toBe('conflict')
  })

  it('版本确认后用服务端新快照替换本地待同步旧版本', () => {
    const store = useLearningSessionStore()
    store.courseId = 'course-1'
    store.snapshot = snapshot({ course_version_id: 'cv1' })
    store.persistLocal(true)
    const migrated = snapshot({
      revision: 2,
      course_version_id: 'cv2',
      task_state: {
        ...snapshot().task_state,
        context: { course_id: 'course-1', course_version_id: 'cv2', node_id: 'node-1' },
      },
    })

    store.acceptVersionTransition(migrated, { status: 'updated_block', resolved_anchor: null, content_changed: true })

    expect(store.snapshot?.course_version_id).toBe('cv2')
    expect(store.status).toBe('synced')
    expect(localStorage.getItem('learning_snapshot_v1:course-1')).toContain('"pending":false')
    expect(localStorage.getItem('learning_snapshot_v1:course-1')).toContain('"course_version_id":"cv2"')
  })

  it('普通阅读位置更新不能跨课程版本改写旧快照', () => {
    const store = useLearningSessionStore()
    store.courseId = 'course-1'
    store.snapshot = snapshot({ course_version_id: 'cv1', revision: 3 })
    store.updatePosition({
      courseId: 'course-1',
      courseVersionId: 'cv2',
      nodeId: 'node-1',
      nodeName: '第一节',
      anchor: null,
      fallbackScrollTop: 900,
    })

    expect(store.snapshot.course_version_id).toBe('cv1')
    expect(store.snapshot.revision).toBe(3)
    expect(store.snapshot.fallback_scroll_top).toBe(120)
    expect(store.status).toBe('idle')
  })

  it('仅在没有新快照时迁移旧位置', () => {
    const store = useLearningSessionStore()
    const migrated = store.migrateLegacy('course-1', 'cv1', 'node-1', '第一节', 900)
    const ignored = store.migrateLegacy('course-1', 'cv1', 'node-2', '第二节', 1200)

    expect(migrated?.source).toBe('legacy_migration')
    expect(migrated?.fallback_scroll_top).toBe(900)
    expect(ignored).toBeNull()
  })

  it('练习任务使用统一任务引用写入当前快照', () => {
    const store = useLearningSessionStore()

    store.setTaskContext({
      kind: 'practice', object_id: 'pa-2', task_revision_id: 'task-2', status: 'active',
      context: { course_id: 'course-1', course_version_id: 'cv1', node_id: 'node-1', objective_revision_id: 'lor-1' },
      return_node_id: 'node-1',
    })

    expect(store.snapshot?.task_state).toMatchObject({
      kind: 'practice', object_id: 'pa-2', task_revision_id: 'task-2', return_node_id: 'node-1',
    })
    expect(localStorage.getItem('learning_snapshot_v1:course-1')).toContain('"task_revision_id":"task-2"')
  })
})
