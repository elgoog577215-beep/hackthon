<template>
  <div class="mastery-tree">
    <header class="tree-toolbar">
      <label class="tree-search"><Search :size="16" /><input v-model="query" type="search" :aria-label="t('knowledgeProfile.search', '搜索知识点')" :placeholder="t('knowledgeProfile.search', '搜索知识点')" /></label>
      <div class="tree-actions">
        <button type="button" @click="expandAll">{{ t('knowledgeProfile.treeView.expandAll', '展开全部') }}</button>
        <button type="button" @click="collapseAll">{{ t('knowledgeProfile.treeView.collapseAll', '收起分支') }}</button>
        <span class="tree-action-divider" />
        <button type="button" :aria-label="t('knowledgeProfile.treeView.zoomOut', '缩小')" :disabled="zoom <= .45" @click="setZoom(zoom - .1)"><Minus :size="16" /></button>
        <span class="tree-zoom">{{ Math.round(zoom * 100) }}%</span>
        <button type="button" :aria-label="t('knowledgeProfile.treeView.zoomIn', '放大')" :disabled="zoom >= 1.5" @click="setZoom(zoom + .1)"><Plus :size="16" /></button>
        <button type="button" :aria-label="t('knowledgeProfile.treeView.fit', '适应视图')" :title="t('knowledgeProfile.treeView.fit', '适应视图')" @click="fitView"><Scan :size="16" /></button>
      </div>
    </header>
    <div v-if="query && !tree.children.length" class="tree-no-results" role="status">{{ t('knowledgeProfile.noResults', '没有匹配的知识点') }}</div>
    <div v-else ref="viewport" class="tree-viewport" :class="{ 'is-panning': panning }" tabindex="0" :aria-label="t('knowledgeProfile.tree', '知识树与掌握状态')"
      @pointerdown="startPan" @pointermove="movePan" @pointerup="endPan" @pointercancel="endPan" @lostpointercapture="endPan">
      <div class="tree-stage-space" :style="{ width: `${Math.max(viewSize.width, layout.width * zoom)}px`, height: `${Math.max(viewSize.height, layout.height * zoom)}px` }">
        <div class="tree-stage" :style="{ left: `${stageLeft}px`, top: `${stageTop}px`, width: `${layout.width}px`, height: `${layout.height}px`, transform: `scale(${zoom})` }">
          <svg class="tree-edges" :width="layout.width" :height="layout.height" aria-hidden="true"><path v-for="edge in layout.edges" :key="edge.id" :d="edge.path" :class="{ 'edge-to-leaf': edge.target.kind === 'knowledge' }" /></svg>
          <template v-for="node in layout.nodes" :key="node.id">
            <div v-if="node.kind === 'course'" class="tree-course" :style="nodeStyle(node)"><span><BookOpen :size="16" />{{ t('knowledgeProfile.courseScope', '全课范围') }}</span><strong :title="node.label">{{ node.label }}</strong><small>{{ node.count }} {{ t('knowledgeProfile.points', '个元知识点') }}</small></div>
            <button v-else-if="node.kind === 'branch'" type="button" class="tree-branch" :class="{ expanded: node.expanded, pending: node.pending }" :style="nodeStyle(node)" :data-branch-id="node.sourceId" :aria-expanded="node.expanded" :disabled="Boolean(query.trim()) || node.pending" @click="toggle(node.id)">
              <span class="tree-branch-name">{{ node.label }}</span><span v-if="node.pending" class="tree-branch-meta">{{ t('courseKnowledgeStudy.pendingLecture') }}</span><span v-else class="tree-branch-meta">{{ node.count }} {{ t('knowledgeProfile.points', '个元知识点') }} · {{ node.progress === null ? t('knowledgeProfile.unassessed') : `${node.progress}%` }}</span><span v-if="!node.pending" class="tree-branch-toggle"><Minus v-if="node.expanded" :size="13" /><Plus v-else :size="13" /></span>
            </button>
            <button v-else type="button" class="tree-leaf" :class="node.status" :style="nodeStyle(node)" :data-knowledge-id="node.sourceId" aria-haspopup="dialog"
              :aria-label="`${node.label} · ${node.progress === null ? t('knowledgeProfile.unassessed', '未评估') : `${node.progress}%`}`" @click="select(node.sourceId, $event)">
              <span class="mastery-orb" :style="{ '--mastery-angle': `${(node.progress ?? 0) * 3.6}deg` }"><span class="orb-core"><strong>{{ node.progress ?? '—' }}<small v-if="node.progress !== null">%</small></strong><span v-if="node.progress === null">{{ t('knowledgeProfile.unassessed', '未评估') }}</span></span></span>
              <span class="tree-leaf-copy"><strong>{{ node.label }}</strong><small>{{ t(`knowledgeProfile.${node.status}`) }} <ArrowUpRight :size="12" /></small></span>
            </button>
          </template>
        </div>
      </div>
    </div>
    <footer class="tree-help"><MousePointer2 :size="14" /><span>{{ t('knowledgeProfile.treeView.help', '点击分支展开 · 点击圆球查看详情 · 拖动空白处移动视图') }}</span><span v-if="query">{{ t('knowledgeProfile.treeView.searchHint', '搜索不会改变全课统计') }}</span></footer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowUpRight, BookOpen, Minus, MousePointer2, Plus, Scan, Search } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { KnowledgeProfile } from '../types/knowledge-profile'
