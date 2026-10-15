<template>
  <aside ref="panel" class="handout-concept-map" :aria-label="tr('title')" :style="availableHeight == null ? undefined : { '--handout-aside-available-height': `${availableHeight}px` }" tabindex="0" data-handout-print-exclude>
    <header><span class="concept-eyebrow">{{ tr('eyebrow') }}</span><h3>{{ tr('title') }}</h3><p>{{ tr('hint') }}</p></header>
    <nav v-if="sections.length > 1" class="concept-sections" :aria-label="tr('sections')">
      <button v-for="section in sections" :key="section.id" :aria-pressed="current?.id === section.id" @click="chooseSection(section.id)"><MathText :content="section.title" /></button>
    </nav>
    <p v-if="current?.sourceStatus" class="concept-source-state" role="status">{{ tr(`source.${current.sourceStatus}`) }}</p>
    <template v-if="current?.nodes.length">
      <div class="concept-section-title"><MathText :content="current.title" /><span>{{ current.nodes.length }} {{ tr('concepts') }}</span></div>
      <div ref="graph" class="concept-graph" :aria-label="tr('graph')">
        <svg aria-hidden="true" class="concept-edges">
          <defs><marker :id="markerId" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" /></marker></defs>
          <g v-for="edge in paths" :key="edge.relation.id" :class="['concept-edge', `is-${edge.relation.type}`, { 'is-muted': selected && !connected(edge.relation) }]">
            <path :d="edge.path" :marker-end="`url(#${markerId})`" :marker-start="symmetric(edge.relation) ? `url(#${markerId})` : undefined" />
            <text :x="edge.x" :y="edge.y">{{ relationLabel(edge.relation.type) }}</text>
          </g>
        </svg>
        <div v-for="(row, index) in layers" :key="index" class="concept-row">
          <button v-for="node in row" :key="node.id" :data-concept-id="node.id" :class="{ selected: selected === node.id, external: node.external }" :aria-pressed="selected === node.id" @click="selectConcept(node)"><MathText :content="node.name" /><small v-if="node.external">{{ tr('prior') }}</small></button>
        </div>
      </div>
      <div v-if="selectedNode" class="concept-detail">
        <strong><MathText :content="selectedNode.name" /></strong>
        <MathText v-if="selectedNode.statement" tag="p" :content="selectedNode.statement" />
        <button v-if="selectedNode.anchor" class="concept-jump" @click="jump(selectedNode.anchor)">{{ tr('jump') }} <span aria-hidden="true">↗</span></button>
        <p v-else class="concept-empty">{{ tr('noAnchor') }}</p>
      </div>
      <div class="concept-relations">
        <div class="concept-relations-heading"><h4>{{ tr('relations') }}</h4><button v-if="selected" @click="selected = ''">{{ tr('showAll') }}</button></div>
        <article v-for="edge in visibleRelations" :key="edge.id" :class="`is-${edge.type}`">
          <div class="concept-pair"><MathText :content="conceptName(edge.source)" /><span>{{ symmetric(edge) ? '↔' : '→' }}</span><MathText :content="conceptName(edge.target)" /></div>
          <span class="concept-relation-type">{{ relationLabel(edge.type) }}</span><MathText tag="p" :content="edge.reason" />
          <p v-if="edge.conditions.length"><b>{{ tr('conditions') }}</b><MathText :content="edge.conditions.join('；')" /></p>
          <p v-if="edge.groupId && ['AND', 'OR'].includes(edge.groupOperator)"><b>{{ tr(edge.groupOperator === 'OR' ? 'anyOf' : 'allOf') }}</b><MathText :content="groupNames(edge).join('、')" /></p>
          <p v-if="edge.necessity === 'helpful'" class="concept-source">{{ tr('helpful') }}</p>
          <p v-if="edge.distinction"><b>{{ tr('distinction') }}</b><MathText :content="edge.distinction" /></p>
          <ol v-if="edge.steps.length"><li v-for="step in edge.steps" :key="step"><MathText :content="step" /></li></ol>
          <p v-for="(source, index) in edge.sourceRefs" :key="index" class="concept-source"><MathText :content="sourceLabel(source)" /></p>
        </article>
        <p v-if="!visibleRelations.length" class="concept-empty">{{ tr('noRelations') }}</p>
      </div>
    </template>
    <p v-else class="concept-empty">{{ tr('empty') }}</p>
    <details v-if="current?.coverage" class="concept-coverage" open>
      <summary>{{ tr('coverage.title') }}</summary>
      <p>{{ tr('coverage.hint') }}</p>
      <p v-if="!current.coverage.scope_known">{{ tr('coverage.partialScope') }}</p>
      <div v-if="current.coverage.rows.length" class="coverage-table-wrap">
        <table>
          <caption class="sr-only">{{ tr('coverage.title') }}</caption>
          <thead><tr><th scope="col">{{ tr('coverage.point') }}</th><th scope="col">{{ tr('coverage.explanation') }}</th><th scope="col">{{ tr('coverage.example') }}</th><th scope="col">{{ tr('coverage.exercise') }}</th></tr></thead>
          <tbody><tr v-for="row in current.coverage.rows" :key="row.knowledge_id" :data-knowledge-id="row.knowledge_id">
            <th scope="row"><button v-if="coverageAnchor(row.knowledge_id)" @click="jump(coverageAnchor(row.knowledge_id))"><MathText :content="row.name" /></button><MathText v-else :content="row.name" /><small v-if="!row.block_ids.length">{{ tr('coverage.missing') }}</small></th>
            <td>{{ row.explanation_block_ids.length || '—' }}</td><td>{{ row.example_block_ids.length || '—' }}</td><td>{{ row.exercise_block_ids.length || '—' }}</td>
          </tr></tbody>
        </table>
      </div>
      <p v-if="current.coverage.invalid_refs?.length" role="status">{{ tr('coverage.invalid') }} {{ current.coverage.invalid_refs.length }}</p>
    </details>
    <footer>{{ originLabel || tr(current?.sourceRevision ? 'originPinned' : 'origin') }}</footer>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import MathText from './MathText.vue'
