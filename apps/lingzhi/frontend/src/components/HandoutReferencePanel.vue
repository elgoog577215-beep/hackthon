<template>
  <section class="handout-reference" :aria-label="c('reference')">
    <div class="reference-controls">
      <p>{{ c('referenceHint') }}</p>
      <div class="reference-scope" role="group" :aria-label="c('referenceScope')">
        <button v-for="value in scopes" :key="value" :aria-pressed="scope === value" @click="scope = value">{{ c(value === 'all' ? 'referenceAllCourse' : 'referenceCurrent') }}</button>
      </div>
      <div class="reference-kinds" role="group" :aria-label="c('referenceKind')">
        <button v-for="option in kinds" :key="option.value" :aria-pressed="kind === option.value" @click="kind = option.value">{{ c(option.label) }}</button>
      </div>
      <input v-model="query" type="search" :placeholder="c('referenceSearch')" :aria-label="c('referenceSearch')" />
    </div>
    <p class="reference-count" role="status">{{ c('referenceCount') }} {{ count }}</p>
    <section v-for="section in visible" :key="section.id" class="reference-section">
      <h3><MathText :content="section.title" /></h3>
      <article v-for="item in section.items" :key="item.id" class="reference-item" :data-reference-kind="item.kind">
        <header><span>{{ c(kindLabels[item.kind]) }}</span><h4><MathText :content="item.title" /></h4></header>
        <div v-if="item.html" class="reference-math" v-html="item.html" />
        <MarkdownRenderer v-else :content="item.content" :enable-code-run="false" />
        <button class="reference-jump" @click="emit('jump', item.blockId)">{{ c('referenceJump') }} <span aria-hidden="true">↗</span></button>
      </article>
    </section>
    <p v-if="!count" class="reference-empty">{{ c(query.trim() ? 'referenceNoMatches' : 'referenceEmpty') }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
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
const index = computed(() => buildHandoutReference(props.sections))
const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return index.value.filter(section => scope.value === 'all' || section.id === (props.currentSection || props.sections[0]?.id))
    .map(section => ({ ...section, items: section.items.filter(item =>
      (kind.value === 'all' ? !item.includedInStatement : item.kind === kind.value)
      && (!needle || `${section.title} ${item.title} ${item.content}`.toLocaleLowerCase().includes(needle)),
    ) })).filter(section => section.items.length)
})
const count = computed(() => visible.value.reduce((sum, section) => sum + section.items.length, 0))
</script>

<style scoped>
.handout-reference{min-width:0;padding:0 20px 24px;color:#303746;font:15px/1.7 var(--study-ui-font)}
.reference-controls{padding:0 0 14px;border-bottom:1px solid #e8eaf0}
.reference-controls p,.reference-empty{color:#6d7586;margin:0 0 14px}
.reference-scope,.reference-kinds{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.handout-reference button{font:inherit;cursor:pointer;border:0;background:transparent;color:#5c6475;border-radius:6px;padding:5px 10px;min-height:36px}
.handout-reference button[aria-pressed=true]{background:var(--lz-brand-soft,#f1edfa);color:var(--lz-brand-strong,#6a47a0);font-weight:650}
.handout-reference button:focus-visible,.reference-controls input:focus-visible{outline:2px solid #7652b5;outline-offset:2px}
.reference-controls input{box-sizing:border-box;width:100%;min-width:0;padding:8px 10px;border:1px solid #dfe3eb;border-radius:7px;font:inherit;background:#fff;color:inherit}
.reference-count{color:#7a8190;font-size:13px;margin:12px 0}
.reference-section h3{font-size:16px;line-height:1.6;margin:22px 0 12px;color:#444b60}
.reference-item{border-top:1px solid #e8eaf0;padding:15px 0 10px;min-width:0;overflow-wrap:anywhere}
.reference-item header{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
.reference-item header>span{flex:none;color:#7652a5;font-size:13px}
.reference-item h4{font-size:15px;line-height:1.7;margin:0;font-weight:650}
.reference-item :deep(.markdown-renderer){font-size:15px;line-height:1.85;min-width:0}
.reference-math{max-width:100%;overflow-x:auto;padding:4px 0}
.reference-math :deep(.reference-formula){padding:6px 0}
.reference-item :deep(.katex-display){max-width:100%;overflow-x:auto;overflow-y:hidden;padding:4px 0}
.reference-item :deep(pre),.reference-item :deep(table){max-width:100%;overflow-x:auto}
.reference-item :deep(img){max-width:100%}
.handout-reference .reference-jump{color:#70509e;padding-left:0;margin-top:6px}
@media(max-width:760px){.handout-reference{padding:0 16px 20px}.handout-reference button{min-height:42px}}
</style>
