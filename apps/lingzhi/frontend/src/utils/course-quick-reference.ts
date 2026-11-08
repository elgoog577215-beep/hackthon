import type { Node } from '../stores/types'

export type CourseReferenceKind = 'definition' | 'formula' | 'law' | 'theorem'

export interface CourseQuickReferenceItem {
  id: string
  kind: CourseReferenceKind
  title: string
  summary: string
  expression?: string
  nodeId: string
  nodeName: string
  blockId: string
}

type Marker = {
  marker_id?: unknown
  kind?: unknown
  heading?: unknown
  expression?: unknown
}

const KINDS = new Set<CourseReferenceKind>(['definition', 'formula', 'law', 'theorem'])

function conciseText(value: unknown): string {
  return String(value || '')
    .replace(/^#{1,6}\s+.*$/gm, '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\$\$[\s\S]*?\$\$/g, ' ')
    .replace(/\\\[[\s\S]*?\\\]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function safeMarkers(value: unknown): Marker[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is Marker => Boolean(
    item && typeof item === 'object' && KINDS.has(String((item as Marker).kind) as CourseReferenceKind),
  ))
}

/** Build the all-course reference list from the same blocks rendered in the lecture. */
export function collectCourseQuickReferences(nodes: Node[]): CourseQuickReferenceItem[] {
  const items: CourseQuickReferenceItem[] = []
  for (const node of nodes) {
    const legacy = new Map((node.content_blocks || []).map(block => [block.block_id, block]))
    const blocks = node.course_blocks?.length
      ? node.course_blocks.map(block => {
          const title = String(block.payload.title || '')
          const content = String(block.payload.markdown || block.payload.text || block.payload.formula || block.payload.expression || '')
          const previous = legacy.get(block.block_id)
          let markers = safeMarkers(block.payload.knowledge_markers)
          if (!markers.length) markers = safeMarkers(previous?.metadata?.knowledge_markers)
          if (!markers.length && block.kind === 'formula') {
            markers = [{ marker_id: `${block.block_id}:formula`, kind: 'formula', heading: title || '公式', expression: block.payload.formula || block.payload.expression }]
          }
          return {
            blockId: block.block_id,
            title,
            content,
            summary: String(block.payload.summary || previous?.summary || ''),
            markers,
            status: block.status,
          }
        })
      : (node.content_blocks || []).map(block => ({
          blockId: block.block_id,
          title: block.title,
          content: block.content,
          summary: block.summary || '',
          markers: safeMarkers(block.metadata?.knowledge_markers),
          status: block.status || 'final',
        }))

    for (const block of blocks) {
      if (block.status === 'draft' || block.status === 'retired') continue
      block.markers.forEach((marker, markerIndex) => {
        const kind = String(marker.kind) as CourseReferenceKind
        const heading = String(marker.heading || '').replace(/^#{1,6}\s+/, '').trim()
        const title = heading || block.title || (kind === 'formula' ? '公式' : '知识条目')
        const expression = String(marker.expression || '').trim()
        const summary = conciseText(block.summary || block.content)
        items.push({
          id: `${node.node_id}:${block.blockId}:${String(marker.marker_id || markerIndex)}`,
          kind,
          title,
          summary,
          ...(expression ? { expression } : {}),
          nodeId: node.node_id,
          nodeName: node.node_name,
          blockId: block.blockId,
        })
      })
    }
  }
  return items
}
