export const PPT_SAME_SOURCE_STORAGE_KEY = 'qizhi:ppt-same-source-highlight:v1'
export const PPT_SAME_SOURCE_TTL_MS = 10 * 60 * 1000

export interface PptSameSourceHighlightState {
  courseId: string
  sectionId: string
  blockIds: string[]
  primaryBlockId: string
  beforeText: string
  afterText: string
  createdAt: number
  animationPlayed?: boolean
}

type SessionStorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function normalizedState(value: unknown): PptSameSourceHighlightState | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Record<string, unknown>
  const blockIds = Array.isArray(raw.blockIds) ? [...new Set(raw.blockIds.map(String).filter(Boolean))] : []
  const state: PptSameSourceHighlightState = {
    courseId: String(raw.courseId || ''),
    sectionId: String(raw.sectionId || ''),
    blockIds,
    primaryBlockId: String(raw.primaryBlockId || blockIds[0] || ''),
    beforeText: String(raw.beforeText || ''),
    afterText: String(raw.afterText || ''),
    createdAt: Number(raw.createdAt || 0),
    animationPlayed: raw.animationPlayed === true,
  }
  if (!state.courseId || !state.sectionId || !state.blockIds.length || !state.primaryBlockId || !state.createdAt) return null
  return state
}

export function writePptSameSourceHighlight(storage: SessionStorageLike, state: PptSameSourceHighlightState) {
  const normalized = normalizedState(state)
  if (!normalized) throw new Error('Invalid PPT same-source highlight state')
  storage.setItem(PPT_SAME_SOURCE_STORAGE_KEY, JSON.stringify(normalized))
  return normalized
}

export function peekPptSameSourceHighlight(storage: SessionStorageLike, courseId: string, now = Date.now()) {
  const raw = storage.getItem(PPT_SAME_SOURCE_STORAGE_KEY)
  if (!raw) return null
  let state: PptSameSourceHighlightState | null = null
  try {
    state = normalizedState(JSON.parse(raw))
  } catch {
    storage.removeItem(PPT_SAME_SOURCE_STORAGE_KEY)
    return null
  }
  if (!state) {
    storage.removeItem(PPT_SAME_SOURCE_STORAGE_KEY)
    return null
  }
  if (now - state.createdAt > PPT_SAME_SOURCE_TTL_MS || state.createdAt > now + 60_000) {
    storage.removeItem(PPT_SAME_SOURCE_STORAGE_KEY)
    return null
  }
  if (state.courseId !== courseId) return null
  return state
}

export function readPptSameSourceHighlight(storage: SessionStorageLike, courseId: string, sectionId: string, now = Date.now()) {
  const state = peekPptSameSourceHighlight(storage, courseId, now)
  if (!state || state.sectionId !== sectionId) return null
  return state
}

export function markPptSameSourceAnimationPlayed(storage: SessionStorageLike, expectedCreatedAt: number) {
  const raw = storage.getItem(PPT_SAME_SOURCE_STORAGE_KEY)
  if (!raw) return
  try {
    const state = normalizedState(JSON.parse(raw))
    if (!state || state.createdAt !== expectedCreatedAt || state.animationPlayed) return
    storage.setItem(PPT_SAME_SOURCE_STORAGE_KEY, JSON.stringify({ ...state, animationPlayed: true }))
  } catch {
    storage.removeItem(PPT_SAME_SOURCE_STORAGE_KEY)
  }
}
