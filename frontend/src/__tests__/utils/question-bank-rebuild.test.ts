import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get, post } }))

import { runQuestionBankRebuild } from '@/utils/question-bank-rebuild'

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
})
