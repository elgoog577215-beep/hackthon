import { t } from '../shared/i18n'
import { toAppError, type AppErrorPresentation } from './app-error'

type PptOperation = 'manuscript' | 'render'
type PptFailure = { code?: string; message?: string; stage?: string; retryable?: boolean }

/** Present the failure of an operation without changing the availability of its saved input. */
export function pptFailurePresentation(
  failure: PptFailure | null | undefined,
  error: string | undefined,
  operation: PptOperation,
  hasContent = false,
): AppErrorPresentation | null {
  if (!failure && !error) return null
  const code = String(failure?.code || '')
  const message = String(failure?.message || error || '')
  let title = t(operation === 'render' ? 'pptWorkspace.editor.renderFailed' : hasContent
    ? 'pptWorkspace.editor.manuscriptUpdateFailed' : 'pptWorkspace.manuscriptGenerationFailedTitle')
  let summary = t(operation === 'render' ? 'pptWorkspace.editor.renderFailureHelp' : 'pptWorkspace.manuscriptGenerationFailedMessage')
  if (!failure) {
    title = t('pptWorkspace.manuscriptOperationFailedTitle')
    summary = /[\u3400-\u9fff]/u.test(message) ? message : t('pptWorkspace.editor.operationFailedHelp')
  } else if (/exported_text_frame_overflow|layout_capacity_failed|text_overflow/.test(`${code} ${message}`)) {
    summary = t('pptWorkspace.editor.overflowHelp')
  } else if (code === 'story_ai_batch_request_budget_exceeded') {
    title = t('pptWorkspace.manuscriptBudgetRecoveredTitle')
    summary = t('pptWorkspace.manuscriptBudgetRecoveredMessage')
  } else if (code.startsWith('story_title_') || code === 'duplicate_slide_title') {
    title = t('pptWorkspace.manuscriptTitleRecoveryTitle')
    summary = t('pptWorkspace.manuscriptTitleRecoveryMessage')
  } else if (code.endsWith('_rate_limited')) {
    summary = t('pptWorkspace.manuscriptRateLimitedMessage')
  } else if (code.endsWith('_authentication') || code.endsWith('_balance_unavailable')) {
    summary = t('pptWorkspace.editor.providerUnavailable')
  }
  return toAppError({ code, message }, { title, summary, retryable: failure?.retryable })
}
