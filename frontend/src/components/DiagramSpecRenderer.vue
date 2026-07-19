<template>
  <div class="diagram-spec-renderer" :data-render-state="layout.ok ? 'ready' : 'degraded'">
    <svg
      v-if="layout.ok"
      class="diagram-svg"
      data-testid="diagram-svg"
      :viewBox="`0 0 ${layout.width} ${layout.height}`"
      :width="layout.width"
      :height="layout.height"
      role="img"
      :aria-label="resolvedTitle"
      xmlns="http://www.w3.org/2000/svg"
    >
      <title>{{ resolvedTitle }}</title>
      <g class="diagram-edges">
        <g
          v-for="edge in layout.edges"
          :key="edge.id"
          class="diagram-edge"
          :data-edge-id="edge.id"
          :data-relation="edge.relation"
        >
          <line :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" />
          <text class="diagram-edge-label" :x="edge.labelX" :y="edge.labelY">{{ edge.label }}</text>
        </g>
      </g>
      <g class="diagram-nodes">
        <g
          v-for="node in layout.nodes"
          :key="node.id"
          class="diagram-node"
          :data-node-id="node.id"
          :data-kind="node.kind"
        >
          <rect :x="node.x" :y="node.y" :width="NODE_WIDTH" :height="NODE_HEIGHT" rx="10" ry="10" />
          <text class="diagram-node-label" :x="node.textX" :y="node.textY">{{ node.label }}</text>
        </g>
      </g>
    </svg>

    <div v-else class="diagram-fallback" role="note" data-testid="diagram-fallback">
      <strong>{{ t('teachingRepresentations.diagram.fallback', '图解暂时无法渲染') }}</strong>
      <span class="diagram-fallback-reason" data-testid="diagram-fallback-reason" :data-reason="layout.reason">
        {{ reasonText(layout.reason) }}
      </span>
      <ul v-if="layout.items.length" class="diagram-fallback-list" data-testid="diagram-fallback-list">
        <li v-for="item in layout.items" :key="item.key">{{ item.text }}</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'

/** Rendering limits; exceeding them degrades instead of producing an unreadable graph. */
const MAX_NODES = 40
const MAX_LABEL_CHARS = 28
const NODE_WIDTH = 220
const NODE_HEIGHT = 52
const ROW_GAP = 26
const COLUMN_GAP = 140
const PADDING = 20

const KNOWN_DIAGRAM_KINDS = ['concept_map', 'learning_path']

/** 关系类型是有限字面量集合，因此每条合法边必定有标签（label 必填，无需可选）。 */
type KnownRelation = 'supports' | 'prepares'
const RELATION_LABELS: Record<KnownRelation, string> = { supports: '支撑', prepares: '承接' }

function isKnownRelation(value: string): value is KnownRelation {
  return value === 'supports' || value === 'prepares'
}

type FallbackReason =
  | 'missing_spec'
  | 'invalid_nodes'
  | 'too_many_nodes'
  | 'unknown_diagram_kind'
  | 'invalid_edges'

interface LayoutNode {
  id: string
  kind: string
  label: string
  x: number
  y: number
  textX: number
  textY: number
}

interface LayoutEdge {
  id: string
  relation: KnownRelation
  label: string
  x1: number
  y1: number
  x2: number
  y2: number
  labelX: number
  labelY: number
}

interface FallbackItem { key: string, text: string }

type Layout =
  | { ok: true, width: number, height: number, nodes: LayoutNode[], edges: LayoutEdge[] }
  | { ok: false, reason: FallbackReason, items: FallbackItem[] }

const props = withDefaults(defineProps<{
  /** A single DiagramSpec unit (diagram_spec_v1 / diagram_compiler_v1). */
  unit?: unknown
  title?: string
}>(), {
  unit: undefined,
  title: '',
})

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  return typeof value === 'string' ? value : ''
}

function truncate(label: string): string {
  const flat = label.replace(/\s+/g, ' ').trim()
  return flat.length > MAX_LABEL_CHARS ? `${flat.slice(0, MAX_LABEL_CHARS)}…` : flat
}

const unitRecord = computed<Record<string, unknown> | null>(() => (isRecord(props.unit) ? props.unit : null))

const resolvedTitle = computed(() => {
  if (props.title) return props.title
  const fromUnit = unitRecord.value ? readString(unitRecord.value, 'title') : ''
  return fromUnit || t('teachingRepresentations.diagram.defaultTitle', '课程知识图解')
})

/** Fallback list is built from whatever readable text survives; always plain text, never HTML. */
function fallbackItems(unit: Record<string, unknown> | null): FallbackItem[] {
  if (!unit) return []
  const nodes = Array.isArray(unit.nodes) ? unit.nodes : []
  const items: FallbackItem[] = []
  nodes.forEach((node, index) => {
    if (!isRecord(node)) return
    const label = readString(node, 'label') || readString(node, 'node_id')
    if (!label) return
    items.push({ key: `node-${index}`, text: label })
  })
  return items
}

function reasonText(reason: FallbackReason): string {
  const table: Record<FallbackReason, string> = {
    missing_spec: '图解数据缺失或结构不符，已降级为文本列表。',
    invalid_nodes: '图解节点缺失、字段类型不符或存在重复 id，已降级为文本列表。',
    too_many_nodes: `图解节点数超过 ${MAX_NODES} 个上限，已降级为文本列表。`,
    unknown_diagram_kind: '图解类型未知，无法确定渲染方式，已降级为文本列表。',
    invalid_edges: '图解关系指向了不存在的节点或字段不符，已降级为文本列表。',
  }
  return t(`teachingRepresentations.diagram.reason.${reason}`, table[reason])
}

