import type { AxiosError } from 'axios'
import { t } from '../shared/i18n'

export interface AppErrorPresentation {
  title: string
  summary: string
  technicalDetail: string
  code: string
  requestId: string
  status: number | null
  retryable: boolean
}

export interface AppErrorOptions {
  title?: string
  summary?: string
  fallback?: string
  code?: string
  requestId?: string
  retryable?: boolean
}

export interface AppErrorEvent {
  id: string
  signature: string
  presentation: AppErrorPresentation
}

type ErrorRecord = Record<string, unknown>
type ErrorListener = (event: AppErrorEvent) => void

const listeners = new Set<ErrorListener>()
const MAX_TECHNICAL_DETAIL_LENGTH = 6000
let lastPublishedAt = 0

const asRecord = (value: unknown): ErrorRecord => (
  value && typeof value === 'object' ? value as ErrorRecord : {}
)

const text = (value: unknown): string => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function responseHeader(headers: unknown, name: string): string {
  const value = asRecord(headers)
  const getter = value.get
  if (typeof getter === 'function') {
    const result = getter.call(headers, name)
    if (result) return text(result)
  }
  return text(value[name] || value[name.toLowerCase()] || value[name.toUpperCase()])
}

function detailFields(data: unknown): { code: string; message: string; requestId: string; raw: string } {
  const body = asRecord(data)
  const detail = body.detail
  const detailRecord = asRecord(detail)
  const code = text(
    detailRecord.code
    || detailRecord.error_code
    || body.code
    || body.error_code,
  )
  const message = typeof detail === 'string'
    ? detail.trim()
    : text(detailRecord.message || detailRecord.user_message || body.message || body.error)
  const requestId = text(
    detailRecord.request_id
    || body.request_id
    || body.requestId,
  )
  return { code, message, requestId, raw: text(detail || data) }
}

function looksLikeTechnicalText(value: string): boolean {
  return value.length > 240
    || value.includes('\n')
    || /Traceback|\b[A-Z][A-Za-z]+(?:Error|Exception)\b|\bFile "|\/Users\/|node_modules| at [\w$]+ \(/.test(value)
}

