<template>
  <section v-if="continuation" class="continuity" :class="`continuity--${continuation.entry_mode}`" :aria-label="t('courseWorkspace.continuity.title', '学习连续性')">
    <div class="continuity__main">
      <div class="continuity__copy">
        <div class="continuity__eyebrow">
          <Route :size="14" />
          <span>{{ continuation.chapter.chapter_name }}</span>
          <span class="continuity__mode">{{ entryModeLabel }}</span>
        </div>
        <p class="continuity__objective">{{ continuation.current_objective?.statement || chapterResultLabel }}</p>
        <p class="continuity__reason">{{ reasonLabel }}</p>
      </div>

      <div class="continuity__states" aria-live="polite">
        <span><BookOpenCheck :size="14" />{{ learningLabel }}</span>
        <span><BadgeCheck :size="14" />{{ masteryLabel }}</span>
        <span v-if="continuation.progress.task_continuity !== 'none'"><RefreshCw :size="14" />{{ taskLabel }}</span>
      </div>

      <div class="continuity__commands">
        <button
          class="continuity__action"
          :disabled="busy || continuation.primary_action.availability !== 'available'"
          @click="handlePrimaryAction"
        >
          <LoaderCircle v-if="busy" :size="16" class="animate-spin" />
          <component :is="primaryIcon" v-else :size="16" />
          <span>{{ actionLabel }}</span>
        </button>
        <button
          type="button"
          class="continuity__explain"
          :title="t('courseWorkspace.explainContinuity')"
          :aria-label="t('courseWorkspace.explainContinuity')"
          @click="emit('explain', continuation.primary_action)"
        >
          <MessageCircleQuestion :size="16" />
        </button>
      </div>
    </div>

    <div v-if="continuation.secondary_notices.length" class="continuity__notices">
      <div v-for="notice in continuation.secondary_notices" :key="`${notice.notice_type}:${notice.target_id}`" class="continuity__notice">
        <TriangleAlert :size="14" />
        <span>{{ noticeLabel(notice) }}</span>
        <button
          v-if="notice.deferrable"
          type="button"
          :title="t('courseWorkspace.continuity.defer', '暂缓这条提醒')"
          :aria-label="t('courseWorkspace.continuity.defer', '暂缓这条提醒')"
          @click="$emit('deferRisk', notice.target_id)"
        >
          <Clock3 :size="14" />
        </button>
      </div>
    </div>

    <div v-if="expanded" class="continuity__result">
      <div class="continuity__result-head">
        <span>{{ chapterResultLabel }}</span>
        <button type="button" :aria-label="t('courseWorkspace.continuity.closeResult', '收起章节结果')" @click="expanded = false"><X :size="15" /></button>
      </div>
      <div v-for="item in continuation.chapter_result.objectives" :key="item.objective_revision_id" class="continuity__result-row">
        <span class="continuity__result-name">{{ item.node_name }}</span>
        <span>{{ readingStatusLabel(item.reading_status) }}</span>
        <span>{{ masteryStatusLabel(item.mastery_status) }}</span>
        <span>{{ evidenceLabel(item.evidence_strength) }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowRight, BadgeCheck, BookOpenCheck, Check, ClipboardCheck, Clock3,
  LoaderCircle, MessageCircleQuestion, RefreshCw, Route, TriangleAlert, X,
} from 'lucide-vue-next'
import type { LearningContinuationProjection, NextLearningAction } from '../stores/learningProgress'
import { t } from '../shared/i18n'
import { learningActionLabel, learningActionReason } from '../utils/learning-action'

const props = defineProps<{
  continuation: LearningContinuationProjection | null
  busy?: boolean
}>()

const emit = defineEmits<{
  (e: 'action', action: NextLearningAction): void
  (e: 'explain', action: NextLearningAction): void
  (e: 'deferRisk', riskId: string): void
}>()

const expanded = ref(false)
const entryModeLabel = computed(() => t(`courseWorkspace.continuity.entryMode.${props.continuation?.entry_mode || 'continue_learning'}`, '继续学习'))
const learningLabel = computed(() => t(`courseWorkspace.continuity.learning.${props.continuation?.progress.learning || 'not_started'}`, '尚未开始'))
const masteryLabel = computed(() => t(`courseWorkspace.continuity.mastery.${props.continuation?.progress.mastery || 'not_checked'}`, '尚未检查'))
const taskLabel = computed(() => t(`courseWorkspace.continuity.task.${props.continuation?.progress.task_continuity || 'none'}`, ''))
const actionLabel = computed(() => {
  const actionType = props.continuation?.primary_action.action_type || 'start_objective'
  return learningActionLabel(actionType)
})
const reasonLabel = computed(() => learningActionReason(props.continuation?.primary_action.reason_code || 'reading_not_started'))
const chapterResultLabel = computed(() => t(`courseWorkspace.continuity.result.${props.continuation?.chapter_result.state || 'in_progress'}`, '章节学习中'))
const primaryIcon = computed(() => {
  const action = props.continuation?.primary_action.action_type || ''
  if (action.includes('practice') || action.includes('diagnostic') || action.includes('remediation') || action.includes('validation') || action === 'start_mastery_check') return ClipboardCheck
  if (action === 'view_chapter_result') return Check
  if (action === 'confirm_version_change') return RefreshCw
  return ArrowRight
})

function handlePrimaryAction() {
  const action = props.continuation?.primary_action
  if (!action) return
  if (action.action_type === 'view_chapter_result') {
    expanded.value = !expanded.value
    return
  }
  emit('action', action)
}

