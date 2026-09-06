<template>
  <Transition name="suggestion-reveal">
    <aside
      v-if="suggestion"
      class="ai-suggestion"
      :class="`ai-suggestion--${suggestion.severity}`"
      data-testid="ai-suggestion-card"
      role="status"
      aria-live="polite"
      :aria-label="t('courseWorkspace.aiTeacher.suggestion.title', 'AI 老师建议')"
    >
      <span class="ai-suggestion__mark"><Sparkles :size="15" /></span>

      <div class="ai-suggestion__copy">
        <small>{{ t('courseWorkspace.aiTeacher.suggestion.eyebrow', 'AI 老师注意到') }}</small>
        <strong>{{ actionLabel }}</strong>
        <p>{{ t('courseWorkspace.aiTeacher.suggestion.body', '这一步依据你的正式学习记录，确认前不会改变任何内容。') }}</p>
      </div>

      <div class="ai-suggestion__commands">
        <button type="button" class="ai-suggestion__primary" @click="accept">
          {{ t('courseWorkspace.aiTeacher.suggestion.explain', '看看为什么') }}
        </button>
        <button type="button" class="ai-suggestion__secondary" @click="decline('not_now')">
          {{ t('courseWorkspace.aiTeacher.suggestion.notNow', '暂时不要') }}
        </button>
        <button
          type="button"
          class="ai-suggestion__quiet"
          :title="t('courseWorkspace.aiTeacher.suggestion.neverHint', '不再就这件事提醒我')"
          @click="decline('never')"
        >
          {{ t('courseWorkspace.aiTeacher.suggestion.never', '不再提醒') }}
        </button>
      </div>

      <button
        type="button"
        class="ai-suggestion__close"
        :title="t('common.close', '关闭')"
        :aria-label="t('common.close', '关闭')"
        @click="decline('not_now')"
      >
        <X :size="14" />
      </button>
    </aside>
  </Transition>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { Sparkles, X } from 'lucide-vue-next'
import type { AISuggestion } from '../stores/aiTeacher'
import { t } from '../shared/i18n'

const props = defineProps<{ suggestion: AISuggestion | null }>()
const emit = defineEmits<{
  (event: 'accept', suggestion: AISuggestion): void
  (event: 'decline', payload: { suggestion: AISuggestion; reason: 'not_now' | 'never' }): void
  (event: 'shown', suggestion: AISuggestion): void
}>()

// The interruption budget is spent when the card actually reaches the learner,
// not when the candidate is computed — polling for one must stay free.
watch(() => props.suggestion?.trigger_id, (triggerId) => {
  if (triggerId && props.suggestion) emit('shown', props.suggestion)
}, { immediate: true })

const ACTION_LABELS: Record<string, [string, string]> = {
  confirm_version_change: ['courseWorkspace.aiTeacher.suggestion.actions.confirmVersionChange', '课程有更新等待你确认'],
  resume_diagnostic: ['courseWorkspace.aiTeacher.suggestion.actions.resumeDiagnostic', '你有一次诊断没有完成'],
  resume_remediation: ['courseWorkspace.aiTeacher.suggestion.actions.resumeRemediation', '你有一次补救练习没有完成'],
  resume_validation: ['courseWorkspace.aiTeacher.suggestion.actions.resumeValidation', '你有一次独立验证没有完成'],
  resolve_diagnostic_support: ['courseWorkspace.aiTeacher.suggestion.actions.resolveDiagnosticSupport', '有一条诊断结论等待你处理'],
  resolve_blocking_issue: ['courseWorkspace.aiTeacher.suggestion.actions.resolveBlockingIssue', '有一个问题正挡住后面的学习'],
  start_due_review: ['courseWorkspace.aiTeacher.suggestion.actions.startDueReview', '有一项复习到期了'],
}

const actionLabel = computed(() => {
  const actionType = String(props.suggestion?.runtime_action?.action_type || '')
  const copy = ACTION_LABELS[actionType]
  return copy
    ? t(copy[0], copy[1])
    : t('courseWorkspace.aiTeacher.suggestion.actions.generic', '有一个学习任务等待继续')
})

function accept() {
  if (props.suggestion) emit('accept', props.suggestion)
}

function decline(reason: 'not_now' | 'never') {
  if (props.suggestion) emit('decline', { suggestion: props.suggestion, reason })
}
</script>

<style scoped>
.ai-suggestion { position:relative; min-width:0; display:grid; grid-template-columns:28px minmax(0,1fr); align-items:start; gap:10px; margin:0 0 12px; padding:12px 34px 12px 12px; border-left:3px solid var(--lz-brand); border-radius:0 10px 10px 0; background:linear-gradient(110deg,#f4f5ff 0%,#fafaff 68%,#fff 100%); box-shadow:inset 0 0 0 1px rgba(199,210,254,.8),0 6px 18px rgba(79,70,229,.05); }
.ai-suggestion--high { border-left-color:var(--lz-brand-strong); }
.ai-suggestion__mark { width:28px; height:28px; display:grid; place-items:center; border-radius:9px; color:var(--lz-brand-strong); background:#fff; box-shadow:0 3px 10px rgba(79,70,229,.08); }
.ai-suggestion__copy { min-width:0; display:grid; gap:2px; }
.ai-suggestion__copy small { color:var(--lz-text-muted); font-size:9px; line-height:1.2; }
.ai-suggestion__copy strong { color:var(--lz-text-strong); font-size:12px; line-height:1.4; overflow-wrap:anywhere; }
.ai-suggestion__copy p { margin:2px 0 0; color:var(--lz-text-secondary); font-size:10px; line-height:1.5; overflow-wrap:anywhere; }
.ai-suggestion__commands { grid-column:2; display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:9px; }
.ai-suggestion__commands button { min-height:30px; display:inline-flex; align-items:center; padding:0 10px; border-radius:8px; font-size:10px; font-weight:650; cursor:pointer; }
.ai-suggestion__primary { border:0; color:#fff; background:var(--lz-brand-strong); }
.ai-suggestion__secondary { border:1px solid rgba(199,210,254,.78); color:var(--lz-text-secondary); background:rgba(255,255,255,.86); }
.ai-suggestion__quiet { border:0; color:var(--lz-text-muted); background:transparent; }
.ai-suggestion__secondary:hover,.ai-suggestion__quiet:hover { color:var(--lz-brand-strong); background:#fff; }
.ai-suggestion__close { position:absolute; top:8px; right:8px; width:22px; height:22px; display:grid; place-items:center; border:0; border-radius:6px; color:var(--lz-text-muted); background:transparent; cursor:pointer; }
.ai-suggestion__close:hover { color:var(--lz-text-strong); background:var(--lz-surface-soft); }
.suggestion-reveal-enter-active,.suggestion-reveal-leave-active { transition:opacity .18s ease,transform .18s ease; }
.suggestion-reveal-enter-from,.suggestion-reveal-leave-to { opacity:0; transform:translateY(-4px); }
@media (max-width:520px) {
  .ai-suggestion { grid-template-columns:minmax(0,1fr); padding:11px 30px 11px 11px; }
  .ai-suggestion__mark { display:none; }
  .ai-suggestion__commands { grid-column:1; }
  .ai-suggestion__commands button { flex:1 1 auto; justify-content:center; }
}
</style>
