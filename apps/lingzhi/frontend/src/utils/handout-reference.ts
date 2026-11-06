import { renderMarkdown } from './markdown'
import { handoutContentType } from './handout-content'

export type ReferenceKind = 'definition' | 'theorem' | 'result' | 'formula' | 'rule' | 'method'
export interface ReferenceRange { id: string; title: string; kind: ReferenceKind; start: number; end: number; content: string }
export interface ReferenceSection {
  id: string
  title: string
  blocks: { block_id: string; content_type: string; title: string; content: string; answer_to?: string;
    references?: ReferenceRange[]; reference_schema_version?: string; reference_issues?: string[] }[]
}
export interface HandoutReference {
  id: string; blockId: string; title: string; kind: ReferenceKind; content: string; html: string
  mode: 'range' | 'formula' | 'source'
}
const kinds = new Set(['definition', 'theorem', 'result', 'formula', 'rule', 'method'])
const legacyKinds: Record<string, ReferenceKind> = { definition: 'definition', theorem: 'theorem', rule: 'rule', result: 'result', method: 'method', checklist: 'method' }
const excluded = new Set(['answer', 'exercise', 'question', 'review_question', 'guiding_question', 'example'])

/** Never expose folded answers, including nested and unfinished legacy details. */
function withoutFoldedContent(content: string): string {
  let depth = 0, end = 0, visible = ''
  for (const match of content.matchAll(/<\/?details\b[^>]*>/gi)) {
    if (!depth) visible += content.slice(end, match.index)
    depth = /^<\//.test(match[0]) ? Math.max(0, depth - 1) : depth + 1
    end = match.index! + match[0].length
  }
  return (visible + (depth ? '' : content.slice(end))).trim()
}

/** Projections contain source excerpts, never summaries or a second teaching body. */
export function buildHandoutReference(sections: ReferenceSection[]) {
  return sections.map(section => ({ id: section.id, title: section.title,
    items: section.blocks.flatMap((block): HandoutReference[] => {
      const type = handoutContentType(block.content_type)
      if (block.answer_to || excluded.has(type)) return []
      const content = withoutFoldedContent(block.content)
      if (!content) return []
      // Python offsets count Unicode code points rather than UTF-16 code units.
      const characters = Array.from(block.content)
      const ranges = block.reference_schema_version === 'handout_reference_v1' ? (block.references || []).filter(ref =>
        kinds.has(ref.kind) && Number.isInteger(ref.start) && Number.isInteger(ref.end) && ref.start >= 0 && ref.end > ref.start
        && characters.slice(ref.start, ref.end).join('') === ref.content
        && withoutFoldedContent(characters.slice(0, ref.end).join('')).includes(ref.content)
        && withoutFoldedContent(ref.content) === ref.content,
      ) : []
      if (ranges.length) return ranges.map(ref => ({ id: `${block.block_id}:${ref.id}`, blockId: block.block_id,
        title: ref.title, kind: ref.kind, content: ref.content, html: renderMarkdown(ref.content), mode: 'range' as const }))
      // A marked revision with missing/invalid ranges must not silently invent an excerpt.
      if (block.reference_schema_version && ((block.references?.length || 0) > 0 || (block.reference_issues?.length || 0) > 0)) return []
      const canonical = ['definition', 'theorem', 'rule', 'result'].includes(type)
      const boxed = ['explanation', 'derivation', 'introduction'].includes(type) && content.includes('\\boxed')
      const root = document.createElement('template')
      root.innerHTML = renderMarkdown(content)
      const displays = Array.from(root.content.querySelectorAll('.katex-display, .math-fallback.is-display'))
        .filter(node => !node.querySelector('.katex-display, .math-fallback.is-display') && !node.closest('pre, code, details'))
      const candidates = canonical ? (displays.length ? displays : Array.from(root.content.querySelectorAll('.katex, .math-fallback'))
        .filter(node => !node.closest('pre, code, details') && node.textContent?.includes('=')).slice(0, 2))
        : boxed ? displays.filter(node => node.querySelector('.fbox, .boxpad')) : []
      const seen = new Set<string>(), formulas: string[] = []
      for (const formula of candidates) {
        const source = formula.querySelector('annotation')?.textContent || formula.textContent || ''
        if (seen.has(source)) continue
        seen.add(source)
        formulas.push(`<div class="reference-formula">${formula.outerHTML}</div>`)
      }
      if (formulas.length) {
        // Preserve adjacent, explicit conditions without copying the whole explanation.
        const conditions = Array.from(root.content.children).filter(node => node.tagName === 'P'
          && !node.querySelector('.katex-display, .math-fallback.is-display')
          && (node.textContent?.length || 0) <= 300
          && /^(?:成立条件|适用条件|条件[：:]|当|若|设|其中[，：:]|对于|where\b|provided\b|assuming\b|if\b)/i.test((node.textContent || '').trim()))
          .map(node => node.outerHTML).join('')
        return [{ id: `${block.block_id}:formulas`, blockId: block.block_id, title: block.title,
          kind: 'formula' as const, content, html: formulas.join('') + conditions, mode: 'formula' as const }]
      }
      // Old prose remains accessible as an honest source index; no first-paragraph heuristic.
      const kind = legacyKinds[type]
      return kind ? [{ id: `${block.block_id}:source`, blockId: block.block_id, title: block.title,
        kind, content, html: '', mode: 'source' as const }] : []
    }),
  }))
}
