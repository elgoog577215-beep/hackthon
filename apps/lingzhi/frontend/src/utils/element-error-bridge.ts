import { t } from '../shared/i18n'
import { publishAppError, wasAppErrorPublishedRecently } from './app-error'

interface ErrorService {
  error: (...args: any[]) => unknown
}

interface ErrorMessageOptions {
  title?: unknown
  message?: unknown
}

const noOpHandle = { close: () => undefined }

function readableText(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function presentationInput(input: unknown) {
  const options = input && typeof input === 'object' ? input as ErrorMessageOptions : {}
  const configuredTitle = readableText(options.title)
  const feedback = readableText(options.message) || readableText(input)
  const feedbackLooksLikeTitle = feedback.length <= 30 && /(失败|异常|错误|未通过)$/.test(feedback)
  const title = configuredTitle
    || (feedbackLooksLikeTitle ? feedback : t('appError.names.operationFallback', '操作失败'))
  const summary = feedback && feedback !== title
    ? feedback
    : t('appError.reasons.generic', '本次操作没有完成，请查看技术详情后重试。')
  return { title, summary, feedback: feedback || title }
}

function bridge(service: ErrorService) {
  service.error = ((input: unknown) => {
    // Axios 已在同一拒绝链中发布了包含请求编号的结构化错误，旧 catch 提示不再重复展示。
    if (wasAppErrorPublishedRecently()) return noOpHandle
    const normalized = presentationInput(input)
    publishAppError(normalized.feedback, {
      title: normalized.title,
      summary: normalized.summary,
    })
    return noOpHandle
  }) as ErrorService['error']
}

export function installElementErrorBridge(message: ErrorService, notification: ErrorService) {
  bridge(message)
  bridge(notification)
}
