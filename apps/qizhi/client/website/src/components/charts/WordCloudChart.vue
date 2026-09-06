<template>
  <div class="word-cloud-root">
    <p v-if="summary" class="word-cloud-summary">{{ summary }}</p>
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      class="word-cloud-svg"
      aria-label="知识点词云"
    >
      <text
        v-for="(item, i) in items"
        :key="i"
        :x="item.x + item.w / 2"
        :y="item.y + item.h * 0.75"
        text-anchor="middle"
        :font-size="item.size"
        :font-weight="item.weight"
        :fill="item.color"
        class="word-cloud-text"
      >{{ item.text }}</text>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface HotWord {
  text: string
  count: number
}

interface CloudItem {
  text: string
  count: number
  size: number
  color: string
  weight: number
  x: number
  y: number
  w: number
  h: number
}

const PALETTE = [
  '#1358e4', '#5B8DEE', '#E06B5A', '#F2B84B', '#5FD3B3',
  '#6B5FE3', '#F28ADC', '#4BC0C0', '#FFA07A', '#20B2AA',
  '#9370DB', '#FFB347', '#A0D468', '#E7C14A',
]
const CELL = 4

const props = withDefaults(defineProps<{
  words: HotWord[]
  width?: number
  height?: number
  maxWords?: number
}>(), {
  width: 520,
  height: 520,
  maxWords: 50,
})

function estimateWidth(text: string, size: number): number {
  let acc = 0
  for (const ch of text) {
    const code = ch.charCodeAt(0)
    acc += code < 128 ? 0.58 : 1.0
  }
  return acc * size
}

const items = computed<CloudItem[]>(() => {
  const words = props.words.slice(0, props.maxWords)
  if (!words.length) return []

  const maxCount = words[0]?.count ?? 1
  const minCount = words[words.length - 1]?.count ?? 1
  const span = Math.max(1, maxCount - minCount)
  const sized = words.map((w, i) => {
    const norm = (w.count - minCount) / span
    const size = Math.round(14 + norm * 40)
    const weight = norm > 0.6 ? 700 : norm > 0.3 ? 600 : 500
    return {
      text: w.text,
      count: w.count,
      size,
      weight,
      color: PALETTE[i % PALETTE.length] ?? '#1358e4',
    }
  })

  const cols = Math.ceil(props.width / CELL)
  const rows = Math.ceil(props.height / CELL)
  const occ = new Uint8Array(cols * rows)
  const cx = props.width / 2
  const cy = props.height / 2
  const placed: CloudItem[] = []
  const pad = 3

  for (const item of sized) {
    const w = Math.ceil(estimateWidth(item.text, item.size)) + pad * 2
    const h = Math.ceil(item.size * 1.18) + pad * 2
    let done = false
    for (let step = 0; step < 5000 && !done; step++) {
      const t = step * 0.22
      const r = 2.5 * t
      const angle = t
      const x = Math.round(cx + r * Math.cos(angle) - w / 2)
      const y = Math.round(cy + r * Math.sin(angle) - h / 2)
      if (x < 0 || y < 0 || x + w > props.width || y + h > props.height) continue
      const c0 = Math.floor(x / CELL)
      const r0 = Math.floor(y / CELL)
      const c1 = Math.ceil((x + w) / CELL)
      const r1 = Math.ceil((y + h) / CELL)
      let clash = false
      for (let ri = r0; ri < r1 && !clash; ri++) {
        for (let ci = c0; ci < c1; ci++) {
          if (occ[ri * cols + ci]) { clash = true; break }
        }
      }
      if (clash) continue
      for (let ri = r0; ri < r1; ri++) {
        for (let ci = c0; ci < c1; ci++) {
          occ[ri * cols + ci] = 1
        }
      }
      placed.push({ ...item, x, y, w, h })
      done = true
    }
  }
  return placed
})

const summary = computed(() => {
  const hot = props.words.slice(0, props.maxWords)
  if (!hot.length) return ''
  const top = hot.slice(0, 3).map((h) => `${h.text}（${h.count} 次）`).join('，')
  return `AI 帮您提取了 ${hot.length} 个知识点热词，其中长提及知识点有：${top}`
})
</script>

<style scoped>
.word-cloud-root {
  display: flex;
  flex-direction: column;
}

.word-cloud-summary {
  font-size: 13px;
  color: #667085;
  margin-bottom: 8px;
  line-height: 1.5;
}

.word-cloud-svg {
  width: 100%;
  height: auto;
}

.word-cloud-text {
  user-select: none;
  cursor: default;
}
</style>