import { t } from '../shared/i18n'
import { conceptLayers, type HandoutConcept, type HandoutConceptSection, type HandoutRelation } from '../utils/handout-concepts'
const props = defineProps<{ sections: HandoutConceptSection[]; target?: HTMLElement | null; originLabel?: string }>()
const tr = (key: string) => t(`handoutConcepts.${key}`)
const relationLabel = (type: string) => t(`handoutConcepts.types.${type}`)
const currentId = ref(''), selected = ref(''), graph = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null), availableHeight = ref<number | null>(null)
const markerId = `handout-arrow-${useId().replace(/[^\w-]/g, '')}`
const current = computed(() => props.sections.find(section => section.id === currentId.value) || props.sections[0])
const layers = computed(() => current.value ? conceptLayers(current.value) : [])
const selectedNode = computed(() => current.value?.nodes.find(node => node.id === selected.value))
const connected = (edge: HandoutRelation) => edge.source === selected.value || edge.target === selected.value
const symmetric = (edge: HandoutRelation) => ['equivalent_to', 'contrasts_with'].includes(edge.type)
const visibleRelations = computed(() => current.value?.relations.filter(edge => !selected.value || connected(edge)) || [])
const paths = ref<{ relation: HandoutRelation; path: string; x: number; y: number }[]>([])
function sourceLabel(source: string | Record<string, unknown>) {
  if (typeof source === 'string') return source
  const locator = source.locator
  let location = typeof locator === 'string' ? locator : ''
  if (locator && typeof locator === 'object' && !Array.isArray(locator)) {
    const value = locator as Record<string, unknown>
    location = [Array.isArray(value.section_path) ? value.section_path.filter(item => typeof item === 'string').join(' › ') : '',
      typeof value.page === 'number' ? `${tr('page')} ${value.page}` : '',
      typeof value.slide === 'number' ? `${tr('slide')} ${value.slide}` : ''].filter(Boolean).join(' · ')
  }
  return [source.filename || source.title || source.source_id || source.evidence_id, location].filter(Boolean).join(' · ')
}
function conceptName(id: string) { return current.value?.nodes.find(node => node.id === id)?.name || id }
function coverageAnchor(id: string) { return current.value?.nodes.find(node => node.id === id)?.anchor || '' }
function groupNames(edge: HandoutRelation) { return [...new Set((current.value?.relations || []).filter(item => item.groupId === edge.groupId).map(item => conceptName(item.source)))] }
function element(id: string): HTMLElement | undefined {
  // Stay inside this handout even if another document has identical anchors.
  return Array.from(props.target?.querySelectorAll<HTMLElement>('[id]') || []).find(node => node.id === id)
}
function jump(anchor: string) {
  const node = element(anchor)
  if (!node) return
  node.querySelectorAll('details').forEach(details => { details.open = true })
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  node.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
  node.classList.remove('handout-concept-flash')
  void node.offsetWidth
  if (!reduced) node.classList.add('handout-concept-flash')
}
function chooseSection(id: string) { currentId.value = id; jump(current.value?.anchor || '') }
function selectConcept(node: HandoutConcept) { selected.value = node.id; if (node.anchor) jump(node.anchor) }
// A reading aside lives inside a scrolling workbench, not necessarily the viewport.
function fitReadingAside() {
  if (!panel.value?.classList.contains('handout-reading-aside')) return
  let top = 0, bottom = window.innerHeight, foundScrollport = false
  for (let parent = panel.value.parentElement; parent; parent = parent.parentElement) {
    const overflow = getComputedStyle(parent).overflowY
    if (!foundScrollport) {
      if (!/^(auto|scroll)$/.test(overflow)) continue
      foundScrollport = true
    }
    if (!/^(auto|scroll|hidden|clip)$/.test(overflow)) continue
    const rect = parent.getBoundingClientRect()
    const contentTop = rect.top + parent.clientTop
    top = Math.max(top, contentTop)
    bottom = Math.min(bottom, contentTop + parent.clientHeight)
  }
  // Keep the same 24px clearance as the sticky reading layout on both ends.
  availableHeight.value = Math.max(0, Math.floor(bottom - top - 48))
}
function draw() {
  const root = graph.value
  if (!root || !current.value) { paths.value = []; return }
  const origin = root.getBoundingClientRect()
  const nodes = new Map(Array.from(root.querySelectorAll<HTMLElement>('[data-concept-id]')).map(node => [node.dataset.conceptId, node.getBoundingClientRect()]))
  paths.value = current.value.relations.flatMap(relation => {
    const a = nodes.get(relation.source), b = nodes.get(relation.target)
    if (!a || !b) return []
    const lateral = Math.abs(a.top - b.top) < 5
    const right = a.left < b.left
    const x1 = (lateral ? right ? a.right : a.left : a.left + a.width / 2) - origin.left
    const x2 = (lateral ? right ? b.left : b.right : b.left + b.width / 2) - origin.left
    const y1 = (lateral ? a.top + a.height / 2 : a.top < b.top ? a.bottom : a.top) - origin.top
    const y2 = (lateral ? b.top + b.height / 2 : a.top < b.top ? b.top : b.bottom) - origin.top
    const middle = (y1 + y2) / 2
    // Lateral labels sit in the gap above the row, away from node text.
    const path = lateral ? `M${x1},${y1} C${x1},${y1-36} ${x2},${y2-36} ${x2},${y2}` : `M${x1},${y1} C${x1},${middle} ${x2},${middle} ${x2},${y2}`
    return [{ relation, path, x: (x1 + x2) / 2, y: lateral ? y1 - 29 : middle - 5 }]
  })
}
let frame = 0, observer: ResizeObserver | undefined, panelObserver: ResizeObserver | undefined
function followReading() {
  if (!props.target) return
  const pane = props.target.closest('.pane-body, .script-document')
  const boundary = Math.max(Math.min(160, window.innerHeight * .2), (pane?.getBoundingClientRect().top || 0) + 36)
  let id = props.sections[0]?.id || ''
  for (const section of props.sections) {
    const positions = [section.anchor, ...section.blockAnchors].map(element).filter(Boolean) as HTMLElement[]
    if (positions.some(node => node.getBoundingClientRect().top <= boundary)) id = section.id
  }
  currentId.value = id
}
function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => { fitReadingAside(); followReading(); draw() }) }
watch(() => props.sections, async () => { await nextTick(); followReading(); draw() }, { deep: true, immediate: true })
watch(current, async (value, previous) => { if (value?.id !== previous?.id) selected.value = ''; await nextTick(); draw() })
watch(graph, node => { observer?.disconnect(); if (node) observer?.observe(node) })
onMounted(() => {
  panelObserver = new ResizeObserver(fitReadingAside)
  if (panel.value?.classList.contains('handout-reading-aside')) {
    for (let parent = panel.value.parentElement; parent; parent = parent.parentElement) panelObserver.observe(parent)
  }
  fitReadingAside()
  observer = new ResizeObserver(draw); if (graph.value) observer.observe(graph.value); window.addEventListener('scroll', schedule, true); window.addEventListener('resize', schedule); draw() })
