<template>
  <figure
    v-if="visual"
    class="slide-visual"
    :data-kind="visual.kind"
    role="img"
    :aria-label="visual.alt_text || visual.purpose"
  >
    <img
      v-if="isImage && imageUrl"
      :src="imageUrl"
      :alt="visual.alt_text"
    />

    <svg
      v-else-if="visual.kind === 'relational_diagram'"
      viewBox="0 0 1000 560"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      <defs>
        <marker id="slide-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
          <path d="M0,0 L0,6 L9,3 z" class="slide-visual__arrow" />
        </marker>
      </defs>
      <line
        v-for="edge in diagramEdges"
        :key="`${edge.source}-${edge.target}`"
        :x1="edge.x1"
        :y1="edge.y1"
        :x2="edge.x2"
        :y2="edge.y2"
        marker-end="url(#slide-arrow)"
      />
      <g
        v-for="node in diagramNodes"
        :key="node.node_id"
        :transform="`translate(${node.x} ${node.y})`"
        :data-emphasis="node.emphasis || 'secondary'"
      >
        <rect :width="node.width" :height="node.height" rx="20" />
        <foreignObject x="18" y="14" :width="node.width - 36" :height="node.height - 28">
          <div xmlns="http://www.w3.org/1999/xhtml">{{ node.label }}</div>
        </foreignObject>
      </g>
    </svg>

    <svg
      v-else-if="visual.kind === 'coordinate_plot'"
      viewBox="0 0 1000 560"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      <line x1="90" y1="280" x2="920" y2="280" />
      <line x1="500" y1="60" x2="500" y2="500" />
      <circle
        v-for="(point, index) in plotPoints"
        :key="index"
        :cx="500 + Number(point[0]) * 92"
        :cy="280 - Number(point[1]) * 62"
        r="11"
      />
      <g
        v-for="(label, index) in plotLabels"
        :key="`${label.text}-${index}`"
        :transform="`translate(${label.x} ${label.y})`"
      >
        <rect width="330" height="104" rx="18" />
        <foreignObject x="18" y="14" width="294" height="76">
          <div xmlns="http://www.w3.org/1999/xhtml">{{ label.text }}</div>
        </foreignObject>
      </g>
      <text
        v-if="visual.parameters?.not_to_scale"
        x="900"
        y="530"
        text-anchor="end"
        class="slide-visual__scale-note"
      >概念位置不表示数值比例</text>
    </svg>

    <div v-else-if="visual.kind === 'chart'" class="slide-visual__chart">
      <div
        v-for="(value, index) in chartValues"
        :key="index"
        class="slide-visual__bar"
        :style="{ height: `${Math.max(8, value.ratio * 100)}%` }"
      >
        <b>{{ value.value }}</b><span>{{ value.label }}</span>
      </div>
    </div>

    <div v-else-if="visual.kind === 'formula'" class="slide-visual__symbol">
      <b>ƒ(x)</b><span>{{ visual.alt_text }}</span>
    </div>
    <div v-else-if="visual.kind === 'code'" class="slide-visual__symbol">
      <b>&lt;/&gt;</b><span>{{ visual.alt_text }}</span>
    </div>
    <div v-else-if="visual.kind === 'table'" class="slide-visual__table-wrap">
      <table v-if="tableRows.length">
        <thead>
          <tr><th v-for="header in tableHeaders" :key="header">{{ header }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in tableRows" :key="rowIndex">
            <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="slide-visual__symbol">
        <b>▦</b><span>{{ visual.alt_text }}</span>
      </div>
    </div>
    <div v-else class="slide-visual__fallback">
      <b>{{ visual.purpose }}</b>
      <span>{{ visual.alt_text }}</span>
    </div>

    <figcaption>{{ visual.alt_text }}</figcaption>
  </figure>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import http from '../utils/http'
import type { SlideVisual } from '../types/slideVisual'

const props = withDefaults(defineProps<{
  visuals: SlideVisual[]
  courseId?: string
  representationId?: string
}>(), {
  visuals: () => [],
  courseId: '',
  representationId: '',
})

const visual = computed(() => props.visuals?.[0])
const imageUrl = ref('')
const isImage = computed(() => ['source_image', 'generated_illustration'].includes(visual.value?.kind || ''))

const diagramNodes = computed(() => {
  const nodes = visual.value?.nodes || []
  const vertical = visual.value?.parameters?.direction === 'vertical'
  if (vertical) {
    const height = Math.min(88, 390 / Math.max(1, nodes.length))
    return nodes.map((node, index) => ({
      ...node,
      x: 150,
      y: 55 + index * (height + 22),
      width: 700,
      height,
    }))
  }
  const columns = nodes.length > 3 ? 2 : Math.max(1, nodes.length)
  const width = columns === 1 ? 720 : 360
  return nodes.map((node, index) => ({
    ...node,
    x: columns === 1 ? 140 : 95 + (index % 2) * 450,
    y: columns === 1 ? 210 : 65 + Math.floor(index / 2) * 170,
    width,
    height: columns === 1 ? 130 : 118,
  }))
})

const diagramEdges = computed(() => {
  const positions = new Map(diagramNodes.value.map(node => [node.node_id, node]))
  return (visual.value?.edges || []).flatMap(edge => {
    const source = positions.get(edge.source)
    const target = positions.get(edge.target)
    if (!source || !target) return []
    return [{
      ...edge,
      x1: source.x + source.width / 2,
      y1: source.y + source.height / 2,
      x2: target.x + target.width / 2,
      y2: target.y + target.height / 2,
    }]
  })
})

const plotPoints = computed(() => visual.value?.parameters?.points || [])
const plotLabels = computed(() => {
  const positions = [
    { x: 110, y: 80 },
    { x: 560, y: 80 },
    { x: 110, y: 360 },
    { x: 560, y: 360 },
  ]
  return (visual.value?.parameters?.labels || []).slice(0, 4).map(
    (label: string | { text?: string }, index: number) => ({
      text: typeof label === 'string' ? label : String(label?.text || ''),
      ...positions[index],
    }),
  )
})
const tableHeaders = computed(() => visual.value?.parameters?.headers || ['顺序', '课程原文要点'])
const tableRows = computed(() => visual.value?.parameters?.rows || [])

const chartValues = computed(() => {
  const labels = visual.value?.parameters?.categories || []
  const values = visual.value?.parameters?.series?.[0]?.values || []
  const maximum = Math.max(1, ...values.map((value: unknown) => Number(value) || 0))
  return values.map((value: unknown, index: number) => ({
    value: Number(value) || 0,
    label: String(labels[index] || index + 1),
    ratio: (Number(value) || 0) / maximum,
  }))
})

function revokeImage() {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = ''
}

async function loadImage() {
  revokeImage()
  const assetId = visual.value?.asset_id
  if (!isImage.value || !assetId || !props.courseId || !props.representationId) return
  const response = await http.get(
    `/api/courses/${props.courseId}/teaching-representations/${props.representationId}/assets/${assetId}`,
    { responseType: 'blob' },
  )
  imageUrl.value = URL.createObjectURL(response.data)
}

watch(
  () => [visual.value?.asset_id, props.courseId, props.representationId],
  () => { void loadImage() },
  { immediate: true },
)
onBeforeUnmount(revokeImage)
</script>

<style scoped>
.slide-visual {
  position: relative;
  min-width: 0;
  min-height: 0;
  margin: 0;
  overflow: hidden;
  border-radius: 1.2cqw;
  color: var(--deck-ink);
  background: var(--deck-blue-soft);
}
.slide-visual img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.slide-visual svg {
  width: 100%;
  height: 100%;
}
.slide-visual svg line {
  stroke: var(--deck-muted);
  stroke-width: 4;
}
.slide-visual svg circle {
  fill: var(--deck-blue);
  stroke: var(--deck-paper);
  stroke-width: 5;
}
.slide-visual__arrow { fill: var(--deck-muted); }
.slide-visual svg g rect {
  fill: var(--deck-card);
  stroke: var(--deck-line);
  stroke-width: 3;
}
.slide-visual svg g[data-emphasis="primary"] rect {
  fill: var(--deck-blue-soft);
  stroke: var(--deck-blue);
  stroke-width: 5;
}
.slide-visual svg foreignObject div {
  display: flex;
  height: 100%;
  align-items: center;
  justify-content: center;
  color: var(--deck-ink);
  font-size: 26px;
  font-weight: 720;
  line-height: 1.25;
  text-align: center;
}
.slide-visual__scale-note {
  fill: var(--deck-muted);
  font-size: 20px;
}
.slide-visual__table-wrap {
  display: grid;
  height: 100%;
  padding: 8% 6%;
  place-items: center;
}
.slide-visual__table-wrap table {
  width: 100%;
  overflow: hidden;
  border-collapse: separate;
  border-spacing: 0;
  border: 2px solid var(--deck-line);
  border-radius: .8cqw;
  background: var(--deck-card);
  font-size: 1.18cqw;
}
.slide-visual__table-wrap th,
.slide-visual__table-wrap td {
  padding: .72cqw .82cqw;
  border-right: 1px solid var(--deck-line);
  border-bottom: 1px solid var(--deck-line);
  text-align: left;
}
.slide-visual__table-wrap th {
  color: var(--deck-blue);
  background: var(--deck-blue-soft);
  font-weight: 800;
}
.slide-visual__table-wrap th:first-child,
.slide-visual__table-wrap td:first-child {
  width: 12%;
  text-align: center;
}
.slide-visual__table-wrap tr:last-child td { border-bottom: 0; }
.slide-visual__table-wrap th:last-child,
.slide-visual__table-wrap td:last-child { border-right: 0; }
.slide-visual__chart {
  display: flex;
  height: 100%;
  align-items: end;
  justify-content: center;
  gap: 7%;
  padding: 10% 8% 13%;
}
.slide-visual__bar {
  position: relative;
  width: 13%;
  min-height: 8%;
  border-radius: .6cqw .6cqw 0 0;
  background: linear-gradient(180deg,var(--deck-blue),var(--deck-teal));
}
.slide-visual__bar b {
  position: absolute;
  bottom: calc(100% + .5cqw);
  width: 100%;
  text-align: center;
}
.slide-visual__bar span {
  position: absolute;
  top: calc(100% + .45cqw);
  width: 100%;
  font-size: 1cqw;
  text-align: center;
}
.slide-visual__symbol,.slide-visual__fallback {
  display: flex;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1.3cqw;
}
.slide-visual__symbol b {
  color: var(--deck-blue);
  font: 800 6cqw/1 var(--deck-title-font);
}
.slide-visual__symbol span,.slide-visual__fallback span {
  max-width: 76%;
  font-size: 1.35cqw;
  font-weight: 700;
  text-align: center;
}
.slide-visual figcaption {
  position: absolute;
  right: 1.2cqw;
  bottom: .85cqw;
  max-width: 80%;
  color: var(--deck-muted);
  font-size: .72cqw;
  line-height: 1.2;
  text-align: right;
}
</style>
