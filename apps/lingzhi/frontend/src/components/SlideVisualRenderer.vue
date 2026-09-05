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
      v-else-if="['relational_diagram', 'rule_diagram'].includes(visual.kind)"
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
      <text
        v-for="edge in diagramEdges.filter(item => item.label)"
        :key="`${edge.source}-${edge.target}-label`"
        :x="(edge.x1 + edge.x2) / 2"
        :y="(edge.y1 + edge.y2) / 2 - 12"
        class="slide-visual__edge-label"
        text-anchor="middle"
      >
        {{ edge.label }}
      </text>
      <g
        v-for="node in diagramNodes"
        :key="node.node_id"
        :transform="`translate(${node.x} ${node.y})`"
        :data-emphasis="node.emphasis || 'secondary'"
      >
        <rect :width="node.width" :height="node.height" rx="20" />
        <foreignObject x="18" y="14" :width="node.width - 36" :height="node.height - 28">
          <div xmlns="http://www.w3.org/1999/xhtml"><MathText :content="node.rawLabel" /></div>
        </foreignObject>
      </g>
    </svg>

    <svg
      v-else-if="visual.kind === 'coordinate_plot'"
      viewBox="0 0 1000 560"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      <defs>
        <marker id="coordinate-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
          <path d="M0,0 L0,6 L9,3 z" class="slide-visual__arrow" />
        </marker>
      </defs>
      <line x1="90" y1="280" x2="920" y2="280" />
      <line x1="500" y1="60" x2="500" y2="500" />
      <line
        v-if="plotConnector"
        :x1="plotConnector.x1"
        :y1="plotConnector.y1"
        :x2="plotConnector.x2"
        :y2="plotConnector.y2"
        class="slide-visual__mapping"
        marker-end="url(#coordinate-arrow)"
      />
      <g
        v-for="(point, index) in plotPoints"
        :key="`${point.label}-${index}`"
      >
        <circle :cx="point.x" :cy="point.y" r="11" />
        <foreignObject :x="point.x + 18" :y="point.y - 48" width="210" height="42">
          <div xmlns="http://www.w3.org/1999/xhtml" class="slide-visual__coordinate-label"><MathText :content="point.label" /></div>
        </foreignObject>
      </g>
      <foreignObject x="920" y="230" width="70" height="42"><div xmlns="http://www.w3.org/1999/xhtml" class="slide-visual__coordinate-label"><MathText :content="axisLabels[0]" /></div></foreignObject>
      <foreignObject x="516" y="50" width="70" height="42"><div xmlns="http://www.w3.org/1999/xhtml" class="slide-visual__coordinate-label"><MathText :content="axisLabels[1]" /></div></foreignObject>
    </svg>

    <div v-else-if="visual.kind === 'chart'" class="slide-visual__chart">
      <div
        v-for="(value, index) in chartValues"
        :key="index"
        class="slide-visual__bar"
        :style="{ height: `${Math.max(8, value.ratio * 100)}%` }"
      >
        <b>{{ value.value }}</b><span><MathText :content="value.label" /></span>
      </div>
    </div>

    <div v-else-if="visual.kind === 'formula'" class="slide-visual__formula">
      <MarkdownRenderer :content="formulaMarkdown" :enable-code-run="false" />
    </div>
    <div v-else-if="visual.kind === 'table'" class="slide-visual__table-wrap">
      <table>
        <thead>
          <tr><th v-for="header in tableHeaders" :key="header"><MathText :content="header" /></th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in tableRows" :key="rowIndex">
            <td v-for="(cell, cellIndex) in row" :key="cellIndex"><MathText :content="String(cell ?? '')" /></td>
          </tr>
        </tbody>
      </table>
    </div>

    <figcaption class="slide-visual__sr-only">{{ visual.alt_text }}</figcaption>
  </figure>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import http from '../utils/http'
import type { SlideVisual } from '../types/slideVisual'
import { isRenderableSlideVisual } from '../utils/slideVisual'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MathText from './MathText.vue'

const props = withDefaults(defineProps<{
  visuals: SlideVisual[]
  courseId?: string
  representationId?: string
}>(), {
  visuals: () => [],
  courseId: '',
  representationId: '',
})

