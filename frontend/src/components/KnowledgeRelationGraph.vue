<template>
  <section
    class="knowledge-relation-graph"
    data-testid="knowledge-relation-graph"
    :aria-label="t('knowledgeLibrary.graphTitle', '知识关系图')"
  >
    <header class="knowledge-relation-graph__header">
      <div>
        <Network :size="17" aria-hidden="true" />
        <strong>{{ t('knowledgeLibrary.graphTitle', '知识关系图') }}</strong>
        <span>
          {{ graphNodes.length }} {{ t('knowledgeLibrary.graphPoints', '个关系节点') }}
          · {{ validRelations.length }} {{ t('knowledgeLibrary.graphRelations', '条已启用关系') }}
        </span>
      </div>
      <span class="knowledge-relation-graph__readonly">
        <LockKeyhole :size="12" aria-hidden="true" />
        {{ t('knowledgeLibrary.graphReadonly', '只读 · 来自当前知识库版本') }}
      </span>
    </header>

    <div v-if="graphNodes.length" class="knowledge-relation-graph__body">
      <div class="knowledge-relation-graph__canvas">
        <div class="knowledge-relation-graph__viewport">
          <svg
            :viewBox="`0 0 ${CANVAS_WIDTH} ${canvasHeight}`"
            role="img"
            :aria-label="t('knowledgeLibrary.graphAriaLabel', '当前课程知识点之间的已启用关系')"
          >
            <defs>
              <marker
                id="knowledge-graph-arrow"
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path class="knowledge-relation-graph__arrow" d="M 0 0 L 8 4 L 0 8 z" />
              </marker>
            </defs>

            <g
              v-for="edge in positionedRelations"
              :key="edge.relation.relation_id"
              class="knowledge-relation-graph__edge"
              :class="`is-${edge.relation.relation_type}`"
              data-testid="knowledge-graph-edge"
              :data-relation-id="edge.relation.relation_id"
            >
              <title>{{ edge.relation.reason || relationTypeLabel(edge.relation.relation_type) }}</title>
              <path :d="edge.path" marker-end="url(#knowledge-graph-arrow)" />
              <text :x="edge.labelX" :y="edge.labelY">
                {{ relationTypeLabel(edge.relation.relation_type) }}
              </text>
            </g>

            <g
              v-for="item in positionedNodes"
              :key="item.node.knowledge_id"
              class="knowledge-relation-graph__node"
              :class="{
                'is-selected': selectedId === item.node.knowledge_id,
                'is-covered': item.node.covered_by_course,
              }"
              :transform="`translate(${item.x} ${item.y})`"
              role="button"
              tabindex="0"
              :aria-label="`${nodeTypeLabel(item.node.node_type)}：${item.node.name}`"
              :aria-pressed="selectedId === item.node.knowledge_id"
              :data-knowledge-id="item.node.knowledge_id"
              @click="emit('select', item.node)"
              @keydown.enter.prevent="emit('select', item.node)"
              @keydown.space.prevent="emit('select', item.node)"
            >
              <title>{{ item.node.name }}</title>
              <rect :width="NODE_WIDTH" :height="NODE_HEIGHT" rx="12" />
              <circle cx="19" cy="20" r="5" />
              <text class="knowledge-relation-graph__node-type" x="31" y="24">
                {{ nodeTypeLabel(item.node.node_type) }}
              </text>
              <text class="knowledge-relation-graph__node-name" x="16" y="48">
                {{ compactName(item.node.name) }}
              </text>
              <path
                v-if="item.node.covered_by_course"
                class="knowledge-relation-graph__covered"
                :d="`M ${NODE_WIDTH - 24} 17 l 4 4 7 -8`"
              />
            </g>
          </svg>
        </div>
      </div>

      <aside class="knowledge-relation-graph__inspector" aria-live="polite">
        <template v-if="selectedGraphNode">
          <span class="knowledge-relation-graph__eyebrow">
            {{ nodeTypeLabel(selectedGraphNode.node_type) }}
          </span>
          <h2>{{ selectedGraphNode.name }}</h2>
          <p v-if="selectedGraphNode.description">{{ selectedGraphNode.description }}</p>

          <h3>{{ t('knowledgeLibrary.graphConnectedRelations', '关联关系') }}</h3>
          <div v-if="selectedConnections.length" class="knowledge-relation-graph__connections">
            <article v-for="entry in selectedConnections" :key="entry.relation.relation_id">
              <span>{{ relationTypeLabel(entry.relation.relation_type) }}</span>
              <strong>{{ entry.otherNode.name }}</strong>
              <p v-if="entry.relation.reason">{{ entry.relation.reason }}</p>
            </article>
          </div>
          <p v-else class="knowledge-relation-graph__no-connections">
            {{ t('knowledgeLibrary.graphNoSelectedRelations', '该知识点暂无已启用关系') }}
          </p>
        </template>
        <div v-else class="knowledge-relation-graph__selection-hint">
          <MousePointerClick :size="22" aria-hidden="true" />
          <strong>{{ t('knowledgeLibrary.graphSelectPoint', '选择图中的知识点') }}</strong>
          <span>{{ t('knowledgeLibrary.graphSelectPointHint', '可查看关系方向、对象和建立理由') }}</span>
        </div>
      </aside>
    </div>

    <div v-else class="knowledge-relation-graph__empty">
      <Network :size="26" aria-hidden="true" />
      <strong>{{ t('knowledgeLibrary.graphEmpty', '当前版本还没有已启用的知识关系') }}</strong>
      <span>{{ t('knowledgeLibrary.graphEmptyHint', '知识树仍可正常使用，关系会在通过质量审核后显示') }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { LockKeyhole, MousePointerClick, Network } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type {
  KnowledgeNode,
  KnowledgeNodeType,
  KnowledgeRelation,
} from '../types/knowledge-library'

const props = defineProps<{
  nodes: KnowledgeNode[]
  relations: KnowledgeRelation[]
  selectedId?: string | null
}>()

const emit = defineEmits<{
  select: [node: KnowledgeNode]
}>()

const CANVAS_WIDTH = 1000
const NODE_WIDTH = 188
const NODE_HEIGHT = 66
const ROW_GAP = 128
const TOP_PADDING = 64

const nodeById = computed(() => new Map(
  props.nodes.map(node => [node.knowledge_id, node]),
))

const validRelations = computed(() => props.relations.filter(relation => (
  relation.status === 'accepted'
  && nodeById.value.has(relation.source_knowledge_id)
  && nodeById.value.has(relation.target_knowledge_id)
)))

const graphNodes = computed(() => props.nodes
  .filter(node => (
    node.node_type === 'knowledge_point'
    && node.status !== 'retired'
  ))
  .sort((left, right) => (
    left.depth - right.depth
    || left.sort_order - right.sort_order
    || left.name.localeCompare(right.name)
  )))

const columnCount = computed(() => Math.min(4, Math.max(2, Math.ceil(Math.sqrt(graphNodes.value.length)))))
const rowCount = computed(() => Math.max(1, Math.ceil(graphNodes.value.length / columnCount.value)))
const canvasHeight = computed(() => Math.max(340, TOP_PADDING * 2 + NODE_HEIGHT + (rowCount.value - 1) * ROW_GAP))

const positionedNodes = computed(() => {
  const columns = columnCount.value
  const usableWidth = CANVAS_WIDTH - (2 * TOP_PADDING) - NODE_WIDTH
  const columnGap = columns > 1 ? usableWidth / (columns - 1) : 0
  return graphNodes.value.map((node, index) => ({
    node,
    x: TOP_PADDING + (index % columns) * columnGap,
    y: TOP_PADDING + Math.floor(index / columns) * ROW_GAP,
  }))
})

const positionById = computed(() => new Map(
  positionedNodes.value.map(item => [item.node.knowledge_id, item]),
))

const graphNodeById = computed(() => new Map(
  graphNodes.value.map(node => [node.knowledge_id, node]),
))

const positionedRelations = computed(() => validRelations.value.flatMap(relation => {
  const source = positionById.value.get(relation.source_knowledge_id)
  const target = positionById.value.get(relation.target_knowledge_id)
  if (!source || !target) return []

  const sourceCenterX = source.x + NODE_WIDTH / 2
  const sourceCenterY = source.y + NODE_HEIGHT / 2
  const targetCenterX = target.x + NODE_WIDTH / 2
  const targetCenterY = target.y + NODE_HEIGHT / 2
  const sameRow = Math.abs(source.y - target.y) < 2
  const leftToRight = sourceCenterX <= targetCenterX
  const startX = sameRow
    ? source.x + (leftToRight ? NODE_WIDTH : 0)
    : sourceCenterX
  const startY = sameRow
    ? sourceCenterY
    : source.y + (sourceCenterY <= targetCenterY ? NODE_HEIGHT : 0)
  const endX = sameRow
    ? target.x + (leftToRight ? 0 : NODE_WIDTH)
    : targetCenterX
  const endY = sameRow
    ? targetCenterY
    : target.y + (sourceCenterY <= targetCenterY ? 0 : NODE_HEIGHT)
  const labelX = (startX + endX) / 2
  const labelY = sameRow ? startY - 25 : (startY + endY) / 2 - 8
  const path = sameRow
    ? `M ${startX} ${startY} C ${labelX} ${startY - 46}, ${labelX} ${endY - 46}, ${endX} ${endY}`
    : `M ${startX} ${startY} C ${startX} ${labelY}, ${endX} ${labelY}, ${endX} ${endY}`

  return [{ relation, path, labelX, labelY }]
}))

const selectedGraphNode = computed(() => (
  props.selectedId ? graphNodeById.value.get(props.selectedId) || null : null
))

const selectedConnections = computed(() => {
  if (!selectedGraphNode.value) return []
  const selectedId = selectedGraphNode.value.knowledge_id
  return validRelations.value.flatMap(relation => {
    const outgoing = relation.source_knowledge_id === selectedId
    const incoming = relation.target_knowledge_id === selectedId
    if (!outgoing && !incoming) return []
    const otherId = outgoing ? relation.target_knowledge_id : relation.source_knowledge_id
    const otherNode = nodeById.value.get(otherId)
    return otherNode ? [{ relation, otherNode }] : []
  })
})

function compactName(name: string): string {
  const limit = /[\u3400-\u9fff]/.test(name) ? 12 : 22
  return name.length > limit ? `${name.slice(0, limit)}…` : name
}

function nodeTypeLabel(type: KnowledgeNodeType): string {
  const labels: Record<string, string> = {
    course: t('knowledgeLibrary.typeCourse', '课程'),
    chapter: t('knowledgeLibrary.typeChapter', '章节'),
    section: t('knowledgeLibrary.typeSection', '小节'),
    concept_group: t('knowledgeLibrary.typeConceptGroup', '概念组'),
    knowledge_point: t('knowledgeLibrary.typePoint', '原子知识点'),
  }
  return labels[type] || t('knowledgeLibrary.typeConcept', '知识概念')
}

function relationTypeLabel(type: KnowledgeRelation['relation_type']): string {
  const labels: Record<string, string> = {
    prerequisite: t('knowledgeLibrary.prerequisite', '前置知识'),
    derives: t('knowledgeLibrary.derives', '推导关系'),
    equivalent_to: t('knowledgeLibrary.equivalent', '等价关系'),
    contrasts_with: t('knowledgeLibrary.contrasts', '对比辨析'),
    applies_to: t('knowledgeLibrary.applies', '应用关系'),
    generalizes: t('knowledgeLibrary.generalizes', '一般化关系'),
    related: t('knowledgeLibrary.related', '相关知识'),
    application: t('knowledgeLibrary.applies', '应用关系'),
    confusable: t('knowledgeLibrary.confusable', '易混淆'),
  }
  return labels[type] || type
}
</script>

<style scoped>
.knowledge-relation-graph { min-width:0; min-height:0; flex:1; display:flex; flex-direction:column; overflow:hidden; color:#41475e; background:#fff; }
.knowledge-relation-graph__header { min-height:48px; flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:0 18px; border-bottom:1px solid #e8eaf2; background:#fbfbfe; }
.knowledge-relation-graph__header > div { min-width:0; display:flex; align-items:center; gap:7px; }
.knowledge-relation-graph__header svg { color:#6b50e8; }
.knowledge-relation-graph__header strong { color:#343a52; font-size:12px; }
.knowledge-relation-graph__header span { color:#8a90a4; font-size:10px; }
.knowledge-relation-graph__readonly { flex:0 0 auto; display:inline-flex; align-items:center; gap:5px; padding:5px 8px; border:1px solid #e2e4ed; border-radius:8px; color:#777e94 !important; background:#fff; font-weight:650; }
.knowledge-relation-graph__readonly svg { color:#8f95a8; }
.knowledge-relation-graph__body { min-height:0; flex:1; display:grid; grid-template-columns:minmax(0,1fr) 286px; overflow:hidden; }
.knowledge-relation-graph__canvas { min-width:0; min-height:0; overflow:auto; padding:18px; background-color:#fafbfe; background-image:radial-gradient(#dfe2ee 1px, transparent 1px); background-size:18px 18px; }
.knowledge-relation-graph__viewport { min-width:720px; min-height:100%; display:flex; align-items:center; }
.knowledge-relation-graph__viewport svg { width:100%; height:auto; min-height:360px; overflow:visible; }
.knowledge-relation-graph__edge path { fill:none; stroke:#9b90d8; stroke-width:2; }
.knowledge-relation-graph__edge text { fill:#7c729f; paint-order:stroke; stroke:#fafbfe; stroke-width:7px; stroke-linejoin:round; font-size:12px; font-weight:700; text-anchor:middle; }
.knowledge-relation-graph__arrow { fill:#8c80ce; stroke:none; }
.knowledge-relation-graph__edge.is-contrasts_with path { stroke:#d48b72; stroke-dasharray:6 4; }
.knowledge-relation-graph__edge.is-equivalent_to path { stroke:#4f9b82; }
.knowledge-relation-graph__edge.is-applies_to path { stroke:#4d7db7; }
.knowledge-relation-graph__node { outline:none; cursor:pointer; }
.knowledge-relation-graph__node rect { fill:#fff; stroke:#dfe2ec; stroke-width:1.5; filter:drop-shadow(0 5px 10px rgba(54,59,91,.08)); transition:fill .15s ease, stroke .15s ease, stroke-width .15s ease; }
.knowledge-relation-graph__node circle { fill:#a8aebe; }
.knowledge-relation-graph__node-type { fill:#858ba0; font-size:10px; font-weight:650; }
.knowledge-relation-graph__node-name { fill:#3b4158; font-size:13px; font-weight:750; }
.knowledge-relation-graph__node:hover rect, .knowledge-relation-graph__node:focus-visible rect { fill:#f7f5ff; stroke:#9e90ef; }
.knowledge-relation-graph__node:focus-visible rect { stroke-width:3; }
.knowledge-relation-graph__node.is-covered circle { fill:#4b9a75; }
.knowledge-relation-graph__node.is-selected rect { fill:#f2efff; stroke:#6d50e8; stroke-width:2.5; }
.knowledge-relation-graph__node.is-selected circle { fill:#6d50e8; }
.knowledge-relation-graph__covered { fill:none; stroke:#4b9a75; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.knowledge-relation-graph__inspector { min-width:0; overflow:auto; padding:24px 20px; border-left:1px solid #e7e9f2; background:#fff; }
.knowledge-relation-graph__eyebrow { color:#6c52dc; font-size:10px; font-weight:750; }
.knowledge-relation-graph__inspector h2 { margin:5px 0 0; color:#2f354d; font-size:18px; line-height:1.4; overflow-wrap:anywhere; }
.knowledge-relation-graph__inspector > p { margin:10px 0 0; color:#737a90; font-size:11px; line-height:1.7; }
.knowledge-relation-graph__inspector h3 { margin:24px 0 10px; color:#4c5269; font-size:11px; }
.knowledge-relation-graph__connections { display:grid; gap:8px; }
.knowledge-relation-graph__connections article { padding:10px; border:1px solid #e4e6ef; border-radius:9px; background:#fbfbfd; }
.knowledge-relation-graph__connections span { color:#735fd2; font-size:9.5px; font-weight:700; }
.knowledge-relation-graph__connections strong { display:block; margin-top:3px; color:#454b62; font-size:11px; line-height:1.45; }
.knowledge-relation-graph__connections p { margin:5px 0 0; color:#7a8094; font-size:10px; line-height:1.55; }
.knowledge-relation-graph__no-connections { color:#989daf !important; }
.knowledge-relation-graph__selection-hint, .knowledge-relation-graph__empty { height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:7px; color:#969caf; text-align:center; }
.knowledge-relation-graph__selection-hint strong, .knowledge-relation-graph__empty strong { color:#535a71; font-size:12px; }
.knowledge-relation-graph__selection-hint span, .knowledge-relation-graph__empty span { max-width:360px; color:#9298ab; font-size:10.5px; line-height:1.6; }
.knowledge-relation-graph__empty { flex:1; padding:32px; }
.knowledge-relation-graph__empty svg { color:#7962df; }

@media (max-width:900px) {
  .knowledge-relation-graph__body { grid-template-columns:minmax(0,1fr) 240px; }
}

@media (max-width:700px) {
  .knowledge-relation-graph__header { align-items:flex-start; flex-direction:column; justify-content:center; gap:5px; padding-block:8px; }
  .knowledge-relation-graph__body { display:block; overflow:auto; }
  .knowledge-relation-graph__canvas { min-height:430px; overflow:auto; }
  .knowledge-relation-graph__inspector { min-height:220px; border-top:1px solid #e7e9f2; border-left:0; }
}
</style>
