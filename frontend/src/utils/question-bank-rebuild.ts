import http from './http'

export type QuestionBankRebuildStatus =
  | 'queued'
  | 'running'
  | 'waiting_review'
  | 'completed'
  | 'failed'

export interface QuestionBankRebuildRequest {
  request_id: string
  scope: 'course' | 'nodes' | 'items'
  node_ids: string[]
  revision_ids?: string[]
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
  rateLimitBackoffMs?: number
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
  const pollIntervalMs = Math.max(0, options.pollIntervalMs ?? 2500)
  const rateLimitBackoffMs = Math.max(
    0,
    options.rateLimitBackoffMs ?? 5000,
  )
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
    let response
    try {
      response = await http.get(job.status_url, { silentError: true })
    } catch (error: any) {
      if (Number(error?.response?.status || 0) !== 429) throw error
      pollCount += 1
      job = {
        ...job,
        message: '请求较多，系统正在自动重试…',
      }
      options.onUpdate?.(job)
      await wait(
        retryAfterMilliseconds(error, rateLimitBackoffMs),
        options.signal,
      )
      continue
    }
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

async function wait(
  milliseconds: number,
  signal?: AbortSignal,
) {
  if (signal?.aborted) {
    throw new DOMException('Question bank rebuild aborted', 'AbortError')
  }
  if (milliseconds <= 0) return
  await new Promise<void>((resolve, reject) => {
    const handleAbort = () => {
      clearTimeout(timeoutId)
      reject(new DOMException(
        'Question bank rebuild aborted',
        'AbortError',
      ))
    }
    const timeoutId = setTimeout(() => {
      signal?.removeEventListener('abort', handleAbort)
      resolve()
    }, milliseconds)
    signal?.addEventListener('abort', handleAbort, { once: true })
  })
}

function retryAfterMilliseconds(
  error: any,
  fallback: number,
) {
  const headers = error?.response?.headers
  const retryAfter = typeof headers?.get === 'function'
    ? headers.get('retry-after')
    : headers?.['retry-after']
  const seconds = Number(retryAfter)
  return Number.isFinite(seconds) && seconds >= 0
    ? seconds * 1000
    : fallback
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
