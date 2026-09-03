import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  getTeacherIdentity: () => 'teacher-test',
  teacherReadRequestConfig: (config = {}) => config,
}))

import { lessonJobsToObserve, mergeLessonJobStreamEvent, useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('teacher lesson authoring store', () => {
  it('observes up to four active jobs so parallel lessons stream independently', () => {
    const queued = [3, 1, 2].map(position => ({
      id: `job-${position}`,
      status: 'pending',
      batch_position: position,
      created_at: `2026-09-01T00:00:0${position}Z`,
    })) as any

    expect(lessonJobsToObserve(queued).map(job => job.id)).toEqual(['job-1', 'job-2', 'job-3'])
    expect(lessonJobsToObserve([
      ...queued,
      { id: 'job-running', status: 'running', batch_position: 2 },
    ] as any).map(job => job.id)).toEqual(['job-running', 'job-1', 'job-2', 'job-3'])
  })

  it('observes every active script job so each lecture can stream independently', () => {
    const jobs = [1, 2, 3].map(position => ({
      id: `script-job-${position}`,
      type: 'teacher_lesson_script_generation',
      status: position === 3 ? 'completed' : position === 1 ? 'running' : 'pending',
      batch_position: position,
    })) as any

    expect(lessonJobsToObserve(jobs).map(job => job.id)).toEqual(['script-job-1', 'script-job-2'])
  })

  it('merges script deltas by sequence and ignores duplicate events', () => {
    const job = {
      id: 'script-job-1', course_id: 'course-1', lesson_unit_id: 'lesson-1',
      type: 'teacher_lesson_script_generation', status: 'running', progress: 10,
      phase: 'lesson_script_generation', message: '正在生成', warnings: [],
    } as any
    const second = mergeLessonJobStreamEvent(undefined, {
      event: 'lesson_script_stream',
      job: {
        ...job,
        progress: 20,
        stream_events: [
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-1', sequence: 2, delta: '第二段' },
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-1', sequence: 1, delta: '第一段' },
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-1', sequence: 2, delta: '重复内容' },
        ],
      },
    })!

    expect(second.progress).toBe(20)
    expect(second.streamed_block_content).toEqual({ 'block-1': '第一段第二段' })
    expect(second.streamed_delta_chunks).toEqual({ 'block-1': { '1:shard-1': '第一段', '2:shard-1': '第二段' } })
    expect(second.streamed_sequence_by_shard).toEqual({ 'block-1:shard-1': 2 })
  })

  it('consumes reset and all deltas in one snapshot without duplicating overlap', () => {
    const baseJob = {
      id: 'script-job-window', course_id: 'course-1', lesson_unit_id: 'lesson-1',
      type: 'teacher_lesson_script_generation', status: 'running', progress: 30,
      phase: 'lesson_script_generation', message: '正在生成', warnings: [],
    } as any
    const first = mergeLessonJobStreamEvent(undefined, {
      event: 'lesson_script_stream',
      job: {
        ...baseJob,
        stream_sequence: 13,
        stream_batches: { 'shard-a': '快速生成' },
        stream_events: [
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 12, delta: '速' },
          { event: 'reset', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 10, delta: '' },
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 11, delta: '快' },
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 13, delta: '生成' },
        ],
        last_stream_event: { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 13, delta: '生成' },
      },
      lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 13, delta: '生成', stream_event: 'delta',
    })!
    const overlapped = mergeLessonJobStreamEvent(first, {
      event: 'lesson_script_stream',
      job: {
        ...baseJob,
        progress: 40,
        stream_sequence: 14,
        stream_batches: { 'shard-a': '快速生成完成' },
        stream_events: [
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 12, delta: '速' },
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 13, delta: '生成' },
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 14, delta: '完成' },
        ],
        last_stream_event: { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 14, delta: '完成' },
      },
      lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 14, delta: '完成', stream_event: 'delta',
    })!

    expect(first.streamed_block_content).toEqual({ 'block-1': '快速生成' })
    expect(overlapped.streamed_block_content).toEqual({ 'block-1': '快速生成完成' })
    expect(overlapped.streamed_delta_chunks).toEqual({ 'block-1': { '14:shard-a': '快速生成完成' } })
    expect(overlapped.streamed_sequence_by_shard).toEqual({ 'block-1:shard-a': 14 })
  })

  it('recovers truncated stream history from cumulative shard batches with exact event mapping', () => {
    const recovered = mergeLessonJobStreamEvent(undefined, {
      event: 'lesson_script_stream',
      job: {
        id: 'script-job-truncated', course_id: 'course-1', lesson_unit_id: 'lesson-1',
        type: 'teacher_lesson_script_generation', status: 'running', progress: 60,
        phase: 'lesson_script_generation', message: '正在生成', warnings: [], stream_sequence: 502,
        stream_batches: { 'lesson-1:block-1': '窗口之前的正文与结尾' },
        stream_events: [
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'lesson-1:block-1', sequence: 501, delta: '结' },
          { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'lesson-1:block-1', sequence: 502, delta: '尾' },
        ],
        last_stream_event: { event: 'delta', lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'lesson-1:block-1', sequence: 502, delta: '尾' },
      },
    })!

    expect(recovered.streamed_block_content).toEqual({ 'block-1': '窗口之前的正文与结尾' })
    expect(recovered.streamed_sequence_by_shard).toEqual({ 'block-1:lesson-1:block-1': 502 })
  })

  it('resets one script shard even without delta and rejects its older events', () => {
    const job = {
      id: 'script-job-1', course_id: 'course-1', lesson_unit_id: 'lesson-1',
      type: 'teacher_lesson_script_generation', status: 'running', progress: 30,
      phase: 'lesson_script_generation', message: '正在生成', warnings: [],
      streamed_block_content: { 'block-1': '旧内容保留内容' },
      streamed_delta_chunks: {
        'block-1': {
          '1:shard-a': '旧内容',
          '2:shard-b': '保留内容',
        },
      },
      streamed_sequence_by_shard: { 'block-1:shard-a': 1, 'block-1:shard-b': 2 },
    } as any
    const reset = mergeLessonJobStreamEvent(job, {
      event: 'lesson_script_stream', stream_event: 'reset', job_id: job.id,
      lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 3, delta: '',
    })!
    const stale = mergeLessonJobStreamEvent(reset, {
      event: 'lesson_script_stream', job_id: job.id,
      lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 1, delta: '迟到旧内容',
    })!
    const resumed = mergeLessonJobStreamEvent(stale, {
      event: 'lesson_script_stream', job_id: job.id,
      lesson_unit_id: 'lesson-1', block_id: 'block-1', shard_id: 'shard-a', sequence: 4, delta: '新内容',
    })!

    expect(reset.streamed_delta_chunks).toEqual({ 'block-1': { '2:shard-b': '保留内容' } })
    expect(reset.streamed_block_content).toEqual({ 'block-1': '保留内容' })
    expect(reset.streamed_reset_sequence_by_shard).toEqual({ 'block-1:shard-a': 3 })
    expect(stale.streamed_block_content).toEqual({ 'block-1': '保留内容' })
    expect(resumed.streamed_block_content).toEqual({ 'block-1': '保留内容新内容' })
  })

  it('loads an empty lesson view without publishing a duplicate global error', async () => {
    httpMock.get.mockResolvedValue({
      data: {
        schema_version: 'teacher_lesson_authoring_view_v1',
        course_id: 'course-1',
        outline_revision_id: '',
        lessons: [],
        jobs: [],
      },
    })
    const store = useTeacherLessonAuthoringStore()

    await store.load('course-1')

    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/teacher/courses/course-1/lesson-authoring',
      {
        headers: { 'X-User-Id': 'teacher-test' },
        silentError: true,
      },
    )
    expect(store.lessons).toEqual([])
    expect(store.error).toBe('')
  })

  it('coalesces concurrent reads for the same course into one request', async () => {
    let resolveRequest!: (value: any) => void
    httpMock.get.mockReturnValue(new Promise(resolve => { resolveRequest = resolve }))
    const store = useTeacherLessonAuthoringStore()

    const first = store.load('course-1')
    const second = store.load('course-1')

    expect(httpMock.get).toHaveBeenCalledTimes(1)
    resolveRequest({
      data: {
        schema_version: 'teacher_lesson_authoring_view_v1',
        course_id: 'course-1',
        outline_revision_id: 'outline-1',
        lessons: [],
        jobs: [],
      },
    })
    await Promise.all([first, second])

    expect(store.loading).toBe(false)
    expect(store.loadedCourseId).toBe('course-1')
  })

  it('keeps the last successful lesson view visible when a background refresh times out', async () => {
    httpMock.get.mockResolvedValueOnce({
      data: {
        schema_version: 'teacher_lesson_authoring_view_v1',
        course_id: 'course-1',
        outline_revision_id: 'outline-1',
        lessons: [{ lesson_unit_id: 'lesson-1', title: '第一讲' }],
        jobs: [],
      },
    })
    const store = useTeacherLessonAuthoringStore()
    await store.load('course-1')
    httpMock.get.mockRejectedValueOnce(Object.assign(new Error('timeout of 10000ms exceeded'), { code: 'ECONNABORTED' }))

    const refresh = store.load('course-1')
    expect(store.loading).toBe(false)
    expect(store.refreshing).toBe(true)
    await expect(refresh).rejects.toThrow('timeout of 10000ms exceeded')

    expect(store.lessons).toEqual([{ lesson_unit_id: 'lesson-1', title: '第一讲' }])
    expect(store.error).toBe('')
    expect(store.refreshError).toBe('读取时间过长，请重新尝试。已生成的内容仍然保留。')
    expect(store.refreshing).toBe(false)
  })

  it('starts lesson-plan generation when HTTP does not expose crypto.randomUUID', async () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (target: Uint8Array) => {
        target.fill(7)
        return target
      },
    })
    httpMock.post.mockResolvedValue({
      data: {
        job: {
          id: 'lesson-job-http',
          course_id: 'course-1',
          lesson_unit_id: 'lesson-1',
          type: 'teacher_lesson_plan_generation',
          status: 'pending',
          progress: 0,
        },
      },
    })
    const store = useTeacherLessonAuthoringStore()
    vi.spyOn(store, 'streamJob').mockResolvedValue(undefined)

    await store.generateLesson('course-1', 'lesson-1')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/teacher/courses/course-1/lessons/lesson-1/plan/generate',
      expect.objectContaining({
        request_id: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/),
      }),
      { headers: { 'X-User-Id': 'teacher-test' } },
    )
    expect(store.error).toBe('')
  })

  it('starts all script jobs in one request and subscribes every child stream', async () => {
    httpMock.post.mockResolvedValue({
      data: {
        parent_job: { id: 'script-batch-1', child_job_ids: ['script-job-1', 'script-job-2'], skipped_lesson_ids: [], total: 2, started: 2 },
        jobs: [1, 2].map(position => ({
          id: `script-job-${position}`, course_id: 'course-1', lesson_unit_id: `lesson-${position}`,
          type: 'teacher_lesson_script_generation', status: 'pending', progress: 0,
          phase: 'queued', message: '等待生成', warnings: [], parent_job_id: 'script-batch-1',
          batch_position: position, batch_size: 2,
        })),
      },
    })
    const store = useTeacherLessonAuthoringStore()
    const stream = vi.spyOn(store, 'streamJob').mockResolvedValue(undefined)

    await store.generateAllScripts('course-1', '')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/teacher/courses/course-1/lesson-scripts/generate-all',
      {
        request_id: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/),
        requirements: '',
      },
      { headers: { 'X-User-Id': 'teacher-test' } },
    )
    expect(stream.mock.calls.map(call => call.slice(0, 2))).toEqual([
      ['course-1', 'script-job-1'],
      ['course-1', 'script-job-2'],
    ])
  })
})
