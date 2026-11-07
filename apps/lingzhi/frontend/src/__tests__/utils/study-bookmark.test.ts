import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
const api = vi.hoisted(() => ({ saveReadingPosition: vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi: api, StudyApiError: class extends Error { constructor(public status: number, message: string) { super(message) } } }))
import { StudyApiError } from '@/api/study'
import { useStudyBookmark } from '@/composables/useStudyBookmark'
const position = { sectionId: 's1', blockId: 'b1', offset: 100, atTop: false, expandedAnswers: [] }
const key = 'lingzhi-study-position:student-a:material-a:revision-a'
let bookmarks: ReturnType<typeof useStudyBookmark>[] = []
function make() { const bookmark = useStudyBookmark(); bookmarks.push(bookmark); return bookmark }
beforeEach(() => {
  vi.useFakeTimers(); localStorage.clear(); sessionStorage.clear(); vi.clearAllMocks()
  api.saveReadingPosition.mockImplementation(async (_id, body) => ({ position: body.position, request_id: body.request_id, version: body.expected_version + 1, updated_at: '' }))
})
afterEach(async () => { bookmarks.forEach(b => b.close()); bookmarks = []; await flushPromises(); vi.useRealTimers() })
it('restores a server bookmark in a fresh browser, scoped to owner material and revision', async () => {
  const bookmark = make()
  expect(bookmark.open('student-a', 'material-a', 'revision-a', { position, version: 2, request_id: 'previous', updated_at: '' })).toEqual(position)
  bookmark.capture(position); await bookmark.flush()
  expect(api.saveReadingPosition).not.toHaveBeenCalled()
  expect(bookmark.open('student-b', 'material-a', 'revision-a')).toBeUndefined()
  expect(bookmark.open('student-a', 'material-a', 'revision-b')).toBeUndefined()
})
it('retains an offline bookmark across sessions and retries the same request', async () => {
  api.saveReadingPosition.mockRejectedValueOnce(new TypeError('offline'))
  const first = make(); first.open('student-a','material-a','revision-a'); first.capture(position)
  await first.flush()
  expect(first.status.value).toBe('local')
  const request = api.saveReadingPosition.mock.calls[0]![1]
  // Simulate a browser shutdown, including its unacknowledged keepalive request.
  api.saveReadingPosition.mockRejectedValueOnce(new TypeError('offline')); first.close(); await flushPromises()
  sessionStorage.clear()
  const second = make(); expect(second.open('student-a','material-a','revision-a')).toEqual(position)
  await second.flush()
  expect(api.saveReadingPosition.mock.calls.at(-1)![1]).toEqual(request)
  expect(second.status.value).toBe('saved')
})
it('serializes scrolling during a save and does not lose the later desired position', async () => {
  let finish!: (result: unknown) => void
  api.saveReadingPosition.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const bookmark = make(); bookmark.open('student-a','material-a','revision-a'); bookmark.capture(position)
  const sending = bookmark.flush()
  bookmark.capture({ ...position, offset: 250 }); await bookmark.flush()
  expect(api.saveReadingPosition).toHaveBeenCalledTimes(1)
  finish({ position, version: 1, request_id: api.saveReadingPosition.mock.calls[0]![1].request_id })
  await sending
  await vi.advanceTimersByTimeAsync(700)
  expect(api.saveReadingPosition).toHaveBeenCalledTimes(2)
  expect(api.saveReadingPosition.mock.calls[1]![1]).toMatchObject({ expected_version: 1, position: { offset: 250 } })
})
it('never overwrites another window after a version conflict and restores it on reopen', async () => {
  api.saveReadingPosition.mockRejectedValueOnce(new StudyApiError(409, 'conflict'))
  const bookmark = make(); bookmark.open('student-a','material-a','revision-a'); bookmark.capture(position)
  await bookmark.flush(); await vi.advanceTimersByTimeAsync(60000)
  expect(bookmark.status.value).toBe('conflict')
  expect(api.saveReadingPosition).toHaveBeenCalledTimes(1)
  const newer = { ...position, offset: 400 }
  expect(bookmark.open('student-a','material-a','revision-a', { position: newer, version: 3, request_id: 'other', updated_at: '' })).toEqual(newer)
})
it('recovers a lost acknowledgement without losing subsequent local scrolling', () => {
  localStorage.setItem(key, JSON.stringify({ position: { ...position, offset: 300 }, version: 0,
    pending: { position, expected_version: 0, request_id: 'sent-before-close' } }))
  const bookmark = make()
  expect(bookmark.open('student-a','material-a','revision-a', { position, version: 1, request_id: 'sent-before-close', updated_at: '' })).toMatchObject({ offset: 300 })
})
it('migrates the original session bookmark when there is no server record', async () => {
  sessionStorage.setItem(key, JSON.stringify(position))
  const bookmark = make(); expect(bookmark.open('student-a','material-a','revision-a')).toEqual(position)
  await bookmark.flush()
  expect(api.saveReadingPosition).toHaveBeenCalledExactlyOnceWith('material-a', expect.objectContaining({ expected_version: 0, position }))
})

it('ignores a previous material save response after switching scope', async () => {
  let finish!: (result: unknown) => void
  api.saveReadingPosition.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const bookmark = make(); bookmark.open('student-a','material-a','revision-a'); bookmark.capture(position)
  const saving = bookmark.flush()
  const oldRequest = api.saveReadingPosition.mock.calls[0]![1]
  bookmark.open('student-b','material-b','revision-b')
  bookmark.capture({ ...position, offset: 500 })
  finish({ position, version: 1, request_id: oldRequest.request_id }); await saving
  expect(bookmark.status.value).toBe('local')
  await bookmark.flush()
  expect(api.saveReadingPosition.mock.calls.at(-1)![0]).toBe('material-b')
  expect(api.saveReadingPosition.mock.calls.at(-1)![1]).toMatchObject({ revision_id:'revision-b', expected_version:0, position:{offset:500} })
})

it('ignores malformed local bookmarks instead of masking the server position', () => {
  localStorage.setItem(key, JSON.stringify({ position: { sectionId: 's1', offset: 'invalid' }, pending: {} }))
  const bookmark = make()
  expect(bookmark.open('student-a','material-a','revision-a', {position,version:2,request_id:'valid',updated_at:''})).toEqual(position)
})
