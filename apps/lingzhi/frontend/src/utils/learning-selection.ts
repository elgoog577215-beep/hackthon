import { buildTextQuoteAnchor } from './text-anchor'

export interface LearningSelectionQuote {
  text: string
  nodeId: string
  anchor: Record<string, unknown>
}

/** Only cite a real selection wholly inside one loaded lecture. */
export function learningSelectionQuote(range: Range, root: HTMLElement, nodeIds: ReadonlySet<string>): LearningSelectionQuote | null {
  const text = range.toString()
  if (range.collapsed || !text.trim()) return null
  const elementAt = (node: Node) => node instanceof Element ? node : node.parentElement
  const start = elementAt(range.startContainer)
  const end = elementAt(range.endContainer)
  if (!start || !end || !root.contains(start) || !root.contains(end)) return null
  const editable = 'input, textarea, button, [contenteditable]:not([contenteditable="false"])'
  if (start.closest(editable) || end.closest(editable)) return null
  const lecture = start.closest<HTMLElement>('[id^="node-"]')
  if (!lecture || lecture !== end.closest('[id^="node-"]')) return null
  const nodeId = lecture.id.slice('node-'.length)
  if (!nodeIds.has(nodeId)) return null
  const anchor = buildTextQuoteAnchor(range, lecture, text)
  const block = start.closest<HTMLElement>('[data-content-block-id]')
  if (block && block === end.closest('[data-content-block-id]')) {
    Object.assign(anchor, { block_id: block.dataset.contentBlockId, block_revision_id: block.dataset.contentBlockRevisionId })
  }
  return { text, nodeId, anchor }
}
