<template>
  <div
    ref="rootEl"
    class="volume-chart-root"
    @pointermove="onPointerMove"
    @pointerleave="onPointerLeave"
    @click="onClick"
  >
    <svg
      class="volume-chart-svg"
      :viewBox="`0 0 ${chartWidth} ${CHART_HEIGHT}`"
      preserveAspectRatio="none"
    >
      <polyline
        :points="chartPoints"
        fill="none"
        stroke="#5B8DEE"
        stroke-width="1.5"
        stroke-linejoin="round"
      />
      <line
        v-if="stats.avg > 0"
        x1="0"
        :y1="stats.avgY"
        :x2="chartWidth"
        :y2="stats.avgY"
        stroke="#F2B84B"
        stroke-width="1"
        stroke-dasharray="4 3"
      />
      <line
        v-if="progressPercent > 0 && progressPercent < 100"
        :x1="progressPercent / 100 * chartWidth"
        y1="0"
        :x2="progressPercent / 100 * chartWidth"
        :y2="CHART_HEIGHT"
        stroke="#667085"
        stroke-width="1"
        stroke-dasharray="3 2"
        opacity="0.5"
      />
      <line
        v-if="hoverLineX !== null"
        :x1="hoverLineX"
        y1="0"
        :x2="hoverLineX"
        :y2="CHART_HEIGHT"
        stroke="#344054"
        stroke-width="1"
        stroke-dasharray="2 2"
      />
    </svg>
    <Transition name="vol-tooltip-fade">
      <div
        v-if="hoverSample"
        class="volume-tooltip"
        :style="tooltipStyle"
      >
        <span class="volume-tooltip-time">{{ formatSec(hoverSample.timeSec) }}</span>
        <span class="volume-tooltip-val">{{ hoverSample.value.toFixed(1) }} dB</span>
      </div>
    </Transition>
    <div class="volume-stats-row">
      <span>最低 {{ stats.min }} dB</span>
      <span>均值 {{ stats.avg }} dB</span>
      <span>最高 {{ stats.max }} dB</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { formatSec } from '../../lib/reportParsers'

const CHART_HEIGHT = 200

const props = defineProps<{
  data: number[]
  durationSec: number
  progressPercent: number
}>()

const emit = defineEmits<{
  seek: [ratio: number]
}>()

const rootEl = ref<HTMLElement | null>(null)
const chartWidth = ref(800)
let resizeObserver: ResizeObserver | null = null

const hoverRatio = ref<number | null>(null)

interface HoverSample { index: number; value: number; timeSec: number; ratio: number }
const hoverSample = ref<HoverSample | null>(null)

const stats = computed(() => {
  const data = props.data
  if (data.length === 0) {
    return { min: 0, max: 0, avg: 0, avgY: 100, chartMin: 0, chartMax: 1, chartRange: 1 }
  }
  const min = Math.min(...data)
  const max = Math.max(...data)
  const avg = Math.round((data.reduce((a, b) => a + b, 0) / data.length) * 10) / 10
  const padding = Math.max(2, (max - min) * 0.1)
  const chartMin = min - padding
  const chartMax = max + padding
  const chartRange = chartMax - chartMin || 1
  const avgY = CHART_HEIGHT - ((avg - chartMin) / chartRange) * CHART_HEIGHT
  return {
    min: Math.round(min * 10) / 10,
    max: Math.round(max * 10) / 10,
    avg,
    avgY,
    chartMin,
    chartMax,
    chartRange,
  }
})

const chartPoints = computed(() => {
  const data = props.data
  if (data.length === 0) return ''
  const width = chartWidth.value
  const { chartMin, chartRange } = stats.value
  return data
    .map((value, index) => {
      const x = (index / (data.length - 1)) * width
      const y = CHART_HEIGHT - ((value - chartMin) / chartRange) * CHART_HEIGHT
      return `${x},${y}`
    })
    .join(' ')
})

const hoverLineX = computed(() => {
  if (hoverRatio.value === null) return null
  return hoverRatio.value * chartWidth.value
})

const tooltipStyle = computed(() => {
  if (hoverRatio.value === null) return {}
  return { left: `${hoverRatio.value * 100}%`, top: '8px' }
})

function ratioFromPointer(event: MouseEvent): number | null {
  const root = rootEl.value
  if (!root) return null
  const svg = root.querySelector('.volume-chart-svg')
  if (!svg) return null
  const rect = svg.getBoundingClientRect()
  if (rect.width <= 0) return null
  return Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
}

function sampleAtRatio(ratio: number): HoverSample | null {
  const data = props.data
  if (!data.length) return null
  const index =
    data.length === 1 ? 0 : Math.min(data.length - 1, Math.max(0, Math.round(ratio * (data.length - 1))))
  const value = data[index] ?? 0
  const timeSec = props.durationSec > 0 ? ratio * props.durationSec : 0
  return { index, value, timeSec, ratio }
}

function onPointerMove(event: MouseEvent) {
  const ratio = ratioFromPointer(event)
  if (ratio === null) return
  hoverRatio.value = ratio
  hoverSample.value = sampleAtRatio(ratio)
}

function onPointerLeave() {
  hoverRatio.value = null
  hoverSample.value = null
}

function onClick(event: MouseEvent) {
  const ratio = ratioFromPointer(event)
  if (ratio === null) return
  emit('seek', ratio)
}

onMounted(() => {
  if (typeof ResizeObserver === 'undefined') return
  resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const w = Math.round(entry.contentRect.width)
      if (w > 0) chartWidth.value = w
    }
  })
  watch(
    rootEl,
    (el, _old, onCleanup) => {
      if (!el || !resizeObserver) return
      resizeObserver.observe(el)
      onCleanup(() => resizeObserver?.unobserve(el))
    },
    { immediate: true },
  )
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})
</script>

<style scoped>
.volume-chart-root {
  position: relative;
  width: 100%;
  cursor: crosshair;
}

.volume-chart-svg {
  width: 100%;
  height: 120px;
  display: block;
}

.volume-tooltip {
  position: absolute;
  transform: translateX(-50%);
  background: #fff;
  border: 1px solid #e4e7ec;
  border-radius: 6px;
  padding: 4px 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  display: flex;
  gap: 8px;
  align-items: center;
  pointer-events: none;
  white-space: nowrap;
  z-index: 10;
  font-size: 12px;
}

.volume-tooltip-time {
  color: #667085;
}

.volume-tooltip-val {
  font-weight: 600;
  color: #344054;
}

.vol-tooltip-fade-enter-active,
.vol-tooltip-fade-leave-active {
  transition: opacity 0.15s ease;
}
.vol-tooltip-fade-enter-from,
.vol-tooltip-fade-leave-to {
  opacity: 0;
}

.volume-stats-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #98a2b3;
  margin-top: 4px;
  padding: 0 4px;
}
</style>
