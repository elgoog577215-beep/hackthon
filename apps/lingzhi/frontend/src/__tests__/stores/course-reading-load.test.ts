import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCourseStore } from '@/stores/course'
import http from '@/utils/http'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  identityReadRequestConfig: (_scope: unknown, config = {}) => config,
  getIdentityForScope: () => 'teacher',
  getQizhiAccessToken: () => '',
}))
vi.mock('@/utils/logger', () => ({ default: { error: vi.fn() } }))

const emptyPreview = (id: string) => ({ data: {
  course_id: id, preview_revision: `trial-${id}`,
  document: { course_id: id, title: id, document_revision: `rev-${id}`, sections: [], blocks: [] },
  questions: [], availability: { reading: false, practice: false },
} })
const deferred = () => {
  let resolve!: (value: any) => void
  let reject!: (value: any) => void
  const promise = new Promise<any>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('reading request completion', () => {
  it('finishes an empty teacher preview without requesting learner records or generation', async () => {
    vi.mocked(http.get).mockResolvedValue(emptyPreview('empty'))
    const store = useCourseStore()
    await store.loadCourse('empty', { teacherTrial: true, silentError: true })
    expect(store.loading).toBe(false)
    expect(store.currentCourseId).toBe('empty')
    expect(store.nodes).toEqual([])
    expect(store.courseLoadError).toBeNull()
    expect(http.get).toHaveBeenCalledExactlyOnceWith('/api/teacher/courses/empty/preview', expect.objectContaining({ silentError: true }))
    expect(http.post).not.toHaveBeenCalled()
  })

  it('ends loading after failure and clears the error on a successful read retry', async () => {
    vi.mocked(http.get).mockRejectedValueOnce(new Error('Read unavailable'))
    const store = useCourseStore()
    await store.loadCourse('empty', { teacherTrial: true, silentError: true })
    expect(store.loading).toBe(false)
    expect(store.currentCourseId).toBe('')
    expect(store.courseLoadError).toEqual(expect.any(String))
    const retry = deferred()
    vi.mocked(http.get).mockReturnValueOnce(retry.promise)
    const pending = store.loadCourse('empty', { teacherTrial: true, silentError: true })
    expect(store.loading).toBe(true)
    expect(store.courseLoadError).toBeNull()
    retry.resolve(emptyPreview('empty'))
    await pending
    expect(store.loading).toBe(false)
    expect(store.currentCourseId).toBe('empty')
    expect(store.courseLoadError).toBeNull()
  })

  it.each(['resolve', 'reject'] as const)('ignores a late %s from the previous course while the next course loads', async outcome => {
    const first = deferred(), second = deferred()
    vi.mocked(http.get).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const store = useCourseStore()
    const oldLoad = store.loadCourse('old', { teacherTrial: true, silentError: true })
    const newLoad = store.loadCourse('new', { teacherTrial: true, silentError: true })
    if (outcome === 'resolve') first.resolve(emptyPreview('old'))
    else first.reject(new Error('Old read failed'))
    await oldLoad
    expect(store.currentCourseId).toBe('new')
    expect(store.loading).toBe(true)
    expect(store.courseLoadError).toBeNull()
    second.resolve(emptyPreview('new'))
    await newLoad
    expect(store.loading).toBe(false)
    expect(store.teacherPreviewSnapshot.course_id).toBe('new')
  })

  it('keeps the reading spinner while an independent course list finishes', async () => {
    const preview = deferred()
    vi.mocked(http.get).mockReturnValueOnce(preview.promise).mockResolvedValueOnce({ data: [] })
    const store = useCourseStore()
    const loading = store.loadCourse('empty', { teacherTrial: true })
    await store.fetchCourseList({ surface: 'teacher', background: true })
    expect(store.loading).toBe(true)
    preview.resolve(emptyPreview('empty'))
    await loading
    expect(store.loading).toBe(false)
  })
})
