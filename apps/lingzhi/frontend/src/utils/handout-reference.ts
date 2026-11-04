import { renderMarkdown } from './markdown'
import { handoutContentType } from './handout-content'

export interface ReferenceSection {
  id: string
  title: string
  blocks: { block_id: string; content_type: string; title: string; content: string; answer_to?: string }[]
}
export type ReferenceKind = 'definition' | 'theorem' | 'formula'
export interface HandoutReference {
  id: string
  blockId: string
  title: string
  kind: ReferenceKind
  content: string
  // In the combined view, the complete definition/theorem already contains its formulas.
  html?: string
  includedInStatement: boolean
}

/** Read the same math parser as the handout, without guessing new statements or calling AI. */
export function buildHandoutReference(sections: ReferenceSection[]) {
  return sections.map(section => ({
    id: section.id, title: section.title,
    items: section.blocks.flatMap(block => {
      const kind = handoutContentType(block.content_type)
      // A reference sheet must not reveal answers that are folded in the reading view.
      if (kind === 'answer' || block.answer_to) return []
      const statement = kind === 'definition' || kind === 'theorem'
      const items: HandoutReference[] = []
      if (statement) items.push({ id: `${block.block_id}:statement`, blockId: block.block_id,
        title: block.title, kind, content: block.content, includedInStatement: false })
      const root = document.createElement('template')
      root.innerHTML = renderMarkdown(block.content)
      const seen = new Set<string>()
      const formulas: string[] = [], searchable: string[] = []
      for (const node of root.content.querySelectorAll('.katex, .math-fallback')) {
        if (node.closest('details')) continue
        const formula = node.closest('.katex-display') || node
        const html = formula.outerHTML
        if (seen.has(html)) continue
        seen.add(html)
        // Only copy sanitized math produced by our renderer; never source HTML.
        // KaTeX is configured for HTML-only output, so there are no TeX annotations.
        formulas.push(`<div class="reference-formula">${html}</div>`)
        searchable.push(formula.textContent || '')
      }
      if (formulas.length) items.push({ id: `${block.block_id}:formulas`, blockId: block.block_id,
        title: block.title, kind: 'formula', content: searchable.join(' '), html: formulas.join(''), includedInStatement: statement })
      return items
    }),
  }))
}
