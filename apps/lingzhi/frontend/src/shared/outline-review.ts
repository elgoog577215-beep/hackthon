import { t } from './i18n'

type ReviewIssue = Record<string, any>

function phrase(key: string, values: Record<string, unknown>): string {
  return t(`courseWorkbench.outlineReview.${key}`).replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''))
}

export function outlineReviewAction(issue: ReviewIssue): 'ai' | 'manual' {
  return issue.repair_mode === 'manual'
    || String(issue.code || '').includes('unverified_extension_resource')
    || !String(issue.repair_instruction || '').trim() ? 'manual' : 'ai'
}

export function outlineReviewMessage(issue: ReviewIssue): string {
  const code = String(issue.code || '').split(':').pop()
  const evidence = issue.evidence || {}
  const values = { count: issue.node_ids?.length || 0, actual: evidence.actual_hours, expected: evidence.expected_hours }
  if (code === 'repeated_objective_template') return phrase('repeatedObjectives', values)
  if (code === 'missing_extension_resources' && typeof evidence.has_course_references === 'boolean') {
    return phrase(evidence.has_course_references ? 'resourcesUnassigned' : 'resourcesNeeded', values)
  }
  if (code === 'unverified_extension_resources') return phrase('resourceRecordsMissing', values)
  if (code === 'missing_hour_breakdown') {
    const total = evidence.expected_hours && Math.abs(evidence.actual_hours - evidence.expected_hours) > 0.01
      ? ` ${phrase('hourTotals', values)}` : ''
    return phrase('hoursMissing', values) + total
  }
  if (code === 'hour_total_mismatch') return phrase('hourTotals', values)
  return String(issue.message || '')
}

export function outlineReviewEvidence(issue: ReviewIssue): string[] {
  const evidence = issue.evidence || {}
  const lines: string[] = []
  if (Array.isArray(evidence.examples) && evidence.examples.length) {
    lines.push(t('courseWorkbench.outlineReview.templateLimit'))
    for (const example of evidence.examples) lines.push(`${example.title}: ${example.text}`)
  }
  if (Array.isArray(evidence.resources) && evidence.resources.length) {
    lines.push(t('courseWorkbench.outlineReview.verificationLimit'))
    for (const resource of evidence.resources) {
      const missing = (resource.missing_fields || []).map((field: string) => t(`courseWorkbench.outlineReview.missingFields.${field}`)).join(' / ')
      lines.push(phrase('resourceEvidence', { title: resource.title, resource: resource.resource || t('courseWorkbench.outlineReview.unnamedResource'), missing }))
    }
  }
  return lines
}
