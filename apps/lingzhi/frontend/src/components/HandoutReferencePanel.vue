<template>
  <section class="handout-reference" :aria-label="c('reference')">
    <div class="reference-controls">
      <div class="reference-scope" role="group" :aria-label="c('referenceScope')">
        <button v-for="value in scopes" :key="value" type="button" :aria-pressed="scope === value" @click="scope = value">{{ c(value === 'all' ? 'referenceAllCourse' : 'referenceCurrent') }}</button>
      </div>
      <div class="reference-kinds" role="group" :aria-label="c('referenceKind')">
        <button v-for="option in kinds" :key="option.value" type="button" :aria-pressed="kind === option.value" @click="kind = option.value">{{ c(option.label) }}</button>
      </div>
      <div class="reference-search"><Search :size="16" aria-hidden="true" /><input v-model="query" type="search" :placeholder="c('referenceSearch')" :aria-label="c('referenceSearch')" /></div>
    </div>
    <div ref="results" class="reference-results" @scroll="rememberPosition" tabindex="0" :aria-label="c('reference')">
      <p class="reference-count" role="status" :title="c('referenceHint')">{{ c('referenceCount') }} · {{ count }}</p>
      <section v-for="section in visible" :key="section.id" class="reference-section" :class="{ 'is-current': section.id === currentSection }">
        <h3><span class="reference-section-number">{{ String(section.number).padStart(2, '0') }}</span><MathText :content="section.title" /></h3>
        <article v-for="item in section.items" :key="item.id" class="reference-item" :data-reference-kind="item.kind">
          <header>
            <h4><span class="reference-kind-label">{{ c(kindLabels[item.kind]) }} · </span><MathText :content="item.title" /></h4>
            <button type="button" class="reference-jump" :aria-label="`${c('referenceJump')}：${item.title}`" :title="c('referenceJump')" @click="emit('jump', item.blockId)"><ArrowUpRight :size="17" aria-hidden="true" /><span class="reference-sr-only">{{ c('referenceJump') }}</span></button>
          </header>
          <div v-if="item.html" class="reference-math" v-html="item.html" />
          <MarkdownRenderer v-else :content="item.content" :enable-code-run="false" />
        </article>
      </section>
      <p v-if="!count" class="reference-empty">{{ c(query.trim() ? 'referenceNoMatches' : 'referenceEmpty') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, ref, watch } from 'vue'
import { ArrowUpRight, Search } from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MathText from './MathText.vue'
import { studyCopy as c, type StudyCopyKey } from '../shared/study-copy'
import { buildHandoutReference, type ReferenceKind, type ReferenceSection } from '../utils/handout-reference'
const props = defineProps<{ sections: ReferenceSection[]; currentSection: string }>()
const emit = defineEmits<{ jump: [blockId: string] }>()
const scopes = ['all', 'current'] as const
const scope = ref<'all' | 'current'>('all'), kind = ref<'all' | ReferenceKind>('all'), query = ref('')
const kindLabels = { formula: 'referenceFormula', definition: 'referenceDefinition', theorem: 'referenceTheorem' } as const
const kinds: { value: 'all' | ReferenceKind; label: StudyCopyKey }[] = [
  { value: 'all', label: 'referenceAll' },
  { value: 'formula', label: 'referenceFormula' },
  { value: 'definition', label: 'referenceDefinition' },
  { value: 'theorem', label: 'referenceTheorem' },
]
const index = computed(() => buildHandoutReference(props.sections).map((section, index) => ({ ...section, number: index + 1 })))
const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return index.value.filter(section => scope.value === 'all' || section.id === (props.currentSection || props.sections[0]?.id))
    .map(section => ({ ...section, items: section.items.filter(item =>
      (kind.value === 'all' ? !item.includedInStatement : item.kind === kind.value)
      && (!needle || `${section.title} ${item.title} ${item.content}`.toLocaleLowerCase().includes(needle)),
    ) })).filter(section => section.items.length)
})
const count = computed(() => visible.value.reduce((sum, section) => sum + section.items.length, 0))
const results = ref<HTMLElement | null>(null)
let savedScrollTop = 0, deactivated = false
function rememberPosition() { if (!deactivated && results.value) savedScrollTop = results.value.scrollTop }
onDeactivated(() => { deactivated = true })
onActivated(() => { deactivated = false; void nextTick(() => { if (results.value) results.value.scrollTop = savedScrollTop }) })
watch([scope, kind, query, () => scope.value === 'current' ? props.currentSection : ''], () => {
  savedScrollTop = 0
  if (results.value) results.value.scrollTop = 0
})
</script>

