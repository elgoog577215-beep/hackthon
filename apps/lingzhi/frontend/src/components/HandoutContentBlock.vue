<template>
  <component :is="isAnswerDisclosure ? 'details' : 'div'" class="handout-block"
    :class="[`handout-block--${tone}`, group ? `handout-block--group-${group}` : '', { 'handout-block--answer': isAnswerDisclosure, 'handout-block--continuous': isContinuous }]"
    :style="presentation.style" :data-handout-type="contentType || undefined" :data-handout-group="group" :data-answer-to="answerTo || undefined">
    <component :is="isAnswerDisclosure ? 'summary' : 'header'" v-if="showHeader" class="handout-block__heading">
      <div class="handout-block__identity">
        <div v-if="group || displayLabel" class="handout-block__tags">
          <span v-if="group" class="handout-block__group">{{ t(`courseWorkbench.scriptDocument.contentGroups.${group}`) }}</span>
          <span v-if="displayLabel" class="handout-block__label" :title="definition?.purpose?.[activeLocale]">{{ displayLabel }}</span>
        </div>
        <h5 v-if="title"><MathText :content="displayTitle" /></h5>
      </div>
      <span v-if="isAnswerDisclosure" class="handout-block__disclosure">
        <span class="handout-block__reveal">{{ t('courseWorkbench.scriptDocument.revealAnswer', '展开解答') }}</span>
        <span class="handout-block__hide">{{ t('courseWorkbench.scriptDocument.hideAnswer', '收起解答') }}</span>
        <ChevronDown :size="17" aria-hidden="true" />
      </span>
      <slot v-else name="header-extra" />
    </component>
    <div class="handout-block__body"><slot /></div>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import MathText from './MathText.vue'
import { activeLocale, t } from '../shared/i18n'
import { handoutContentGroup, handoutContentType, handoutTypeDefinition, handoutPresentation } from '../utils/handout-content'
import '../styles/handout-document.css'

const props = withDefaults(defineProps<{
  contentType?: string
  label?: string
  title?: string
  answerTo?: string
  collapseAnswer?: boolean
  streaming?: boolean
  showHeader?: boolean
}>(), { contentType: '', label: '', title: '', answerTo: '', collapseAnswer: true, streaming: false, showHeader: true })

// Keep streaming and interrupted drafts visible; only settled linked answers collapse.
const isAnswerDisclosure = computed(() => Boolean(props.answerTo && props.collapseAnswer && !props.streaming && props.showHeader))
const normalizedType = computed(() => handoutContentType(props.contentType))
const definition = computed(() => handoutTypeDefinition(normalizedType.value))
const group = computed(() => props.answerTo ? undefined : handoutContentGroup(normalizedType.value))
const presentation = computed(() => handoutPresentation(normalizedType.value, activeLocale.value, props.label))
const tone = computed(() => presentation.value.tone)
// Reasoning remains part of the reading flow; emphasis belongs to the claim,
// worked example or task, not to every paragraph that explains it.
const isContinuous = computed(() => tone.value === 'prose' || normalizedType.value === 'derivation')
const displayLabel = computed(() => {
  const label = definition.value?.label[activeLocale.value] || (normalizedType.value ? t(`courseWorkbench.scriptDocument.contentTypes.${normalizedType.value}`, props.label || props.contentType) : props.label)
  return group.value && label === t(`courseWorkbench.scriptDocument.contentGroups.${group.value}`) ? '' : label
})
const displayTitle = computed(() => {
  for (const label of [displayLabel.value, props.label]) {
    if (!label) continue
    for (const separator of ['：', ':']) {
      const prefix = label + separator
      if (props.title.startsWith(prefix)) return props.title.slice(prefix.length).trim() || props.title
    }
  }
  return props.title
})
</script>

<style scoped>
.handout-block{--handout-accent:#657080;--handout-tint:transparent;--handout-edge:#e1e5ec;min-width:0;margin:26px 0;padding:0;color:#242a35;font:18px/1.95 var(--handout-serif)}
.handout-block__heading{display:flex;align-items:baseline;justify-content:space-between;gap:20px;margin-bottom:9px}
.handout-block__identity{min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:8px}
.handout-block__tags{display:flex;align-items:center;flex-wrap:wrap;gap:6px}
.handout-block__label,.handout-block__group{display:inline-flex;align-items:center;min-height:24px;box-sizing:border-box;padding:1px 8px;border:1px solid var(--handout-edge);border-radius:5px;color:var(--handout-accent);background:color-mix(in srgb,var(--handout-accent) 7%,white);font:600 13px/20px var(--handout-sans)}
.handout-block__heading h5{margin:0;color:var(--handout-accent);font:700 15px/1.7 var(--handout-sans);overflow-wrap:anywhere}
.handout-block--continuous>.handout-block__heading{margin:32px 0 14px}
.handout-block--continuous>.handout-block__heading h5{color:#242a35;font:700 20px/1.6 var(--handout-serif)}
.handout-block__body :deep(.markdown-renderer){font:inherit;color:inherit}
.handout-block__body :deep(.markdown-renderer> :first-child){margin-top:0}
.handout-block__body :deep(.markdown-renderer> :last-child){margin-bottom:0}
.handout-block:not(.handout-block--continuous):not(.handout-block--answer){padding:18px 22px 20px;border:0;border-left:3px solid var(--handout-accent);border-radius:0;background:var(--handout-tint)}
.handout-block--answer{padding:0;border:1px solid #dbe3ed;border-radius:0;background:#fafbfd}
.handout-block--answer>.handout-block__heading{align-items:center;margin:0;padding:14px 20px;cursor:pointer;list-style:none}
.handout-block--answer>.handout-block__heading::-webkit-details-marker{display:none}
.handout-block--answer>.handout-block__heading:focus-visible{outline:3px solid #328dcc;outline-offset:3px}
.handout-block--answer>.handout-block__body{padding:6px 20px 20px}
.handout-block--answer>.handout-block__heading h5{color:#315e91;font:650 16px/1.7 var(--handout-sans)}
.handout-block__group{color:#657080;background:#f4f5f8;border-color:#e1e5ec;font-weight:500}

.handout-block:not(.handout-block--continuous):not(.handout-block--answer)>.handout-block__heading{margin:0 0 12px}
.handout-block:not(.handout-block--continuous):not(.handout-block--answer)>.handout-block__heading h5{color:#242a35;font:700 20px/1.6 var(--handout-serif)}
.handout-block--warning .handout-block__label,.handout-block--warning .handout-block__separator{color:#a64355}
.handout-block__disclosure{flex:none;display:flex;align-items:center;gap:8px;color:#315e91;font:650 15px/1.7 var(--handout-sans)}
.handout-block__hide{display:none}
.handout-block[open] .handout-block__reveal{display:none}
.handout-block[open] .handout-block__hide{display:inline}
.handout-block[open] .handout-block__disclosure svg{transform:rotate(180deg)}
@media(max-width:600px){.handout-block__heading{flex-wrap:wrap;gap:8px}.handout-block:not(.handout-block--continuous):not(.handout-block--answer){padding:14px 16px}.handout-block--answer>.handout-block__heading{padding:12px 16px}.handout-block--answer>.handout-block__body{padding:4px 16px 16px}}
@media print{.handout-block{font-size:11pt;print-color-adjust:exact;-webkit-print-color-adjust:exact}.handout-block__heading{break-after:avoid}.handout-block__disclosure{display:none}}
</style>
