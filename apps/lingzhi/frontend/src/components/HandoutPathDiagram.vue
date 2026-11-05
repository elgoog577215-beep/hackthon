<template>
  <div class="path-diagram-scroll" tabindex="0" :aria-label="path.title">
    <div ref="canvas" class="path-diagram" :style="{ gridTemplateColumns: `repeat(${layout.columns}, minmax(150px, 1fr))`, minWidth: `${layout.columns * 168 - 18}px` }">
      <svg class="path-diagram-edges" aria-hidden="true">
        <defs><marker :id="markerId" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" /></marker></defs>
        <path v-for="edge in edges" :key="edge.id" :d="edge.d" :data-parent="edge.parent" :data-child="edge.id" :marker-end="`url(#${markerId})`" />
      </svg>
      <button v-for="node in layout.nodes" :key="node.step.id" class="path-node" :data-step-id="node.step.id" :data-stage="node.step.stage" :aria-pressed="selected === node.step.id" :style="{ gridColumn: `${node.start + 1} / span ${node.span}`, gridRow: node.depth + 1 }" @click="emit('select', node.step.id)">
        <span v-if="node.step.condition" class="path-branch"><MathText :content="node.step.condition" /></span>
        <span v-else-if="node.step.stage !== 'step'" class="path-stage">{{ c(stageLabels[node.step.stage]) }}</span>
        <MathText :content="node.step.text" />
      </button>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import MathText from './MathText.vue'
import { studyCopy as c } from '../shared/study-copy'
import type { LearningPath, LearningPathStep } from '../utils/handout-paths'
const props = defineProps<{ path: LearningPath; selected: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const stageLabels = { start: 'pathStart', choice: 'pathChoice', step: 'pathStep', result: 'pathResult', check: 'pathCheck' } as const
const markerId = `path-arrow-${useId().replace(/[^\w-]/g, '')}`
const layout = computed(() => {
  const nodes: { step: LearningPathStep; start: number; span: number; depth: number }[] = []
  const children = (id: string) => props.path.steps.filter(s => s.parentId === id)
  function visit(step: LearningPathStep, start: number, depth: number): number {
    let span = 0
    for (const child of children(step.id)) span += visit(child, start + span, depth + 1)
    span = Math.max(1, span); nodes.push({ step, start, span, depth }); return span
  }
  let columns = 0
  for (const root of children('')) columns += visit(root, columns, 0)
  return { nodes: nodes.sort((a,b) => a.depth - b.depth || a.start - b.start), columns: Math.max(1, columns) }
})
const canvas = ref<HTMLElement | null>(null), edges = ref<{ id: string; parent: string; d: string }[]>([])
function draw() {
  if (!canvas.value) return
  const rect = canvas.value.getBoundingClientRect()
  const bounds = new Map(Array.from(canvas.value.querySelectorAll<HTMLElement>('[data-step-id]')).map(el => [el.dataset.stepId, el.getBoundingClientRect()]))
  edges.value = props.path.steps.flatMap(step => {
    const a = bounds.get(step.parentId), b = bounds.get(step.id)
    if (!a || !b) return []
    const x1 = a.left + a.width / 2 - rect.left, y1 = a.bottom - rect.top
    const x2 = b.left + b.width / 2 - rect.left, y2 = b.top - rect.top - 2, mid = (y1 + y2) / 2
    return [{ id: step.id, parent: step.parentId, d: `M${x1},${y1} C${x1},${mid} ${x2},${mid} ${x2},${y2}` }]
  })
}
let observer: ResizeObserver | undefined
function observe() { observer?.disconnect(); if (canvas.value) { observer?.observe(canvas.value); canvas.value.querySelectorAll('[data-step-id]').forEach(el => observer?.observe(el)) }; draw() }
watch(() => props.path, async () => { await nextTick(); observe() }, { deep: true })
onMounted(() => { observer = new ResizeObserver(draw); observe() })
onBeforeUnmount(() => observer?.disconnect())
</script>
<style scoped>
.path-diagram-scroll { max-width:100%; overflow:auto; padding:8px 2px; scrollbar-width:thin; }
.path-diagram { display:grid; position:relative; gap:34px 18px; align-items:center; justify-items:center; padding:4px 2px; }
.path-diagram-edges { position:absolute; inset:0; width:100%; height:100%; overflow:visible; pointer-events:none; }
.path-diagram-edges > path { fill:none; stroke:#b9a6da; stroke-width:1.5; }
.path-diagram-edges marker path { fill:#9b87c9; }
.path-node { position:relative; box-sizing:border-box; width:max-content; max-width:min(100%, 280px); padding:7px 10px; border:1px solid #b9a6da; border-radius:7px; background:#f3effa; color:#3d2a63; cursor:pointer; font:14px/1.55 var(--study-ui-font); text-align:left; overflow-wrap:anywhere; }
.path-node[data-stage=result],.path-node[data-stage=check] { background:#eef7f3; border-color:#a6cbbb; color:#285c48; }
.path-node[aria-pressed=true] { outline:2px solid #806298; outline-offset:2px; }
.path-stage,.path-branch { display:block; margin-bottom:3px; font-size:12px; font-weight:600; color:#735889; }
.path-node :deep(.katex) { font-size:1em; }
.path-diagram-scroll:focus-visible,.path-node:focus-visible { outline:2px solid #8875b2; outline-offset:2px; }
</style>
