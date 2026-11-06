import { renderMarkdown } from './markdown'
import { resolvePersonalAnchor } from './personal-note-anchor'

/** Use the same rendered text as selection notes, including KaTeX's visible layer. */
function renderedText(markdown: string) {
  const root = document.createElement('div')
  root.innerHTML = renderMarkdown(markdown)
  root.querySelectorAll('.katex-mathml,button,script,style').forEach(node => node.remove())
  return (root.textContent || '').replace(/\s+/g, ' ').trim()
}
export function resolveReferenceAnchor(root: HTMLElement, content: string, reference: { start: number; end: number; content: string }): Range | null {
  const chars = Array.from(content)
  if (chars.slice(reference.start, reference.end).join('') !== reference.content) return null
  const quote = renderedText(reference.content)
  const prefix = renderedText(chars.slice(0, reference.start).join('')).slice(-60)
  return resolvePersonalAnchor(root, { quote, anchor_prefix: prefix })
}