import { createKnowledgeTree, layoutKnowledgeTree, type PositionedProfileNode, type ProfileTreeItem } from '../utils/knowledge-tree-layout'

const props = defineProps<{ profile: KnowledgeProfile; courseTitle?: string }>()
const emit = defineEmits<{ (event: 'select', id: string, trigger: HTMLElement): void }>()
const query = ref('')
const collapsed = ref(new Set<string>())
const viewport = ref<HTMLElement | null>(null)
const zoom = ref(1)
const panning = ref(false)
const viewSize = ref({ width: 0, height: 0 })
let resizeObserver: ResizeObserver | undefined
let resizeFrame: number | undefined
let pan: { id: number; x: number; y: number; left: number; top: number; target: HTMLElement } | null = null
const tree = computed(() => createKnowledgeTree(props.profile, props.courseTitle || t('knowledgeProfile.treeView.course', '当前课程'), query.value))
const layout = computed(() => layoutKnowledgeTree(tree.value, query.value.trim() ? new Set() : collapsed.value))
const stageLeft = computed(() => Math.max(0, (viewSize.value.width - layout.value.width * zoom.value) / 2))
const stageTop = computed(() => Math.max(0, (viewSize.value.height - layout.value.height * zoom.value) / 2))
function measureViewport() {
  const element = viewport.value
  if (element && (viewSize.value.width !== element.clientWidth || viewSize.value.height !== element.clientHeight)) {
    viewSize.value = { width: element.clientWidth, height: element.clientHeight }
  }
}
function scheduleMeasure() {
  if (resizeFrame !== undefined) return
  resizeFrame = requestAnimationFrame(() => { resizeFrame = undefined; measureViewport() })
}
watch(viewport, (element, previous) => {
  if (previous) resizeObserver?.unobserve(previous)
  if (element) { resizeObserver?.observe(element); measureViewport() }
})
onMounted(() => {
  measureViewport()
  if (typeof ResizeObserver !== 'undefined') { resizeObserver = new ResizeObserver(scheduleMeasure); if (viewport.value) resizeObserver.observe(viewport.value) }
  window.addEventListener('blur', endPan)
})
onBeforeUnmount(() => { endPan(); resizeObserver?.disconnect(); if (resizeFrame !== undefined) cancelAnimationFrame(resizeFrame); window.removeEventListener('blur', endPan) })
function resetBranches() {
  const root = createKnowledgeTree(props.profile, '')
  const closed = new Set<string>()
  const visit = (node: ProfileTreeItem, firstPath: boolean) => {
    if (node.kind === 'branch' && !firstPath) closed.add(node.id)
    let first = true
    for (const child of node.children) { visit(child, firstPath && first); if (child.kind === 'branch') first = false }
  }
  visit(root, true)
  collapsed.value = closed
}
watch(() => `${props.profile.course_id}:${props.profile.baseline_revision}`, () => { query.value = ''; resetBranches(); zoom.value = 1 }, { immediate: true })
function toggle(id: string) {
  if (query.value.trim()) return
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  collapsed.value = next
}
function expandAll() { collapsed.value = new Set() }
function collapseAll() { query.value = ''; collapsed.value = new Set(props.profile.branches.map(b => `branch:${b.id}`)) }
function nodeStyle(node: PositionedProfileNode) { return { left: `${node.x}px`, top: `${node.y}px`, width: `${node.width}px`, height: `${node.height}px` } }
function select(id: string, event: MouseEvent) { emit('select', id, event.currentTarget as HTMLElement) }
async function setZoom(value: number) {
  const element = viewport.value
  const previous = zoom.value
  const left = element ? (element.scrollLeft + element.clientWidth / 2 - stageLeft.value) / previous : 0
  const top = element ? (element.scrollTop + element.clientHeight / 2 - stageTop.value) / previous : 0
  zoom.value = Math.max(.45, Math.min(1.5, Math.round(value * 100) / 100))
  await nextTick()
  if (element) { element.scrollLeft = left * zoom.value + stageLeft.value - element.clientWidth / 2; element.scrollTop = top * zoom.value + stageTop.value - element.clientHeight / 2 }
}
async function fitView() {
  const element = viewport.value
  if (!element) return
  await setZoom(Math.min(element.clientWidth / layout.value.width, element.clientHeight / layout.value.height, 1))
  element.scrollLeft = 0; element.scrollTop = 0
}
function startPan(event: PointerEvent) {
  if (event.button !== 0 || (event.target as Element).closest('button')) return
  const target = event.currentTarget as HTMLElement
  pan = { id: event.pointerId, x: event.clientX, y: event.clientY, left: target.scrollLeft, top: target.scrollTop, target }
  target.setPointerCapture?.(event.pointerId)
  panning.value = true
}
function movePan(event: PointerEvent) {
  if (!pan || event.pointerId !== pan.id) return
  pan.target.scrollLeft = pan.left + pan.x - event.clientX
  pan.target.scrollTop = pan.top + pan.y - event.clientY
}
function endPan() {
  const previous = pan; pan = null; panning.value = false
  if (previous?.target.hasPointerCapture?.(previous.id)) previous.target.releasePointerCapture(previous.id)
}
</script>

