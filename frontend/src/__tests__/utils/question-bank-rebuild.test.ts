import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get, post } }))

import {
  resumeQuestionBankRebuild,
  runQuestionBankRebuild,
} from '@/utils/question-bank-rebuild'

describe('runQuestionBankRebuild', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('creates an async job and polls monotonic progress to completion', async () => {
    post.mockResolvedValue({
      data: {
        job_id: 'job-1',
        status: 'queued',
        progress: 0,
        status_url: '/api/jobs/job-1',
      },
    })
    get
      .mockResolvedValueOnce({
        data: {
          job_id: 'job-1',
          status: 'running',
          progress: 55,
          current_stage: 'question_generation',
          message: '正在生成题目',
          status_url: '/api/jobs/job-1',
        },
      })
      .mockResolvedValueOnce({
        data: {
          job_id: 'job-1',
          status: 'completed',
          progress: 100,
          current_stage: 'publication',
          result: { bundle_revision_id: 'qbb-2' },
          status_url: '/api/jobs/job-1',
        },
      })
    const updates: number[] = []

    const result = await runQuestionBankRebuild(
      'course-1',
      {
        request_id: 'request-1234',
        scope: 'nodes',
        node_ids: ['node-1'],
        mode: 'incremental',
      },
      {
        pollIntervalMs: 0,
        onUpdate: job => updates.push(job.progress),
      },
    )

    expect(post).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank/rebuild',
      {
        request_id: 'request-1234',
        scope: 'nodes',
        node_ids: ['node-1'],
        mode: 'incremental',
      },
    )
    expect(get).toHaveBeenCalledTimes(2)
    expect(updates).toEqual([0, 55, 100])
    expect(result.status).toBe('completed')
  })

  it('surfaces a durable failed job instead of reporting success', async () => {
    post.mockResolvedValue({
      data: {
        job_id: 'job-failed',
        status: 'queued',
        progress: 0,
        status_url: '/api/jobs/job-failed',
      },
    })
    get.mockResolvedValue({
      data: {
        job_id: 'job-failed',
        status: 'failed',
        progress: 30,
        error: {
          code: 'model_unavailable',
          message: '模型暂不可用',
        },
        status_url: '/api/jobs/job-failed',
      },
    })

    await expect(runQuestionBankRebuild(
      'course-1',
      {
        request_id: 'request-failed',
        scope: 'course',
        node_ids: [],
        mode: 'incremental',
      },
      { pollIntervalMs: 0 },
    )).rejects.toMatchObject({
      code: 'model_unavailable',
      message: '模型暂不可用',
    })
  })

  it('backs off and continues polling when the status endpoint returns 429', async () => {
    post.mockResolvedValue({
      data: {
        job_id: 'job-rate-limited',
        status: 'running',
        progress: 50,
        status_url: '/api/jobs/job-rate-limited',
      },
    })
    get
      .mockRejectedValueOnce({
        response: {
          status: 429,
          headers: { 'retry-after': '0' },
        },
      })
      .mockResolvedValueOnce({
        data: {
          job_id: 'job-rate-limited',
          status: 'completed',
          progress: 100,
          status_url: '/api/jobs/job-rate-limited',
        },
      })
    const messages: string[] = []

    const result = await runQuestionBankRebuild(
      'course-1',
      {
        request_id: 'request-rate-limited',
        scope: 'nodes',
        node_ids: ['node-1'],
        mode: 'incremental',
      },
      {
        pollIntervalMs: 0,
        rateLimitBackoffMs: 0,
        onUpdate: job => messages.push(job.message || ''),
      },
    )

    expect(get).toHaveBeenCalledTimes(2)
    expect(messages).toContain('请求较多，系统正在自动重试…')
    expect(result.status).toBe('completed')
  })

  it('recovers the active course job without creating another job', async () => {
    get
      .mockResolvedValueOnce({
        data: {
          job_id: 'job-active',
          status: 'running',
          progress: 52,
          current_stage: 'question_generation',
          status_url: '/api/jobs/job-active',
        },
      })
      .mockResolvedValueOnce({
        data: {
          job_id: 'job-active',
          status: 'completed',
          progress: 100,
          current_stage: 'publication',
          status_url: '/api/jobs/job-active',
        },
      })
    const updates: number[] = []

    const result = await resumeQuestionBankRebuild(
      'course-1',
      {
        pollIntervalMs: 0,
        onUpdate: job => updates.push(job.progress),
      },
    )

    expect(post).not.toHaveBeenCalled()
    expect(get).toHaveBeenNthCalledWith(
      1,
      '/api/courses/course-1/question-bank/rebuilds/active',
      { silentError: true },
    )
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/api/jobs/job-active',
      { silentError: true },
    )
    expect(updates).toEqual([52, 100])
    expect(result?.status).toBe('completed')
  })

  it('returns null when the course has no active rebuild', async () => {
    get.mockRejectedValue({
      response: { status: 404 },
    })

    await expect(
      resumeQuestionBankRebuild('course-1'),
    ).resolves.toBeNull()
    expect(post).not.toHaveBeenCalled()
  })
})