const visual = computed(() => props.visuals?.find(isRenderableSlideVisual))
const imageUrl = ref('')
const isImage = computed(() => ['source_image', 'retrieved_image', 'generated_illustration'].includes(visual.value?.kind || ''))
function formatVisualText(value: unknown) {
  return String(value || '')
    .replace(/\\mathbb\{([A-Za-z])\}/g, '$1')
    .replace(/\\(?:mathbf|mathrm|operatorname|text)\{([^{}]+)\}/g, '$1')
    .replace(/\\subseteq/g, '⊆')
    .replace(/\\cap/g, '∩')
    .replace(/\\cup/g, '∪')
    .replace(/\\in(?![A-Za-z])/g, '∈')
    .replace(/\\mid/g, '∣')
    .replace(/\\land/g, '∧')
    .replace(/\\lor/g, '∨')
    .replace(/\\cdots/g, '⋯')
    .replace(/\\times/g, '×')
    .replace(/\\to(?![A-Za-z])/g, '→')
    .replace(/\\\{/g, '{')
    .replace(/\\\}/g, '}')
    .replace(/\$\$/g, '')
    .trim()
}

const diagramNodes = computed(() => {
  const nodes = visual.value?.nodes || []
  const vertical = visual.value?.parameters?.direction === 'vertical'
  if (vertical) {
    const height = Math.min(88, 390 / Math.max(1, nodes.length))
    return nodes.map((node, index) => ({
      ...node,
      label: formatVisualText(node.label),
      rawLabel: String(node.label || ''),
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
    label: formatVisualText(node.label),
    rawLabel: String(node.label || ''),
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

const plotPoints = computed(() => {
  const points = (visual.value?.parameters?.points || []).slice(0, 10)
  const labels = visual.value?.parameters?.point_labels || []
  const maximum = Math.max(
    1,
    ...points.flatMap((point: unknown[]) => [
      Math.abs(Number(point?.[0]) || 0),
      Math.abs(Number(point?.[1]) || 0),
    ]),
  )
  return points.map((point: unknown[], index: number) => ({
    x: 500 + (Number(point?.[0]) || 0) * (340 / maximum),
    y: 280 - (Number(point?.[1]) || 0) * (190 / maximum),
    label: String(labels[index] || `(${point?.[0]}, ${point?.[1]})`),
  }))
})
const plotConnector = computed(() => {
  if (!visual.value?.parameters?.connect_points || plotPoints.value.length < 2) return null
  return {
    x1: plotPoints.value[0].x,
    y1: plotPoints.value[0].y,
    x2: plotPoints.value[1].x,
    y2: plotPoints.value[1].y,
  }
})
const axisLabels = computed(() => visual.value?.parameters?.axis_labels || ['x', 'y'])
const formulaMarkdown = computed(() => {
  const source = String(
    visual.value?.parameters?.formula
    || visual.value?.alt_text
    || '',
  ).trim()
  if (/^(?:\$\$|\\\[|\\\()/.test(source)) return source
  const lines = source.split(/\n{2,}/).map(line => line.trim()).filter(Boolean)
  if (lines.length > 1) {
    return lines.map((line) => {
      const inlineMath = line.match(/^\$(?!\$)([\s\S]+)\$$/)
      return inlineMath ? `$$${inlineMath[1]}$$` : line
    }).join('\n\n')
  }
  const inlineMath = source.match(/^\$(?!\$)([\s\S]+)\$$/)
  if (inlineMath) return `$$${inlineMath[1]}$$`
  if (source.includes('$')) return source
  return `$$${source}$$`
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
.slide-visual svg foreignObject .slide-visual__coordinate-label {
  justify-content: flex-start;
  font-size: 24px;
  font-weight: 760;
  white-space: nowrap;
}
.slide-visual__point-label,
.slide-visual__axis-label,
.slide-visual__edge-label {
  fill: var(--deck-muted);
  font-size: 24px;
  font-weight: 760;
}
.slide-visual__edge-label {
  paint-order: stroke;
  stroke: var(--deck-card);
  stroke-width: 8px;
  stroke-linejoin: round;
}
.slide-visual svg line.slide-visual__mapping {
  stroke: var(--deck-blue);
  stroke-width: 6;
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
.slide-visual__formula {
  display: grid;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  padding: clamp(12px, 4%, 32px);
  place-items: center;
  color: var(--deck-ink);
  background: var(--deck-card);
  font-size: clamp(24px, 2.35cqw, 38px);
  overflow: auto;
}
.slide-visual__formula :deep(.markdown-body) {
  width: 100%;
  margin: 0;
  color: inherit;
  text-align: center;
}
.slide-visual__formula :deep(.katex-display) {
  margin: .35em 0;
  overflow: visible;
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
.slide-visual__sr-only {
  position:absolute;
  width:1px;
  height:1px;
  padding:0;
  margin:-1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
  border:0;
}
</style>
