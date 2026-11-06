<template>
  <section class="handout-reference" :aria-label="c('reference')">
    <ReadingAidToolbar :hide-scope="true" v-model:scope="scope" v-model:query="query" :placeholder="c('referenceSearch')" :current-title="sections.find(section => section.id === currentSection)?.title" />
    <p v-if="hasUnavailableReferences" class="reference-source-note" role="status">{{ c('referenceUnavailable') }}</p>
    <div ref="results" class="reference-results" @scroll="onReferenceScroll" @wheel.passive="claim" @pointerdown="claimScrollbar" @keydown="claimKeys" tabindex="0" :aria-label="c('reference')">
      <section v-for="section in visible" :key="section.id" class="reference-section" :class="{ 'is-current': section.id === currentSection }" :data-reference-section="section.id">
        <h3><MathText :content="section.title" /></h3>
        <article v-for="item in section.items" :key="item.id" class="reference-item" :data-reference-kind="item.kind" :data-reference-block="item.blockId" :data-reference-id="item.id" :class="{ 'is-current': item.id === activeReferenceId }"><button type="button" class="reference-open" :aria-label="`${c('referenceJump')}：${item.title}`" @click="emit('jump', item.blockId, item.id)">
          <span class="reference-item-heading">
            <span class="reference-item-title"><MathText :content="item.title" /></span>
            <span class="reference-jump">{{ c('referenceJump') }} <ArrowUpRight :size="14" aria-hidden="true" /></span>
          </span>
        </button>
          <div v-if="item.html" class="reference-expression" v-html="item.html" />
          <p v-if="item.mode === 'source'" class="reference-source-note">{{ c('referenceLegacy') }}</p>
        </article>
      </section>
      <p v-if="!count" class="reference-empty">{{ c(query.trim() ? 'referenceNoMatches' : 'referenceEmpty') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { readingScrollKeys, type ReadingOwner } from '../composables/useReadingNavigation'
import ReadingAidToolbar from './ReadingAidToolbar.vue'
import { computed, nextTick, onActivated, onDeactivated, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowUpRight } from 'lucide-vue-next'
import MathText from './MathText.vue'
import { studyCopy as c } from '../shared/study-copy'
import { buildHandoutReference, type ReferenceSection } from '../utils/handout-reference'
const props = defineProps<{ sections: ReferenceSection[]; currentSection: string; currentBlock?: string; navigationOwner?: ReadingOwner; currentReference?: string }>()
const emit = defineEmits<{ jump: [blockId: string, referenceId?: string]; follow: [blockId: string, referenceId: string]; claim: [] }>()
const query = ref('')
const scope = ref<'all' | 'current'>('all')
const index = computed(() => buildHandoutReference(props.sections))
const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return index.value.map(section => ({ ...section, items: section.items.filter(item => !needle || `${section.title} ${item.title} ${item.content}`.toLocaleLowerCase().includes(needle)) })).filter(s => s.items.length)
})
const activeReferenceId = computed(() => {
  if (props.currentReference) return props.currentReference
  const section = index.value.find(s => s.id === props.currentSection)
  const blocks = props.sections.find(s => s.id === props.currentSection)?.blocks || []
  const position = blocks.findIndex(b => b.block_id === props.currentBlock)
  const exactBlock = section?.items.find(item => item.blockId === props.currentBlock)
  if (exactBlock) return exactBlock.id
  const preceding = section?.items.filter(item => blocks.findIndex(b => b.block_id === item.blockId) <= position) || []
  return preceding.at(-1)?.id || section?.items[0]?.id || ''
})
const hasUnavailableReferences = computed(() => props.sections.some(section => section.blocks.some(block =>
  (block.reference_issues?.length || 0) > 0 || block.reference_schema_version && (block.references?.length || 0)
    > (index.value.find(s => s.id === section.id)?.items.filter(item => item.blockId === block.block_id && item.mode === 'range').length || 0),
)))
const count = computed(() => visible.value.reduce((sum, section) => sum + section.items.length, 0))
const results = ref<HTMLElement | null>(null)
let savedScrollTop = 0, deactivated = false, userIntent = false, frame = 0
function claim() { userIntent = true; emit('claim'); void nextTick(onReferenceScroll) }
function claimKeys(event: KeyboardEvent) { if (readingScrollKeys.has(event.key)) claim() }
function claimScrollbar(event: PointerEvent) { if (event.target === results.value) claim() }
function rememberPosition() { if (!deactivated && results.value) savedScrollTop = results.value.scrollTop }
function onReferenceScroll() {
  rememberPosition()
  if (!userIntent || props.navigationOwner !== 'reference' || query.value.trim() || deactivated) return
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    const root = results.value
    if (!root || deactivated || props.navigationOwner !== 'reference') return
    const top = root.getBoundingClientRect().top
    const items = Array.from(root.querySelectorAll<HTMLElement>('[data-reference-block]'))
    const atBottom = root.scrollHeight > root.clientHeight && root.scrollHeight - root.scrollTop - root.clientHeight <= 2
    const active = atBottom ? items.at(-1) : items.find(item => item.getBoundingClientRect().bottom > top + 12)
    if (active?.dataset.referenceBlock && active.dataset.referenceId && active.dataset.referenceId !== props.currentReference) emit('follow', active.dataset.referenceBlock, active.dataset.referenceId)
  })
}
async function followDocument() {
  await nextTick()
  const root = results.value
  if (!root || deactivated || props.navigationOwner === 'reference' || query.value.trim()) return
  userIntent = false
  const item = Array.from(root.querySelectorAll<HTMLElement>('[data-reference-id]')).find(node => node.dataset.referenceId === activeReferenceId.value)
  if (!item) return
  const rect = item.getBoundingClientRect(), bounds = root.getBoundingClientRect()
  // Reveal only when outside the viewport. Never reset to the lecture header.
  if (rect.top < bounds.top || rect.bottom > bounds.bottom) root.scrollTop += rect.top - bounds.top - 8
}
watch(() => [activeReferenceId.value, props.navigationOwner], followDocument, { flush: 'post' })
watch(query, () => { userIntent = false; if (results.value) results.value.scrollTop = 0 })
onBeforeUnmount(() => cancelAnimationFrame(frame))
onDeactivated(() => { deactivated = true; userIntent = false; cancelAnimationFrame(frame) })
onActivated(async () => { deactivated = false; userIntent = false; await nextTick(); if (results.value) results.value.scrollTop = savedScrollTop; await followDocument() })
</script>

