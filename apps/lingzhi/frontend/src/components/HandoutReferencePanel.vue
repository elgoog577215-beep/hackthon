<template>
  <section class="handout-reference" :aria-label="c('reference')">
    <ReadingAidToolbar :hide-scope="true" :label="c('referenceCatalog')" v-model:scope="scope" v-model:query="query" :placeholder="c('referenceSearch')" :current-title="sections.find(section => section.id === currentSection)?.title" />
    <p v-if="hasUnavailableReferences" class="reference-source-note" role="status">{{ c('referenceUnavailable') }}</p>
    <div ref="results" class="reference-results" @scroll="rememberPosition" tabindex="0" :aria-label="c('reference')">
      <section v-for="section in visible" :key="section.id" class="reference-section" :class="{ 'is-current': section.id === currentSection }" :data-reference-section="section.id">
        <h3><MathText :content="section.title" /></h3>
        <article v-for="item in section.items" :key="item.id" class="reference-item" @click="openCard($event, item.blockId, item.id)" :data-reference-kind="item.kind" :data-reference-block="item.blockId" :data-reference-id="item.id" :class="{ 'is-current': item.id === activeReferenceId }"><button type="button" class="reference-open" :aria-label="`${c('referenceJump')}：${item.title}`" @click="emit('jump', item.blockId, item.id)">
          <span class="reference-item-heading">
            <span class="reference-item-number">{{ item.number }}</span><span class="reference-item-title"><MathText :content="item.title" /></span>
            <span class="reference-jump" aria-hidden="true"><ArrowUpRight :size="14" aria-hidden="true" /></span>
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
import ReadingAidToolbar from './ReadingAidToolbar.vue'
import { computed, nextTick, onActivated, onDeactivated, ref, watch } from 'vue'
import { ArrowUpRight } from 'lucide-vue-next'
import MathText from './MathText.vue'
import { studyCopy as c } from '../shared/study-copy'
import { buildHandoutReference, type ReferenceSection } from '../utils/handout-reference'
const props = defineProps<{ sections: ReferenceSection[]; currentSection: string; currentBlock?: string; currentReference?: string }>()
const emit = defineEmits<{ jump: [blockId: string, referenceId?: string] }>()
const query = ref('')
const scope = ref<'all' | 'current'>('all')
const index = computed(() => buildHandoutReference(props.sections))
const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return index.value.map(section => ({ ...section, items: section.items.map((item, itemIndex) => ({ ...item, number: itemIndex + 1 })).filter(item => !needle || `${section.title} ${item.title} ${item.content}`.toLocaleLowerCase().includes(needle)) })).filter(s => s.items.length)
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
let savedScrollTop = 0, deactivated = false
function rememberPosition() { if (!deactivated && results.value) savedScrollTop = results.value.scrollTop }
function openCard(event: MouseEvent, blockId: string, referenceId: string) {
  if ((event.target as HTMLElement).closest('a,button,input,summary')) return
  const selection = window.getSelection()
  if (selection && !selection.isCollapsed && selection.anchorNode && (event.currentTarget as HTMLElement).contains(selection.anchorNode)) return
  emit('jump', blockId, referenceId)
}
watch(query, () => { if (results.value) results.value.scrollTop = 0 })
onDeactivated(() => { deactivated = true })
onActivated(async () => { deactivated = false; await nextTick(); if (results.value) results.value.scrollTop = savedScrollTop })
</script>

<style scoped>
.handout-reference { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; overflow:hidden; color:#343c50; background:#fff; font:15px/1.65 var(--study-ui-font); }
.handout-reference button:focus-visible,.reference-results:focus-visible { outline:2px solid #8875b2; outline-offset:-2px; }
.reference-results { flex:1; min-height:0; overflow:auto; overscroll-behavior:contain; padding:0 12px 16px; scrollbar-width:thin; }
.reference-section { margin:16px 0 20px; }
.reference-section h3 { margin:0 0 4px; color:#505c72; font-size:14px; font-weight:600; line-height:1.55; overflow-wrap:anywhere; }
.reference-section.is-current h3 { padding:3px 6px; border-radius:7px; background:#d6eaff; color:#1f4f7a; }
.reference-open { display:block; width:100%; border:0; padding:0; background:transparent; color:inherit; font:inherit; text-align:left; cursor:pointer; }
.reference-item { display:block; width:100%; min-width:0; margin:6px 0; padding:8px 10px; border:1px solid #eceff4; border-radius:10px; background:#fff; color:inherit; text-align:left; font:inherit; overflow-wrap:anywhere; }
.reference-item:hover .reference-item-title { color:#513279; }
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
.reference-item.is-current { border-color:#b6cde6; }
@media(max-width:760px) { .reference-item { padding:12px; } .reference-item-title { font-size:15px; } }
</style>

<style scoped>
.reference-item { cursor:pointer; transition:border-color .15s; }
.reference-item:hover { border-color:#b6cde6; }
.reference-jump { opacity:0; transition:opacity .15s; }
.reference-item:hover .reference-jump,.reference-item:focus-within .reference-jump { opacity:1; }
.reference-section h3 { padding:5px 8px; margin:12px 0 6px; border-radius:8px; background:#f0f1f5; color:#3a4250; font-weight:650; }
.reference-section.is-current h3 { padding:5px 8px; }
</style>

<style scoped>
.reference-section h3 { display:flex; gap:9px; align-items:baseline; font-size:15px; line-height:1.55; }

.reference-item-heading { align-items:baseline; gap:8px; }
.reference-item-number { flex:none; color:#7c7388; font-size:12px; font-weight:500; font-variant-numeric:tabular-nums; }
.reference-expression { margin-left:0; }
</style>
