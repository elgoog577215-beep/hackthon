<template>
  <section class="practice-workspace" :aria-busy="workspace.loading">
    <header class="practice-header">
      <div class="practice-heading">
        <p>{{ practiceScopeLabel }} · {{ practiceLevelLabel }}</p>
        <h2>{{ currentQuestion?.learning_objective || currentNodeLabel }}</h2>
      </div>
      <div class="practice-header-state">
        <span v-if="practiceView === 'current' && questions.length" class="practice-progress">
          {{ workspace.currentQuestionIndex + 1 }}/{{ questions.length }}
        </span>
        <span v-if="workspace.currentAttempt" class="attempt-count">
          {{ t('courseWorkspace.practice.attempt', '第 {count} 次尝试').replace('{count}', String(workspace.currentAttempt.attempt_number || 1)) }}
        </span>
      </div>
    </header>

    <nav class="practice-tabs" :aria-label="t('courseWorkspace.practice.views', '练习视图')">
      <button :class="{ active: practiceView === 'current' }" @click="selectView('current')">
        {{ t('courseWorkspace.practice.current', '当前练习') }}
      </button>
      <button :class="{ active: practiceView === 'history' }" @click="openHistory('all')">
        {{ t('courseWorkspace.practice.history', '练习历史') }}
      </button>
      <button :class="{ active: practiceView === 'needs_review' }" @click="openHistory('needs_review')">
        {{ t('courseWorkspace.practice.needsReview', '待巩固') }}
      </button>
    </nav>

    <section v-if="workflowActive" class="workflow-band" :data-phase="workflowPhase">
      <div>
        <span>{{ workflowPhaseLabel }}</span>
        <strong>{{ workflowHeadline }}</strong>
      </div>
      <p v-if="workflowHypothesis">{{ workflowHypothesis }}</p>
    </section>

    <div v-if="workspace.loading" class="practice-empty">
      <LoaderCircle :size="22" class="animate-spin" />
      <span>{{ t('courseWorkspace.practice.loading', '正在恢复练习') }}</span>
    </div>

    <template v-else-if="practiceView === 'current'">
      <div v-if="workspace.taskResumeError" class="practice-empty workflow-result warning">
        <CircleAlert :size="30" />
        <strong>{{ t('courseWorkspace.practiceRuntime.resumeUnavailableTitle', '原学习任务已经发生变化') }}</strong>
        <span>{{ t('courseWorkspace.practiceRuntime.resumeUnavailableBody', '系统没有打开其他题目。请返回课程，按最新学习状态重新选择下一步。') }}</span>
      </div>

      <div v-else-if="workflowPhase === 'resolved'" class="practice-empty workflow-result">
        <CheckCircle2 :size="30" />
        <strong>{{ t('courseWorkspace.practice.workflow.resolvedTitle', '本次卡点已经通过独立复验') }}</strong>
        <span>{{ t('courseWorkspace.practice.workflow.resolvedBody', '诊断案例已结案，可以返回原课程目标继续学习。') }}</span>
        <button class="primary-command" @click="resumeCoursePractice">
          <ArrowRight :size="16" />
          {{ t('courseWorkspace.practice.workflow.resume', '返回课程练习') }}
        </button>
      </div>

      <div v-else-if="workflowPhase === 'needs_support'" class="practice-empty workflow-result warning">
        <CircleAlert :size="30" />
        <strong>{{ t('courseWorkspace.practice.workflow.needsSupportTitle', '当前证据不足以继续自动补救') }}</strong>
        <span>{{ t('courseWorkspace.practice.workflow.needsSupportBody', '记录已经保留，可以让 AI 老师结合完整过程进一步判断。') }}</span>
        <button class="primary-command" @click="escalateToTeacher">
          <MessageCircleQuestion :size="16" />
          {{ t('courseWorkspace.practice.askTeacher', '问老师') }}
        </button>
      </div>

      <div v-else-if="!currentQuestion" class="practice-empty">
        <CircleAlert v-if="workspace.practice?.practice_availability?.status === 'blocked'" :size="28" />
        <ClipboardCheck v-else :size="28" />
        <strong>{{ emptyState.title }}</strong>
        <span>{{ emptyState.body }}</span>
      </div>

      <main v-else class="question-stage">
        <article class="question-content">
          <section v-if="workflowPhase === 'remediation' && remediationUnit" class="remediation-context">
            <strong>{{ remediationUnit.remediation_objective }}</strong>
            <p>{{ remediationUnit.micro_explanation }}</p>
            <small>{{ remediationUnit.worked_contrast }}</small>
          </section>
          <div class="question-meta">
            <span>{{ questionTypeLabel }}</span>
            <span>{{ saveStateLabel }}</span>
          </div>
          <h3>{{ currentQuestion.prompt }}</h3>

          <div v-if="workspace.currentAttempt?.status === 'invalidated'" class="state-notice danger">
            <CircleAlert :size="18" />
            <span>{{ t('courseWorkspace.practice.invalidated', '题目版本已经更新，本次草稿已保留，请重新开始') }}</span>
          </div>

          <div v-if="isChoiceQuestion" class="choice-list">
            <label v-for="option in currentQuestion.options || []" :key="option.id || option.value">
              <input v-model="workspace.currentDraft.selected_option_id" type="radio" :value="option.id || option.value" :disabled="answerLocked" />
              <span>{{ option.label || option.text || option.value }}</span>
            </label>
          </div>
          <textarea
            v-else
            v-model="workspace.currentDraft.text"
            class="answer-editor"
            :disabled="answerLocked"
            :placeholder="answerPlaceholder"
          />

          <section v-if="workspace.revealedHints.length" class="hint-results">
            <div v-for="hint in workspace.revealedHints" :key="hint.level" class="hint-result">
              <span>{{ t('courseWorkspace.practice.hintLevel', '{level} 级提示').replace('{level}', String(hint.level)) }}</span>
              <p>{{ hint.content }}</p>
            </div>
          </section>

          <section v-if="workspace.practiceResult" class="practice-feedback" :data-passed="workspace.practiceResult.passed">
            <div class="feedback-heading">
              <CheckCircle2 v-if="workspace.practiceResult.passed" :size="21" />
              <Clock3 v-else-if="workspace.practiceResult.status === 'pending_review'" :size="21" />
              <CircleAlert v-else :size="21" />
              <strong>{{ feedbackTitle }}</strong>
              <span v-if="workspace.practiceResult.score !== null && workspace.practiceResult.score !== undefined">{{ workspace.practiceResult.score }}</span>
            </div>
            <p>{{ workspace.practiceResult.feedback }}</p>
            <div v-if="workspace.practiceResult.rubric_results?.length" class="rubric-list">
              <div v-for="item in workspace.practiceResult.rubric_results" :key="item.criterion">
                <component :is="item.met ? CheckCircle2 : Circle" :size="15" />
                <span>{{ item.criterion }}</span>
                <small>{{ item.feedback }}</small>
              </div>
            </div>
            <small>{{ evidenceLabel }}</small>
          </section>

          <section v-if="workspace.revealedSolution" class="solution-result">
            <strong>{{ t('courseWorkspace.practice.solutionTitle', '完整解析') }}</strong>
            <p>{{ workspace.revealedSolution.guidance }}</p>
            <ul v-if="workspace.revealedSolution.criteria?.length">
              <li v-for="criterion in workspace.revealedSolution.criteria" :key="criterion">{{ criterion }}</li>
            </ul>
            <p v-if="workspace.revealedSolution.correct_answer">
              {{ t('courseWorkspace.practice.referenceAnswer', '参考答案') }}：{{ workspace.revealedSolution.correct_answer }}
            </p>
          </section>
        </article>

        <footer class="practice-actions">
          <div class="support-actions">
            <button
              v-for="level in [1, 2, 3]"
              :key="level"
              class="icon-command"
              :disabled="!canRevealHint(level) || answerLocked"
              :title="t('courseWorkspace.practice.hintLevel', '{level} 级提示').replace('{level}', String(level))"
              @click="revealHint(level)"
            >
              <Lightbulb :size="16" />
              <span>{{ level }}</span>
            </button>
            <button class="text-command" :disabled="!workspace.currentAttempt || answerLocked" @click="askTeacher">
              <MessageCircleQuestion :size="16" />
              {{ t('courseWorkspace.practice.askTeacher', '问老师') }}
            </button>
          </div>
          <button v-if="answerLocked && canRetry" class="primary-command" @click="retry">
            <RotateCcw :size="16" />
            {{ t('courseWorkspace.practice.retry', '重新尝试') }}
          </button>
          <button
            v-if="answerLocked && canRevealSolution"
            class="text-command"
            @click="revealSolution"
          >
            <BookOpenCheck :size="16" />
            {{ t('courseWorkspace.practice.revealSolution', '查看完整解析') }}
          </button>
          <button v-else-if="answerLocked && hasNext" class="primary-command" @click="nextQuestion">
            <ArrowRight :size="16" />
            {{ t('courseWorkspace.practice.next', '继续下一题') }}
          </button>
          <button v-else-if="!answerLocked" class="primary-command" :disabled="!hasAnswer || submitting || workspace.practiceSaveState === 'saving' || workspace.practiceSaveState === 'conflict'" @click="submit">
            <LoaderCircle v-if="submitting" :size="16" class="animate-spin" />
            <Send v-else :size="16" />
            {{ t('courseWorkspace.practice.submit', '提交作答') }}
          </button>
        </footer>
      </main>
    </template>

    <div v-else class="history-list">
      <div v-if="!historyAttempts.length && !legacyEvents.length" class="practice-empty">
        <History :size="24" />
        <span>{{ t('courseWorkspace.practice.noHistory', '还没有相关练习记录') }}</span>
      </div>
      <article v-for="attempt in historyAttempts" :key="attempt.attempt_id" class="history-row">
        <div>
          <strong>{{ attempt.node_name || t('courseWorkspace.practice.unknownNode', '课程练习') }}</strong>
          <span>{{ statusLabel(attempt) }}</span>
        </div>
        <small>{{ attempt.result?.feedback || t('courseWorkspace.practice.savedAttempt', '作答历史已保留') }}</small>
      </article>
      <article v-for="event in legacyEvents" :key="event.event_id" class="history-row legacy">
        <div>
          <strong>{{ event.node_name || t('courseWorkspace.practice.legacy', '历史导入') }}</strong>
          <span>{{ t('courseWorkspace.practice.lowConfidence', '低置信历史') }}</span>
        </div>
        <small>{{ t('courseWorkspace.practice.notMasteryEvidence', '不参与当前掌握判断') }}</small>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowRight, BookOpenCheck, CheckCircle2, Circle, CircleAlert, ClipboardCheck, Clock3, History,
  Lightbulb, LoaderCircle, MessageCircleQuestion, RotateCcw, Send,
} from 'lucide-vue-next'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { t } from '../shared/i18n'
import { practiceAvailabilityCopy } from '../utils/course-availability'
import { practiceScopeKind } from '../utils/learning-scope'

