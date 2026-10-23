<template>
  <component :is="isAnswerDisclosure ? 'details' : 'div'" class="handout-block"
    :class="[`handout-block--${tone}`, { 'handout-block--answer': isAnswerDisclosure }]"
    :data-handout-type="contentType || undefined" :data-answer-to="answerTo || undefined">
    <component :is="isAnswerDisclosure ? 'summary' : 'header'" v-if="showHeader" class="handout-block__heading">
      <div class="handout-block__identity">
        <span v-if="displayLabel" class="handout-block__label">{{ displayLabel }}</span>
        <span v-if="displayLabel && title" class="handout-block__separator" aria-hidden="true">·</span>
        <h5 v-if="title"><MathText :content="title" /></h5>
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
import { t } from '../shared/i18n'
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
const tone = computed(() => {
  const tones: Record<string, string> = {
    definition: 'definition', 定义: 'definition',
    theorem: 'theorem', 定理: 'theorem', result: 'result', 结论: 'result', summary: 'result',
    example: 'example', 例题: 'example', exercise: 'exercise', 练习: 'exercise', case:'exercise', question:'theorem',
    misconception: 'warning', 辨析: 'warning', warning: 'warning', 易错点: 'warning',
  }
  return tones[props.contentType] || 'prose'
})
// Explanatory paragraphs read as a chapter, rather than a sequence of role badges.
const displayLabel = computed(() => tone.value === 'prose' && ['introduction', 'explanation', 'comparison', 'derivation'].includes(props.contentType) ? '' : props.label)
</script>

<style scoped>
.handout-block{--handout-accent:#657080;--handout-tint:transparent;--handout-edge:#e1e5ec;min-width:0;margin:26px 0;padding:0;color:#242a35;font:18px/1.95 var(--handout-serif)}
.handout-block__heading{display:flex;align-items:baseline;justify-content:space-between;gap:20px;margin-bottom:9px}
.handout-block__identity{min-width:0;display:flex;align-items:baseline;flex-wrap:wrap;gap:5px 8px}
.handout-block__label,.handout-block__separator{flex:none;color:var(--handout-accent);font:700 15px/1.7 var(--handout-sans)}
.handout-block__heading h5{margin:0;color:var(--handout-accent);font:700 15px/1.7 var(--handout-sans);overflow-wrap:anywhere}
.handout-block--prose>.handout-block__heading{margin:36px 0 18px}
.handout-block--prose>.handout-block__heading h5{color:#242a35;font:700 21px/1.6 var(--handout-serif)}
.handout-block__body :deep(.markdown-renderer){font:inherit;color:inherit}
.handout-block__body :deep(.markdown-renderer> :first-child){margin-top:0}
.handout-block__body :deep(.markdown-renderer> :last-child){margin-bottom:0}
.handout-block--definition{--handout-accent:#17815a;--handout-tint:#edf7f2;--handout-edge:#cbe5d8}
.handout-block--theorem{--handout-accent:#6e4a9c;--handout-tint:#f0ecf7;--handout-edge:#d8cce9}
.handout-block--result,.handout-block--exercise{--handout-accent:#126d9b;--handout-tint:#eef7fb;--handout-edge:#cce3ef}
.handout-block--example{--handout-accent:#9a531d;--handout-tint:#fcf2e9;--handout-edge:#ead5c3}
.handout-block--warning{--handout-accent:#a64355;--handout-tint:#fcf0f2;--handout-edge:#efd1d7}
.handout-block:not(.handout-block--prose):not(.handout-block--answer){padding:17px 23px 19px;border:1px solid var(--handout-edge);border-left:4px solid var(--handout-accent);border-radius:0;background:var(--handout-tint)}
.handout-block--answer{padding:0;border:1px solid #dbe3ed;border-radius:0;background:#fafbfd}
.handout-block--answer>.handout-block__heading{align-items:center;margin:0;padding:14px 20px;cursor:pointer;list-style:none}
.handout-block--answer>.handout-block__heading::-webkit-details-marker{display:none}
.handout-block--answer>.handout-block__heading:focus-visible{outline:3px solid #328dcc;outline-offset:3px}
.handout-block--answer>.handout-block__body{padding:6px 20px 20px}
.handout-block--answer>.handout-block__heading h5{color:#315e91;font:650 16px/1.7 var(--handout-sans)}
.handout-block__disclosure{flex:none;display:flex;align-items:center;gap:8px;color:#315e91;font:650 15px/1.7 var(--handout-sans)}
.handout-block__hide{display:none}
.handout-block[open] .handout-block__reveal{display:none}
.handout-block[open] .handout-block__hide{display:inline}
.handout-block[open] .handout-block__disclosure svg{transform:rotate(180deg)}
@media print{.handout-block{break-inside:avoid;font-size:11pt;print-color-adjust:exact;-webkit-print-color-adjust:exact}.handout-block__disclosure{display:none}}
</style>
