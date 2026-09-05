import type { Node } from '../stores/types'

const lessonPrefix = /^(?:第\s*([\d一二三四五六七八九十百零〇两]+)\s*讲|(?:lesson|lecture)\s+(\d+))\s*[：:、.\-–—]?\s*/i

/** Presentation only: keep the original node title and navigation target intact. */
export function lessonNavigationLabel(node: Node, index: number) {
  const title = node.node_name.trim()
  const prefix = title.match(lessonPrefix)
  const number = prefix?.[1] || prefix?.[2] || String(index + 1)
  return {
    number: /^\d+$/.test(number) ? number.padStart(2, '0') : number,
    title: prefix && title.slice(prefix[0].length).trim()
      ? title.slice(prefix[0].length).trim()
      : title,
  }
}

export function isLessonNavigation(nodes: Node[]): boolean {
  return nodes.length > 0 && nodes.every(node => {
    const children = node.children || []
    if (!children.length) return true
    // Older lesson projections keep the real content in one section child.
    return lessonPrefix.test(node.node_name.trim())
      && children.length === 1
      && children[0]?.node_level === 2
      && !children[0].children?.length
  })
}

export function navigationNodeMatches(node: Node, query: string, roleLabel: (role: string) => string): boolean {
  const term = query.trim().toLocaleLowerCase()
  if (!term || node.node_name.toLocaleLowerCase().includes(term)) return true
  if (node.course_blocks?.some(block => block.status !== 'retired'
    && `${roleLabel(block.role)} ${String(block.payload.title || '')}`.toLocaleLowerCase().includes(term))) return true
  return node.children?.some(child => navigationNodeMatches(child, term, roleLabel)) || false
}

/** A compatibility wrapper without content should not become a second lesson cover. */
export function emptyLessonShellContent(node: Node): Node | null {
  const children = node.children || []
  if (node.node_level !== 1 || !lessonPrefix.test(node.node_name.trim()) || children.length !== 1) return null
  if (node.node_content?.trim() || node.learning_objective?.trim() || node.course_blocks?.length || node.content_blocks?.length) return null
  const child = children[0]!
  return child.node_level === 2 && !child.children?.length ? child : null
}