const props = defineProps<{
  courseId: string
  nodeId?: string
  nodeLabel?: string
  scope: 'node' | 'final' | 'all'
}>()
const emit = defineEmits<{
  (event: 'askTeacher', payload: { text: string; nodeId: string }): void
  (event: 'graded'): void
}>()
const workspace = useCourseWorkspaceStore()
const practiceView = ref<'current' | 'history' | 'needs_review'>(workspace.practiceLandingView)
const submitting = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

const questions = computed(() => workspace.practice?.questions || [])
const currentQuestion = computed(() => workspace.currentPracticeQuestion)
const currentNodeLabel = computed(() => props.nodeLabel || t('courseWorkspace.allCourse', '全课程'))
const practiceScopeLabel = computed(() => {
  const kind = practiceScopeKind(props.scope)
  if (kind === 'final') return t('courseWorkspace.scope.finalAssessment', '综合检测')
  if (kind === 'course') return t('courseWorkspace.scope.entireCourse', '全课程')
  return `${t('courseWorkspace.scope.currentObjective', '当前目标')} · ${currentNodeLabel.value}`
})
const emptyState = computed(() => practiceAvailabilityCopy(
  workspace.practice?.practice_availability?.reason_code || 'no_questions_in_scope',
  t,
))
const isChoiceQuestion = computed(() => currentQuestion.value?.input_contract?.mode === 'choice')
const answerLocked = computed(() => !!workspace.currentAttempt && workspace.currentAttempt.status !== 'in_progress')
const hasAnswer = computed(() => Object.values(workspace.currentDraft || {}).some(value => value !== '' && value !== null && value !== undefined))
const hasNext = computed(() => workspace.currentQuestionIndex < questions.value.length - 1)
const canRetry = computed(() => answerLocked.value && workspace.currentAttempt?.status !== 'grading')
const canRevealSolution = computed(() => workspace.practiceResult?.passed === false && !workspace.currentAttempt?.solution_revealed)
const historyAttempts = computed(() => workspace.practiceHistory?.attempts || [])
const legacyEvents = computed(() => workspace.practiceHistory?.legacy_events || [])
const workflowPhase = computed(() => workspace.diagnosticWorkflow?.phase || 'practice')
const workflowActive = computed(() => workflowPhase.value !== 'practice')
const remediationUnit = computed(() => workspace.diagnosticWorkflow?.session?.unit || null)
const workflowHypothesis = computed(() => {
  const current = workspace.diagnosticWorkflow?.case
  const id = current?.confirmed_hypothesis_id
  return (current?.hypotheses || []).find((item: any) => item.hypothesis_id === id)?.claim
    || (current?.hypotheses || []).find((item: any) => item.status === 'testing')?.claim
    || ''
})
const workflowPhaseLabel = computed(() => t(
  `courseWorkspace.practice.workflow.phase.${workflowPhase.value}`,
  ({ diagnostic: '辨别卡点', remediation: '局部补救', validation: '独立复验', resolved: '已经结案', needs_support: '需要老师介入' } as Record<string, string>)[workflowPhase.value] || '正式练习',
))
const workflowHeadline = computed(() => t(
  `courseWorkspace.practice.workflow.headline.${workflowPhase.value}`,
  ({
    diagnostic: '先查清原因，不根据一次错误直接下结论',
    remediation: '只修复已确认的局部问题',
    validation: '换一道未见题，独立证明已经解决',
    resolved: '独立复验已经通过',
    needs_support: '自动链路已停止，等待进一步判断',
  } as Record<string, string>)[workflowPhase.value] || '',
))
const practiceLevelLabel = computed(() => t(
  `courseWorkspace.practice.level.${currentQuestion.value?.practice_level || 'mastery_check'}`,
  props.scope === 'final' ? '综合检测' : '正式练习',
))
const questionTypeLabel = computed(() => t(
  `courseWorkspace.questionTypes.${currentQuestion.value?.question_type || 'short_answer'}`,
  currentQuestion.value?.question_type || '练习',
))
const answerPlaceholder = computed(() => t('courseWorkspace.practice.answerPlaceholder', '写下完整过程、依据和结果检查'))
const saveStateLabel = computed(() => t(
  `courseWorkspace.practice.saveState.${workspace.practiceSaveState}`,
  ({ idle: '尚未保存', saving: '正在保存', saved: '已保存', local_only: '仅保存在本机', conflict: '草稿冲突' } as Record<string, string>)[workspace.practiceSaveState],
))
const feedbackTitle = computed(() => {
  const result = workspace.practiceResult || {}
  if (result.status === 'pending_review') return t('courseWorkspace.practice.pendingReview', '等待评阅')
  return result.passed ? t('courseWorkspace.practice.passed', '达到本题标准') : t('courseWorkspace.practice.notPassed', '尚未达到标准')
})
const evidenceLabel = computed(() => t(
  `courseWorkspace.practice.evidence.${workspace.practiceResult?.evidence_strength || 'invalid'}`,
  `证据强度：${workspace.practiceResult?.evidence_strength || '待确认'}`,
))

