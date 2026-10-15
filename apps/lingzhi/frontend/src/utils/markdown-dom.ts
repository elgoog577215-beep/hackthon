/**
 * Reconcile only HTML already sanitized by renderMarkdown. Keep a separate
 * source snapshot: live nodes may contain Vue diagrams, open details, code
 * results, selection and focus that must survive an ordinary streamed append.
 */
type Entry = { source: Node; live: Node; children: Entry[] }
const atomic = (node: Node) => node instanceof Element && node.matches(
  '.teaching-diagram-host, .mermaid, .code-block-wrapper, pre',
)

export function createMarkdownDom(root: HTMLElement, beforeRemove: (node: Node) => void) {
  let entries: Entry[] = []

  function create(source: Node): Entry {
    const live = source.cloneNode(false)
    const children = Array.from(source.childNodes, create)
    for (const child of children) live.appendChild(child.live)
    return { source, live, children }
  }

  function remove(entry: Entry) {
    beforeRemove(entry.live)
    entry.live.parentNode?.removeChild(entry.live)
  }

  function compatible(entry: Entry, source: Node) {
    return entry.source.nodeType === source.nodeType
      && entry.source.nodeName === source.nodeName
      && !atomic(entry.source) && !atomic(source)
  }

  function update(entry: Entry, source: Node): Entry {
    if (entry.source.isEqualNode(source)) return entry
    if (entry.live instanceof Element && source instanceof Element && entry.source instanceof Element) {
      // Compare with the source snapshot, not live attributes such as `open`.
      for (const attr of Array.from(entry.source.attributes)) {
        if (!source.hasAttribute(attr.name)) entry.live.removeAttribute(attr.name)
      }
      for (const attr of Array.from(source.attributes)) {
        if (entry.source.getAttribute(attr.name) !== attr.value) entry.live.setAttribute(attr.name, attr.value)
      }
      entry.children = reconcile(entry.live, entry.children, Array.from(source.childNodes))
    } else if (entry.live.nodeValue !== source.nodeValue) {
      entry.live.nodeValue = source.nodeValue
    }
    entry.source = source
    return entry
  }

  function reconcile(parent: Node, previous: Entry[], sources: Node[]): Entry[] {
    const remaining = [...previous]
    const next: Entry[] = []
    let cursor = parent.firstChild
    for (const source of sources) {
      // Exact matches take precedence over positional matching. Repeated equal
      // diagrams consume distinct entries in order, never share a live host.
      let index = remaining.findIndex(entry => entry.source.isEqualNode(source))
      if (index < 0 && remaining[0] && compatible(remaining[0], source)) index = 0
      const entry = index < 0 ? create(source) : update(remaining.splice(index, 1)[0]!, source)
      if (entry.live !== cursor) parent.insertBefore(entry.live, cursor)
      cursor = entry.live.nextSibling
      next.push(entry)
    }
    for (const entry of remaining) remove(entry)
    return next
  }

  return {
    update(sanitizedHtml: string, reset = false) {
      if (reset) { for (const entry of entries) remove(entry); entries = [] }
      const template = document.createElement('template')
      template.innerHTML = sanitizedHtml
      entries = reconcile(root, entries, Array.from(template.content.childNodes))
    },
    clear() { for (const entry of entries) remove(entry); entries = [] },
  }
}
