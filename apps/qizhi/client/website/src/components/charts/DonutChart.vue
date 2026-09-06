<template>
  <div class="donut-chart-root">
    <div class="donut-chart-wrap">
      <svg viewBox="0 0 400 400" class="donut-svg" :aria-label="ariaLabel">
        <circle cx="200" cy="200" :r="radius" fill="none" stroke="#f0f2f8" :stroke-width="strokeWidth" />
        <g transform="rotate(-90 200 200)">
          <circle
            v-for="s in geom"
            :key="s.key + '-arc'"
            cx="200"
            cy="200"
            :r="radius"
            fill="none"
            :stroke="s.color"
            :stroke-width="strokeWidth"
            :stroke-dasharray="`${s.percent * circumference} ${circumference}`"
            :stroke-dashoffset="-s.offsetPercent * circumference"
          />
        </g>
        <template v-for="s in geom" :key="s.key + '-label'">
          <text
            :x="s.labelX"
            :y="s.labelY"
            :text-anchor="s.labelAnchor"
            class="donut-label-text"
          >{{ s.key }} {{ formatCount(s) }}</text>
          <text
            :x="s.labelX"
            :y="s.labelY + 18"
            :text-anchor="s.labelAnchor"
            class="donut-label-pct"
          >{{ (s.percent * 100).toFixed(2) }}%</text>
        </template>
      </svg>
    </div>
    <div class="donut-legend">
      <div
        v-for="s in geom"
        :key="s.key + '-legend'"
        class="donut-legend-item"
      >
        <span class="donut-legend-dot" :style="{ background: s.color }"></span>
        <span>{{ s.key }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface DonutSlice {
  key: string
  color: string
  count: number
  percent: number
  duration?: number
}

interface SliceGeom extends DonutSlice {
  offsetPercent: number
  labelX: number
  labelY: number
  labelAnchor: 'start' | 'end' | 'middle'
}

const props = withDefaults(defineProps<{
  slices: DonutSlice[]
  ariaLabel?: string
  radius?: number
  strokeWidth?: number
  labelRadius?: number
  countSuffix?: string
}>(), {
  ariaLabel: '环形图',
  radius: 120,
  strokeWidth: 30,
  labelRadius: 155,
  countSuffix: ' 次',
})

const circumference = computed(() => 2 * Math.PI * props.radius)

const geom = computed<SliceGeom[]>(() => {
  let cumulative = 0
  return props.slices.map((s) => {
    const offsetPercent = cumulative
    cumulative += s.percent
    const midPercent = offsetPercent + s.percent / 2
    const angle = midPercent * 2 * Math.PI - Math.PI / 2
    const cx = 200
    const cy = 200
    const labelX = cx + Math.cos(angle) * props.labelRadius
    const labelY = cy + Math.sin(angle) * props.labelRadius
    const dx = Math.cos(angle)
    const labelAnchor: 'start' | 'end' | 'middle' = dx > 0.2 ? 'start' : dx < -0.2 ? 'end' : 'middle'
    return { ...s, offsetPercent, labelX, labelY, labelAnchor }
  })
})

function formatCount(s: SliceGeom): string {
  if (s.duration != null) {
    const m = Math.round(s.duration / 60)
    return `${m} 分钟`
  }
  return `${s.count}${props.countSuffix}`
}
</script>

<style scoped>
.donut-chart-root {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.donut-chart-wrap {
  width: 100%;
  max-width: 340px;
}

.donut-svg {
  width: 100%;
  height: auto;
}

.donut-label-text {
  font-size: 13px;
  fill: #344054;
  font-weight: 500;
}

.donut-label-pct {
  font-size: 11px;
  fill: #98a2b3;
}

.donut-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  justify-content: center;
  margin-top: 8px;
}

.donut-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #344054;
}

.donut-legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
