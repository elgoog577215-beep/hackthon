import http from './http'

export type QuestionBankRebuildStatus =
  | 'queued'
  | 'running'
  | 'waiting_review'
  | 'completed'
  | 'failed'

export interface QuestionBankRebuildRequest {
  request_id: string
  scope: 'course' | 'nodes'
  node_ids: string[]
  mode: 'incremental' | 'full'
}

export interface QuestionBankRebuildJob {
  job_id: string
  status: QuestionBankRebuildStatus
  progress: number
  current_stage?: string
  message?: string
  status_url: string
  error?: {
    code?: string
    message?: string
    retryable?: boolean
  } | null
  result?: Record<string, unknown> | null
  stages?: Array<Record<string, unknown>>
}

interface RebuildOptions {
  pollIntervalMs?: number
  maxPolls?: number
  onUpdate?: (job: QuestionBankRebuildJob) => void
  signal?: AbortSignal
}

export class QuestionBankRebuildError extends Error {
  code: string
  retryable: boolean
  job: QuestionBankRebuildJob

  constructor(job: QuestionBankRebuildJob) {
    super(job.error?.message || '题目生成失败')
    this.name = 'QuestionBankRebuildError'
    this.code = job.error?.code || 'question_bank_rebuild_failed'
    this.retryable = Boolean(job.error?.retryable)
    this.job = job
  }
}

const TERMINAL = new Set<QuestionBankRebuildStatus>([
  'waiting_review',
  'completed',
  'failed',
])

export async function runQuestionBankRebuild(
  courseId: string,
  request: QuestionBankRebuildRequest,
  options: RebuildOptions = {},
): Promise<QuestionBankRebuildJob> {
  const created = await http.post(
    `/api/courses/${courseId}/question-bank/rebuild`,
    request,
  )
  let job = normalizeJob(created.data)
  options.onUpdate?.(job)
  const pollIntervalMs = Math.max(0, options.pollIntervalMs ?? 800)
  const maxPolls = Math.max(1, options.maxPolls ?? 450)
  let pollCount = 0

  while (!TERMINAL.has(job.status)) {
    if (options.signal?.aborted) {
      throw new DOMException('Question bank rebuild aborted', 'AbortError')
    }
    if (pollCount >= maxPolls) {
      const timeoutJob: QuestionBankRebuildJob = {
        ...job,
        status: 'failed',
        error: {
          code: 'question_bank_rebuild_timeout',
          message: '题目生成仍在后台进行，请稍后返回查看进度。',
          retryable: true,
        },
      }
      throw new QuestionBankRebuildError(timeoutJob)
    }
    if (pollIntervalMs > 0) {
      await new Promise(resolve => setTimeout(resolve, pollIntervalMs))
    }
    const response = await http.get(job.status_url)
    const next = normalizeJob({
      ...job,
      ...(response.data || {}),
    })
    job = {
      ...next,
      progress: Math.max(job.progress, next.progress),
    }
    pollCount += 1
    options.onUpdate?.(job)
  }

  if (job.status === 'failed') {
    throw new QuestionBankRebuildError(job)
  }
  return job
}

function normalizeJob(value: Record<string, unknown>): QuestionBankRebuildJob {
  const status = String(value.status || 'queued') as QuestionBankRebuildStatus
  const statusUrl = String(value.status_url || '')
  if (!String(value.job_id || '') || !statusUrl) {
    throw new Error('题库重建任务响应不完整')
  }
  return {
    ...(value as unknown as QuestionBankRebuildJob),
    job_id: String(value.job_id),
    status,
    progress: Math.max(0, Math.min(100, Number(value.progress || 0))),
    status_url: statusUrl,
  }
}