const layout = computed<Layout>(() => {
  const unit = unitRecord.value
  const items = fallbackItems(unit)
  const degrade = (reason: FallbackReason): Layout => ({ ok: false, reason, items })

  if (!unit) return degrade('missing_spec')

  const rawKind = unit.diagram_kind
  if (rawKind !== undefined && (typeof rawKind !== 'string' || !KNOWN_DIAGRAM_KINDS.includes(rawKind))) {
    return degrade('unknown_diagram_kind')
  }

  const rawNodes = unit.nodes
  if (!Array.isArray(rawNodes) || rawNodes.length === 0) return degrade('invalid_nodes')
  if (rawNodes.length > MAX_NODES) return degrade('too_many_nodes')

  const seen = new Set<string>()
  const parsedNodes: Array<{ nodeId: string, kind: string, label: string }> = []
  for (const raw of rawNodes) {
    if (!isRecord(raw)) return degrade('invalid_nodes')
    const nodeId = readString(raw, 'node_id')
    const label = readString(raw, 'label')
    if (!nodeId || !label || seen.has(nodeId)) return degrade('invalid_nodes')
    seen.add(nodeId)
    parsedNodes.push({ nodeId, kind: readString(raw, 'kind') || 'knowledge', label })
  }

  const rawEdges = unit.edges === undefined ? [] : unit.edges
  if (!Array.isArray(rawEdges)) return degrade('invalid_edges')
  const parsedEdges: Array<{ edgeId: string, source: string, target: string, relation: KnownRelation }> = []
  for (const raw of rawEdges) {
    if (!isRecord(raw)) return degrade('invalid_edges')
    const source = readString(raw, 'source_node_id')
    const target = readString(raw, 'target_node_id')
    const relation = readString(raw, 'relation')
    if (!seen.has(source) || !seen.has(target)) return degrade('invalid_edges')
    if (!isKnownRelation(relation)) return degrade('invalid_edges')
    const edgeId = readString(raw, 'edge_id') || `${source}->${target}:${relation}`
    parsedEdges.push({ edgeId, source, target, relation })
  }

  // Deterministic two-column layout: objective nodes on the left, content nodes on the right,
  // every coordinate derived from the node's index inside the spec — no randomness, no clock.
  const objectives = parsedNodes.filter(node => node.kind === 'objective')
  const contents = parsedNodes.filter(node => node.kind !== 'objective')
  const columns = objectives.length ? [objectives, contents] : [contents]
  const rowCount = Math.max(...columns.map(column => column.length), 1)

  const width = PADDING * 2 + columns.length * NODE_WIDTH + (columns.length - 1) * COLUMN_GAP
  const height = PADDING * 2 + rowCount * NODE_HEIGHT + (rowCount - 1) * ROW_GAP

  const positions = new Map<string, { x: number, y: number }>()
  const nodes: LayoutNode[] = []
  columns.forEach((column, columnIndex) => {
    const x = PADDING + columnIndex * (NODE_WIDTH + COLUMN_GAP)
    column.forEach((node, rowIndex) => {
      const y = PADDING + rowIndex * (NODE_HEIGHT + ROW_GAP)
      positions.set(node.nodeId, { x, y })
      nodes.push({
        id: node.nodeId,
        kind: node.kind,
        label: truncate(node.label),
        x,
        y,
        textX: x + NODE_WIDTH / 2,
        textY: y + NODE_HEIGHT / 2 + 5,
      })
    })
  })

  const edges: LayoutEdge[] = []
  for (const edge of parsedEdges) {
    const from = positions.get(edge.source)
    const to = positions.get(edge.target)
    // 端点已按节点集合校验过，这里再守一次以免布局阶段出现未定位节点。
    if (!from || !to) return degrade('invalid_edges')
    const sameColumn = from.x === to.x
    const x1 = sameColumn ? from.x + NODE_WIDTH / 2 : from.x + NODE_WIDTH
    const y1 = sameColumn ? from.y + NODE_HEIGHT : from.y + NODE_HEIGHT / 2
    const x2 = sameColumn ? to.x + NODE_WIDTH / 2 : to.x
    const y2 = sameColumn ? to.y : to.y + NODE_HEIGHT / 2
    edges.push({
      id: edge.edgeId,
      relation: edge.relation,
      label: RELATION_LABELS[edge.relation],
      x1,
      y1,
      x2,
      y2,
      labelX: (x1 + x2) / 2,
      labelY: (y1 + y2) / 2 - 4,
    })
  }

  return { ok: true, width, height, nodes, edges }
})
</script>

<style scoped>
.diagram-spec-renderer { min-height:180px; }
.diagram-svg { width:100%; height:auto; max-height:440px; padding:12px; border:1px solid #e8eaf2; border-radius:12px; background:#fbfcff; }
.diagram-node rect { fill:#fff; stroke:#c7d2fe; stroke-width:1.5; }
.diagram-node[data-kind='objective'] rect { fill:#eef2ff; stroke:#818cf8; }
.diagram-node-label { font:12px/1.4 ui-sans-serif,system-ui,sans-serif; fill:#1f2937; text-anchor:middle; }
.diagram-edge line { stroke:#cbd5e1; stroke-width:1.5; }
.diagram-edge-label { font:10px/1.4 ui-sans-serif,system-ui,sans-serif; fill:#94a3b8; text-anchor:middle; }
.diagram-fallback { display:grid; gap:7px; padding:14px; border:1px dashed #f3c878; border-radius:10px; color:#92400e; background:#fffbeb; }
.diagram-fallback strong { font-size:12px; }
.diagram-fallback-reason { font-size:10px; }
.diagram-fallback-list { margin:0; padding-left:18px; color:#475569; font-size:11px; line-height:1.7; }
</style>