<style scoped>
.handout-reference { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; overflow:hidden; color:#343c50; background:#fafbfe; font:15px/1.65 var(--study-ui-font); }
.reference-controls { flex:none; padding:14px 16px 12px; border-bottom:1px solid #e7eaf2; background:#fff; }
.handout-reference button { font:inherit; cursor:pointer; color:#626b80; background:transparent; border:0; }
.reference-scope { display:grid; grid-template-columns:1fr 1fr; gap:3px; padding:3px; border-radius:9px; background:#f0f1f6; }
.reference-scope button { min-height:34px; padding:4px 8px; border-radius:7px; font-size:14px; line-height:1.4; }
.reference-scope button[aria-pressed=true] { color:#62529a; background:#fff; box-shadow:0 1px 4px #28354b0d; font-weight:600; }
.reference-kinds { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:4px; margin:10px 0; }
.reference-kinds button { min-height:34px; padding:4px 2px; border-radius:6px; font-size:14px; }
.reference-kinds button[aria-pressed=true] { background:#eeebf7; color:#645099; font-weight:600; }
.reference-search { display:flex; align-items:center; gap:8px; border:1px solid #e5e7ef; border-radius:8px; background:#f8f9fc; padding:0 10px; color:#9299aa; }
.reference-search input { box-sizing:border-box; width:100%; min-width:0; min-height:36px; padding:6px 0; border:0; outline:none; font:inherit; font-size:14px; background:transparent; color:#343c50; }
.reference-search:focus-within { border-color:#9c8bbe; box-shadow:0 0 0 2px #9c8bbe16; }
.handout-reference button:focus-visible,.reference-results:focus-visible { outline:2px solid #8875b2; outline-offset:-2px; }
.reference-results { flex:1; min-height:0; overflow:auto; overscroll-behavior:contain; padding:0 14px 24px; scrollbar-width:thin; scrollbar-color:#d9dce8 transparent; }
.reference-count { margin:10px 2px; color:#858d9f; font-size:12px; }
.reference-section { margin-bottom:20px; }
.reference-section h3 { display:flex; align-items:baseline; gap:8px; padding:7px 9px; margin:0 0 9px; border-radius:7px; color:#505c72; background:#edf1f7; font-size:14px; font-weight:600; line-height:1.55; overflow-wrap:anywhere; }
.reference-section.is-current h3 { background:#e5eefb; color:#385e91; }
.reference-section-number { flex:none; font-size:12px; font-variant-numeric:tabular-nums; opacity:.7; }
.reference-item { min-width:0; margin-bottom:8px; padding:10px 12px 12px; border:1px solid #e7eaf1; border-radius:10px; background:#fff; overflow-wrap:anywhere; }
.reference-item header { display:flex; align-items:flex-start; gap:6px; margin-bottom:6px; }
.reference-item h4 { flex:1; min-width:0; margin:2px 0 0; font-size:14px; line-height:1.65; color:#7456a2; font-weight:600; }
.reference-kind-label { font-weight:500; }
.handout-reference .reference-jump { display:grid; place-items:center; flex:none; min-width:32px; min-height:32px; padding:4px; margin:-2px -5px 0 0; border-radius:6px; color:#8c86a3; }
.handout-reference .reference-jump:hover { color:#654b94; background:#f1eef8; }
.reference-item :deep(.markdown-renderer) { font-size:15px; line-height:1.8; min-width:0; }
.reference-item :deep(.markdown-renderer > :first-child) { margin-top:0; }
.reference-item :deep(.markdown-renderer > :last-child) { margin-bottom:0; }
.reference-math { max-width:100%; overflow-x:auto; padding:2px 0; text-align:center; }
.reference-math :deep(.reference-formula) { padding:5px 0; }
.reference-item :deep(.katex-display) { max-width:100%; overflow-x:auto; overflow-y:hidden; padding:4px 0; margin:.4em 0; }
.reference-item :deep(.code-block-wrapper) { margin:12px 0; border:0; border-radius:8px; box-shadow:none; }
.reference-item :deep(.markdown-code-tools) { padding:5px 10px 0; gap:7px; }
.reference-item :deep(.markdown-code-tools span),.reference-item :deep(.copy-btn) { font-size:12px; }
.reference-item :deep(.copy-btn) { min-height:28px; padding:3px 7px; border-radius:5px; }
.reference-item :deep(pre) { max-width:100%; overflow-x:auto; margin:0; padding:10px 12px 12px; font-size:13px; line-height:1.65; }
.reference-item :deep(table) { display:block; max-width:100%; overflow-x:auto; }
.reference-item :deep(img) { max-width:100%; }
.reference-empty { margin:24px 4px; color:#778095; font-size:14px; }
.reference-sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
@media(max-width:760px) {
  .reference-controls { padding:10px 12px; }
  .reference-results { padding:0 12px 20px; }
  .reference-scope button,.reference-kinds button,.reference-search input { min-height:44px; }
  .reference-search input { font-size:16px; }
  .reference-item :deep(.copy-btn) { min-width:44px; min-height:44px; }
  .reference-kinds { margin:6px 0; }
  .reference-kinds button { font-size:13px; padding-inline:0; }
  .handout-reference .reference-jump { min-width:44px; min-height:44px; margin:-6px -6px -4px 0; }
}
</style>
