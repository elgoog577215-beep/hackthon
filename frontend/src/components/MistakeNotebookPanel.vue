<template>
  <section class="mistake-notebook">
    <header class="mistake-notebook__header">
      <div class="mistake-notebook__title">
        <span><BookX :size="20" /></span>
        <div>
          <h3>{{ t('mistakeNotebook.title', '错题本') }}</h3>
          <p>{{ t('mistakeNotebook.count', '共 {count} 道待巩固题目').replace('{count}', String(attempts.length)) }}</p>
        </div>
      </div>
      <div class="mistake-notebook__tools">
        <button
          type="button"
          :disabled="loading"
          :title="t('mistakeNotebook.refresh', '刷新错题本')"
          :aria-label="t('mistakeNotebook.refresh', '刷新错题本')"
          @click="loadMistakes"
        >
          <LoaderCircle v-if="loading" :size="16" class="mistake-notebook__spin" />
          <RefreshCw v-else :size="16" />
        </button>
        <button
          type="button"
          :title="t('mistakeNotebook.close', '关闭错题本')"
          :aria-label="t('mistakeNotebook.close', '关闭错题本')"
          @click="emit('close')"
        >
          <X :size="17" />
        </button>
      </div>
    </header>

    <div class="mistake-notebook__list">
      <div v-if="loading && !attempts.length" class="mistake-notebook__empty">
        <LoaderCircle :size="28" class="mistake-notebook__spin" />
        <span>{{ t('mistakeNotebook.loading', '正在读取错题本') }}</span>
      </div>
      <div v-else-if="loadError" class="mistake-notebook__empty is-error">
        <CircleAlert :size="28" />
        <strong>{{ t('mistakeNotebook.unavailable', '错题本暂时无法读取') }}</strong>
        <button type="button" @click="loadMistakes">{{ t('common.retry', '重试') }}</button>
      </div>
      <div v-else-if="!attempts.length" class="mistake-notebook__empty is-clear">
        <CircleCheck :size="34" />
        <strong>{{ t('mistakeNotebook.empty', '暂无错题，继续保持') }}</strong>
        <span>{{ t('mistakeNotebook.emptyHint', '未通过或证据不足的正式练习会自动出现在这里。') }}</span>
      </div>
      <article
        v-for="(attempt, index) in attempts"
        v-else
        :key="attempt.attempt_id"
        class="mistake-notebook__item"
      >
        <span class="mistake-notebook__index">{{ index + 1 }}</span>
        <div class="mistake-notebook__copy">
          <div class="mistake-notebook__item-heading">
            <strong>{{ attemptTitle(attempt) }}</strong>
            <span :data-status="attemptStatus(attempt)">{{ attemptStatusLabel(attempt) }}</span>
          </div>
          <p class="mistake-notebook__meta">
            {{ attempt.node_name || t('mistakeNotebook.unknownNode', '课程练习') }}
            <template v-if="attemptTime(attempt)">· {{ attemptTime(attempt) }}</template>
          </p>
          <p class="mistake-notebook__feedback">
            {{ attemptFeedback(attempt) || t('mistakeNotebook.saved', '本次作答与判断依据已保留') }}
          </p>
        </div>
        <button
          v-if="canRetry(attempt)"
          type="button"
          class="mistake-notebook__retry"
          :disabled="retryingId === attempt.attempt_id"
          @click="startTargetedRetry(attempt)"
        >
          <LoaderCircle v-if="retryingId === attempt.attempt_id" :size="14" class="mistake-notebook__spin" />
          <RotateCcw v-else :size="14" />
          {{ t('mistakeNotebook.retry', '针对再练') }}
        </button>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { BookX, CircleAlert, CircleCheck, LoaderCircle, RefreshCw, RotateCcw, X } from 'lucide-vue-next'
import { useCourseWorkspaceStore, type PracticeAttempt } from '../stores/courseWorkspace'
import { t } from '../shared/i18n'

