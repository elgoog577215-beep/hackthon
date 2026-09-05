import type { Node } from '../stores/types'

const lessonPrefix = /^(?:第\s*([\d一二三四五六七八九十百零〇两]+)\s*讲|(?:lesson|lecture)\s+(\d+))\s*[：:、.\-–—]?\s*/i

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
