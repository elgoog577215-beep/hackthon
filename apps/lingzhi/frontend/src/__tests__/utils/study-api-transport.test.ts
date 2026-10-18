import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { studyApi, studySession, type StudyGenerationRequest } from '@/api/study'

const state = vi.hoisted(() => ({ locale: 'zh' }))
vi.mock('@/utils/http', () => ({
  getQizhiAccessToken: () => '',
  INTERACTIVE_READ_TIMEOUT_MS: 10000,
  withApiBase: (path: string) => `/lingzhi${path}`,
}))
vi.mock('@/shared/study-copy', () => ({
  studyCopy: () => state.locale === 'en' ? 'Connection timed out' : '连接超时',
}))

const request: StudyGenerationRequest = {
  request_id: 'stable-request-123456', title: '函数基础', purpose: 'systematic',
  selections: [{ asset_id: 'mat-123', section_id: 'section-1' }],
  level: 'beginner', time_minutes: 30, requirements: '', language: 'zh',
}
const response = (value: unknown = {}) => ({ ok: true, json: async () => value })
const pendingFetch = (_url: unknown, options?: RequestInit) => new Promise<Response>((_resolve, reject) => {
  const signal = options?.signal
  if (signal?.aborted) reject(signal.reason)
  else signal?.addEventListener('abort', () => reject(signal.reason), { once: true })
})
async function expectNoPendingDeadline() {
  // Flush platform microtasks without advancing an outstanding request deadline.
  await vi.advanceTimersByTimeAsync(0)
  expect(vi.getTimerCount()).toBe(0)
}

beforeEach(() => {
  vi.useFakeTimers(); state.locale = 'zh'; studySession.set('student-session')
})
afterEach(() => { studySession.clear(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('student API transport boundaries', () => {
  it.each(['zh', 'en'])('bounds a stalled read and reports %s without retrying', async locale => {
    state.locale = locale
    const fetcher = vi.fn(pendingFetch); vi.stubGlobal('fetch', fetcher)
    const failed = expect(studyApi.get('material-a')).rejects.toMatchObject({
      status: 408, message: locale === 'en' ? 'Connection timed out' : '连接超时',
    })
    await vi.advanceTimersByTimeAsync(10000); await failed
    expect(fetcher).toHaveBeenCalledTimes(1)
    await expectNoPendingDeadline()
  })

  it('keeps generation submission alive beyond the read deadline with its original request ID', async () => {
    let complete!: (value: unknown) => void
    const fetcher = vi.fn((_url: string, _options: RequestInit) => new Promise(resolve => { complete = resolve }))
    vi.stubGlobal('fetch', fetcher)
    const submitted = studyApi.generate(request)
    await vi.advanceTimersByTimeAsync(10001)
    const [url, options] = fetcher.mock.calls[0]!
    expect(url).toBe('/lingzhi/api/study/materials')
    expect(options.signal?.aborted).toBe(false)
    expect(JSON.parse(options.body as string)).toEqual(request)
    complete(response({ id: 'material-a' }))
    expect(await submitted).toMatchObject({ id: 'material-a' })
    expect(fetcher).toHaveBeenCalledTimes(1)
    await expectNoPendingDeadline()
  })

  it.each(['courses', 'list'] as const)('cancels %s observation without turning it into a timeout or retry', async method => {
    const fetcher = vi.fn(pendingFetch); vi.stubGlobal('fetch', fetcher)
    const controller = new AbortController(), reason = new DOMException('Page left', 'AbortError')
    const remove = vi.spyOn(controller.signal, 'removeEventListener')
    const failed = expect(studyApi[method](controller.signal)).rejects.toBe(reason)
    controller.abort(reason); await failed
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function))
    await expectNoPendingDeadline()
  })

  it('honors a signal that was already cancelled before the request', async () => {
    vi.stubGlobal('fetch', vi.fn(pendingFetch))
    const controller = new AbortController(), reason = new DOMException('Already left', 'AbortError')
    controller.abort(reason)
    await expect(studyApi.list(controller.signal)).rejects.toBe(reason)
    await expectNoPendingDeadline()
  })

  it('sends uploads as multipart with student authorization and without the JSON content type', async () => {
    const fetcher = vi.fn(async () => response({ id: 'source-a' })); vi.stubGlobal('fetch', fetcher)
    const file = new File(['# 教材\n正文'], 'source.md', { type: 'text/markdown' })
    await studyApi.upload(file)
    const [url, options] = vi.mocked(fetch).mock.calls[0]!
    expect(url).toBe('/lingzhi/api/study/sources/upload')
    const headers = new Headers(options?.headers)
    expect(headers.get('Authorization')).toBe('Bearer student-session')
    expect(headers.has('Content-Type')).toBe(false)
    expect(headers.has('X-User-Id')).toBe(false)
    expect(options?.body).toBeInstanceOf(FormData)
    expect((options?.body as FormData).get('file')).toBeInstanceOf(File)
    await expectNoPendingDeadline()
  })

  it('reads exported and published files as binary while retaining publication revision binding', async () => {
    const blob = new Blob(['# Saved handout'], { type: 'text/markdown' })
    const json = vi.fn(), fetcher = vi.fn(async () => ({ ok: true, blob: async () => blob, json }))
    vi.stubGlobal('fetch', fetcher)
    expect(await studyApi.export('material/with space')).toBe(blob)
    expect(await studyApi.coursePpt('course/a', 'asset/a', 'release-a')).toBe(blob)
    const calls = vi.mocked(fetch).mock.calls
    expect(calls[0]?.[0]).toBe('/lingzhi/api/study/materials/material%2Fwith%20space/export')
    expect(calls[1]?.[0]).toBe('/lingzhi/api/study/courses/course%2Fa/exchange/ppt/asset%2Fa/download')
    expect(calls[1]?.[1]?.method).toBe('POST')
    expect(JSON.parse(calls[1]?.[1]?.body as string)).toEqual({ expected_release_id: 'release-a' })
    expect(json).not.toHaveBeenCalled()
    await expectNoPendingDeadline()
  })

  it('applies the write deadline without reissuing a possibly accepted note update', async () => {
    const fetcher = vi.fn(pendingFetch); vi.stubGlobal('fetch', fetcher)
    const failed = expect(studyApi.note('material-a', 'revision-a', '我的理解')).rejects.toMatchObject({ status: 408 })
    await vi.advanceTimersByTimeAsync(120000); await failed
    expect(fetcher).toHaveBeenCalledTimes(1)
    const [url, options] = vi.mocked(fetch).mock.calls[0]!
    expect(url).toBe('/lingzhi/api/study/materials/material-a/note')
    expect(options?.method).toBe('PUT')
    expect(JSON.parse(options?.body as string)).toEqual({ revision_id: 'revision-a', content: '我的理解' })
    await expectNoPendingDeadline()
  })
})
