import { ref } from 'vue'
import { studyApi, StudyApiError, type StudyReadingBookmark } from '../api/study'
import { createUuid } from '../utils/client-id'
import type { ReadingPosition } from '../utils/reading-position'
import { readRecoveryDelay } from '../utils/read-recovery'

type Pending = { position: ReadingPosition; expected_version: number; request_id: string }
type Scope = {
  key: string; material: string; revision: string; version: number
  desired?: ReadingPosition; pending?: Pending; saved: string; saving: boolean; blocked: boolean; failures: number
}
function validPosition(value: unknown): value is ReadingPosition {
  if (!value || typeof value !== 'object') return false
  const p = value as ReadingPosition
  return typeof p.sectionId === 'string' && p.sectionId.length > 0 && typeof p.blockId === 'string' &&
    Number.isFinite(p.offset) && typeof p.atTop === 'boolean' &&
    (p.expandedAnswers === undefined || Array.isArray(p.expandedAnswers) && p.expandedAnswers.every(id => typeof id === 'string'))
}
export function useStudyBookmark() {
  const status = ref<'saved' | 'local' | 'saving' | 'conflict' | 'unavailable'>('saved')
  let scope: Scope | undefined, timer: ReturnType<typeof setTimeout> | undefined
  function cache(s: Scope) {
    try { localStorage.setItem(s.key, JSON.stringify({ position: s.desired, pending: s.pending, version: s.version, blocked: s.blocked })) }
    catch { if (scope === s) status.value = 'unavailable' }
  }
  function schedule(delay = 700) {
    clearTimeout(timer)
    timer = setTimeout(() => { void flush() }, delay)
  }
  async function flush() {
    clearTimeout(timer)
    const s = scope
    if (!s || s.saving || s.blocked || !s.desired || (!s.pending && JSON.stringify(s.desired) === s.saved)) return
    s.pending ||= { position: JSON.parse(JSON.stringify(s.desired)), expected_version: s.version, request_id: createUuid() }
    const pending = s.pending
    cache(s); s.saving = true; status.value = 'saving'
    try {
      const result = await studyApi.saveReadingPosition(s.material, { ...pending, revision_id: s.revision })
      s.version = result.version; s.saved = JSON.stringify(result.position); s.pending = undefined; s.failures = 0
      if (scope === s) cache(s)
      if (scope === s) {
        status.value = 'saved'
        if (JSON.stringify(s.desired) !== s.saved) schedule()
      }
    } catch (error) {
      if (scope !== s) return
      const retry = readRecoveryDelay(error, s.failures++)
      s.blocked = retry === null
      status.value = error instanceof StudyApiError && error.status === 409 ? 'conflict' : 'local'
      cache(s)
      if (retry !== null) schedule(retry)
    } finally { s.saving = false }
  }
  function close() {
    void flush()
    clearTimeout(timer); scope = undefined
  }
  function open(owner: string, material: string, revision: string, remote?: StudyReadingBookmark) {
    close()
    const key = `lingzhi-study-position:${owner}:${material}:${revision}`
    const s: Scope = { key, material, revision, version: remote?.version || 0, saved: JSON.stringify(remote?.position) || '', saving: false, blocked: false, failures: 0 }
    scope = s; status.value = 'saved'
    let cached: { position?: ReadingPosition; pending?: Pending; version?: number; blocked?: boolean } = {}
    try { cached = JSON.parse(localStorage.getItem(key) || 'null') || {} } catch { /* The server bookmark remains usable. */ }
    if (!validPosition(cached.position)) cached = {}
    if (cached.pending && (!validPosition(cached.pending.position) || !Number.isInteger(cached.pending.expected_version) || typeof cached.pending.request_id !== 'string')) cached.pending = undefined
    if (cached.blocked && remote) s.desired = remote.position
    else if (cached.pending && cached.pending.request_id === remote?.request_id) {
      s.desired = cached.position || remote?.position
      if (JSON.stringify(s.desired) !== s.saved) schedule()
    } else if (cached.pending) {
      s.desired = cached.position; s.pending = cached.pending
      if (cached.pending.expected_version !== s.version) { s.blocked = true; status.value = 'conflict'; cache(s) }
      else { status.value = 'local'; schedule() }
    } else if (remote) {
      s.desired = cached.version === remote.version && cached.position ? cached.position : remote.position
      if (JSON.stringify(s.desired) !== s.saved) schedule()
    }
    else {
      // Upgrade an existing tab bookmark only when no server bookmark exists.
      let legacy: ReadingPosition | undefined
      try { legacy = JSON.parse(sessionStorage.getItem(key) || 'null') || undefined } catch { /* Ignore damaged cache. */ }
      s.desired = cached.position || (validPosition(legacy) ? legacy : undefined)
      if (s.desired) { status.value = 'local'; schedule() }
    }
    return s.desired
  }
  function capture(position: ReadingPosition) {
    const s = scope
    if (!s || !position.sectionId) return
    s.desired = position
    // Persist a request before leaving, so an unacknowledged save is safely replayed.
    if (!s.pending && JSON.stringify(position) !== s.saved) {
      s.pending = { position: structuredClone(position), expected_version: s.version, request_id: createUuid() }
    }
    if (s.pending && !s.saving && !s.blocked) { status.value = 'local'; schedule() }
    cache(s)
  }
  return { status, open, capture, flush, close }
}
