export type RetrievalErrorCode =
  | 'not_configured'
  | 'timeout'
  | 'provider_error'
  | 'no_sources'
  | 'privacy_blocked'

const ERROR_CODES = new Set<RetrievalErrorCode>([
  'not_configured',
  'timeout',
  'provider_error',
  'no_sources',
  'privacy_blocked',
])

const NESTED_KEYS = [
  'receipt',
  'retrieval_receipt',
  'retrieval_package',
  'package',
  'web_enrichment',
] as const

function knownCode(value: unknown): RetrievalErrorCode | null {
  const code = String(value || '').trim() as RetrievalErrorCode
  return ERROR_CODES.has(code) ? code : null
}

function errorCodeFromRecord(
  value: Record<string, unknown>,
  visited: Set<Record<string, unknown>>,
): RetrievalErrorCode | null {
  if (visited.has(value)) return null
  visited.add(value)

  const direct = knownCode(value.error_code)
  if (direct) return direct

  const errors = Array.isArray(value.error_codes) ? value.error_codes : []
  for (const error of errors) {
    const code = knownCode(error)
    if (code) return code
  }

  for (const key of NESTED_KEYS) {
    const nested = value[key]
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      const code = errorCodeFromRecord(nested as Record<string, unknown>, visited)
      if (code) return code
    }
  }
  return null
}

export function retrievalErrorCode(value: unknown): RetrievalErrorCode | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return errorCodeFromRecord(value as Record<string, unknown>, new Set())
}

export function retrievalErrorTranslationKey(value: unknown): string | null {
  const code = retrievalErrorCode(value)
  return code ? `courseGeneration.retrieval.errors.${code}` : null
}
