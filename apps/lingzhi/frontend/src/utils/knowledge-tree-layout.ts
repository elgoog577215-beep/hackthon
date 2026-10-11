import type { KnowledgeProfile } from '../types/knowledge-profile'

export interface ProfileTreeItem {
  id: string; sourceId: string; kind: 'course' | 'branch' | 'knowledge'
  label: string; progress: number | null; count: number; status?: string
  children: ProfileTreeItem[]
}
export interface PositionedProfileNode extends ProfileTreeItem {
  x: number; y: number; width: number; height: number; expanded: boolean
}
export interface ProfileTreeEdge { id: string; source: PositionedProfileNode; target: PositionedProfileNode; path: string }

export function createKnowledgeTree(profile: KnowledgeProfile, title: string, query = ''): ProfileTreeItem {
  const search = query.trim().toLocaleLowerCase()
  const groups = new Map(profile.branches.map(b => [b.id, b]))
  const placed = new Set<string>()
  const point = (p: KnowledgeProfile['nodes'][number]): ProfileTreeItem | null => {
    if (placed.has(p.knowledge_id) || (search && !`${p.name} ${p.statement}`.toLocaleLowerCase().includes(search))) return null
    placed.add(p.knowledge_id)
    return { id: `knowledge:${p.knowledge_id}`, sourceId: p.knowledge_id, kind: 'knowledge', label: p.name,
      progress: p.mastery, status: p.status, count: 1, children: [] }
  }
  const branch = (id: string, seen: Set<string>): ProfileTreeItem | null => {
    const current = groups.get(id)
    if (!current || seen.has(id)) return null
    const next = new Set([...seen, id])
    const children = [
      ...profile.branches.filter(b => b.parent_id === id).map(b => branch(b.id, next)),
      ...profile.nodes.filter(p => p.parent_id === id).map(point),
    ].filter((n): n is ProfileTreeItem => n !== null)
    if (!children.length) return null
    return { id: `branch:${id}`, sourceId: id, kind: 'branch', label: current.name,
      progress: current.summary.assessed_count ? current.summary.verified_progress : null, count: current.summary.total_count, children }
  }
  const children = profile.branches.filter(b => !b.parent_id || !groups.has(b.parent_id))
    .map(b => branch(b.id, new Set())).filter((n): n is ProfileTreeItem => n !== null)
  // Keep valid points reachable even if an older payload lacks its category.
  children.push(...profile.nodes.map(point).filter((n): n is ProfileTreeItem => n !== null))
  return { id: `course:${profile.course_id}`, sourceId: profile.course_id, kind: 'course', label: title,
    progress: profile.summary.verified_progress, count: profile.summary.total_count, children }
}

export function layoutKnowledgeTree(root: ProfileTreeItem, collapsed: Set<string>) {
  const nodes: PositionedProfileNode[] = []
  const edges: ProfileTreeEdge[] = []
  let cursor = 36
  const visit = (item: ProfileTreeItem, depth: number): PositionedProfileNode => {
    const visibleChildren = collapsed.has(item.id) ? [] : item.children
    const node: PositionedProfileNode = { ...item, x: 48 + depth * 268, y: 0,
      width: item.kind === 'knowledge' ? 304 : item.kind === 'course' ? 168 : 184,
      height: item.kind === 'course' ? 108 : item.kind === 'knowledge' ? 92 : 88, expanded: visibleChildren.length > 0 }
    nodes.push(node)
    if (!visibleChildren.length) {
      node.y = cursor + (104 - node.height) / 2
      cursor += 104
    } else {
      const children = visibleChildren.map(child => visit(child, depth + 1))
      const first = children[0]!, last = children.at(-1)!
      node.y = ((first.y + first.height / 2) + (last.y + last.height / 2)) / 2 - node.height / 2
      for (const child of children) {
        const sx = node.x + node.width, sy = node.y + node.height / 2
        const tx = child.x, ty = child.y + child.height / 2
        const bend = sx + (tx - sx) / 2
        edges.push({ id: `${node.id}->${child.id}`, source: node, target: child,
          path: `M ${sx} ${sy} C ${bend} ${sy}, ${bend} ${ty}, ${tx} ${ty}` })
      }
    }
    return node
  }
  visit(root, 0)
  return { nodes, edges, width: Math.max(920, ...nodes.map(n => n.x + n.width + 40)), height: Math.max(380, cursor + 36) }
}
