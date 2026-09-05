<template>
  <div class="radar-chart-root">
    <div
      class="radar-wrap"
      :class="{ 'is-animating': animating }"
      @mouseleave="hoverIndex = null"
    >
      <svg class="radar-svg" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="radarFill" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="rgba(197, 217, 255, 0.5)" />
            <stop offset="100%" stop-color="rgba(197, 217, 255, 0.15)" />
          </linearGradient>
        </defs>
        <g v-for="level in 5" :key="'grid-' + level" class="radar-grid">
          <polygon
            :points="gridPoints(level / 5)"
            fill="none"
            stroke="#e0e0e0"
            stroke-width="1"
            :style="{ animationDelay: `${(level - 1) * 0.06}s` }"
          />
        </g>
        <g
          v-for="(label, i) in labels"
          :key="'axis-' + i"
          class="radar-axis"
          :class="{ 'is-hovered': hoverIndex === i }"
          @mouseenter="hoverIndex = i"
        >
          <line
            :x1="center.x"
            :y1="center.y"
            :x2="axisEnd(i, false).x"
            :y2="axisEnd(i, false).y"
            class="radar-axis-line"
          />
          <text
            :x="axisEnd(i, true).x"
            :y="axisEnd(i, true).y"
            class="radar-label"
            text-anchor="middle"
            dominant-baseline="middle"
          >{{ label }}</text>
          <text
            :x="axisEnd(i, true).x"
            :y="axisEnd(i, true).y + 14"
            class="radar-label-score"
            text-anchor="middle"
            dominant-baseline="middle"
          >{{ formatScore(values[i]) }}</text>
        </g>
        <polygon
          class="radar-data-polygon"
          :class="{ 'is-ready': !animating }"
          :points="animatedDataPoints"
          fill="url(#radarFill)"
          stroke="#5B8DEE"
          stroke-width="2"
          stroke-linejoin="round"
        />
        <g
          v-for="(_, i) in labels"
          :key="'vertex-' + i"
          class="radar-vertex-group"
          @mouseenter="hoverIndex = i"
        >
          <circle
            :cx="vertex(i).x"
            :cy="vertex(i).y"
            r="16"
            class="radar-hit"
          />
          <circle
            :cx="vertex(i).x"
            :cy="vertex(i).y"
            :r="hoverIndex === i ? 6 : 4"
            class="radar-vertex"
            :class="{ 'is-active': hoverIndex === i }"
          />
          <text
            :x="vertex(i).x"
            :y="vertex(i).y - 12"
            class="radar-vertex-score"
            :class="{ 'is-active': hoverIndex === i }"
            text-anchor="middle"
            dominant-baseline="middle"
          >{{ formatScore(displayValues[i] ?? values[i]) }}</text>
        </g>
      </svg>
      <Transition name="radar-tooltip-fade">
        <div
          v-if="hoverIndex !== null"
          class="radar-tooltip"
          :style="tooltipStyle"
        >
          <span class="radar-tooltip-label">{{ labels[hoverIndex] }}</span>
          <span class="radar-tooltip-score">{{ formatScore(values[hoverIndex]) }} 分</span>
        </div>
      </Transition>
    </div>
    <p class="radar-tip">教学表现雷达图 · 悬停查看详情</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { formatRadarScore } from '../../lib/reportParsers'

const props = defineProps<{
  labels: string[]
  values: number[]
}>()

const center = { x: 200, y: 200 }
const radius = 120

const hoverIndex = ref<number | null>(null)
const displayValues = ref<number[]>([])
const animating = ref(false)
let animFrameId = 0

const formatScore = formatRadarScore

function angle(i: number): number {
  const n = props.labels.length
  if (n < 3) return 0
  return Math.PI / 2 + (i * 2 * Math.PI) / n
}

function gridPoints(ratio: number): string {
  const r = radius * ratio
  return props.labels
    .map((_, i) => {
      const a = angle(i)
      return `${center.x + r * Math.cos(a)},${center.y - r * Math.sin(a)}`
    })
    .join(' ')
}

function axisEnd(i: number, forLabel = false): { x: number; y: number } {
  const a = angle(i)
  const r = forLabel ? radius + 22 : radius
  return { x: center.x + r * Math.cos(a), y: center.y - r * Math.sin(a) }
}

function valuesForDraw(): number[] {
  const animated = displayValues.value
  if (animated.length === props.values.length && animated.length >= 3) return animated
  return props.values
}

function vertex(i: number): { x: number; y: number } {
  const vals = valuesForDraw()
  const v = vals[i] ?? 0
  const a = angle(i)
  const r = radius * (v / 100)
  return { x: center.x + r * Math.cos(a), y: center.y - r * Math.sin(a) }
}

