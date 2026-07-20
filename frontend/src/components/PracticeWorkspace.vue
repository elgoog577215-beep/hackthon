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
        <div v-if="canRebuildQuestionBank" class="question-bank-rebuild">
          <button
            type="button"
            class="primary-command"
            data-testid="rebuild-question-bank"
            :disabled="questionBankRebuilding"
            @click="rebuildQuestionBank"
          >
            <LoaderCircle v-if="questionBankRebuilding" :size="16" class="animate-spin" />
            <RefreshCw v-else :size="16" />
            {{ questionBankRebuilding
              ? t('courseAvailability.rebuildingQuestions', '正在按新版链路生成题目')
              : t('courseAvailability.rebuildQuestions', '重新生成题目') }}
          </button>
          <small>{{ t(
            'courseAvailability.rebuildQuestionsHelp',
            '将按当前课程目标重建题库、题目修订与正式练习契约；历史作答记录会保留。',
          ) }}</small>
          <div
            v-if="questionBankRebuildJob"
            class="question-bank-rebuild__progress"
            role="status"
            aria-live="polite"
          >
            <span>{{ questionBankRebuildJob.message || emptyState.title }}</span>
            <strong>{{ questionBankRebuildJob.progress }}%</strong>
            <i><b :style="{ width: `${questionBankRebuildJob.progress}%` }"></b></i>
          </div>
          <small v-if="questionBankRebuildError" class="question-bank-rebuild__error">
            {{ questionBankRebuildError }}
          </small>
        </div>
      </div>

      <main v-else class="question-stage">
        <article class="question-content">
          <section v-if="workspace.targetedRetryContext" class="targeted-retry-context">
            <RotateCcw :size="17" aria-hidden="true" />
            <div>
              <strong>{{ t('courseWorkspace.targetedRetry.title', '针对错题再练') }}</strong>
              <p>{{ workspace.targetedRetryContext.usedAlternateQuestion
                ? t('courseWorkspace.targetedRetry.alternateHint', '已优先选择同一易错点或能力的另一道正式练习')
                : t('courseWorkspace.targetedRetry.sameHint', '当前没有同能力的替代题，继续用原题巩固') }}</p>
            </div>
          </section>
          <section v-if="workflowPhase === 'remediation' && remediationUnit" class="remediation-context">
            <strong>{{ remediationUnit.remediation_objective }}</strong>
            <p>{{ remediationUnit.micro_explanation }}</p>
            <small>{{ remediationUnit.worked_contrast }}</small>
          </section>
          <div class="question-meta">
            <div>
              <span>{{ questionTypeLabel }}</span>
              <span>{{ saveStateLabel }}</span>
            </div>
            <button
              type="button"
              class="refresh-question-command"
              data-testid="refresh-practice-question"
              :disabled="!canRefreshQuestion || questionRefreshing || submitting"
              @click="refreshQuestion"
            >
              <LoaderCircle v-if="questionRefreshing" :size="14" class="animate-spin" />
              <RefreshCw v-else :size="14" />
              {{ questionRefreshing
                ? t('courseWorkspace.practice.refreshing', '正在换题')
                : t('courseWorkspace.practice.refreshQuestion', '换一题') }}
            </button>
          </div>
          <section
            class="question-prompt"
            data-testid="practice-question-markdown"
            :aria-label="t('courseWorkspace.practice.questionContent', '题目内容')"
          >
            <div
              v-if="currentQuestionMarkdown.stimulus"
              class="question-stimulus"
              data-testid="practice-question-stimulus"
            >
              <header>
                <strong>{{ t('courseWorkspace.practice.questionStimulus', '题目材料') }}</strong>
              </header>
              <MarkdownRenderer
                :content="currentQuestionMarkdown.stimulus"
                :enable-code-run="false"
              />
            </div>

            <div class="question-task" data-testid="practice-question-task">
              <header>
                <strong>{{ t('courseWorkspace.practice.answerTask', '作答任务') }}</strong>
                <span>{{ t('courseWorkspace.practice.answerTaskHint', '先明确要求，再开始作答') }}</span>
              </header>
              <MarkdownRenderer
                :content="currentQuestionMarkdown.task"
                :enable-code-run="false"
              />
            </div>

            <details
              v-if="currentQuestionMarkdown.material"
              :key="currentQuestion?.revision_id || currentQuestion?.asset_id || currentQuestion?.question_id"
              class="question-material"
              data-testid="practice-question-material"
            >
              <summary>
                <span class="question-material__icon" aria-hidden="true">
                  <BookOpenCheck :size="17" />
                </span>
                <span class="question-material__copy">
                  <strong>{{ t('courseWorkspace.practice.referenceMaterial', '参考材料') }}</strong>
                  <small>{{ t('courseWorkspace.practice.referenceMaterialHint', '课程原文较长，需要时再展开查看') }}</small>
                </span>
                <span class="question-material__action" aria-hidden="true">
                  <span class="expand-label">{{ t('courseWorkspace.practice.expandMaterial', '展开材料') }}</span>
                  <span class="collapse-label">{{ t('courseWorkspace.practice.collapseMaterial', '收起材料') }}</span>
                  <ChevronDown :size="16" />
                </span>
              </summary>
              <div class="question-material__body">
                <MarkdownRenderer
                  :content="currentQuestionMarkdown.material"
                  :enable-code-run="false"
                />
              </div>
            </details>
          </section>

          <div v-if="workspace.currentAttempt?.status === 'invalidated'" class="state-notice danger">
            <CircleAlert :size="18" />
            <span>{{ t('courseWorkspace.practice.invalidated', '题目版本已经更新，本次草稿已保留，请重新开始') }}</span>
          </div>

          <PracticeAnswerRenderer
            v-model="workspace.currentDraft"
            :contract="currentQuestion.input_contract"
            :options="currentQuestion.options || []"
            :question-type="currentQuestion.question_type"
            :disabled="answerLocked"
            :placeholder="answerPlaceholder"
          />

          <section
            v-if="hintDisplayRows.length"
            class="hint-results"
            aria-live="polite"
            :aria-busy="hintLoadingLevel !== null"
          >
            <div
              v-for="hint in hintDisplayRows"
              :key="hint.loading ? `loading-${hint.level}` : `hint-${hint.level}`"
              class="hint-result"
              :class="{ loading: hint.loading }"
              :data-testid="hint.loading ? 'hint-loading-placeholder' : undefined"
              :aria-live="hint.loading ? 'polite' : undefined"
              :aria-busy="hint.loading ? 'true' : undefined"
            >
              <span>{{ t('courseWorkspace.practice.hintLevel', '{level} 级提示').replace('{level}', String(hint.level)) }}</span>
              <p>
                <LoaderCircle v-if="hint.loading" :size="15" class="animate-spin hint-loading-icon" aria-hidden="true" />
                {{ hint.content }}
              </p>
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
            <section v-if="answerDiagnosis" class="answer-diagnosis">
              <header>
                <strong>{{ t('courseWorkspace.practiceAnalysis.title', '题目解析与本次判断') }}</strong>
                <span v-if="answerDiagnosis.diagnosis?.library_fit">
                  {{ analysisFitLabel }}
                </span>
              </header>
              <dl>
                <div>
                  <dt>{{ t('courseWorkspace.practiceAnalysis.taskGoal', '这道题在考什么') }}</dt>
                  <dd>{{ answerDiagnosis.question_understanding?.task_goal }}</dd>
                </div>
                <div v-if="answerDiagnosis.student_response?.approach">
                  <dt>{{ studentResponseEvidenceLabel }}</dt>
                  <dd>{{ answerDiagnosis.student_response.approach }}</dd>
                </div>
                <div v-if="answerDiagnosis.student_response?.behavior_gap">
                  <dt>{{ t('courseWorkspace.practiceAnalysis.behaviorGap', '当前最关键的差距') }}</dt>
                  <dd>{{ answerDiagnosis.student_response.behavior_gap }}</dd>
                </div>
              </dl>
              <div v-if="diagnosisTags.length" class="diagnosis-tags">
                <span v-for="tag in diagnosisTags" :key="`${tag.kind}-${tag.id}`" :data-kind="tag.kind">
                  {{ tag.name }}
                </span>
              </div>
              <ul v-if="answerDiagnosis.diagnosis?.issues?.length" class="diagnosis-issues">
                <li v-for="issue in answerDiagnosis.diagnosis.issues" :key="issue.issue_id">
                  <strong>{{ issue.title }}</strong>
                  <span>{{ issue.what_happened }}</span>
                </li>
              </ul>
              <p class="diagnosis-summary">{{ answerDiagnosis.student_feedback?.summary }}</p>
              <div class="diagnosis-next">
                <span>{{ t('courseWorkspace.practiceAnalysis.nextAction', '下一步只做这一件事') }}</span>
                <strong>{{ answerDiagnosis.student_feedback?.next_action }}</strong>
              </div>
            </section>
            <small>{{ evidenceLabel }}</small>
          </section>

          <section v-if="workspace.revealedSolution" class="solution-result">
            <strong>{{ t('courseWorkspace.practice.solutionTitle', '完整解析') }}</strong>
            <p v-if="workspace.revealedSolution.summary || workspace.revealedSolution.guidance">
              {{ workspace.revealedSolution.summary || workspace.revealedSolution.guidance }}
            </p>
            <div v-if="workspace.revealedSolution.steps?.length" class="solution-steps">
              <h4>{{ t('courseWorkspace.practice.solutionSteps', '解题步骤') }}</h4>
              <ol>
                <li v-for="(step, index) in workspace.revealedSolution.steps" :key="`${index}-${step}`">
                  {{ step }}
                </li>
              </ol>
            </div>
            <div
              v-if="
                workspace.revealedSolution.representation?.content
                && workspace.revealedSolution.representation?.kind !== 'reasoning_path'
              "
              class="solution-representation"
            >
              <h4>{{ t('courseWorkspace.practice.referenceImplementation', '参考实现或结构') }}</h4>
              <pre>{{ formatSolutionValue(workspace.revealedSolution.representation.content) }}</pre>
            </div>
            <div
              v-if="workspace.revealedSolution.final_answer !== null && workspace.revealedSolution.final_answer !== undefined"
              class="solution-final-answer"
            >
              <h4>{{ t('courseWorkspace.practice.referenceAnswer', '参考答案') }}</h4>
              <pre>{{ formatSolutionValue(workspace.revealedSolution.final_answer) }}</pre>
            </div>
            <div v-if="workspace.revealedSolution.checks?.length" class="solution-checks">
              <h4>{{ t('courseWorkspace.practice.resultChecks', '结果检查') }}</h4>
              <ul>
                <li v-for="check in workspace.revealedSolution.checks" :key="check">{{ check }}</li>
              </ul>
            </div>
            <p
              v-else-if="workspace.revealedSolution.correct_answer !== null && workspace.revealedSolution.correct_answer !== undefined"
            >
              {{ t('courseWorkspace.practice.referenceAnswer', '参考答案') }}：
              {{ formatSolutionValue(workspace.revealedSolution.correct_answer) }}
            </p>
            <ul v-if="workspace.revealedSolution.criteria?.length">
              <li v-for="criterion in workspace.revealedSolution.criteria" :key="criterion">{{ criterion }}</li>
            </ul>
            <ol v-if="workspace.revealedSolution.key_steps?.length">
              <li v-for="step in workspace.revealedSolution.key_steps" :key="step">{{ step }}</li>
            </ol>
            <p v-if="workspace.revealedSolution.self_check">
              {{ t('courseWorkspace.practiceAnalysis.selfCheck', '自查方法') }}：{{ workspace.revealedSolution.self_check }}
            </p>
          </section>
        </article>

        <footer class="practice-actions">
          <div class="support-actions">
            <button
              v-for="level in [1, 2, 3]"
              :key="level"
              class="icon-command"
              :disabled="!canRevealHint(level) || answerLocked || hintLoadingLevel !== null"
              :title="hintButtonLabel(level)"
              :aria-label="hintButtonLabel(level)"
              :aria-busy="hintLoadingLevel === level"
              @click="revealHint(level)"
            >
              <LoaderCircle v-if="hintLoadingLevel === level" :size="16" class="animate-spin" aria-hidden="true" />
              <Lightbulb v-else :size="16" aria-hidden="true" />
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
          <div class="history-row-actions">
            <span>{{ statusLabel(attempt) }}</span>
            <button
              v-if="canTargetRetry(attempt)"
              class="targeted-retry-command"
              type="button"
              :disabled="targetedRetryingId === attempt.attempt_id"
              @click="startTargetedRetry(attempt)"
            >
              <LoaderCircle v-if="targetedRetryingId === attempt.attempt_id" :size="14" class="animate-spin" />
              <RotateCcw v-else :size="14" />
              {{ t('courseWorkspace.targetedRetry.action', '针对再练') }}
            </button>
          </div>
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
  ArrowRight, BookOpenCheck, CheckCircle2, ChevronDown, Circle, CircleAlert, ClipboardCheck, Clock3, History,
  Lightbulb, LoaderCircle, MessageCircleQuestion, RefreshCw, RotateCcw, Send,
} from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import PracticeAnswerRenderer from './PracticeAnswerRenderer.vue'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { t } from '../shared/i18n'
import { isQuestionBankRepairReason, practiceAvailabilityCopy } from '../utils/course-availability'
import { practiceScopeKind } from '../utils/learning-scope'
import { splitPracticeQuestionMarkdown } from '../utils/practice-question-markdown'
import { hasMeaningfulAnswer } from '../utils/answer-payload'
import { presentSolutionValue } from '../utils/solution-presentation'
import {
  runQuestionBankRebuild,
  type QuestionBankRebuildJob,
} from '../utils/question-bank-rebuild'

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
const targetedRetryingId = ref('')
const questionRefreshing = ref(false)
const hintLoadingLevel = ref<number | null>(null)
const questionBankRebuilding = ref(false)
const questionBankRebuildError = ref('')
const questionBankRebuildJob = ref<QuestionBankRebuildJob | null>(null)
let saveTimer: ReturnType<typeof setTimeout> | null = null
let rebuildAbortController: AbortController | null = null

