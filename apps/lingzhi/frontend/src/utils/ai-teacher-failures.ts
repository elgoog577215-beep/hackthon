import { t } from '../shared/i18n'

/**
 * The backend classifies every AI-teacher provider failure with `ai_base`'s
 * existing taxonomy (auth, quota, rate limit, timeout, budget, truncation) and
 * forwards it as a stable code on the SSE `error` event. Translate from that
 * code — not from the server's Chinese message — so both languages describe the
 * same failure and a retryable outage reads differently from a config problem.
 */
const MODEL_FAILURE_COPY: Record<string, [string, string]> = {
  model_not_configured: ['courseWorkspace.aiTeacher.failure.notConfigured', 'AI 老师尚未配置模型'],
  model_auth_failed: ['courseWorkspace.aiTeacher.failure.authFailed', 'AI 模型认证失败'],
  model_quota_exhausted: ['courseWorkspace.aiTeacher.failure.quotaExhausted', 'AI 模型额度已用完'],
  model_request_too_large: ['courseWorkspace.aiTeacher.failure.requestTooLarge', '这次提问的上下文过大，请缩小选区'],
  model_rate_limited: ['courseWorkspace.aiTeacher.failure.rateLimited', 'AI 模型当前繁忙'],
  model_timeout: ['courseWorkspace.aiTeacher.failure.timeout', 'AI 模型响应超时'],
  model_response_truncated: ['courseWorkspace.aiTeacher.failure.truncated', '回答被长度限制截断，内容不完整'],
  model_unavailable: ['courseWorkspace.aiTeacher.failure.unavailable', 'AI 老师暂时不可用'],
  cancelled: ['courseWorkspace.aiTeacher.failure.cancelled', '已停止生成'],
}

export function modelFailureLabel(code: string | undefined) {
  const copy = MODEL_FAILURE_COPY[String(code || '')] || MODEL_FAILURE_COPY.model_unavailable!
  return t(copy[0], copy[1])
}

export function modelFailureHint(retryable: boolean | undefined) {
  return retryable === false
    ? t(
        'courseWorkspace.aiTeacher.failure.noRetryHint',
        '重试无法解决，请联系管理员；课程与正式学习任务不受影响。',
      )
    : t(
        'courseWorkspace.aiTeacher.failure.retryHint',
        '课程与正式学习任务不受影响，可以重试。',
      )
}
