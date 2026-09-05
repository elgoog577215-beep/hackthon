import { t } from '@/shared/i18n'

/**
 * Shared handling for generation review issues.
 *
 * The release gate and the task centre both merge `blocking_issues` with
 * `source_chain.issues`, but only the task centre used to deduplicate them. The
 * gate therefore counted an issue twice while the list below it showed one, so
 * the same course reported "3 blockers" next to 2 visible items. Both surfaces
 * now share this module.
 */

export function reviewIssueMessage(issue: any): string {
  if (String(issue?.code || '') === 'teaching_plan:local_fallback') {
    return t(
      'courseTasks.review.teachingPlanFallback',
      '部分教案单元使用本地保底生成，请重点复核标记小节的教学语义。',
    )
  }
  return String(issue?.message || issue || '')
}

export function reviewIssueTarget(issue: any): string {
  return String(issue?.target_id || issue?.node_id || issue?.asset_id || '')
}

export function reviewIssueSuggestion(issue: any): string {
  return String(issue?.suggestion || '')
}

export function qualityIssueKey(issue: any, index: number): string {
  return `${String(issue?.code || issue?.issue_id || 'issue')}-${reviewIssueTarget(issue)}-${index}`
}

/**
 * Collapse issues that describe the same problem on the same target.
 *
 * Later duplicates are not discarded outright: their fields backfill blanks on
 * the entry that is kept, so a richer duplicate still contributes its
 * suggestion or target.
 */
export function dedupeReviewIssues(issues: any[]): any[] {
  const result: any[] = []
  const positions = new Map<string, number>()
  for (const raw of issues) {
    if (!raw) continue
    const issue = typeof raw === 'object' ? { ...raw } : { message: String(raw) }
    const message = reviewIssueMessage(issue).trim()
    const target = reviewIssueTarget(issue).trim()
    const key = `${message}\u0000${target}\u0000${String(issue.severity || '')}`
    const position = positions.get(key)
    if (position === undefined) {
      positions.set(key, result.length)
      result.push(issue)
      continue
    }
    const existing = result[position]
    for (const [field, value] of Object.entries(issue)) {
      if (value !== undefined && value !== null && value !== '' && !existing[field]) existing[field] = value
    }
  }
  return result
}

/**
 * The blocking issues for a review artifact, as one deduplicated list.
 *
 * Callers must not re-merge these two sources themselves — that is exactly how
 * the count and the list drifted apart.
 */
export function reviewBlockingIssues(artifact: any): any[] {
  return dedupeReviewIssues([
    ...(artifact?.blocking_issues || []),
    ...(artifact?.source_chain?.issues || []),
  ])
}
