import { StudyApiError } from '../api/study'

/** Retry observation only. This never submits or resumes a generation task. */
export function readRecoveryDelay(error: unknown, failures: number): number | null {
  const transient = error instanceof TypeError || error instanceof StudyApiError &&
    (error.status === 408 || error.status === 429 || error.status >= 500)
  return transient ? Math.min(1500 * 2 ** Math.min(failures, 5), 30000) : null
}
