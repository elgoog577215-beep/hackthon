import MarkdownIt from 'markdown-it'
import { renderMarkdown } from './markdown'

const parser = new MarkdownIt({ html: true })
const normalize = (text: string) => text.replace(/\s+/g, ' ').trim()

/** Bind paragraphs to source Markdown. Unmatched or repaired text never guesses a source range. */
export function bindInlineMarkdownSource(html: string, source: string): string {
  const root = document.createElement('div')
  root.innerHTML = html
  const elements = Array.from(
    root.querySelectorAll<HTMLElement>('p,li,h2,h3,h4,h5,td,th'),
  )
  const consumed = new Set<HTMLElement>()
  const probe = document.createElement('div')
  for (const token of parser.parse(source, {})) {
    if (token.type !== 'inline' || !token.content.trim()) continue
    probe.innerHTML = renderMarkdown(token.content)
    const rendered = normalize(probe.textContent || '')
    const element = elements.find(
      (el) => !consumed.has(el) && normalize(el.textContent || '') === rendered,
    )
    if (!element) continue
    element.dataset.aiSource = token.content
    consumed.add(element)
  }
  return root.innerHTML
}