const questions = computed(() => workspace.practice?.questions || [])
const currentQuestion = computed(() => workspace.currentPracticeQuestion)
const currentQuestionMarkdown = computed(() => (
  splitPracticeQuestionMarkdown(currentQuestion.value)
))

interface HintDisplayRow {
  level: number
  content: string
  loading: boolean
  [key: string]: unknown
}

const hintDisplayRows = computed<HintDisplayRow[]>(() => {
  const loadingLevel = hintLoadingLevel.value
  const rows: HintDisplayRow[] = workspace.revealedHints
    .filter(hint => Number(hint.level) !== loadingLevel)
    .map(hint => ({
      ...hint,
      level: Number(hint.level),
      content: String(hint.content || ''),
      loading: false,
    }))
  if (loadingLevel !== null) {
    rows.push({
      level: loadingLevel,
      kind: 'loading',
      content: t('courseWorkspace.practice.hintGenerating', '正在生成提示，请稍候…'),
      loading: true,
    })
  }
  return rows.sort((left, right) => Number(left.level) - Number(right.level))
})
const canRebuildQuestionBank = computed(() => isQuestionBankRepairReason(
  workspace.practice?.practice_availability?.reason_code,
))
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
const hasAnswer = computed(() => hasMeaningfulAnswer(workspace.currentDraft || {}))
const hasNext = computed(() => workspace.currentQuestionIndex < questions.value.length - 1)
const normalizedCurrentPrompt = computed(() => String(currentQuestion.value?.prompt || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase())
const canRefreshQuestion = computed(() => (
  !!currentQuestion.value
  && questions.value.some((question: any) => (
    String(question?.prompt || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase()
    !== normalizedCurrentPrompt.value
  ))
  && workflowPhase.value === 'practice'
  && workspace.practiceSaveState !== 'saving'
  && workspace.practiceSaveState !== 'conflict'
))
const canRetry = computed(() => answerLocked.value && workspace.currentAttempt?.status !== 'grading')
const canRevealSolution = computed(() => workspace.practiceResult?.passed === false && !workspace.currentAttempt?.solution_revealed)
const answerDiagnosis = computed(() => {
  const value = workspace.practiceResult?.answer_diagnosis
  return value?.status === 'completed' ? value : null
})
const analysisFitLabel = computed(() => t(
  `courseWorkspace.practiceAnalysis.fit.${answerDiagnosis.value?.diagnosis?.library_fit || 'MISS'}`,
  ({ HIT: '已定位到本课目标', PARTIAL: '部分定位到本课目标', MISS: '暂未归入现有目标' } as Record<string, string>)[answerDiagnosis.value?.diagnosis?.library_fit || 'MISS'],
))
const studentResponseEvidenceLabel = computed(() => (
  isChoiceQuestion.value
    ? t('courseWorkspace.practiceAnalysis.selectedMeaning', '你的选择反映了什么')
    : t('courseWorkspace.practiceAnalysis.studentApproach', '你采用了什么思路')
))
const diagnosisTags = computed(() => {
  if (!answerDiagnosis.value) return []
  const diagnosis = answerDiagnosis.value.diagnosis || {}
  return [
    ...(diagnosis.knowledge || []).map((item: any) => ({ ...item, kind: 'knowledge' })),
    ...(diagnosis.skills || []).map((item: any) => ({ ...item, kind: 'skill' })),
    ...(diagnosis.misconceptions || []).map((item: any) => ({ ...item, kind: 'misconception' })),
  ]
})
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
    questionBankRebuildError.value = ''
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
  rebuildAbortController?.abort()
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
  const attempt = workspace.currentAttempt
  if (!attempt || attempt.status !== 'in_progress') return false
  const used = attempt.revealed_hint_levels || []
  if (used.includes(level)) return true
  return level === 1 || used.includes(level - 1)
}

function hintButtonLabel(level: number) {
  if (hintLoadingLevel.value === level) {
    return t(
      'courseWorkspace.practice.hintGeneratingLevel',
      '正在生成 {level} 级提示',
    ).replace('{level}', String(level))
  }
  return t(
    'courseWorkspace.practice.hintLevel',
    '{level} 级提示',
  ).replace('{level}', String(level))
}

async function revealHint(level: number) {
  if (hintLoadingLevel.value !== null) return
  if (level >= 2) {
    await ElMessageBox.confirm(
      level === 3
        ? t('courseWorkspace.practice.hintThreeImpact', '三级提示会使本次作答不能单独证明掌握，仍要继续吗？')
        : t('courseWorkspace.practice.hintTwoImpact', '二级提示会把本次结果标记为在支持下完成，仍要继续吗？'),
      t('courseWorkspace.practice.useHint', '使用提示'),
      { confirmButtonText: t('common.confirm', '确认'), cancelButtonText: t('common.cancel', '取消') },
    )
  }
  hintLoadingLevel.value = level
  try {
    await workspace.revealPracticeHint(props.courseId, level)
  } catch {
    // The shared HTTP layer already reports the request error.
  } finally {
    if (hintLoadingLevel.value === level) hintLoadingLevel.value = null
  }
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

async function refreshQuestion() {
  if (!canRefreshQuestion.value || questionRefreshing.value) return
  if (
    workspace.currentAttempt?.status === 'in_progress'
    && hasAnswer.value
  ) {
    try {
      await ElMessageBox.confirm(
        t(
          'courseWorkspace.practice.refreshDraftWarning',
          '当前未提交草稿会结束并保留为一次已放弃记录，确定换一题吗？',
        ),
        t('courseWorkspace.practice.refreshQuestion', '换一题'),
        {
          confirmButtonText: t('common.confirm', '确认'),
          cancelButtonText: t('common.cancel', '取消'),
        },
      )
    } catch {
      return
    }
  }
  questionRefreshing.value = true
  try {
    await workspace.refreshPracticeQuestion(
      props.courseId,
      props.nodeId,
      props.scope,
    )
    await ensureAttempt()
    ElMessage.success(t(
      'courseWorkspace.practice.refreshSuccess',
      '已切换到同一课程范围内的另一道题。',
    ))
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(
      (typeof detail === 'string' ? detail : detail?.message)
      || t(
        'courseWorkspace.practice.refreshFailed',
        '当前没有可切换的正式题目，请稍后重试。',
      ),
    )
  } finally {
    questionRefreshing.value = false
  }
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

function canTargetRetry(attempt: any) {
  return attempt?.status === 'graded' && attempt?.result?.passed === false
}

async function startTargetedRetry(attempt: any) {
  targetedRetryingId.value = attempt.attempt_id
  try {
    const started = await workspace.startTargetedRetry(props.courseId, attempt)
    if (!started) {
      ElMessage.warning(t('courseWorkspace.targetedRetry.unavailable', '原题已不在当前课程版本中，无法发起针对练习'))
      return
    }
    practiceView.value = 'current'
    workspace.practiceLandingView = 'current'
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(
      (typeof detail === 'string' ? detail : detail?.message)
      || t('courseWorkspace.targetedRetry.failed', '针对练习启动失败，请稍后重试'),
    )
  } finally {
    targetedRetryingId.value = ''
  }
}

function selectView(view: 'current') {
  practiceView.value = view
  workspace.practiceLandingView = view
}

async function rebuildQuestionBank() {
  if (!props.courseId || questionBankRebuilding.value) return
  questionBankRebuilding.value = true
  questionBankRebuildError.value = ''
  questionBankRebuildJob.value = null
  rebuildAbortController = new AbortController()
  try {
    const nodeScoped = props.scope === 'node' && Boolean(props.nodeId)
    const job = await runQuestionBankRebuild(
      props.courseId,
      {
        request_id: crypto.randomUUID(),
        scope: nodeScoped ? 'nodes' : 'course',
        node_ids: nodeScoped ? [String(props.nodeId)] : [],
        mode: 'incremental',
      },
      {
        signal: rebuildAbortController.signal,
        onUpdate: update => {
          questionBankRebuildJob.value = update
        },
      },
    )
    workspace.currentQuestionIndex = 0
    workspace.currentAttempt = null
    workspace.currentDraft = {}
    workspace.practiceResult = null
    await workspace.loadAssets(props.courseId, props.nodeId)
    await workspace.loadPractice(props.courseId, props.nodeId, props.scope)
    if (job.status === 'waiting_review') {
      ElMessage.warning(t(
        'courseAvailability.rebuildQuestionsReview',
        '候选题已生成。请教师前往“课程库 → 题库审核 → 课程题库与风险审核”处理。',
      ))
    } else {
      ElMessage.success(t(
        'courseAvailability.rebuildQuestionsSuccess',
        '题目已完成独立验证并发布，可以开始正式练习。',
      ))
    }
  } catch (error: any) {
    if (error?.name === 'AbortError') return
    const detail = error?.response?.data?.detail
    questionBankRebuildError.value = (
      typeof detail === 'string'
        ? detail
        : detail?.message
    ) || error?.message || t(
      'courseAvailability.rebuildQuestionsFailed',
      '题目生成失败，旧题库和历史记录未被覆盖，请稍后重试。',
    )
  } finally {
    rebuildAbortController = null
    questionBankRebuilding.value = false
  }
}

function statusLabel(attempt: any) {
  if (attempt.status === 'grading') return t('courseWorkspace.practice.pendingReview', '等待评阅')
  if (attempt.result?.passed) return t('courseWorkspace.practice.passed', '达到本题标准')
  if (attempt.status === 'in_progress') return t('courseWorkspace.practice.inProgress', '进行中')
  return t('courseWorkspace.practice.notPassed', '尚未达到标准')
}

function formatSolutionValue(value: unknown) {
  return presentSolutionValue(value)
}

</script>

<style scoped>
.practice-workspace { height:100%; overflow:auto; background:#f8fafc; color:#172033; }
.practice-header { position:sticky; top:0; z-index:4; display:flex; justify-content:space-between; gap:20px; align-items:center; padding:18px clamp(18px,4vw,48px); border-bottom:1px solid #dbe3ed; background:rgba(255,255,255,.96); }
.practice-heading { min-width:0; }.practice-heading p { margin:0 0 3px; font-size:11px; color:#0f766e; font-weight:700; }.practice-heading h2 { margin:0; font-size:17px; line-height:1.35; letter-spacing:0; overflow-wrap:anywhere; }
.practice-header-state { display:flex; align-items:center; gap:10px; white-space:nowrap; font-size:12px; color:#526174; }.practice-progress { font:700 13px ui-monospace,monospace; color:#0f766e; }
.practice-tabs { display:flex; max-width:1280px; margin:18px auto 0; padding:0 20px; border-bottom:1px solid #dbe3ed; }.practice-tabs button { padding:10px 14px; border:0; border-bottom:2px solid transparent; background:transparent; color:#64748b; font-size:13px; }.practice-tabs button.active { color:#0f766e; border-color:#0f766e; font-weight:700; }
.workflow-band { width:min(1280px,calc(100% - 64px)); margin:18px auto 0; padding:14px 0; border-top:2px solid #0f766e; border-bottom:1px solid #cbd5e1; display:flex; justify-content:space-between; gap:24px; align-items:flex-start; }.workflow-band>div { display:grid; gap:4px; }.workflow-band span { color:#0f766e; font-size:11px; font-weight:800; }.workflow-band strong { font-size:14px; }.workflow-band p { max-width:48%; margin:0; color:#526174; font-size:13px; line-height:1.55; }.workflow-band[data-phase="needs_support"] { border-top-color:#b45309; }.workflow-band[data-phase="resolved"] { border-top-color:#047857; }
.question-stage,.history-list { width:min(1280px,calc(100% - 64px)); margin:0 auto; padding:24px 0 36px; }.question-content { padding:0; }.question-meta { display:flex; justify-content:space-between; align-items:center; gap:16px; color:#64748b; font-size:12px; }.question-meta>div { display:flex; gap:16px; }.refresh-question-command { display:inline-flex; align-items:center; gap:6px; min-height:30px; padding:0 9px; border:1px solid #cbd5e1; border-radius:6px; color:#475569; background:#fff; font-size:12px; }.refresh-question-command:hover:not(:disabled) { border-color:#0f766e; color:#0f766e; }.refresh-question-command:disabled { opacity:.45; cursor:not-allowed; }
.question-prompt { display:grid; gap:12px; margin:14px 0 22px; color:#334155; font-size:15px; line-height:1.78; }
.question-stimulus { padding:18px clamp(18px,2.5vw,26px); border:1px solid #dbe3ed; border-radius:8px; background:#fff; box-shadow:0 1px 2px rgba(15,23,42,.03); }
.question-stimulus>header { margin-bottom:9px; }
.question-stimulus>header strong { color:#334155; font-size:13px; font-weight:800; }
.question-stimulus :deep(p:last-child),.question-stimulus :deep(pre:last-child) { margin-bottom:0; }
.question-task { padding:18px clamp(18px,2.5vw,26px); border:1px solid #99d8cf; border-left:4px solid #0f766e; border-radius:8px; background:#fff; box-shadow:0 1px 2px rgba(15,23,42,.03); }
.question-task>header { display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:9px; }
.question-task>header strong { color:#115e59; font-size:13px; font-weight:800; }
.question-task>header span { color:#64748b; font-size:11px; }
.question-task :deep(p:last-child) { margin-bottom:0; }
.question-material { overflow:hidden; border:1px solid #dbe3ed; border-radius:8px; background:#fff; }
.question-material>summary { min-width:0; display:grid; grid-template-columns:36px minmax(0,1fr) auto; align-items:center; gap:11px; padding:13px 16px; cursor:pointer; list-style:none; }
.question-material>summary::-webkit-details-marker { display:none; }
.question-material>summary:focus-visible { outline:3px solid rgba(15,118,110,.16); outline-offset:-3px; }
.question-material__icon { width:34px; height:34px; display:grid; place-items:center; border-radius:7px; color:#0f766e; background:#e9f8f5; }
.question-material__copy { min-width:0; display:block; }
.question-material__copy strong { display:block; color:#334155; font-size:13px; line-height:1.4; }
.question-material__copy small { display:block; margin-top:2px; overflow:hidden; color:#64748b; font-size:11px; line-height:1.4; text-overflow:ellipsis; white-space:nowrap; }
.question-material__action { display:inline-flex; align-items:center; gap:6px; color:#0f766e; font-size:11px; font-weight:750; white-space:nowrap; }
.question-material__action svg { transition:transform .18s ease; }
.question-material .collapse-label { display:none; }
.question-material[open] .question-material__action svg { transform:rotate(180deg); }
.question-material[open] .expand-label { display:none; }
.question-material[open] .collapse-label { display:inline; }
.question-material[open] .question-material__copy small { white-space:normal; }
.question-material__body { padding:22px clamp(18px,2.5vw,30px); border-top:1px solid #dbe3ed; }
.question-prompt :deep(h1),.question-prompt :deep(h2),.question-prompt :deep(h3),.question-prompt :deep(h4),.question-prompt :deep(h5),.question-prompt :deep(h6) { color:#172033; letter-spacing:0; }
.question-prompt :deep(h1) { margin:0 0 18px; font-size:24px; line-height:1.35; }
.question-prompt :deep(h2) { margin:30px 0 12px; padding-top:2px; font-size:19px; line-height:1.4; }
.question-prompt :deep(h3) { margin:24px 0 10px; font-size:16px; line-height:1.45; }
.question-prompt :deep(p) { margin:0 0 14px; line-height:1.82; }
.question-prompt :deep(ul),.question-prompt :deep(ol) { margin:8px 0 18px; padding-left:24px; }
.question-prompt :deep(li) { margin:6px 0; line-height:1.72; }
.question-prompt :deep(hr) { margin:26px 0; border-color:#dbe3ed; }
.question-prompt :deep(pre) { position:relative; margin:14px 0 20px; padding:16px 18px; overflow:auto; border:1px solid #1e293b; border-radius:8px; background:#0f172a; color:#e2e8f0; font:13px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre; }
.question-prompt :deep(pre code) { color:inherit; font:inherit; }
.question-prompt :deep(blockquote) { margin:16px 0; border-left-color:#0f766e; background:#f0fdfa; }
.question-prompt :deep(table) { display:block; width:100%; overflow-x:auto; }
.answer-editor { width:100%; min-height:clamp(360px,54vh,680px); padding:16px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; resize:vertical; font:inherit; line-height:1.7; outline:none; }.answer-editor:focus { border-color:#0f766e; box-shadow:0 0 0 3px rgba(15,118,110,.1); }.answer-editor:disabled { background:#f1f5f9; }
.choice-list { display:grid; gap:10px; }.choice-list label { display:grid; grid-template-columns:auto 24px minmax(0,1fr); gap:10px; align-items:flex-start; padding:13px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; cursor:pointer; }.choice-list label:has(input:checked) { border-color:#0f766e; background:#f0fdfa; }.choice-list input { margin-top:3px; }.choice-list strong { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:999px; background:#f1f5f9; color:#475569; font-size:12px; }.choice-list span { padding-top:2px; line-height:1.55; }.choice-list label:has(input:checked) strong { background:#0f766e; color:#fff; }
.practice-actions { position:sticky; bottom:0; display:flex; justify-content:space-between; gap:14px; align-items:center; margin-top:22px; padding:12px 0; background:linear-gradient(to bottom,rgba(248,250,252,.86),#f8fafc 28%); }.support-actions { display:flex; gap:8px; align-items:center; }.icon-command,.text-command,.primary-command { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; padding:0 12px; color:#334155; }.icon-command { width:42px; padding:0; }.icon-command:disabled,.text-command:disabled,.primary-command:disabled { opacity:.45; cursor:not-allowed; }.primary-command { border-color:#0f766e; background:#0f766e; color:#fff; font-weight:700; }
.hint-results,.practice-feedback,.solution-result { margin-top:18px; border-top:1px solid #dbe3ed; padding-top:16px; }.hint-result { display:grid; grid-template-columns:78px 1fr; gap:12px; margin:8px 0; }.hint-result span { color:#a16207; font-size:12px; font-weight:700; }.hint-result p { margin:0; line-height:1.6; }.hint-result.loading p { display:flex; align-items:center; gap:8px; color:#64748b; }.hint-loading-icon { flex:0 0 auto; color:#0f766e; }
.solution-result { color:#334155; }.solution-result p,.solution-result li { line-height:1.65; }.solution-result ul,.solution-result ol { padding-left:20px; }.solution-result h4 { margin:14px 0 7px; font-size:13px; color:#172033; }.solution-result pre { margin:0; padding:12px 14px; max-height:420px; overflow:auto; border:1px solid #dbe3ed; border-radius:6px; background:#f1f5f9; color:#0f172a; font:12px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }.solution-steps ol,.solution-checks ul { margin:6px 0; }
.remediation-context { margin-bottom:22px; padding:14px 0; border-top:1px solid #99f6e4; border-bottom:1px solid #99f6e4; }.remediation-context strong { color:#115e59; }.remediation-context p { margin:8px 0; line-height:1.65; }.remediation-context small { color:#64748b; }.workflow-result strong { color:#172033; }.workflow-result.warning svg { color:#b45309; }
.practice-feedback { color:#9a3412; }.practice-feedback[data-passed="true"] { color:#047857; }.feedback-heading { display:flex; gap:9px; align-items:center; }.feedback-heading span { margin-left:auto; font-size:22px; font-weight:800; }.practice-feedback>p { color:#475569; }.rubric-list { display:grid; gap:7px; margin:12px 0; }.rubric-list>div { display:grid; grid-template-columns:18px minmax(120px,auto) 1fr; gap:7px; align-items:start; color:#334155; }.rubric-list small { color:#64748b; }
.answer-diagnosis { margin:18px 0 12px; padding:16px; border:1px solid #cbd5e1; border-radius:8px; background:#fff; color:#172033; }.answer-diagnosis>header { display:flex; justify-content:space-between; gap:12px; align-items:center; padding-bottom:12px; border-bottom:1px solid #e2e8f0; }.answer-diagnosis>header span { color:#0f766e; font-size:11px; font-weight:700; }.answer-diagnosis dl { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:14px 0; }.answer-diagnosis dl>div { min-width:0; }.answer-diagnosis dt { color:#64748b; font-size:11px; font-weight:700; }.answer-diagnosis dd { margin:5px 0 0; color:#334155; line-height:1.55; overflow-wrap:anywhere; }.diagnosis-tags { display:flex; flex-wrap:wrap; gap:6px; }.diagnosis-tags span { padding:4px 8px; border-radius:999px; background:#f1f5f9; color:#475569; font-size:11px; }.diagnosis-tags span[data-kind="skill"] { background:#ecfeff; color:#0e7490; }.diagnosis-tags span[data-kind="misconception"] { background:#fff7ed; color:#c2410c; }.diagnosis-issues { display:grid; gap:8px; padding:0; margin:14px 0; list-style:none; }.diagnosis-issues li { display:grid; gap:3px; padding-left:10px; border-left:2px solid #f59e0b; }.diagnosis-issues span,.diagnosis-summary { color:#475569; line-height:1.6; }.diagnosis-next { display:grid; gap:4px; margin-top:14px; padding:11px 12px; border-left:3px solid #0f766e; background:#f0fdfa; }.diagnosis-next span { color:#0f766e; font-size:11px; }.diagnosis-next strong { color:#115e59; line-height:1.5; }
.practice-empty { min-height:260px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; color:#64748b; }.state-notice { display:flex; gap:9px; padding:12px; margin-bottom:14px; border:1px solid #fecaca; color:#b91c1c; background:#fef2f2; border-radius:6px; }
.question-bank-rebuild { display:flex; max-width:520px; flex-direction:column; align-items:center; gap:8px; margin-top:8px; text-align:center; }.question-bank-rebuild small { color:#64748b; font-size:11px; line-height:1.55; }.question-bank-rebuild__error { color:#b91c1c!important; }
.question-bank-rebuild__progress { width:min(380px,100%); display:grid; grid-template-columns:1fr auto; gap:6px 10px; align-items:center; color:#475569; font-size:11px; text-align:left; }.question-bank-rebuild__progress strong { color:#0f766e; }.question-bank-rebuild__progress i { grid-column:1/-1; height:5px; overflow:hidden; border-radius:999px; background:#dbe3ed; }.question-bank-rebuild__progress b { display:block; height:100%; border-radius:inherit; background:#0f766e; transition:width .25s ease; }
.history-row { padding:16px 0; border-bottom:1px solid #dbe3ed; }.history-row>div { display:flex; justify-content:space-between; gap:20px; }.history-row span,.history-row small { color:#64748b; }.history-row.legacy { border-left:3px solid #94a3b8; padding-left:12px; }
.history-row-actions { display:flex; align-items:center; gap:10px; }.targeted-retry-command { min-height:30px; display:inline-flex; align-items:center; gap:5px; padding:0 9px; border:1px solid #99f6e4; border-radius:6px; color:#0f766e; background:#f0fdfa; font-size:11px; font-weight:700; }.targeted-retry-command:disabled { opacity:.55; }.targeted-retry-context { display:flex; align-items:flex-start; gap:10px; margin-bottom:20px; padding:12px 14px; border:1px solid #99f6e4; border-radius:7px; color:#115e59; background:#f0fdfa; }.targeted-retry-context>div { min-width:0; }.targeted-retry-context strong { font-size:12px; }.targeted-retry-context p { margin:3px 0 0; color:#526174; font-size:11px; line-height:1.55; }
@media (max-width:640px) { .practice-header { padding:12px 16px; align-items:flex-start; }.attempt-count { display:none; }.practice-tabs { margin-top:8px; padding:0 10px; overflow-x:auto; }.practice-tabs button { flex:0 0 auto; }.workflow-band { width:calc(100% - 28px); display:grid; gap:8px; }.workflow-band p { max-width:none; }.question-stage,.history-list { width:calc(100% - 28px); padding-top:18px; }.question-prompt { font-size:14px; }.question-task { padding:16px 15px; }.question-task>header { display:grid; gap:2px; }.question-material>summary { grid-template-columns:32px minmax(0,1fr) 20px; gap:8px; padding:12px; }.question-material__icon { width:30px; height:30px; }.question-material__action>span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }.question-material__body { padding:18px 15px; }.question-prompt :deep(h1) { font-size:20px; }.question-prompt :deep(h2) { font-size:17px; }.answer-editor { min-height:180px; }.practice-actions { padding-bottom:max(12px,env(safe-area-inset-bottom)); }.text-command { width:40px; padding:0; font-size:0; }.support-actions { gap:5px; }.icon-command { width:38px; }.primary-command { padding:0 11px; }.hint-result { grid-template-columns:1fr; gap:3px; }.answer-diagnosis dl { grid-template-columns:1fr; }.answer-diagnosis>header { align-items:flex-start; } }
</style>
