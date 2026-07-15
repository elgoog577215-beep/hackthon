import { defineStore } from 'pinia'
import { learnerIdentityHeaders, withApiBase } from '@/utils/http'
import type { ViewportContentAnchor } from '@/utils/learning-position'
import type { LearningTaskRef } from './learningProgress'

export type LearningSyncStatus = 'idle' | 'loading' | 'pending' | 'syncing' | 'synced' | 'offline' | 'conflict'

export interface LearningSnapshot {
  snapshot_id?: string
  revision: number
  course_id: string
  course_version_id: string
  node_id: string
  node_name: string
  content_anchor: ViewportContentAnchor | null
  session: { session_id: string; device_id: string; started_at: string }
  task_state: LearningTaskRef & {
    draft_revision: number
    metadata: Record<string, string | number | boolean | null>
  }
  interaction_state: { conversation_id: string; issue_id: string; remediation_session_id: string }
  fallback_scroll_top: number
  activity_at: string
  source: 'live' | 'legacy_migration' | 'offline_recovery'
  updated_at?: string
}

export interface AnchorResolution {
  status: 'exact' | 'updated_block' | 'fingerprint_remap' | 'node_fallback' | 'course_fallback' | 'unavailable'
  resolved_anchor: (ViewportContentAnchor & { node_id: string; node_name: string }) | null
  content_changed: boolean
  current_course_version_id?: string
}

interface SnapshotApiResponse {
  current_course_version_id?: string
  snapshot: LearningSnapshot | null
  resolution: AnchorResolution | null
}

interface LocalEnvelope {
  snapshot: LearningSnapshot
  resolution: AnchorResolution | null
  pending: boolean
}

interface PositionUpdate {
  courseId: string
  courseVersionId: string
  nodeId: string
  nodeName: string
  anchor: ViewportContentAnchor | null
  fallbackScrollTop: number
  source?: LearningSnapshot['source']
}

const SAVE_DELAY_MS = 1200
let saveTimer: number | null = null
let connectivityBound = false

