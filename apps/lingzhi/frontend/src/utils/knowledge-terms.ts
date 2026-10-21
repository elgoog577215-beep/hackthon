export interface KnowledgeTerm {
  name?: string
  english_name?: string
  abbreviations?: string[]
  aliases?: string[]
  origin?: string
  status?: string
  evidence_refs?: Array<{ evidence_id: string; quote?: string }>
}

export interface KnowledgeSearchFields {
  name?: string
  display_name?: string
  display_aliases?: string[]
  statement?: string
  aliases?: string[]
  english_name?: string
  abbreviations?: string[]
  terms?: KnowledgeTerm[]
}

export function knowledgeDisplayName(point?: KnowledgeSearchFields | null): string {
  return point?.display_name?.trim() || point?.name || ''
}

export function normalizeKnowledgeSearch(value: string): string {
  return value.normalize('NFKC').toLocaleLowerCase().replace(/[‐‑–—]/g, '-').replace(/\s+/g, ' ').trim()
}

export function knowledgeSearchText(point: KnowledgeSearchFields): string {
  return normalizeKnowledgeSearch([
    point.display_name, point.name, point.statement, point.english_name, ...(point.display_aliases || []), ...(point.aliases || []), ...(point.abbreviations || []),
    ...(point.terms || []).flatMap(term => [term.name, term.english_name, ...(term.aliases || []), ...(term.abbreviations || [])]),
  ].filter(Boolean).join(' '))
}