<style scoped>
.mastery-tree { border:1px solid #e6e2ef; border-radius:16px; overflow:hidden; background:#fcfbff; }
.tree-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 16px; border-bottom:1px solid #eee9f5; background:#fff; }
.tree-search { display:flex; align-items:center; gap:8px; max-width:290px; min-width:140px; color:#9a8fac; }.tree-search input { width:100%; min-width:0; padding:8px 4px; border:0; outline:0; background:transparent; color:#4e435f; font:inherit; font-size:14px; }
.tree-actions { display:flex; align-items:center; gap:4px; flex-wrap:wrap; justify-content:flex-end; }.tree-actions button { min-width:32px; min-height:34px; display:grid; place-items:center; padding:6px 8px; border:0; border-radius:7px; background:transparent; color:#837293; font:inherit; font-size:12px; cursor:pointer; }.tree-actions button:hover { background:#f2edf9; color:#644a8c; }.tree-actions button:disabled { opacity:.4; cursor:default; }.tree-action-divider { width:1px; height:20px; background:#eae3f1; margin:0 5px; }.tree-zoom { min-width:38px; text-align:center; color:#9c8bab; font-size:11px; }
.tree-viewport { height:560px; overflow:auto; scrollbar-gutter:stable; cursor:grab; touch-action:none; background-color:#fdfcff; background-image:radial-gradient(#d9d2e940 .8px,transparent .8px); background-size:20px 20px; overscroll-behavior:contain; }
.tree-viewport.is-panning { cursor:grabbing; user-select:none; }.tree-stage-space { position:relative; }.tree-stage { position:absolute; inset:0 auto auto 0; transform-origin:0 0; }.tree-edges { position:absolute; inset:0; pointer-events:none; overflow:visible; }.tree-edges path { fill:none; stroke:#bfb0db; stroke-width:2; }.tree-edges path.edge-to-leaf { stroke:#d3c7e7; stroke-width:1.6; }
.tree-course,.tree-branch,.tree-leaf { position:absolute; box-sizing:border-box; }
.tree-course { display:flex; flex-direction:column; justify-content:center; gap:7px; padding:14px 16px; border:1px solid #bcb0dc; border-radius:15px; background:linear-gradient(130deg,#f0ebfa,#e6dff5); box-shadow:0 6px 18px #785da610; }.tree-course>span { display:flex; align-items:center; gap:6px; font-size:11px; color:#907ba7; }.tree-course strong { font-size:16px; line-height:1.3; color:#584374; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.tree-course small { font-size:11px; color:#9a85b0; }
.tree-branch { display:flex; flex-direction:column; justify-content:center; gap:8px; padding:14px 27px 14px 16px; text-align:left; border:1px solid #dbd0eb; border-radius:12px; background:#fff; box-shadow:0 3px 13px #68488708; cursor:pointer; }.tree-branch:hover { border-color:#a78ac8; }.tree-branch.expanded { border-color:#c7b5df; background:#faf7ff; }.tree-branch-name { font-size:15px; font-weight:600; color:#6a507f; line-height:1.45; }.tree-branch-meta { font-size:11px; color:#a08cae; }.tree-branch-toggle { position:absolute; right:-11px; top:33px; width:22px; height:22px; display:grid; place-items:center; border:1px solid #d2c3e3; border-radius:50%; background:#fff; color:#9b82b4; }
.tree-leaf { display:flex; align-items:center; gap:14px; padding:0; border:0; text-align:left; background:transparent; cursor:pointer; --orb-color:#9580c8; --orb-light:#faf6ff; --orb-dark:#665186; }.tree-leaf.supported_mastery { --orb-color:#72a996; --orb-light:#f1fbf6; --orb-dark:#447967; }.tree-leaf.needs_review { --orb-color:#cca06a; --orb-light:#fff9ee; --orb-dark:#977049; }
.mastery-orb { display:grid; place-items:center; flex:none; width:80px; height:80px; border-radius:50%; padding:3px; background:conic-gradient(var(--orb-color) var(--mastery-angle),#eae4f1 0); box-shadow:0 6px 16px #76559612; transition:transform 160ms ease,box-shadow 160ms ease; }.orb-core { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:3px; width:100%; height:100%; border:3px solid #fff; border-radius:50%; background:radial-gradient(circle at 32% 24%,#fff,var(--orb-light) 65%,#ede7f530); }.orb-core strong { font-size:23px; color:var(--orb-dark); font-weight:650; letter-spacing:-.8px; font-variant-numeric:tabular-nums; }.orb-core strong small { font-size:11px; margin-left:1px; font-weight:500; }.orb-core>span { font-size:10px; color:#a295ac; }
.tree-leaf.unassessed .mastery-orb { background:#fff; border:1px dashed #c6bbd0; box-shadow:none; padding:3px; }.tree-leaf.unassessed .orb-core { background:#f7f5fa; }.tree-leaf.unassessed .orb-core strong { font-size:21px; color:#afa3b9; }
.tree-leaf-copy { display:flex; flex-direction:column; gap:7px; min-width:0; }.tree-leaf-copy strong { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-size:14px; font-weight:500; line-height:1.65; color:#6c5e7d; }.tree-leaf-copy>small { display:flex; gap:4px; align-items:center; color:#a290b0; font-size:11px; }.tree-leaf:hover .mastery-orb { transform:translateY(-2px); box-shadow:0 9px 20px #75539020; }.tree-leaf:hover .tree-leaf-copy strong { color:#745695; }
.tree-help { display:flex; align-items:center; gap:7px; flex-wrap:wrap; padding:11px 16px; border-top:1px solid #ece7f2; background:#fff; color:#a18db0; font-size:12px; }.tree-help span:last-child:not(:nth-child(2)) { margin-left:auto; }.tree-no-results { display:grid; place-items:center; height:280px; color:#a593b3; font-size:14px; }
button:focus-visible,.tree-viewport:focus-visible,input:focus-visible { outline:2px solid #9376be; outline-offset:3px; }.tree-leaf:focus-visible { outline-offset:5px; border-radius:12px; }
@media(max-width:900px) { .tree-toolbar { flex-wrap:wrap; }.tree-search { max-width:none; flex:1; }.tree-viewport { height:500px; } }
@media(prefers-reduced-motion:reduce) { .mastery-orb { transition:none; }.tree-leaf:hover .mastery-orb { transform:none; } }
</style>

<style scoped>
.tree-branch.pending{border-style:dashed;background:#faf9fd;color:#897996;opacity:1;cursor:default}.tree-branch.pending .tree-branch-meta{color:#94859e}
</style>
