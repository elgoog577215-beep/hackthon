import { renderMarkdown } from './markdown'
import { handoutContentType } from './handout-content'

export interface ReferenceSection {
  id: string
  title: string
  blocks: { block_id: string; content_type: string; title: string; content: string; answer_to?: string }[]
}
export type ReferenceKind = 'definition' | 'theorem' | 'result' | 'formula' | 'method' | 'warning'
export interface HandoutReference {
  id: string; blockId: string; title: string; kind: ReferenceKind; content: string
  html?: string
  includedInStatement: boolean
}
const statementKinds: Record<string, Exclude<ReferenceKind, 'formula'>> = {
  definition: 'definition', theorem: 'theorem', rule: 'theorem', result: 'result', summary: 'result',
  method: 'method', checklist: 'method', warning: 'warning', misconception: 'warning', counterexample: 'warning',
}

/** Follow the reference reader's inclusion rules, while retaining text and conditions. */
export function buildHandoutReference(sections: ReferenceSection[]) {
  return sections.map(section => ({
    id: section.id, title: section.title,
    items: section.blocks.flatMap(block => {
      const type = handoutContentType(block.content_type)
      if (type === 'answer' || block.answer_to) return []
      // Folded answers are not part of the quick reference, even in legacy blocks.
      const content = block.content.replace(/<details\b[^>]*>[\s\S]*?(?:<\/details>|$)/gi, '').trim()
      if (!content) return []
      const kind = statementKinds[type]
      const items: HandoutReference[] = []
      if (kind) items.push({ id: `${block.block_id}:statement`, blockId: block.block_id,
        title: block.title, kind, content, includedInStatement: false })
      const canonical = ['definition', 'theorem', 'rule', 'result'].includes(type)
      const boxedProse = ['explanation', 'derivation', 'introduction'].includes(type) && content.includes('\\boxed')
      if (!canonical && !boxedProse) return items
      const root = document.createElement('template')
      root.innerHTML = renderMarkdown(content)
      // Markdown may wrap KaTeX's own display span; keep only the actual inner display.
      const displays = Array.from(root.content.querySelectorAll('.katex-display, .math-fallback.is-display'))
        .filter(node => !node.querySelector('.katex-display, .math-fallback.is-display'))
      const candidates = displays.length ? displays : Array.from(root.content.querySelectorAll('.katex, .math-fallback'))
        .filter(node => node.textContent?.includes('=')).slice(0, 2)
      const seen = new Set<string>(), formulas: string[] = []
      for (const formula of candidates) {
        if (formula.closest('details')) continue
        if (boxedProse && !formula.querySelector('.fbox, .boxpad')) continue
        const html = formula.outerHTML
        if (seen.has(html)) continue
        seen.add(html)
        // Only sanitized math from the existing renderer, never raw source HTML.
        formulas.push(`<div class="reference-formula">${html}</div>`)
      }
      if (formulas.length) items.push({ id: `${block.block_id}:formulas`, blockId: block.block_id,
        title: block.title, kind: 'formula', content, html: formulas.join(''), includedInStatement: Boolean(kind) })
      return items
    }),
  }))
}