const animatedDataPoints = computed(() => {
  const vals = valuesForDraw()
  const n = props.labels.length
  if (n < 3 || vals.length !== n) return ''
  return vals
    .map((_, i) => {
      const p = vertex(i)
      return `${p.x},${p.y}`
    })
    .join(' ')
})

const tooltipStyle = computed(() => {
  const i = hoverIndex.value
  if (i === null) return {}
  const p = vertex(i)
  return { left: `${(p.x / 400) * 100}%`, top: `${(p.y / 400) * 100}%` }
})

function stopAnimation() {
  if (animFrameId) {
    cancelAnimationFrame(animFrameId)
    animFrameId = 0
  }
  animating.value = false
}

function animate() {
  stopAnimation()
  const target = props.values
  if (target.length < 3) {
    displayValues.value = []
    return
  }
  animating.value = true
  hoverIndex.value = null
  const duration = 900
  const startAt = performance.now()
  const tick = (now: number) => {
    const t = Math.min(1, (now - startAt) / duration)
    const ease = 1 - (1 - t) ** 3
    displayValues.value = target.map((v) => v * ease)
    if (t < 1) {
      animFrameId = requestAnimationFrame(tick)
    } else {
      displayValues.value = [...target]
      animFrameId = 0
      animating.value = false
    }
  }
  displayValues.value = target.map(() => 0)
  animFrameId = requestAnimationFrame(tick)
}

const hasChart = computed(() => props.labels.length >= 3 && props.labels.length === props.values.length)

watch(
  hasChart,
  (ok) => {
    if (ok) nextTick(() => animate())
    else {
      stopAnimation()
      displayValues.value = []
      hoverIndex.value = null
    }
  },
  { immediate: true },
)

watch(() => props.values, () => {
  if (hasChart.value) nextTick(() => animate())
})

onBeforeUnmount(() => stopAnimation())
</script>

<style scoped>
.radar-chart-root {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.radar-wrap {
  position: relative;
  width: 100%;
  max-width: 380px;
  aspect-ratio: 1/1;
}

.radar-svg {
  width: 100%;
  height: 100%;
}

.radar-grid polygon {
  animation: radarGridFadeIn 0.5s ease-out both;
}

@keyframes radarGridFadeIn {
  from { opacity: 0; transform: scale(0.85); }
  to { opacity: 1; transform: scale(1); }
}

.radar-axis-line {
  stroke: #d0d5dd;
  stroke-width: 1;
  transition: stroke 0.2s;
}

.radar-axis.is-hovered .radar-axis-line {
  stroke: #5B8DEE;
  stroke-width: 1.5;
}

.radar-label {
  font-size: 12px;
  fill: #344054;
  font-weight: 500;
}

.radar-label-score {
  font-size: 11px;
  fill: #667085;
  font-weight: 400;
}

.radar-data-polygon {
  transition: opacity 0.3s;
  opacity: 0.85;
}

.radar-data-polygon.is-ready {
  opacity: 1;
}

.radar-hit {
  fill: transparent;
  cursor: pointer;
}

.radar-vertex {
  fill: #5B8DEE;
  stroke: #fff;
  stroke-width: 2;
  transition: r 0.2s, fill 0.2s;
}

.radar-vertex.is-active {
  fill: #3b6fd9;
}

.radar-vertex-score {
  font-size: 11px;
  fill: transparent;
  font-weight: 600;
  transition: fill 0.2s;
  pointer-events: none;
}

.radar-vertex-score.is-active {
  fill: #344054;
}

.radar-tooltip {
  position: absolute;
  transform: translate(-50%, -100%);
  margin-top: -8px;
  background: #fff;
  border: 1px solid #e4e7ec;
  border-radius: 8px;
  padding: 6px 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  display: flex;
  gap: 8px;
  align-items: center;
  pointer-events: none;
  white-space: nowrap;
  z-index: 10;
}

.radar-tooltip-label {
  font-size: 12px;
  color: #667085;
}

.radar-tooltip-score {
  font-size: 13px;
  font-weight: 600;
  color: #344054;
}

.radar-tooltip-fade-enter-active,
.radar-tooltip-fade-leave-active {
  transition: opacity 0.15s ease;
}
.radar-tooltip-fade-enter-from,
.radar-tooltip-fade-leave-to {
  opacity: 0;
}

.radar-tip {
  text-align: center;
  font-size: 12px;
  color: #98a2b3;
  margin-top: 8px;
}
</style>