const now = () => new Date().toISOString()
const randomId = (prefix: string) => `${prefix}_${typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random().toString(16).slice(2)}`}`
const cacheKey = (courseId: string) => `learning_snapshot_v1:${courseId}`

const deviceId = () => {
  const key = 'learning_device_id'
  const current = localStorage.getItem(key)
  if (current) return current
  const created = randomId('device')
  localStorage.setItem(key, created)
  return created
}

const session = () => {
  const key = 'learning_session_id'
  const current = sessionStorage.getItem(key)
  if (current) return current
  const created = randomId('session')
  sessionStorage.setItem(key, created)
  return created
}

const parseTime = (value?: string) => {
  const parsed = Date.parse(value || '')
  return Number.isFinite(parsed) ? parsed : 0
}

export const useLearningSessionStore = defineStore('learningSession', {
  state: () => ({
    courseId: '',
    snapshot: null as LearningSnapshot | null,
    resolution: null as AnchorResolution | null,
    status: 'idle' as LearningSyncStatus,
    restored: false,
  }),
  actions: {
    loadLocal(courseId: string): LocalEnvelope | null {
      try {
        const raw = localStorage.getItem(cacheKey(courseId))
        return raw ? JSON.parse(raw) as LocalEnvelope : null
      } catch {
        return null
      }
    },

    persistLocal(pending: boolean) {
      if (!this.snapshot?.course_id) return
      const envelope: LocalEnvelope = { snapshot: this.snapshot, resolution: this.resolution, pending }
      localStorage.setItem(cacheKey(this.snapshot.course_id), JSON.stringify(envelope))
    },

    acceptVersionTransition(snapshot: LearningSnapshot | null, resolution: AnchorResolution | null) {
      if (saveTimer !== null) {
        window.clearTimeout(saveTimer)
        saveTimer = null
      }
      this.snapshot = snapshot
      this.resolution = resolution
      this.restored = true
      this.status = snapshot ? 'synced' : 'idle'
      if (snapshot) {
        this.courseId = snapshot.course_id
        this.persistLocal(false)
      } else if (this.courseId) {
        localStorage.removeItem(cacheKey(this.courseId))
      }
    },

    async load(courseId: string): Promise<LearningSnapshot | null> {
      this.courseId = courseId
      this.status = 'loading'
      this.restored = false
      const local = this.loadLocal(courseId)
      if (local) {
        this.snapshot = local.snapshot
        this.resolution = local.resolution
      }

      try {
        const response = await fetch(withApiBase(`/api/courses/${courseId}/learning-snapshot`), {
          headers: learnerIdentityHeaders(),
        })
        if (!response.ok) throw new Error(`snapshot load failed: ${response.status}`)
        const remote = await response.json() as SnapshotApiResponse
        if (remote.snapshot) {
          if (local?.pending && parseTime(local.snapshot.activity_at) > parseTime(remote.snapshot.activity_at)) {
            this.snapshot = { ...local.snapshot, revision: remote.snapshot.revision, source: 'offline_recovery' }
            this.resolution = local.resolution
            this.status = 'pending'
            await this.flush()
          } else {
            this.snapshot = remote.snapshot
            this.resolution = remote.resolution
            this.status = 'synced'
            this.persistLocal(false)
          }
        } else if (local?.snapshot) {
          this.snapshot = { ...local.snapshot, revision: 0, source: 'offline_recovery' }
          this.status = 'pending'
          await this.flush()
        } else {
          this.snapshot = null
          this.resolution = null
          this.status = 'idle'
        }
      } catch {
        this.status = this.snapshot ? 'offline' : 'idle'
      }
      return this.snapshot
    },

    migrateLegacy(courseId: string, courseVersionId: string, nodeId: string, nodeName: string, scrollTop: number) {
      if (this.snapshot || !nodeId) return null
      const timestamp = now()
      this.snapshot = this.newSnapshot({
        courseId,
        courseVersionId,
        nodeId,
        nodeName,
        anchor: null,
        fallbackScrollTop: Math.max(0, scrollTop || 0),
        source: 'legacy_migration',
      }, timestamp)
      this.status = 'pending'
      this.persistLocal(true)
      this.scheduleSave()
      return this.snapshot
    },

    updatePosition(position: PositionUpdate) {
      const previous = this.snapshot
      if (
        previous?.course_version_id
        && position.courseVersionId
        && previous.course_version_id !== position.courseVersionId
      ) return
      const sameBlock = previous?.node_id === position.nodeId
        && previous.content_anchor?.block_id === position.anchor?.block_id
      const progressDelta = Math.abs((previous?.content_anchor?.progress || 0) - (position.anchor?.progress || 0))
      const scrollDelta = Math.abs((previous?.fallback_scroll_top || 0) - position.fallbackScrollTop)
      if (sameBlock && progressDelta < 0.02 && scrollDelta < 100) return

      const timestamp = now()
      this.courseId = position.courseId
      this.snapshot = previous
        ? {
            ...previous,
            course_version_id: position.courseVersionId || previous.course_version_id,
            node_id: position.nodeId,
            node_name: position.nodeName,
            content_anchor: position.anchor,
            fallback_scroll_top: Math.max(0, Math.round(position.fallbackScrollTop)),
            activity_at: timestamp,
            source: position.source || 'live',
          }
        : this.newSnapshot(position, timestamp)
      this.status = 'pending'
      this.persistLocal(true)
      this.scheduleSave()
    },

    setTaskContext(taskRef: LearningTaskRef) {
      const context = taskRef.context || {}
      if (!this.snapshot && context.course_id && context.node_id) {
        const timestamp = now()
        this.courseId = context.course_id
        this.snapshot = this.newSnapshot({
          courseId: context.course_id,
          courseVersionId: context.course_version_id || '',
          nodeId: context.node_id,
          nodeName: '',
          anchor: (context.content_anchor as ViewportContentAnchor | null | undefined) || null,
          fallbackScrollTop: 0,
        }, timestamp)
      }
      if (!this.snapshot) return false
      const timestamp = now()
      this.snapshot = {
        ...this.snapshot,
        task_state: {
          ...this.snapshot.task_state,
          ...taskRef,
          draft_revision: this.snapshot.task_state.draft_revision || 0,
          metadata: this.snapshot.task_state.metadata || {},
        },
        interaction_state: {
          ...this.snapshot.interaction_state,
          remediation_session_id: ['remediation', 'validation'].includes(taskRef.kind) ? taskRef.object_id : '',
        },
        activity_at: timestamp,
      }
      this.status = 'pending'
      this.persistLocal(true)
      this.scheduleSave()
      return true
    },

    updateTaskContext(kind: string, objectId: string, remediationSessionId = '') {
      if (!this.snapshot) return false
      return this.setTaskContext({
        kind: ['practice', 'diagnostic', 'remediation', 'validation', 'record', 'review'].includes(kind)
          ? kind as LearningTaskRef['kind']
          : 'reading',
        object_id: remediationSessionId || objectId,
        task_revision_id: objectId,
        status: 'active',
        context: {
          course_id: this.snapshot.course_id,
          course_version_id: this.snapshot.course_version_id,
          node_id: this.snapshot.node_id,
          content_anchor: this.snapshot.content_anchor,
        },
        return_node_id: this.snapshot.node_id,
      })
    },

    clearTaskContext(nodeId?: string) {
      if (!this.snapshot) return false
      return this.setTaskContext({
        kind: 'reading',
        object_id: nodeId || this.snapshot.node_id,
        task_revision_id: '',
        status: 'active',
        context: {
          course_id: this.snapshot.course_id,
          course_version_id: this.snapshot.course_version_id,
          node_id: nodeId || this.snapshot.node_id,
          content_anchor: this.snapshot.content_anchor,
        },
        return_node_id: nodeId || this.snapshot.node_id,
      })
    },

    newSnapshot(position: PositionUpdate, timestamp = now()): LearningSnapshot {
      return {
        revision: 0,
        course_id: position.courseId,
        course_version_id: position.courseVersionId || '',
        node_id: position.nodeId,
        node_name: position.nodeName,
        content_anchor: position.anchor,
        session: { session_id: session(), device_id: deviceId(), started_at: timestamp },
        task_state: {
          kind: 'reading',
          object_id: position.nodeId,
          task_revision_id: '',
          status: 'active',
          context: {
            course_id: position.courseId,
            course_version_id: position.courseVersionId,
            node_id: position.nodeId,
            content_anchor: position.anchor,
          },
          return_node_id: position.nodeId,
          draft_revision: 0,
          metadata: {},
        },
        interaction_state: { conversation_id: '', issue_id: '', remediation_session_id: '' },
        fallback_scroll_top: Math.max(0, Math.round(position.fallbackScrollTop)),
        activity_at: timestamp,
        source: position.source || 'live',
      }
    },

    scheduleSave() {
      if (saveTimer !== null) window.clearTimeout(saveTimer)
      saveTimer = window.setTimeout(() => {
        saveTimer = null
        void this.flush()
      }, SAVE_DELAY_MS)
    },

    async flush(retried = false): Promise<boolean> {
      if (!this.snapshot || !this.courseId) return false
      if (saveTimer !== null) {
        window.clearTimeout(saveTimer)
        saveTimer = null
      }
      this.status = 'syncing'
      const local = this.snapshot
      const payload = {
        expected_revision: local.revision || 0,
        course_version_id: local.course_version_id,
        node_id: local.node_id,
        node_name: local.node_name,
        content_anchor: local.content_anchor,
        session: local.session,
        task_state: local.task_state,
        interaction_state: local.interaction_state,
        fallback_scroll_top: local.fallback_scroll_top,
        activity_at: local.activity_at,
        source: local.source,
      }
      try {
        const response = await fetch(withApiBase(`/api/courses/${this.courseId}/learning-snapshot`), {
          method: 'PUT',
          headers: learnerIdentityHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
          keepalive: true,
        })
        const data = await response.json() as SnapshotApiResponse & { detail?: { current_snapshot?: LearningSnapshot } }
        if (response.status === 409) {
          const remote = data.detail?.current_snapshot
          if (!remote) throw new Error('snapshot conflict without remote state')
          if (!retried && parseTime(local.activity_at) > parseTime(remote.activity_at)) {
            this.snapshot = { ...local, revision: remote.revision, source: 'offline_recovery' }
            return this.flush(true)
          }
          this.snapshot = remote
          this.resolution = null
          this.status = 'conflict'
          this.persistLocal(false)
          return false
        }
        if (!response.ok) throw new Error(`snapshot save failed: ${response.status}`)
        this.snapshot = data.snapshot
        this.resolution = data.resolution
        this.status = 'synced'
        this.persistLocal(false)
        return true
      } catch {
        this.status = 'offline'
        this.persistLocal(true)
        return false
      }
    },

    bindConnectivity() {
      if (connectivityBound) return
      connectivityBound = true
      window.addEventListener('online', () => {
        const local = this.courseId ? this.loadLocal(this.courseId) : null
        if (local?.pending || this.status === 'offline') void this.flush()
      })
    },
  },
})