const props = defineProps<{ courseId: string }>()
const emit = defineEmits<{
  (event: 'close'): void
  (event: 'retry', payload: { nodeId: string; taskRevisionId: string }): void
}>()
const workspace = useCourseWorkspaceStore()
const loading = ref(false)
const loadError = ref(false)
const retryingId = ref('')

const attempts = computed<PracticeAttempt[]>(() => workspace.mistakeBookAttempts)
const taskByRevision = computed(() => {
  const values = Object.values(workspace.assets?.assets || {})
    .flatMap(value => Array.isArray(value) ? value : [])
  return new Map(values.map(task => [
    String(task.task_revision_id || task.revision_id || ''),
    task,
  ]))
})

watch(() => props.courseId, () => {
  void loadMistakes()
}, { immediate: true })

async function loadMistakes() {
  if (!props.courseId || loading.value) return
  loading.value = true
  loadError.value = false
  try {
    await workspace.loadMistakeBook(props.courseId)
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function taskFor(attempt: PracticeAttempt) {
  return taskByRevision.value.get(String(attempt.task_revision_id || attempt.question_revision_id || ''))
}

function attemptTitle(attempt: PracticeAttempt) {
  const task = taskFor(attempt)
  return String(
    attempt.question
    || attempt.prompt
    || task?.prompt
    || task?.learning_objective
    || attempt.node_name
    || t('mistakeNotebook.unknownQuestion', '待巩固练习'),
  )
}

function attemptFeedback(attempt: PracticeAttempt) {
  const result = attempt.result || {}
  const diagnosis = result.answer_diagnosis?.diagnosis || {}
  return String(
    result.feedback
    || diagnosis.behavior_gap
    || diagnosis.next_action
    || result.message
    || '',
  )
}

function attemptStatus(attempt: PracticeAttempt) {
  if (attempt.status === 'grading') return 'pending'
  if (attempt.result?.passed === false) return 'incorrect'
  return 'review'
}

function attemptStatusLabel(attempt: PracticeAttempt) {
  const status = attemptStatus(attempt)
  return t(
    `mistakeNotebook.status.${status}`,
    status === 'pending' ? '等待评阅' : status === 'incorrect' ? '尚未通过' : '需要巩固',
  )
}

function attemptTime(attempt: PracticeAttempt) {
  const value = attempt.updated_at || attempt.submitted_at || attempt.created_at
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : ''
}

function canRetry(attempt: PracticeAttempt) {
  return attempt.status === 'graded'
    && (attempt.result?.passed === false || attempt.result?.mastery_eligible === false)
}

async function startTargetedRetry(attempt: PracticeAttempt) {
  retryingId.value = attempt.attempt_id
  try {
    const started = await workspace.startTargetedRetry(props.courseId, attempt)
    if (!started) {
      ElMessage.warning(t('mistakeNotebook.retryUnavailable', '原题已不在当前课程版本中，暂时无法发起针对练习'))
      return
    }
    const task = workspace.currentPracticeQuestion
    emit('retry', {
      nodeId: String(task?.node_id || attempt.node_id || ''),
      taskRevisionId: String(task?.task_revision_id || task?.revision_id || started.task_revision_id || ''),
    })
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(
      (typeof detail === 'string' ? detail : detail?.message)
      || t('mistakeNotebook.retryFailed', '针对练习启动失败，请稍后重试'),
    )
  } finally {
    retryingId.value = ''
  }
}
</script>

<style scoped>
.mistake-notebook { height:100%; min-height:0; display:flex; flex-direction:column; color:#172033; background:#fff; }
.mistake-notebook__header { min-height:70px; flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:13px 18px 13px 20px; border-bottom:1px solid #e2e8f0; }
.mistake-notebook__title { min-width:0; display:flex; align-items:center; gap:11px; }
.mistake-notebook__title > span { width:40px; height:40px; flex:0 0 auto; display:grid; place-items:center; border-radius:11px; color:#fff; background:linear-gradient(135deg,#f87171,#e11d48); box-shadow:0 6px 16px rgba(225,29,72,.18); }
.mistake-notebook__title h3,.mistake-notebook__title p { margin:0; }
.mistake-notebook__title h3 { color:#1e293b; font-size:17px; }
.mistake-notebook__title p { margin-top:3px; color:#64748b; font-size:11px; }
.mistake-notebook__tools { display:flex; align-items:center; gap:7px; }
.mistake-notebook__tools button { width:34px; height:34px; display:grid; place-items:center; padding:0; border:1px solid #cbd5e1; border-radius:7px; color:#64748b; background:#fff; cursor:pointer; }
.mistake-notebook__tools button:hover:not(:disabled) { color:#be123c; border-color:#fecdd3; background:#fff1f2; }
.mistake-notebook__tools button:disabled { opacity:.55; cursor:not-allowed; }
.mistake-notebook__list { flex:1; min-height:0; overflow:auto; padding:10px 20px 24px; }
.mistake-notebook__empty { min-height:280px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; color:#64748b; text-align:center; }
.mistake-notebook__empty strong { color:#334155; font-size:14px; }
.mistake-notebook__empty span { max-width:360px; font-size:11px; line-height:1.6; }
.mistake-notebook__empty button { min-height:34px; padding:0 13px; border:1px solid #cbd5e1; border-radius:7px; color:#475569; background:#fff; }
.mistake-notebook__empty.is-error svg { color:#e11d48; }
.mistake-notebook__empty.is-clear svg { color:#10b981; }
.mistake-notebook__item { display:grid; grid-template-columns:30px minmax(0,1fr) auto; align-items:start; gap:12px; padding:15px 2px; border-bottom:1px solid #e8edf4; }
.mistake-notebook__index { width:28px; height:28px; display:grid; place-items:center; border-radius:8px; color:#e11d48; background:#fff1f2; font-size:12px; font-weight:800; }
.mistake-notebook__copy { min-width:0; }
.mistake-notebook__item-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.mistake-notebook__item-heading strong { min-width:0; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; color:#1e293b; font-size:13px; line-height:1.55; }
.mistake-notebook__item-heading span { flex:0 0 auto; padding:3px 7px; border-radius:999px; color:#be123c; background:#fff1f2; font-size:9px; font-weight:750; }
.mistake-notebook__item-heading span[data-status="pending"] { color:#a16207; background:#fffbeb; }
.mistake-notebook__item-heading span[data-status="review"] { color:#6d28d9; background:#f5f3ff; }
.mistake-notebook__meta,.mistake-notebook__feedback { margin:0; }
.mistake-notebook__meta { margin-top:5px; color:#94a3b8; font-size:10px; }
.mistake-notebook__feedback { margin-top:7px; color:#64748b; font-size:11px; line-height:1.6; }
.mistake-notebook__retry { min-height:34px; display:inline-flex; align-items:center; gap:6px; padding:0 10px; border:1px solid #fecdd3; border-radius:7px; color:#be123c; background:#fff1f2; font-size:10px; font-weight:720; cursor:pointer; }
.mistake-notebook__retry:hover:not(:disabled) { color:#fff; border-color:#e11d48; background:#e11d48; }
.mistake-notebook__retry:disabled { opacity:.55; cursor:not-allowed; }
.mistake-notebook__spin { animation:mistake-notebook-spin .8s linear infinite; }
@keyframes mistake-notebook-spin { to { transform:rotate(360deg); } }
@media (max-width:720px) {
  .mistake-notebook__header { min-height:62px; padding:10px 12px 10px 14px; }
  .mistake-notebook__title > span { width:36px; height:36px; }
  .mistake-notebook__list { padding:6px 14px 18px; }
  .mistake-notebook__item { grid-template-columns:28px minmax(0,1fr); }
  .mistake-notebook__retry { grid-column:2; justify-self:start; }
  .mistake-notebook__item-heading { display:block; }
  .mistake-notebook__item-heading span { display:inline-flex; margin-top:6px; }
}
@media (prefers-reduced-motion:reduce) {
  .mistake-notebook__spin { animation:none; }
}
</style>