watch(
  () => [props.courseId, props.nodeId, props.scope],
  async () => {
    if (!props.courseId) return
    await workspace.loadPractice(props.courseId, props.nodeId, props.scope)
    await ensureAttempt()
  },
  { immediate: true },
)

watch(
  () => workspace.practiceLandingView,
  async view => {
    if (view === 'current') practiceView.value = 'current'
    else await openHistory(view === 'history' ? 'all' : 'needs_review')
  },
  { immediate: true },
)

watch(
  () => currentQuestion.value?.revision_id,
  async () => {
    if (practiceView.value === 'current') await ensureAttempt()
  },
)

watch(
  () => workspace.currentDraft,
  () => {
    if (!workspace.currentAttempt || answerLocked.value) return
    if (JSON.stringify(workspace.currentDraft) === JSON.stringify(workspace.currentAttempt.answer_payload || {})) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      void workspace.savePracticeDraft(props.courseId).catch(() => undefined)
    }, 700)
  },
  { deep: true },
)

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
  if (workspace.currentAttempt?.status === 'in_progress') {
    void workspace.savePracticeDraft(props.courseId).catch(() => undefined)
  }
})

async function ensureAttempt() {
  const question = currentQuestion.value
  if (
    !question || !props.courseId || workspace.practiceLoading || workspace.requestedTaskRef
    || workspace.taskResumeError || ['resolved', 'needs_support'].includes(workflowPhase.value)
  ) return
  const taskId = question.task_revision_id || question.revision_id
  if ((workspace.currentAttempt?.task_revision_id || workspace.currentAttempt?.question_revision_id) === taskId) return
  await workspace.startPracticeAttempt(props.courseId, taskId)
}