function sanitizeTechnicalText(value: string): string {
  return value
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, '$1[hidden]')
    .replace(/((?:api[_-]?key|access[_-]?token|password|secret)["'\s:=]+)[^\s,"'}]+/gi, '$1[hidden]')
    .replace(/\/Users\/[^\s"']+/g, '[server path hidden]')
    .replace(/[A-Za-z]:\\Users\\[^\s"']+/g, '[server path hidden]')
}

function domainName(url: string): string {
  const domains: Array<[RegExp, string]> = [
    [/\/lesson-authoring|\/lessons\/[^/]+\/plan/, t('appError.domains.lessonPlan', '教案')],
    [/\/lessons\/[^/]+\/script/, t('appError.domains.script', '讲稿')],
    [/question[_-]bank|question-bank/, t('appError.domains.questionBank', '题库')],
    [/slide|ppt/i, t('appError.domains.ppt', 'PPT')],
    [/calendar|session/i, t('appError.domains.calendar', '教学日历')],
    [/material|reference|course-space/i, t('appError.domains.material', '课程资料')],
    [/assistant|ai-teacher/i, t('appError.domains.assistant', 'AI 助手')],
    [/task|job/i, t('appError.domains.task', '任务状态')],
    [/practice|attempt/i, t('appError.domains.practice', '练习')],
    [/course/i, t('appError.domains.course', '课程')],
  ]
  return domains.find(([pattern]) => pattern.test(url))?.[1]
    || t('appError.domains.request', '操作')
}

function operationName(method: string, url: string): string {
  if (/generate|build|create/i.test(url)) return t('appError.operations.generate', '生成')
  if (/confirm|publish|release|resolve/i.test(url)) return t('appError.operations.confirm', '确认')
  if (/upload|import/i.test(url)) return t('appError.operations.upload', '上传')
  if (/export|download/i.test(url)) return t('appError.operations.export', '导出')
  if (method === 'GET') return t('appError.operations.load', '读取')
  if (method === 'DELETE') return t('appError.operations.delete', '删除')
  if (method === 'PATCH' || method === 'PUT') return t('appError.operations.save', '保存')
  return t('appError.operations.submit', '提交')
}

function titleFor(code: string, status: number | null, method: string, url: string): string {
  if (/course_change_source_unavailable/.test(code)) {
    return t('appError.names.courseChangeSource', '课程修改条件不足')
  }
  if (/lesson_sections_empty|sections_missing|outline_empty/.test(code)) {
    return t('appError.names.lessonPrerequisite', '教案生成条件不足')
  }
  if (/provider_|generation_deadline|generation_budget|response_truncated/.test(code)) {
    return t('appError.names.aiService', 'AI 服务调用失败')
  }
  if (/quality_gate|quality_failed/.test(code)) return t('appError.names.quality', '质量检查未通过')
  if (/conflict|revision_changed|stale/.test(code) || (status === 409 && !code)) {
    return t('appError.names.conflict', '内容版本冲突')
  }
  if (/permission|forbidden|unauthorized/.test(code) || status === 401 || status === 403) {
    return t('appError.names.permission', '权限校验失败')
  }
  if (/validation|invalid|unprocessable/.test(code) || status === 400 || status === 422) {
    return t('appError.names.validation', '信息校验失败')
  }
  if (status === 429) return t('appError.names.rateLimit', '请求频率受限')
  if (status && status >= 500) return t('appError.names.service', '服务处理失败')
  const template = t('appError.names.operation', '{domain}{operation}失败')
  return template
    .replace('{domain}', domainName(url))
    .replace('{operation}', operationName(method, url))
}

function reasonFor(
  code: string,
  status: number | null,
  rawMessage: string,
  fallback: string,
  hasResponse: boolean,
  networkFailure: boolean,
): string {
  if (networkFailure) return t('appError.reasons.network', '请求没有收到服务响应，请检查网络连接后重试。')
  const known: Array<[RegExp, string]> = [
    [/course_change_source_unavailable/i, t('appError.reasons.courseChangeSource', '当前课程还没有可分析的大纲或教学资产，请先完成课程大纲。')],
    [/lesson_sections_empty|sections_missing|outline_empty/i, t('appError.reasons.lessonPrerequisite', '当前讲次没有可生成教案的小节，请先补全课程大纲或课次小节。')],
    [/provider_rate_limited|too_many_requests|rate.?limit|\b429\b/i, t('appError.reasons.rateLimit', '服务请求过于频繁，当前操作尚未完成，请稍后重试。')],
    [/provider_quota_exhausted|insufficient_quota/i, t('appError.reasons.quota', 'AI 服务额度已用尽，继续重试不会成功，请先检查服务配置。')],
    [/provider_auth_failed|authentication|credential|api[_ -]?key/i, t('appError.reasons.providerAuth', 'AI 服务身份校验未通过，请检查服务配置后重试。')],
    [/provider_timeout|generation_deadline|timed? ?out|timeout/i, t('appError.reasons.timeout', '服务响应超时，本次操作尚未完成；已保存内容不会被清空。')],
    [/provider_unavailable|connection|network|econnreset/i, t('appError.reasons.unavailable', '服务暂时无法连接，请在网络或服务恢复后重试。')],
    [/quality_gate|quality_failed/i, t('appError.reasons.quality', '结果没有通过质量检查，正式内容保持不变。')],
    [/conflict|revision_changed|stale/i, t('appError.reasons.conflict', '内容已被其他操作更新，请重新载入最新版本后再继续。')],
    [/course_missing|course_not_found/i, t('appError.reasons.courseMissing', '当前课程不存在，或已被删除。')],
  ]
  const source = `${code} ${rawMessage}`
  const match = known.find(([pattern]) => pattern.test(source))
  if (match) return match[1]
  if ((status === 401 || status === 403)) return t('appError.reasons.permission', '当前身份没有完成此操作的权限。')
  if (status === 404) return t('appError.reasons.notFound', '请求的内容不存在，或已经被删除。')
  if (status === 409 && !code) return t('appError.reasons.conflict', '内容已被其他操作更新，请重新载入最新版本后再继续。')
  if (status === 429) return t('appError.reasons.rateLimit', '服务请求过于频繁，当前操作尚未完成，请稍后重试。')
  if (status && status >= 500) return t('appError.reasons.service', '服务端处理本次请求时发生异常，请稍后重试。')
  if (rawMessage && rawMessage !== 'Request failed' && !looksLikeTechnicalText(rawMessage)) return rawMessage
  if (status === 400 || status === 422) return t('appError.reasons.validation', '请求信息没有通过校验，请检查输入后重试。')
  if (status === 408) return t('appError.reasons.timeout', '服务响应超时，本次操作尚未完成；已保存内容不会被清空。')
  if (!hasResponse && fallback) return fallback
  return fallback || t('appError.reasons.generic', '本次操作没有完成，请查看技术详情后重试。')
}

function technicalLines(input: {
  code: string
  requestId: string
  status: number | null
  method: string
  url: string
  raw: string
  clientMessage: string
}): string {
  const lines = [
    input.code ? `${t('appError.details.code', '错误码')}: ${input.code}` : '',
    input.requestId ? `${t('appError.details.requestId', '请求编号')}: ${input.requestId}` : '',
    input.status ? `${t('appError.details.httpStatus', 'HTTP 状态')}: ${input.status}` : '',
    input.method || input.url
      ? `${t('appError.details.request', '请求')}: ${[input.method, input.url].filter(Boolean).join(' ')}`
      : '',
    input.raw ? `${t('appError.details.feedback', '原始反馈')}:\n${sanitizeTechnicalText(input.raw)}` : '',
    input.clientMessage && input.clientMessage !== input.raw
      ? `${t('appError.details.client', '客户端异常')}:\n${sanitizeTechnicalText(input.clientMessage)}`
      : '',
  ].filter(Boolean)
  return lines.join('\n\n').slice(0, MAX_TECHNICAL_DETAIL_LENGTH)
}

export function toAppError(error: unknown, options: AppErrorOptions = {}): AppErrorPresentation {
  const axiosError = asRecord(error).isAxiosError === true ? error as AxiosError : null
  const errorRecord = asRecord(error)
  const config = asRecord(axiosError?.config)
  const response = axiosError?.response
  const fields = detailFields(response?.data)
  const status = response?.status || null
  const method = text(config.method).toUpperCase()
  const url = text(config.url)
  const clientMessage = axiosError ? text(errorRecord.message) : text(errorRecord.message || error)
  const rawMessage = fields.message || clientMessage
  const code = options.code
    || fields.code
    || text(errorRecord.code)
    || (!response && axiosError?.request ? 'network_error' : '')
  const requestId = options.requestId
    || fields.requestId
    || responseHeader(response?.headers, 'x-request-id')
  const configuredTitle = text(config.errorTitle)
  const configuredSummary = text(config.errorSummary)
  const title = options.title || configuredTitle || titleFor(code, status, method, url)
  const summary = options.summary || configuredSummary || reasonFor(
    code,
    status,
    rawMessage,
    options.fallback || '',
    Boolean(response),
    Boolean(axiosError?.request && !response),
  )
  const technicalDetail = technicalLines({
    code,
    requestId,
    status,
    method,
    url,
    raw: fields.raw || rawMessage,
    clientMessage,
  })
  return {
    title,
    summary,
    technicalDetail,
    code,
    requestId,
    status,
    retryable: options.retryable ?? ![400, 401, 403, 404, 409, 422].includes(status || 0),
  }
}

function eventId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `app-error-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function publishAppError(error: unknown, options: AppErrorOptions = {}): AppErrorPresentation {
  const presentation = toAppError(error, options)
  const signature = [
    presentation.code,
    presentation.status || '',
    presentation.title,
    presentation.summary,
  ].join('|')
  const event = { id: eventId(), signature, presentation }
  lastPublishedAt = Date.now()
  listeners.forEach(listener => listener(event))
  return presentation
}

export function wasAppErrorPublishedRecently(maxAgeMs = 150): boolean {
  const age = Date.now() - lastPublishedAt
  return lastPublishedAt > 0 && age >= 0 && age <= maxAgeMs
}

export function subscribeAppErrors(listener: ErrorListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