<style scoped>
.handout-reference { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; overflow:hidden; color:#343c50; background:#fff; font:15px/1.65 var(--study-ui-font); }
.handout-reference button:focus-visible,.reference-results:focus-visible { outline:2px solid #8875b2; outline-offset:-2px; }
.reference-results { flex:1; min-height:0; overflow:auto; overscroll-behavior:contain; padding:0 12px 16px; scrollbar-width:thin; }
.reference-section { margin:16px 0 20px; }
.reference-section h3 { margin:0 0 4px; color:#505c72; font-size:14px; font-weight:600; line-height:1.55; overflow-wrap:anywhere; }
.reference-section.is-current h3 { padding:3px 6px; border-radius:7px; background:#d6eaff; color:#1f4f7a; }
.reference-open { display:block; width:100%; border:0; padding:0; background:transparent; color:inherit; font:inherit; text-align:left; cursor:pointer; }
.reference-item { display:block; width:100%; min-width:0; margin:6px 0; padding:10px 12px; border:1px solid #e9e5ef; border-radius:8px; background:#fff; color:inherit; text-align:left; font:inherit; overflow-wrap:anywhere; }
.reference-open:hover .reference-item-title { color:#513279; }
.reference-item-heading { display:flex; align-items:center; gap:6px; }
.reference-item-title { flex:1; min-width:0; font-size:15px; line-height:1.5; color:#6e4a9c; font-weight:600; }
.reference-jump { display:inline-flex; align-items:center; gap:3px; flex:none; color:#69587f; font-size:12px; font-weight:400; }
.reference-math { display:block; max-width:100%; overflow-x:auto; padding:2px 0; text-align:center; font-size:17px; }
.reference-math :deep(.reference-formula) { padding:5px 0; }
.reference-item :deep(.katex-display) { max-width:100%; overflow-x:auto; overflow-y:hidden; padding:4px 0; margin:.4em 0; }
.reference-empty { margin:24px 4px; color:#687287; font-size:14px; }
.reference-sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
.reference-expression { color:#343c50; font-size:14px; line-height:1.65; overflow-wrap:anywhere; }
.reference-expression :deep(p) { margin:6px 0; }
.reference-expression :deep(ol),.reference-expression :deep(ul) { margin:6px 0; padding-left:22px; }
.reference-expression :deep(pre) { max-width:100%; overflow-x:auto; font-size:13px; line-height:1.6; padding:10px; border-radius:6px; box-shadow:none; }
.reference-expression :deep(.katex-display) { margin:8px 0; }
.reference-source-note { margin:6px 16px; color:#687287; font-size:13px; line-height:1.6; }
.reference-item .reference-source-note { margin:4px 0; }
.reference-item.is-current { background:#f7f4fb; }
@media(max-width:760px) { .reference-item { padding:12px; } .reference-item-title { font-size:15px; } }
</style>