function canRevealHint(level: number) {
  const used = workspace.currentAttempt?.revealed_hint_levels || []
  if (used.includes(level)) return false
  return level === 1 || used.includes(level - 1)
}

async function revealHint(level: number) {
  if (level >= 2) {
    await ElMessageBox.confirm(
      level === 3
        ? t('courseWorkspace.practice.hintThreeImpact', '三级提示会使本次作答不能单独证明掌握，仍要继续吗？')
        : t('courseWorkspace.practice.hintTwoImpact', '二级提示会把本次结果标记为在支持下完成，仍要继续吗？'),
      t('courseWorkspace.practice.useHint', '使用提示'),
      { confirmButtonText: t('common.confirm', '确认'), cancelButtonText: t('common.cancel', '取消') },
    )
  }
  await workspace.revealPracticeHint(props.courseId, level)
}

async function askTeacher() {
  await workspace.recordPracticeAiSupport(props.courseId, 1)
  emit('askTeacher', { text: currentQuestion.value?.prompt || '', nodeId: props.nodeId || '' })
}

function escalateToTeacher() {
  emit('askTeacher', {
    text: workflowHypothesis.value || currentQuestion.value?.prompt || '',
    nodeId: props.nodeId || '',
  })
}

async function submit() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  submitting.value = true
  try {
    await workspace.submitCurrentPractice(props.courseId)
    if (workspace.diagnosticWorkflow?.current_task && !['resolved', 'needs_support'].includes(workflowPhase.value)) {
      await ensureAttempt()
    }
    emit('graded')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || t('courseWorkspace.practice.submitFailed', '提交失败，请确认网络后重试'))
  } finally {
    submitting.value = false
  }
}

