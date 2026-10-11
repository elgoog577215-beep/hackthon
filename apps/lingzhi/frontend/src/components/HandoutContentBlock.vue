<template>
  <component :is="isAnswerDisclosure ? 'details' : 'div'" class="handout-block"
    :class="[`handout-block--${tone}`, { 'handout-block--answer': isAnswerDisclosure }]"
    :data-handout-type="contentType || undefined" :data-answer-to="answerTo || undefined">
    <component :is="isAnswerDisclosure ? 'summary' : 'header'" v-if="showHeader" class="handout-block__heading">
      <div class="handout-block__identity">
        <span v-if="label" class="handout-block__label">{{ label }}</span>
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
    theorem: 'result', 定理: 'result', result: 'result', 结论: 'result', summary: 'result',
    example: 'example', 例题: 'example', exercise: 'exercise', 练习: 'exercise',
    misconception: 'warning', 辨析: 'warning', warning: 'warning', 易错点: 'warning',
  }
  return tones[props.contentType] || 'prose'
})
</script>

<style scoped>
.handout-block{--handout-accent:#64748b;--handout-tint:transparent;min-width:0;margin:0 0 28px;padding:0;color:#29364b}
.handout-block__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:14px}
.handout-block__identity{min-width:0;display:flex;align-items:baseline;flex-wrap:wrap;gap:8px 12px}
.handout-block__label{flex:none;color:var(--handout-accent);font-size:15px;line-height:1.6;font-weight:750;letter-spacing:.03em}
.handout-block__heading h5{margin:0;color:#25324a;font-size:18px;line-height:1.55;font-weight:720;overflow-wrap:anywhere}
.handout-block__body :deep(.markdown-renderer){font-size:16px;line-height:1.9;color:#34435b}
.handout-block__body :deep(.markdown-renderer> :first-child){margin-top:0}
.handout-block__body :deep(.markdown-renderer> :last-child){margin-bottom:0}
.handout-block__body :deep(.markdown-renderer strong){color:#233450;font-weight:750}
.handout-block__body :deep(.markdown-renderer .katex-display){margin:1.4em 0;overflow-x:auto;overflow-y:hidden;padding:5px 0}
.handout-block--definition{--handout-accent:#137d78;--handout-tint:#f1faf8}
.handout-block--result{--handout-accent:#6251c3;--handout-tint:#f6f4ff}
.handout-block--example{--handout-accent:#936617;--handout-tint:#fffbf1}
.handout-block--exercise{--handout-accent:#4168b2;--handout-tint:#f4f7ff}
.handout-block--warning{--handout-accent:#b34c62;--handout-tint:#fff5f6}
.handout-block:not(.handout-block--prose):not(.handout-block--answer){padding:21px 24px;border-left:3px solid var(--handout-accent);border-radius:0 12px 12px 0;background:var(--handout-tint)}
.handout-block--answer{padding:0;border:1px solid #e1e6f0;border-radius:10px;background:#fafbfe}
.handout-block--answer>.handout-block__heading{align-items:center;margin:0;padding:17px 20px;cursor:pointer;list-style:none}
.handout-block--answer>.handout-block__heading::-webkit-details-marker{display:none}
.handout-block--answer>.handout-block__heading:focus-visible{outline:2px solid #6860d9;outline-offset:3px;border-radius:8px}
.handout-block--answer>.handout-block__body{padding:0 20px 22px}
.handout-block__disclosure{flex:none;display:flex;align-items:center;gap:8px;color:#6251c3;font-size:15px;font-weight:650}
.handout-block__hide{display:none}
.handout-block[open] .handout-block__reveal{display:none}
.handout-block[open] .handout-block__hide{display:inline}
.handout-block[open] .handout-block__disclosure svg{transform:rotate(180deg)}
</style>
