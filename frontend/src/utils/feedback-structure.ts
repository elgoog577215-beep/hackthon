export type FeedbackSectionKind = 'reference_answer' | 'task_review' | 'rubric' | 'common_errors' | 'guidance'

export interface FeedbackSection {
  sectionId: string
  title: string
  kind: FeedbackSectionKind
  markdown: string
  summary: string
  collapsedByDefault: boolean
}

interface PersistedFeedbackSection {
  section_id?: unknown
  title?: unknown
  kind?: unknown
  markdown?: unknown
  summary?: unknown
  collapsed_by_default?: unknown
}

interface PersistedFeedbackStructure {
  schema_version?: unknown
  mode?: unknown
  sections?: unknown
}

const LEGACY_TITLE = '(?:任务\\s*\\d+[^*\\n]*|常见错误(?:反馈)?|典型错误(?:反馈)?|评价标准[^*\\n]*|评分标准[^*\\n]*|参考答案[^*\\n]*|答案方向[^*\\n]*|核对标准[^*\\n]*)'
const sectionHeading = new RegExp(`^(?:###\\s+(.+?)|\\*\\*(${LEGACY_TITLE})\\*\\*[：:]?)\\s*$`, 'gm')

export function resolveFeedbackSections(content: string, rawStructure?: unknown): FeedbackSection[] {
  const persisted = normalizePersistedStructure(rawStructure)
  return persisted.length ? persisted : parseLegacyFeedback(content)
}

export function normalizeLegacyFeedbackMath(markdown: string): string {
  return String(markdown || '').replace(/(?<!`)`([^`\n]+)`(?!`)/g, (full, value: string) => (
    looksLikeMath(value) ? `$${value.trim()}$` : full
  ))
}

function normalizePersistedStructure(raw: unknown): FeedbackSection[] {
  if (!raw || typeof raw !== 'object') return []
  const structure = raw as PersistedFeedbackStructure
  if (structure.schema_version !== 'course_feedback_v1' || structure.mode !== 'static_reference' || !Array.isArray(structure.sections)) {
    return []
  }
  return structure.sections
    .map((section, index) => normalizeSection(section as PersistedFeedbackSection, index))
    .filter((section): section is FeedbackSection => Boolean(section))
}

function normalizeSection(raw: PersistedFeedbackSection, index: number): FeedbackSection | null {
  const markdown = String(raw.markdown || '').trim()
  if (!markdown) return null
  const title = String(raw.title || '').trim() || `参考与检查 ${index + 1}`
  return {
    sectionId: String(raw.section_id || `feedback-section-${index + 1}`),
    title,
    kind: normalizeKind(raw.kind, title),
    markdown,
    summary: String(raw.summary || summarize(markdown)),
    collapsedByDefault: raw.collapsed_by_default !== false,
  }
}

function parseLegacyFeedback(content: string): FeedbackSection[] {
  const text = String(content || '').trim()
  if (!text) return []
  const matcher = new RegExp(sectionHeading.source, sectionHeading.flags)
  const matches = Array.from(text.matchAll(matcher))
  const rawSections: Array<{ title: string; markdown: string }> = []

  if (matches.length) {
    const preface = cleanBody(text.slice(0, matches[0]?.index || 0))
    if (preface) rawSections.push({ title: '核对说明', markdown: preface })
    matches.forEach((match, index) => {
      const start = (match.index || 0) + match[0].length
      const end = index + 1 < matches.length ? (matches[index + 1]?.index || text.length) : text.length
      const markdown = cleanBody(text.slice(start, end))
      if (!markdown) return
      rawSections.push({ title: String(match[1] || match[2] || '参考与检查').trim().replace(/[：:]$/, ''), markdown })
    })
  } else {
    rawSections.push({ title: '参考与检查', markdown: cleanBody(text) })
  }

  const multiple = rawSections.length > 1
  return rawSections.map((section, index) => {
    const kind = normalizeKind('', section.title)
    return {
      sectionId: `legacy-feedback-section-${index + 1}`,
      title: section.title,
      kind,
      markdown: section.markdown,
      summary: summarize(section.markdown),
      collapsedByDefault: multiple || section.markdown.length >= 700 || kind === 'reference_answer',
    }
  })
}

function normalizeKind(value: unknown, title: string): FeedbackSectionKind {
  if (['reference_answer', 'task_review', 'rubric', 'common_errors', 'guidance'].includes(String(value))) {
    return value as FeedbackSectionKind
  }
  const normalized = title.replace(/\s+/g, '')
  if (/(常见错误|典型错误|误区)/.test(normalized)) return 'common_errors'
  if (/(评价标准|评分标准|核对标准)/.test(normalized)) return 'rubric'
  if (/(答案|解答|答案方向)/.test(normalized)) return 'reference_answer'
  if (/任务/.test(normalized)) return 'task_review'
  return 'guidance'
}

function looksLikeMath(value: string): boolean {
  const text = String(value || '').trim()
  return /[ΘΩε≈≤≥∞]/.test(text)
    || /[A-Za-z0-9)\]]\^[({A-Za-z0-9+\-]/.test(text)
    || /(?:log|ln)(?:_|\s)[A-Za-z0-9(]/i.test(text)
    || /\bN\s*\/\s*log\b/i.test(text)
    || /(?:T|f)\s*\([^)]*\)\s*=/.test(text)
    || /^(?:\d+(?:\.\d+)?|[A-Za-zε])\s*(?:\/|=|≈|≤|≥|<|>)\s*[A-Za-z0-9ε()./^+*=≈≤≥<>\-\s]+$/.test(text)
    || /^[A-Za-z](?:_[A-Za-z0-9]+)?$/.test(text)
}

function cleanBody(value: string): string {
  return String(value || '').replace(/^---\s*$/gm, '').trim()
}

function summarize(markdown: string): string {
  return String(markdown || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`$\\-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 96)
}
