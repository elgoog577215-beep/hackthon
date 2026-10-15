import type { KnowledgeProfile } from '../types/knowledge-profile'

export interface ProfileTreeItem {
  id: string; sourceId: string; kind: 'course' | 'branch' | 'knowledge'
  label: string; progress: number | null; count: number; status?: string; pending?: boolean
  children: ProfileTreeItem[]
  searchText?: string
}
export interface PositionedProfileNode extends ProfileTreeItem {
  x: number; y: number; width: number; height: number; expanded: boolean
}
export interface ProfileTreeEdge { id: string; source: PositionedProfileNode; target: PositionedProfileNode; path: string }

/** Display course content without manufacturing a learner assessment profile. */
export function createContentKnowledgeTree(
  courseId: string,
  title: string,
  categories: Array<{ id: string; parent_id?: string | null; name: string }>,
  points: Array<{ knowledge_id: string; parent_id?: string | null; name: string; statement?: string }>,
): ProfileTreeItem {
  const groups = new Map(categories.map(category => [category.id, category]))
  const placed = new Set<string>()
  const visited = new Set<string>()
  const point = (item: typeof points[number]): ProfileTreeItem | null => {
    if (placed.has(item.knowledge_id)) return null
    placed.add(item.knowledge_id)
    return { id: `knowledge:${item.knowledge_id}`, sourceId: item.knowledge_id, kind: 'knowledge',
      label: item.name, searchText: `${item.name} ${item.statement || ''}`, progress: null, count: 1, children: [] }
  }
  const branch = (id: string): ProfileTreeItem | null => {
    const category = groups.get(id)
    if (!category || visited.has(id)) return null
    visited.add(id)
    const children = [
      ...categories.filter(item => item.parent_id === id).map(item => branch(item.id)),
      ...points.filter(item => item.parent_id === id).map(point),
    ].filter((item): item is ProfileTreeItem => item !== null)
    if (!children.length) return null
    return { id: `branch:${id}`, sourceId: id, kind: 'branch', label: category.name,
      progress: null, count: children.reduce((total, child) => total + child.count, 0), children }
  }
  const children = categories.filter(item => !item.parent_id || !groups.has(item.parent_id))
    .map(item => branch(item.id)).filter((item): item is ProfileTreeItem => item !== null)
  children.push(...points.map(point).filter((item): item is ProfileTreeItem => item !== null))
  return { id: `course:${courseId}`, sourceId: courseId, kind: 'course', label: title,
    progress: null, count: placed.size, children }
}

export function filterKnowledgeTree(root: ProfileTreeItem, query: string): ProfileTreeItem {
  const search = query.trim().toLocaleLowerCase()
  if (!search) return root
  const filter = (item: ProfileTreeItem): ProfileTreeItem | null => {
    if (item.kind === 'knowledge') return (item.searchText || item.label).toLocaleLowerCase().includes(search) ? item : null
    const children = item.children.map(filter).filter((child): child is ProfileTreeItem => child !== null)
    return children.length || (item.pending && item.label.toLocaleLowerCase().includes(search)) ? { ...item, children } : null
  }
  return { ...root, children: root.children.map(filter).filter((item): item is ProfileTreeItem => item !== null) }
}

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
    if (!children.length && !(current.pending && (!search || current.name.toLocaleLowerCase().includes(search)))) return null
    return { id: `branch:${id}`, sourceId: id, kind: 'branch', label: current.name,
      progress: current.summary.assessed_count ? current.summary.verified_progress : null, count: current.summary.total_count, pending: current.pending, children }
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