async function revealSolution() {
  await ElMessageBox.confirm(
    t('courseWorkspace.practice.solutionImpact', '查看完整解析后，本次结果不再作为独立掌握证据。仍要继续吗？'),
    t('courseWorkspace.practice.revealSolution', '查看完整解析'),
    { confirmButtonText: t('common.confirm', '确认'), cancelButtonText: t('common.cancel', '取消') },
  )
  await workspace.revealPracticeSolution(props.courseId)
}

async function retry() {
  await workspace.retryCurrentPractice(props.courseId)
}

async function nextQuestion() {
  workspace.nextPracticeQuestion()
  await ensureAttempt()
}

async function resumeCoursePractice() {
  workspace.diagnosticWorkflow = null
  workspace.currentAttempt = null
  workspace.currentDraft = {}
  workspace.practiceResult = null
  await ensureAttempt()
}

async function openHistory(view: 'all' | 'needs_review') {
  practiceView.value = view === 'all' ? 'history' : 'needs_review'
  workspace.practiceLandingView = practiceView.value
  await workspace.loadPracticeHistory(props.courseId, view, props.nodeId)
}

function selectView(view: 'current') {
  practiceView.value = view
  workspace.practiceLandingView = view
}

function statusLabel(attempt: any) {
  if (attempt.status === 'grading') return t('courseWorkspace.practice.pendingReview', '等待评阅')
  if (attempt.result?.passed) return t('courseWorkspace.practice.passed', '达到本题标准')
  if (attempt.status === 'in_progress') return t('courseWorkspace.practice.inProgress', '进行中')
  return t('courseWorkspace.practice.notPassed', '尚未达到标准')
}
</script>

