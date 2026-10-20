<template>
  <div class="handout-reading-guide" data-handout-print-exclude>
    <div class="handout-reading-guide__legend" :aria-label="tr('colorGuide')">
      <span v-for="group in ['explanation', 'practice', 'question']" :key="group" :class="group" :title="t(`courseWorkbench.scriptDocument.contentGroupHints.${group}`)">{{ t(`courseWorkbench.scriptDocument.contentGroups.${group}`) }}</span>
    </div>
    <div class="handout-reading-guide__actions">
      <button v-if="hasAnswers" type="button" @click="toggleAnswers">{{ tr(allExpanded ? 'collapseAnswers' : 'expandAnswers') }}</button>
      <button type="button" :disabled="!target || printing" @click="printHandout">{{ tr('printHandout') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { t } from '../shared/i18n'
import { printHandoutDocument } from '../utils/handout-print'

const props = defineProps<{ target: HTMLElement | null; title?: string }>()
const allExpanded = ref(false)
const hasAnswers = ref(false)
const printing = ref(false)
const tr = (key: string) => t(`courseWorkbench.scriptDocument.${key}`)
const answers = () => Array.from(props.target?.querySelectorAll<HTMLDetailsElement>('details.handout-block--answer') || [])
function syncAnswers() {
  const nodes = answers()
  hasAnswers.value = nodes.length > 0
  allExpanded.value = nodes.length > 0 && nodes.every(node => node.open)
}
function toggleAnswers() {
  const expanded = !allExpanded.value
  answers().forEach(node => { node.open = expanded })
  syncAnswers()
}
let observer: MutationObserver | undefined
watch(() => props.target, (root, previous) => {
  previous?.removeEventListener('toggle', syncAnswers, true)
  observer?.disconnect()
  root?.addEventListener('toggle', syncAnswers, true)
  if (root) {
    observer = new MutationObserver(syncAnswers)
    observer.observe(root, { childList: true, subtree: true })
  }
  syncAnswers()
}, { immediate: true, flush: 'post' })
onBeforeUnmount(() => {
  props.target?.removeEventListener('toggle', syncAnswers, true)
  observer?.disconnect()
})
async function printHandout() {
  if (!props.target || printing.value) return
  printing.value = true
  try { await printHandoutDocument(props.target, props.title || '') }
  finally { printing.value = false }
}
</script>

<style scoped>
.handout-reading-guide{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px 20px;padding:15px 0;margin:26px 0 32px;border-top:1px solid #e1e5ec;border-bottom:1px solid #e1e5ec;font:15px/1.7 var(--handout-sans);color:#53606e}
.handout-reading-guide__legend,.handout-reading-guide__actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px 20px}
.handout-reading-guide__legend span:before{content:'';display:inline-block;width:5px;height:13px;margin-right:7px;vertical-align:-1px;background:var(--tone)}
.explanation{--tone:#315e91}.practice{--tone:#17815a}.question{--tone:#6e4a9c}
.handout-reading-guide button{border:0;padding:4px 0;background:transparent;color:#526071;font:inherit;cursor:pointer}
.handout-reading-guide button:hover{color:#6e4a9c}.handout-reading-guide button:disabled{opacity:.5;cursor:default}.handout-reading-guide button:focus-visible{outline:3px solid #328dcc;outline-offset:4px}
@media print{.handout-reading-guide{display:none}}
</style>