const readingStatusLabel = (status: string) => t(`courseWorkspace.progress.reading.${status}`, status)
const masteryStatusLabel = (status: string) => t(`courseWorkspace.continuity.objectiveMastery.${status}`, status)
const evidenceLabel = (strength: string) => t(`courseWorkspace.continuity.evidence.${strength}`, strength)
const noticeLabel = (notice: Record<string, any>) => t(`courseWorkspace.continuity.notices.${notice.reason_code}`, '有一项学习提醒')
</script>

<style scoped>
.continuity { flex:0 0 auto; border-bottom:1px solid rgba(219,227,234,.82); background:linear-gradient(90deg,rgba(248,250,252,.96),rgba(245,243,255,.72)); color:#172033; }
.continuity__main { min-height:82px; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:7px 12px; padding:9px 14px; }
.continuity__copy { min-width:0; grid-column:1 / -1; }
.continuity__eyebrow { display:flex; align-items:center; gap:7px; color:#166534; font-size:11px; font-weight:750; }
.continuity__mode { border-left:1px solid #cbd5e1; padding-left:7px; color:#475569; }
.continuity__objective { margin:4px 0 0; color:#1e293b; font-size:13px; font-weight:700; line-height:1.35; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.continuity__reason { display:none; }
.continuity__states { grid-column:1; grid-row:2; display:flex; align-items:center; gap:10px; color:#64748b; font-size:11px; white-space:nowrap; }
.continuity__states span { display:inline-flex; align-items:center; gap:5px; }
.continuity__action { min-height:36px; display:inline-flex; align-items:center; justify-content:center; gap:7px; border:1px solid #166534; border-radius:10px; padding:0 12px; background:#166534; color:#fff; font-size:12px; font-weight:750; cursor:pointer; }
.continuity__action:hover { background:#14532d; }
.continuity__action:disabled { opacity:.55; cursor:wait; }
.continuity__commands { grid-column:2; grid-row:2; display:flex; align-items:center; gap:6px; }
.continuity__explain { width:36px; height:36px; display:inline-flex; align-items:center; justify-content:center; border:1px solid #cbd5e1; border-radius:10px; background:#fff; color:#475569; cursor:pointer; }
.continuity__explain:hover { border-color:#166534; color:#166534; }
.continuity__notices { display:flex; flex-wrap:wrap; gap:8px 16px; border-top:1px solid #e2e8f0; padding:7px 16px; background:#fff; }
.continuity__notice { display:flex; align-items:center; gap:6px; color:#854d0e; font-size:11px; }
.continuity__notice button,.continuity__result-head button { display:inline-flex; align-items:center; justify-content:center; border:0; background:transparent; color:#64748b; cursor:pointer; }
.continuity__result { border-top:1px solid #dbe3ea; padding:8px 16px 10px; background:#fff; }
.continuity__result-head { display:flex; align-items:center; justify-content:space-between; color:#334155; font-size:12px; font-weight:750; }
.continuity__result-row { display:grid; grid-template-columns:minmax(160px,1fr) repeat(3,minmax(80px,auto)); gap:12px; padding:7px 0; border-top:1px solid #edf2f7; color:#64748b; font-size:11px; }
.continuity__result-name { color:#334155; font-weight:650; }
@media (max-width:760px) {
  .continuity__main { grid-template-columns:minmax(0,1fr) auto; gap:8px 10px; padding:9px 12px; }
  .continuity__copy { grid-column:1 / -1; }
  .continuity__eyebrow { min-width:0; }
  .continuity__eyebrow > span:first-of-type { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .continuity__objective { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .continuity__reason { display:none; }
  .continuity__states { grid-column:1; grid-row:2; min-width:0; flex-wrap:wrap; gap:6px 9px; }
  .continuity__commands { grid-column:2; grid-row:2; }
  .continuity__action { min-width:0; padding:0 10px; white-space:nowrap; }
  .continuity__notices { padding:7px 12px; }
  .continuity__result { overflow-x:auto; padding-inline:12px; }
  .continuity__result-row { min-width:560px; }
}
@media (max-width:480px) {
  .continuity__main { padding-inline:10px; }
  .continuity__reason { display:none; }
  .continuity__states { font-size:10px; }
  .continuity__states svg { width:12px; height:12px; }
  .continuity__action { min-height:32px; font-size:11px; }
  .continuity__explain { width:32px; height:32px; }
}
@container (max-width:760px) {
  .continuity__main { grid-template-columns:minmax(0,1fr) auto; gap:8px 10px; padding:9px 12px; }
  .continuity__copy { grid-column:1 / -1; }
  .continuity__eyebrow { min-width:0; }
  .continuity__eyebrow > span:first-of-type { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .continuity__objective { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .continuity__reason { display:none; }
  .continuity__states { grid-column:1; grid-row:2; min-width:0; flex-wrap:wrap; gap:6px 9px; }
  .continuity__commands { grid-column:2; grid-row:2; }
  .continuity__action { min-width:0; padding:0 10px; white-space:nowrap; }
}
@container (max-width:480px) {
  .continuity__main { padding-inline:10px; }
  .continuity__reason { display:none; }
  .continuity__states { font-size:10px; }
  .continuity__states svg { width:12px; height:12px; }
  .continuity__action { min-height:32px; font-size:11px; }
  .continuity__explain { width:32px; height:32px; }
}
</style>
