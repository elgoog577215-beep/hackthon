<template>
  <section class="handout-reference" :aria-label="c('reference')">
    <ReadingAidToolbar v-model:scope="scope" v-model:query="query" :placeholder="c('referenceSearch')" :current-title="sections.find(section => section.id === currentSection)?.title" />
    <div ref="results" class="reference-results" @scroll="rememberPosition" tabindex="0" :aria-label="c('reference')">
      <section v-for="section in visible" :key="section.id" class="reference-section" :class="{ 'is-current': section.id === currentSection }" :data-reference-section="section.id">
        <h3><MathText :content="section.title" /></h3>
        <article v-for="item in section.items" :key="item.id" class="reference-item" :data-reference-kind="item.kind"><button type="button" class="reference-open" :aria-label="`${c('referenceJump')}：${item.title}`" @click="emit('jump', item.blockId)">
          <span class="reference-item-heading">
            <span class="reference-item-title"><MathText :content="item.title" /></span>
            <span class="reference-jump">{{ c('referenceJump') }} <ArrowUpRight :size="14" aria-hidden="true" /></span>
          </span>
          <span v-if="item.kind === 'formula'" class="reference-math" v-html="item.html" />
        </button><div v-if="item.kind !== 'formula'" class="reference-excerpt">
          <div v-html="item.previewHtml || item.html" />
          <details v-if="item.remainderHtml" class="reference-details">
            <summary><span class="reference-expand">{{ c('referenceExpand') }}</span><span class="reference-collapse">{{ c('referenceCollapse') }}</span></summary>
            <div v-html="item.remainderHtml" />
          </details>
        </div></article>
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
const props = defineProps<{ sections: ReferenceSection[]; currentSection: string }>()
const emit = defineEmits<{ jump: [blockId: string] }>()
const scope = ref<'all' | 'current'>('current'), query = ref('')
const index = computed(() => buildHandoutReference(props.sections).map((section, index) => ({ ...section, number: index + 1 })))
const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return index.value.filter(section => scope.value === 'all' || section.id === (props.currentSection || props.sections[0]?.id))
    .map(section => ({ ...section, items: section.items.filter(item =>
      (!item.includedInStatement && ['formula', 'definition', 'theorem', 'result', 'method', 'warning'].includes(item.kind))
      && (!needle || `${section.title} ${item.title} ${item.content}`.toLocaleLowerCase().includes(needle)),
    ) })).filter(section => section.items.length)
})
const count = computed(() => visible.value.reduce((sum, section) => sum + section.items.length, 0))
const results = ref<HTMLElement | null>(null)
let savedScrollTop = 0, deactivated = false
function rememberPosition() { if (!deactivated && results.value) savedScrollTop = results.value.scrollTop }
onDeactivated(() => { deactivated = true })
onActivated(() => { deactivated = false; void nextTick(() => { if (results.value) results.value.scrollTop = savedScrollTop }) })
async function revealCurrentSection() {
  await nextTick()
  const root = results.value
  if (!root || deactivated || query.value.trim()) return
  const section = Array.from(root.querySelectorAll<HTMLElement>('[data-reference-section]')).find(node => node.dataset.referenceSection === props.currentSection)
  if (section) root.scrollTop += section.getBoundingClientRect().top - root.getBoundingClientRect().top
}
watch(() => props.currentSection, () => { if (scope.value === 'all') void revealCurrentSection() })
watch(scope, () => { if (scope.value === 'all') void revealCurrentSection() })
watch([scope, query, () => scope.value === 'current' ? props.currentSection : ''], () => {
  savedScrollTop = 0
  if (results.value) results.value.scrollTop = 0
})
</script>

<style scoped>
.handout-reference { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; overflow:hidden; color:#343c50; background:#fff; font:15px/1.65 var(--study-ui-font); }
.handout-reference button:focus-visible,.reference-results:focus-visible { outline:2px solid #8875b2; outline-offset:-2px; }
.reference-results { flex:1; min-height:0; overflow:auto; overscroll-behavior:contain; padding:0 16px 24px; scrollbar-width:thin; }
.reference-section { margin:16px 0 20px; }
.reference-section h3 { margin:0 0 4px; color:#505c72; font-size:14px; font-weight:600; line-height:1.55; overflow-wrap:anywhere; }
.reference-section.is-current h3 { padding:3px 6px; border-radius:7px; background:#d6eaff; color:#1f4f7a; }
.reference-open { display:block; width:100%; border:0; padding:0; background:transparent; color:inherit; font:inherit; text-align:left; cursor:pointer; }
.reference-item { display:block; width:100%; min-width:0; margin:5px 0; padding:16px 0; border:0; border-bottom:1px solid #eceff4; border-radius:0; background:#fff; color:inherit; text-align:left; font:inherit; overflow-wrap:anywhere; }
.reference-open:hover .reference-item-title { color:#513279; }
.reference-item-heading { display:flex; align-items:center; gap:6px; }
.reference-item-title { flex:1; min-width:0; font-size:17px; line-height:1.5; color:#6e4a9c; font-weight:600; }
.reference-jump { display:inline-flex; align-items:center; gap:3px; flex:none; color:#69587f; font-size:12px; font-weight:400; }
.reference-math { display:block; max-width:100%; overflow-x:auto; padding:2px 0; text-align:center; font-size:17px; }
.reference-math :deep(.reference-formula) { padding:5px 0; }
.reference-item :deep(.katex-display) { max-width:100%; overflow-x:auto; overflow-y:hidden; padding:4px 0; margin:.4em 0; }
.reference-empty { margin:24px 4px; color:#687287; font-size:14px; }
.reference-sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
.reference-excerpt { display:block; color:#454f62; font-size:15px; line-height:1.75; }
.reference-excerpt :deep(pre) { overflow:auto; white-space:pre; font-size:13px; }
.reference-excerpt :deep(p) { margin:10px 0; }
.reference-excerpt :deep(strong) { font-weight:600; }
.reference-details summary { width:fit-content; padding:6px 0; color:#6e4a9c; cursor:pointer; font-size:14px; }
.reference-collapse,.reference-details[open] .reference-expand { display:none; }
.reference-details[open] .reference-collapse { display:inline; }
.reference-details summary:focus-visible { outline:2px solid #8875b2; outline-offset:2px; }
@media(max-width:760px) { .reference-item { padding:12px; } .reference-item-title { font-size:15px; } }
</style>
