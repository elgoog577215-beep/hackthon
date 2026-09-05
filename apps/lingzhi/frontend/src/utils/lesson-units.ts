import type { Node } from '../stores/types'

const ROOT_IDS = new Set(['', 'root'])

/**
 * Teacher-facing lesson units are outline chapters, not every generated
 * content node. Preserve source order so existing node ids and deep links stay
 * stable while the UI projects one chapter as one lecture.
 */
export function projectLessonUnits(nodes: Node[]): Node[] {
  const topLevel = nodes.filter(node => (
    node.node_level === 1
    && ROOT_IDS.has(String(node.parent_node_id || '').toLowerCase())
  ))
  if (topLevel.length) return topLevel

  const nodeIds = new Set(nodes.map(node => node.node_id))
  const graphRoots = nodes.filter(node => !nodeIds.has(String(node.parent_node_id || '')))
  if (graphRoots.length) return graphRoots

  const minimumLevel = Math.min(...nodes.map(node => Number(node.node_level || 0)))
  return nodes.filter(node => Number(node.node_level || 0) === minimumLevel)
}

export function lessonUnitMembers(nodes: Node[], lessonUnitId: string): Node[] {
  if (!lessonUnitId) return []
  const childrenByParent = new Map<string, Node[]>()
  for (const node of nodes) {
    const parentId = String(node.parent_node_id || '')
    childrenByParent.set(parentId, [...(childrenByParent.get(parentId) || []), node])
  }

  const result: Node[] = []
  const queue = [...(childrenByParent.get(lessonUnitId) || [])]
  const visited = new Set<string>()
  while (queue.length) {
    const node = queue.shift()!
    if (visited.has(node.node_id)) continue
    visited.add(node.node_id)
    result.push(node)
    queue.push(...(childrenByParent.get(node.node_id) || []))
  }
  return result
}

/**
 * Return the ordered, directly addressable sections inside one teacher lesson.
 * Deeper knowledge nodes remain section content and do not become pager items.
 */
export function lessonUnitSections(nodes: Node[], lessonUnitId: string): Node[] {
  if (!lessonUnitId) return []
  return nodes.filter(node => String(node.parent_node_id || '') === lessonUnitId)
}

export function resolveLessonSection(
  nodes: Node[],
  lessonUnitId: string,
  requestedSectionId = '',
): Node | undefined {
  const sections = lessonUnitSections(nodes, lessonUnitId)
  return sections.find(section => section.node_id === requestedSectionId) || sections[0]
}

export function resolveLessonUnit(nodes: Node[], nodeId: string): Node | undefined {
  const units = projectLessonUnits(nodes)
  const direct = units.find(node => node.node_id === nodeId)
  if (direct) return direct

  const byId = new Map(nodes.map(node => [node.node_id, node]))
  const unitIds = new Set(units.map(node => node.node_id))
  const visited = new Set<string>()
  let current = byId.get(nodeId)
  while (current && !visited.has(current.node_id)) {
    if (unitIds.has(current.node_id)) return current
    visited.add(current.node_id)
    current = byId.get(String(current.parent_node_id || ''))
  }
  return undefined
}

export function lessonUnitHasContent(nodes: Node[], lessonUnit: Node): boolean {
  return [lessonUnit, ...lessonUnitMembers(nodes, lessonUnit.node_id)].some(node => (
    Boolean(node.node_content)
    || Boolean(node.content_blocks?.some(block => Boolean(block.content)))
    || node.generation_status === 'completed'
  ))
}

export function lessonUnitPreviewMarkdown(nodes: Node[], lessonUnit: Node): string {
  const members = lessonUnitMembers(nodes, lessonUnit.node_id)
  const knowledgeItems = members
    .filter(node => node.node_level === lessonUnit.node_level + 1 || !members.some(candidate => candidate.parent_node_id === node.node_id))
    .map(node => node.node_name)
    .filter(Boolean)
  const objectives = [lessonUnit, ...members]
    .map(node => String(node.learning_objective || '').trim())
    .filter(Boolean)

  const sections = [
    '## 本讲备课范围',
    knowledgeItems.length
      ? knowledgeItems.slice(0, 8).map(item => `- ${item}`).join('\n')
      : `- ${lessonUnit.node_name}`,
  ]
  if (objectives.length) {
    sections.push('## 本讲教学目标', objectives.slice(0, 5).map(item => `- ${item}`).join('\n'))
  }
  sections.push(
    '## 当前资产',
    `- 教案：${lessonUnitHasContent(nodes, lessonUnit) ? '已有当前内容，可继续编辑' : '等待生成'}`,
    '- PPT：本讲教案和讲义当前可用后可独立制作',
    '- 学生版：只读取已发布快照',
  )
  return sections.join('\n\n')
}
