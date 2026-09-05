<template>
  <div class="bc-wrap">
    <div v-if="!sortedData.length" class="bc-empty">暂无数据</div>
    <svg
      v-else
      class="bc-svg"
      :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
      preserveAspectRatio="none"
      role="img"
      aria-label="使用次数柱状图"
    >
      <g
        v-for="(item, idx) in sortedData"
        :key="`${item.label}-${idx}`"
        :transform="`translate(0, ${idx * rowHeight + topPad})`"
      >
        <text
          :x="labelWidth - 8"
          :y="rowHeight / 2"
          dominant-baseline="middle"
          text-anchor="end"
          class="bc-label"
        >
          {{ truncate(item.label, 14) }}
        </text>
        <rect
          :x="labelWidth"
          :y="(rowHeight - barHeight) / 2"
          :width="barWidth(item.value)"
          :height="barHeight"
          :fill="item.color || palette[idx % palette.length]"
          rx="4"
        />
        <text
          :x="labelWidth + barWidth(item.value) + 6"
          :y="rowHeight / 2"
          dominant-baseline="middle"
          class="bc-value"
        >
          {{ formatValue(item.value) }}
        </text>
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface BarChartItem {
  label: string
  value: number
  color?: string
}

const props = withDefaults(
  defineProps<{
    data: BarChartItem[]
    /** 内部 viewBox 宽度，整体响应式拉伸到容器；不需要传 */
    width?: number
    /** 单行高度（含间距） */
    rowHeight?: number
    /** 实际柱体高度 */
    barHeight?: number
    /** 左侧标签区宽度 */
    labelWidth?: number
    /** 右侧数值区宽度 */
    valueWidth?: number
    /** 数值格式化器 */
    valueFormatter?: (v: number) => string
  }>(),
  {
    width: 480,
    rowHeight: 32,
    barHeight: 18,
    labelWidth: 110,
    valueWidth: 48,
  },
)

const palette = ['#2f4aa6', '#4467d9', '#5b8def', '#7cb1ff', '#a0c7ff', '#c8def8']
const topPad = 8

const sortedData = computed(() =>
  [...props.data].sort((a, b) => b.value - a.value),
)

const maxValue = computed(() => {
  let m = 0
  for (const it of sortedData.value) if (it.value > m) m = it.value
  return m || 1
})

const barAreaWidth = computed(() => props.width - props.labelWidth - props.valueWidth)
const svgWidth = computed(() => props.width)
const svgHeight = computed(() => sortedData.value.length * props.rowHeight + topPad * 2)

function barWidth(value: number): number {
  if (maxValue.value === 0) return 0
  return Math.max(2, (value / maxValue.value) * barAreaWidth.value)
}

function formatValue(value: number): string {
  return props.valueFormatter ? props.valueFormatter(value) : String(value)
}

function truncate(s: string, maxLen: number): string {
  if (!s) return ''
  return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
}
</script>

<style scoped>
.bc-wrap {
  width: 100%;
}

.bc-svg {
  width: 100%;
  height: auto;
  display: block;
}

.bc-label {
  font-size: 12px;
  fill: #4b5670;
}

.bc-value {
  font-size: 12px;
  fill: #1a2540;
  font-weight: 600;
}

.bc-empty {
  padding: 32px 16px;
  text-align: center;
  color: #8a93a6;
  font-size: 13px;
}
</style>
