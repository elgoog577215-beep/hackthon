/** Text anchors are local reading locations, never evidence of mastery. */
type Position = { node: Text; offset: number }
function index(root: HTMLElement) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let text = '', position: Position[] = []
  for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
    if (node.parentElement?.closest('button,script,style,.katex-mathml,[data-note-controls]')) continue
    for (let offset = 0; offset < node.data.length; offset++) {
      const char = /\s/.test(node.data[offset]!) ? ' ' : node.data[offset]!
      if (char === ' ' && (!text || text.endsWith(' '))) continue
      text += char; position.push({ node, offset })
    }
  }
  if (text.endsWith(' ')) { text = text.slice(0, -1); position = position.slice(0, -1) }
  return { text, position }
}
const normalize = (text: string) => text.replace(/\s+/g, ' ').trim()
function occurrences(haystack: string, needle: string) {
  const found: number[] = []
  if (!needle) return found
  for (let start = haystack.indexOf(needle); start >= 0; start = haystack.indexOf(needle, start + 1)) found.push(start)
  return found
}
export function capturePersonalAnchor(root: HTMLElement, range: Range) {
  const fragment = document.createElement('div')
  fragment.append(range.cloneContents())
  const data = index(root), quote = index(fragment).text
  const matches = occurrences(data.text, quote)
  const selected = matches.find(start => data.position[start]?.node === range.startContainer && data.position[start]!.offset >= range.startOffset
    && data.position[start]!.offset - range.startOffset <= 2)
  const at = selected ?? (matches.length === 1 ? matches[0] : undefined)
  return { quote, anchor_prefix: at === undefined ? '' : data.text.slice(Math.max(0, at - 60), at),
    anchor_suffix: at === undefined ? '' : data.text.slice(at + quote.length, at + quote.length + 60) }
}
export function resolvePersonalAnchor(root: HTMLElement, anchor: { quote: string; anchor_prefix?: string; anchor_suffix?: string }): Range | null {
  const data = index(root), quote = normalize(anchor.quote)
  const matches = occurrences(data.text, quote).filter(start =>
    (!anchor.anchor_prefix || data.text.slice(0, start).trimEnd().endsWith(normalize(anchor.anchor_prefix)))
    && (!anchor.anchor_suffix || data.text.slice(start + quote.length).trimStart().startsWith(normalize(anchor.anchor_suffix))))
  if (matches.length !== 1) return null
  const first = data.position[matches[0]!]!, last = data.position[matches[0]! + quote.length - 1]!
  if (!first || !last) return null
  const range = document.createRange()
  range.setStart(first.node, first.offset); range.setEnd(last.node, last.offset + 1)
  return range
}

/** CSS highlights do not mutate Vue's source DOM or break formula rendering. */
export function highlightPersonalNotes(ranges: Range[]) {
  const highlight = (globalThis as any).Highlight
  const registry = typeof CSS === 'undefined' ? undefined : (CSS as any).highlights
  if (!highlight || !registry) return
  registry.delete('lingzhi-personal-notes')
  if (ranges.length) registry.set('lingzhi-personal-notes', new highlight(...ranges))
}