onBeforeUnmount(() => { panelObserver?.disconnect(); observer?.disconnect(); window.removeEventListener('scroll', schedule, true); window.removeEventListener('resize', schedule); cancelAnimationFrame(frame) })
</script>

<style scoped>
.handout-concept-map{color:#354052;font:15px/1.65 var(--handout-sans);border:1px solid #e1ddec;background:#fbfafc;min-width:0;overflow:auto;overflow-wrap:anywhere}
.handout-concept-map header{padding:20px 20px 14px;border-bottom:1px solid #e7e2ee}.concept-eyebrow{color:#806298;font-size:12px;letter-spacing:1.5px;font-weight:700}.handout-concept-map h3{font:700 21px/1.5 var(--handout-sans);margin:4px 0 8px;color:#403254}.handout-concept-map header p{margin:0;color:#687182;font-size:15px}.concept-section-title{padding:16px 20px 0;display:flex;justify-content:space-between;gap:10px;font-weight:700}.concept-section-title>span:last-child{font-weight:400;color:#806298;white-space:nowrap;font-size:13px}.concept-sections{padding:12px;display:flex;flex-wrap:wrap;gap:6px}.concept-sections button{background:#fff;border:1px solid #e0d8ea;padding:5px 9px;font:15px/1.5 var(--handout-sans);color:inherit;cursor:pointer}.concept-sections button[aria-pressed=true]{background:var(--lz-action-bg);color:var(--lz-action-text);border:1px solid var(--lz-action-border);border-radius:var(--lz-action-radius);box-shadow:var(--lz-action-shadow)}
.concept-graph{position:relative;padding:40px 18px 16px}.concept-edges{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}.concept-edges marker path{fill:#9575b5}.concept-edge>path{fill:none;stroke:#9575b5;stroke-width:1.6}.concept-edge.is-contrasts_with>path{stroke:#a96172;stroke-dasharray:4 3}.concept-edge.is-equivalent_to>path{stroke:#488889}.concept-edge text{font:13px var(--handout-sans);fill:#6e4a9c;paint-order:stroke;stroke:#fbfafc;stroke-width:5px;text-anchor:middle}.concept-edge.is-muted{opacity:.17}.concept-row{position:relative;display:flex;flex-wrap:wrap;justify-content:center;gap:46px 48px;margin-bottom:54px}.concept-row:last-child{margin-bottom:0}.concept-row button{position:relative;border:1px solid var(--lz-action-border);border-radius:var(--lz-action-radius);background:var(--lz-action-bg);padding:9px 10px;max-width:100%;font:600 15px/1.5 var(--handout-sans);color:var(--lz-action-text);cursor:pointer;overflow-wrap:anywhere;box-shadow:var(--lz-action-shadow)}.concept-row button:hover,.concept-row button.selected{background:var(--lz-action-bg);color:var(--lz-action-text);border-color:var(--lz-action-border-hover)}.concept-row button.external{border-style:dashed}.concept-row small{display:block;font-size:12px;font-weight:400}
.concept-detail{margin:0 16px 16px;padding:14px 16px;background:#f0ebf7;border-left:3px solid #6e4a9c}.concept-detail p{margin:8px 0;font:15px/1.65 var(--handout-sans)}.concept-jump,.concept-relations-heading button{border:0;background:none;padding:4px 0;font:15px/1.6 var(--handout-sans);color:#6e4a9c;cursor:pointer}.concept-relations{padding:0 20px 18px}.concept-relations-heading{display:flex;justify-content:space-between;align-items:center;margin:10px 0}.concept-relations h4{font:700 16px/1.6 var(--handout-sans);margin:0}.concept-relations article{padding:14px 0;border-top:1px solid #e6e1ec}.concept-pair{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;font-weight:650}.concept-pair>span:nth-child(2){color:#806298}.concept-relation-type{display:inline-block;color:#6e4a9c;font-size:13px;margin:4px 0}.concept-relations article p{margin:4px 0;font:15px/1.65 var(--handout-sans)}.concept-relations b{font-weight:650;margin-right:6px}.concept-relations ol{margin:8px 0;padding-left:20px;font-size:15px}.concept-source{color:#737c8b;font-size:13px!important}.concept-empty{padding:12px 20px;color:#737c8b;font-size:15px}.concept-detail .concept-empty{padding:0}.handout-concept-map footer{padding:12px 20px;border-top:1px solid #e7e2ee;color:#737c8b;font-size:13px}.handout-concept-map button:focus-visible{outline:3px solid #328dcc;outline-offset:3px}@media print{.handout-concept-map{display:none}}
.concept-source-state{margin:12px 20px;color:#685077;font-size:15px;line-height:1.6}
.concept-coverage{margin:0 16px 18px;border-top:1px solid #dfd6e8;padding-top:14px;font-size:15px}
.concept-coverage summary{cursor:pointer;font-weight:700}.concept-coverage p{color:#685d74;font-size:15px;line-height:1.6}
.coverage-table-wrap{overflow:auto}.concept-coverage table{width:100%;border-collapse:collapse;font-size:15px}.concept-coverage th,.concept-coverage td{padding:9px 5px;border-bottom:1px solid #e5dfeb;text-align:left;vertical-align:top}
.concept-coverage th{font-weight:500}.concept-coverage td{text-align:center}.concept-coverage small{display:block;color:#73526e;font-size:13px}.concept-coverage button{border:0;background:transparent;color:#654386;font:inherit;text-align:left;padding:0;cursor:pointer}
.handout-concept-map:focus-visible,.handout-concept-map button:focus-visible,.concept-coverage summary:focus-visible{outline:3px solid #7953a0;outline-offset:3px}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
</style>