<style scoped>
.practice-workspace { height:100%; overflow:auto; background:#f8fafc; color:#172033; }
.practice-header { position:sticky; top:0; z-index:4; display:flex; justify-content:space-between; gap:20px; align-items:center; padding:18px clamp(18px,4vw,48px); border-bottom:1px solid #dbe3ed; background:rgba(255,255,255,.96); }
.practice-heading { min-width:0; }.practice-heading p { margin:0 0 3px; font-size:11px; color:#0f766e; font-weight:700; }.practice-heading h2 { margin:0; font-size:17px; line-height:1.35; letter-spacing:0; overflow-wrap:anywhere; }
.practice-header-state { display:flex; align-items:center; gap:10px; white-space:nowrap; font-size:12px; color:#526174; }.practice-progress { font:700 13px ui-monospace,monospace; color:#0f766e; }
.practice-tabs { display:flex; max-width:920px; margin:18px auto 0; padding:0 20px; border-bottom:1px solid #dbe3ed; }.practice-tabs button { padding:10px 14px; border:0; border-bottom:2px solid transparent; background:transparent; color:#64748b; font-size:13px; }.practice-tabs button.active { color:#0f766e; border-color:#0f766e; font-weight:700; }
.workflow-band { width:min(920px,calc(100% - 40px)); margin:18px auto 0; padding:14px 0; border-top:2px solid #0f766e; border-bottom:1px solid #cbd5e1; display:flex; justify-content:space-between; gap:24px; align-items:flex-start; }.workflow-band>div { display:grid; gap:4px; }.workflow-band span { color:#0f766e; font-size:11px; font-weight:800; }.workflow-band strong { font-size:14px; }.workflow-band p { max-width:48%; margin:0; color:#526174; font-size:13px; line-height:1.55; }.workflow-band[data-phase="needs_support"] { border-top-color:#b45309; }.workflow-band[data-phase="resolved"] { border-top-color:#047857; }
.question-stage,.history-list { width:min(920px,calc(100% - 40px)); margin:0 auto; padding:26px 0 90px; }.question-content { padding:0; }.question-meta { display:flex; justify-content:space-between; gap:16px; color:#64748b; font-size:12px; }.question-content h3 { margin:14px 0 20px; font-size:19px; line-height:1.65; letter-spacing:0; }
.answer-editor { width:100%; min-height:220px; padding:16px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; resize:vertical; font:inherit; line-height:1.7; outline:none; }.answer-editor:focus { border-color:#0f766e; box-shadow:0 0 0 3px rgba(15,118,110,.1); }.answer-editor:disabled { background:#f1f5f9; }
.choice-list { display:grid; gap:10px; }.choice-list label { display:flex; gap:10px; padding:13px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; }
.practice-actions { position:sticky; bottom:0; display:flex; justify-content:space-between; gap:14px; align-items:center; margin-top:22px; padding:12px 0; background:linear-gradient(to bottom,rgba(248,250,252,.86),#f8fafc 28%); }.support-actions { display:flex; gap:8px; align-items:center; }.icon-command,.text-command,.primary-command { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; padding:0 12px; color:#334155; }.icon-command { width:42px; padding:0; }.icon-command:disabled,.text-command:disabled,.primary-command:disabled { opacity:.45; cursor:not-allowed; }.primary-command { border-color:#0f766e; background:#0f766e; color:#fff; font-weight:700; }
.hint-results,.practice-feedback,.solution-result { margin-top:18px; border-top:1px solid #dbe3ed; padding-top:16px; }.hint-result { display:grid; grid-template-columns:78px 1fr; gap:12px; margin:8px 0; }.hint-result span { color:#a16207; font-size:12px; font-weight:700; }.hint-result p { margin:0; line-height:1.6; }
.solution-result { color:#334155; }.solution-result p,.solution-result li { line-height:1.65; }.solution-result ul { padding-left:20px; }
.remediation-context { margin-bottom:22px; padding:14px 0; border-top:1px solid #99f6e4; border-bottom:1px solid #99f6e4; }.remediation-context strong { color:#115e59; }.remediation-context p { margin:8px 0; line-height:1.65; }.remediation-context small { color:#64748b; }.workflow-result strong { color:#172033; }.workflow-result.warning svg { color:#b45309; }
.practice-feedback { color:#9a3412; }.practice-feedback[data-passed="true"] { color:#047857; }.feedback-heading { display:flex; gap:9px; align-items:center; }.feedback-heading span { margin-left:auto; font-size:22px; font-weight:800; }.practice-feedback>p { color:#475569; }.rubric-list { display:grid; gap:7px; margin:12px 0; }.rubric-list>div { display:grid; grid-template-columns:18px minmax(120px,auto) 1fr; gap:7px; align-items:start; color:#334155; }.rubric-list small { color:#64748b; }
.practice-empty { min-height:260px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; color:#64748b; }.state-notice { display:flex; gap:9px; padding:12px; margin-bottom:14px; border:1px solid #fecaca; color:#b91c1c; background:#fef2f2; border-radius:6px; }
.history-row { padding:16px 0; border-bottom:1px solid #dbe3ed; }.history-row>div { display:flex; justify-content:space-between; gap:20px; }.history-row span,.history-row small { color:#64748b; }.history-row.legacy { border-left:3px solid #94a3b8; padding-left:12px; }
@media (max-width:640px) { .practice-header { padding:12px 16px; align-items:flex-start; }.attempt-count { display:none; }.practice-tabs { margin-top:8px; padding:0 10px; overflow-x:auto; }.practice-tabs button { flex:0 0 auto; }.workflow-band { width:calc(100% - 28px); display:grid; gap:8px; }.workflow-band p { max-width:none; }.question-stage,.history-list { width:calc(100% - 28px); padding-top:18px; }.question-content h3 { font-size:17px; }.answer-editor { min-height:180px; }.practice-actions { padding-bottom:max(12px,env(safe-area-inset-bottom)); }.text-command { width:40px; padding:0; font-size:0; }.support-actions { gap:5px; }.icon-command { width:38px; }.primary-command { padding:0 11px; }.hint-result { grid-template-columns:1fr; gap:3px; } }
</style>
