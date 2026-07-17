<template>
  <div v-if="sections.length === 1 && !sections[0]?.collapsedByDefault" class="feedback-review feedback-review--single">
    <MarkdownRenderer :content="presentMarkdown(sections[0]?.markdown || content)" :search-words="searchWords" />
  </div>
  <section v-else-if="sections.length" class="feedback-review" :aria-label="t('courseBlocks.feedbackReview.title', '逐项核对')">
    <header class="feedback-review__intro">
      <span><ListChecks :size="17" /></span>
      <div>
        <strong>{{ t('courseBlocks.feedbackReview.title', '逐项核对') }}</strong>
        <p>{{ t('courseBlocks.feedbackReview.hint', '先完成任务，再展开参考结论和评价标准') }}</p>
      </div>
    </header>

    <div class="feedback-review__sections">
      <details
        v-for="(section, index) in sections"
        :key="section.sectionId"
        class="feedback-review__section"
        :data-kind="section.kind"
        :open="!section.collapsedByDefault"
      >
        <summary>
          <span class="feedback-review__index">{{ String(index + 1).padStart(2, '0') }}</span>
          <span class="feedback-review__copy">
            <strong>{{ section.title }}</strong>
            <small>{{ section.summary }}</small>
          </span>
          <span class="feedback-review__action" aria-hidden="true">
            <span class="expand-label">{{ t('courseBlocks.feedbackReview.expand', '展开参考') }}</span>
            <span class="collapse-label">{{ t('courseBlocks.feedbackReview.collapse', '收起参考') }}</span>
            <ChevronDown :size="15" />
          </span>
        </summary>
        <div class="feedback-review__body">
          <MarkdownRenderer :content="presentMarkdown(section.markdown)" :search-words="searchWords" />
        </div>
      </details>
    </div>
  </section>
  <MarkdownRenderer v-else :content="presentMarkdown(content)" :search-words="searchWords" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown, ListChecks } from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { t } from '../shared/i18n'
import { normalizeLegacyFeedbackMath, resolveFeedbackSections } from '../utils/feedback-structure'

const props = defineProps<{
  content: string
  structure?: unknown
  searchWords?: string[]
}>()

const sections = computed(() => resolveFeedbackSections(props.content, props.structure))
const presentMarkdown = (markdown: string) => normalizeLegacyFeedbackMath(markdown)
</script>

<style scoped>
.feedback-review { min-width:0; }
.feedback-review--single { padding:2px 0; }
.feedback-review__intro { display:flex; align-items:flex-start; gap:11px; margin:0 0 8px; padding:11px 13px; border-left:3px solid #10b981; border-radius:0 8px 8px 0; background:#f3fbf7; }
.feedback-review__intro > span { width:31px; height:31px; flex:0 0 auto; display:grid; place-items:center; border-radius:8px; color:#047857; background:#dff7ea; }
.feedback-review__intro strong { display:block; color:#14532d; font-size:13px; font-weight:800; line-height:1.35; }
.feedback-review__intro p { margin:3px 0 0; color:#527062; font-size:11px; line-height:1.5; }
.feedback-review__sections { border-top:1px solid #dce8e1; }
.feedback-review__section { border-bottom:1px solid #dce8e1; }
.feedback-review__section summary { min-width:0; display:grid; grid-template-columns:30px minmax(0,1fr) auto; align-items:center; gap:10px; padding:13px 4px; color:var(--lz-text); cursor:pointer; list-style:none; }
.feedback-review__section summary::-webkit-details-marker { display:none; }
.feedback-review__section summary:focus-visible { outline:3px solid rgba(16,185,129,.2); outline-offset:3px; border-radius:7px; }
.feedback-review__index { color:#047857; font:750 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }
.feedback-review__copy { min-width:0; display:block; }
.feedback-review__copy strong { display:block; color:var(--lz-text-strong); font-size:14px; line-height:1.45; }
.feedback-review__copy small { display:block; margin-top:3px; overflow:hidden; color:var(--lz-text-muted); font-size:11px; line-height:1.45; text-overflow:ellipsis; white-space:nowrap; }
.feedback-review__action { display:inline-flex; align-items:center; gap:5px; color:#047857; font-size:11px; font-weight:750; white-space:nowrap; }
.feedback-review__action svg { transition:transform .18s ease; }
.collapse-label { display:none; }
.feedback-review__section[open] { background:linear-gradient(90deg,rgba(236,253,245,.48),rgba(255,255,255,0)); }
.feedback-review__section[open] .feedback-review__action svg { transform:rotate(180deg); }
.feedback-review__section[open] .expand-label { display:none; }
.feedback-review__section[open] .collapse-label { display:inline; }
.feedback-review__section[open] .feedback-review__copy small { white-space:normal; }
.feedback-review__body { padding:2px 4px 18px 40px; color:var(--lz-text-secondary); }
@media (max-width:640px) {
  .feedback-review__section summary { grid-template-columns:25px minmax(0,1fr) 20px; gap:7px; padding-right:48px; }
  .feedback-review__action > span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  .feedback-review__body { padding-left:32px; }
}
</style>
