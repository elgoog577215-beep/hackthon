<template>
  <section class="personal-practice" :aria-label="c('practice')">
    <div class="practice-controls">
      <nav class="practice-tabs" :aria-label="c('practice')">
        <button v-for="tab in tabs" :key="tab" type="button" :aria-current="view === tab ? 'page' : undefined" @click="setView(tab)"><component :is="tabIcons[tab]" :size="16" aria-hidden="true" /><span>{{ c(tab) }}</span></button>
      </nav>
      <div class="practice-scope" role="group" :aria-label="c('scope')">
        <button v-for="item in scopes" :key="item" type="button" :aria-pressed="scope === item" @click="scope = item">{{ c(item) }}</button>
      </div>
      <label v-if="view === 'practice' && visibleQuestions.length" class="practice-choice">
        <span>{{ c('choose') }} <small>{{ visibleQuestions.length }}</small></span>
        <select :value="selectedQuestionId" @change="chooseQuestion(($event.target as HTMLSelectElement).value)">
          <option v-if="!visibleQuestions.some(q => q.question_id === selectedQuestionId)" value="" disabled>{{ c('choose') }}</option>
          <option v-for="(question, index) in visibleQuestions" :key="question.question_id" :value="question.question_id">{{ index + 1 }} · {{ question.title || question.section_title }}</option>
        </select>
      </label>
      <select v-if="view === 'mistakes'" v-model="reviewFilter" :aria-label="c('filter')" class="practice-filter">
        <option value="all">{{ c('filterAll') }}</option><option v-for="state in reviewStates" :key="state" :value="state">{{ c(state) }}</option>
      </select>
    </div>

    <div class="practice-results">
      <p v-if="loading" class="practice-notice" role="status">{{ c('loading') }}</p>
      <div v-if="error" class="practice-error" role="alert"><p>{{ error }}</p><ElButton plain :disabled="!!busy || loading" @click="load()">{{ c('retryLoad') }}</ElButton></div>
      <p v-if="!storageAvailable" class="practice-notice" role="alert">{{ c('unavailableDraft') }}</p>
      <p v-if="!loading && view === 'practice' && !visibleQuestions.length" class="practice-empty">{{ c('empty') }}</p>
      <template v-if="view !== 'practice' && !selectedAttempt">
        <p v-if="!loading && !visibleAttempts.length" class="practice-empty">{{ c(reviewFilter !== 'all' && view === 'mistakes' ? 'noMatches' : view === 'mistakes' ? 'emptyMistakes' : 'emptyHistory') }}</p>
        <ol class="attempt-list">
          <li v-for="attempt in visibleAttempts" :key="attempt.attempt_id">
            <button type="button" :aria-current="selectedAttemptId === attempt.attempt_id ? 'true' : undefined" @click="openAttempt(attempt)">
              <span class="attempt-list-title"><MathText :content="attempt.metadata.title || attempt.node_name" /><span>{{ statusLabel(attempt) }}</span></span>
              <small>{{ attempt.node_name }}<template v-if="attempt.attempt_number"> · {{ c('attemptNumber').replace('{n}', String(attempt.attempt_number)) }}</template><template v-if="attempt.metadata.intent !== 'practice'"> · {{ c(attempt.metadata.intent === 'correction' ? 'correctionLabel' : 'retryLabel') }}</template><template v-if="attempt.metadata.review"> · {{ c(attempt.metadata.review.state) }}</template></small><time v-if="attemptDate(attempt)" :datetime="attempt.created_at">{{ attemptDate(attempt) }}</time>
            </button>
          </li>
        </ol>
      </template>

      <article v-if="displayQuestion && (view === 'practice' || selectedAttempt)" class="practice-question" :data-attempt-id="selectedAttemptId || undefined">
        <button v-if="view !== 'practice'" type="button" class="practice-back" @click="selectedAttemptId = ''"><ArrowLeft :size="15" aria-hidden="true" />{{ c('backToRecords') }}</button>
        <header class="question-heading">
          <div><p>{{ displayQuestion.sectionTitle }}</p><h3><span>{{ c('question') }}<template v-if="questionNumber > 0"> {{ String(questionNumber).padStart(2, '0') }}</template></span><MathText :content="displayQuestion.title" /></h3></div>
          <button v-if="!historical" type="button" class="practice-jump" :aria-label="c('jump')" :title="c('jump')" @click="emit('jump', displayQuestion.blockId)"><ArrowUpRight :size="19" aria-hidden="true" /></button>
        </header>
        <p v-if="historical" class="practice-notice">{{ c('historical') }}</p>
        <p v-else-if="selectedAttempt && scope === 'current' && selectedAttempt.node_id !== props.currentSection" class="practice-notice">{{ c('preserved') }}</p>
        <div class="question-content"><MarkdownRenderer :content="displayQuestion.prompt" :enable-code-run="false" /></div>
        <p v-if="currentQuestion && !currentQuestion.has_answer" class="practice-notice">{{ c('noAnswer') }}</p>

        <ElButton v-if="!selectedAttempt && currentQuestion" type="primary" class="start-answer" :disabled="!!busy || loading || staleRecord" @click="start('practice')">{{ c('start') }}</ElButton>
        <template v-if="selectedAttempt">
          <div class="attempt-heading"><strong>{{ statusLabel(selectedAttempt) }}</strong><span v-if="selectedAttempt.metadata.intent !== 'practice'">{{ c(selectedAttempt.metadata.intent === 'correction' ? 'correctionLabel' : 'retryLabel') }}</span></div>
          <details v-if="selectedAttempt.origin_attempt_id" class="answer-record original-answer">
            <summary>{{ c('original') }}</summary><MarkdownRenderer v-if="originAttempt" :content="originalAnswer(originAttempt) || c('blank')" :enable-code-run="false" /><p v-else>{{ c('originalMissing') }}</p>
          </details>

          <div v-if="canEdit" class="answer-editor">
            <label :for="answerInputId">{{ c('yourAnswer') }}</label>
            <ElInput :id="answerInputId" v-model="answerText" type="textarea" :rows="6" :maxlength="20000" resize="vertical" :disabled="busy === 'submit'" :placeholder="c('answerPlaceholder')" />
            <p class="draft-status" role="status">{{ answerDirty ? c(storageAvailable ? 'localDraft' : 'unavailableDraft') : c('saved') }}</p>
            <div class="answer-actions"><ElButton :disabled="!!busy || loading || !answerDirty || staleRecord" @click="saveDraft">{{ c(busy === 'draft' ? 'saving' : 'save') }}</ElButton><ElButton type="primary" :disabled="!!busy || loading || !answerText.trim() || staleRecord" @click="submit">{{ c(busy === 'submit' ? 'submitting' : 'submit') }}</ElButton></div>
          </div>
          <div v-else class="answer-record submitted-answer"><h4>{{ c('thisAnswer') }}</h4><MarkdownRenderer :content="originalAnswer(selectedAttempt) || c('blank')" :enable-code-run="false" /></div>
          <section v-if="unsubmittedDraft" class="unsubmitted-draft">
            <h4>{{ c('unsubmittedDraft') }}</h4><p class="practice-note">{{ c('unsubmittedDraftHint') }}</p>
            <ElInput :model-value="answerText" type="textarea" :rows="4" readonly resize="vertical" :aria-label="c('unsubmittedDraft')" />
          </section>

          <div class="practice-help">
            <p class="disclosure-status">{{ c(selectedAttempt.solution_revealed ? selectedAttempt.solution_exposure_origin_attempt_id ? 'previouslyRevealed' : 'revealed' : selectedAttempt.revealed_hints?.length ? 'hinted' : 'independent') }}</p>
            <div v-if="hasAnswer || !historical && currentQuestion?.has_hint" class="help-actions">
              <ElButton v-if="!historical && currentQuestion?.has_hint" plain :disabled="!!busy || loading || staleRecord" @click="reveal('hint')"><Lightbulb :size="16" aria-hidden="true" />{{ c('hint') }}</ElButton>
              <ElButton v-if="hasAnswer" plain :disabled="!!busy || loading || staleRecord" @click="reveal('solution')"><BookOpen :size="16" aria-hidden="true" />{{ c(selectedAttempt.solution_revealed ? 'answerAgain' : 'answer') }}</ElButton>
            </div>
            <p v-if="canEdit && (currentQuestion?.has_hint || currentQuestion?.has_answer)" class="practice-note">{{ c('disclosure') }}</p>
            <details v-if="selectedAttempt.revealed_hints?.length" class="help-content" :open="lastDisclosure === 'hint'"><summary>{{ c('hints') }}</summary><MarkdownRenderer v-for="hint in selectedAttempt.revealed_hints" :key="hint.level" :content="hint.content" :enable-code-run="false" /></details>
            <div v-if="solutions[selectedAttemptId]" class="help-content"><h4>{{ c('reference') }}</h4><MarkdownRenderer :content="solutions[selectedAttemptId]!" :enable-code-run="false" /></div>
          </div>

          <section v-if="selectedAttempt.status !== 'in_progress'" class="practice-feedback">
            <h4>{{ c('feedback') }}</h4>
            <MarkdownRenderer v-if="selectedAttempt.result?.feedback" :content="selectedAttempt.result.feedback" :enable-code-run="false" />
            <p v-if="selectedAttempt.grading_state === 'running'" class="practice-notice">{{ c('gradingRunning') }}</p>
            <p v-else-if="selectedAttempt.grading_state === 'interrupted'" class="practice-notice">{{ c('gradingInterrupted') }}</p>
            <p v-else-if="!selectedAttempt.result || selectedAttempt.result.passed === null" class="practice-notice">{{ c('pendingHint') }}</p>
            <div v-if="!historical && currentQuestion" class="feedback-actions">
              <ElButton v-if="['grading', 'submitted'].includes(selectedAttempt.status)" plain :disabled="!!busy || loading" @click="load()">{{ c('refreshGrading') }}</ElButton>
              <ElButton v-if="selectedAttempt.can_request_grade" plain :disabled="!!busy || loading || staleRecord" @click="grade">{{ c(selectedAttempt.grading_state === 'interrupted' ? 'continueGrading' : 'regrade') }}</ElButton>
              <ElButton :disabled="!!busy || loading || staleRecord" @click="start('correction')">{{ c('correction') }}</ElButton><ElButton :disabled="!!busy || loading || staleRecord" @click="start('retry')">{{ c('retry') }}</ElButton>
            </div>
            <button v-if="!reviewExpanded" class="review-open" type="button" @click="openReview"><NotebookPen :size="16" aria-hidden="true" />{{ c('recordReason') }}</button>
          </section>

          <section v-if="reviewExpanded && reviewEditor && selectedAttempt.status !== 'in_progress'" class="practice-review">
            <h4>{{ c('reviewTitle') }}</h4>
            <div class="review-fields"><label>{{ c('errorType') }}<select v-model="reviewEditor.error_type"><option v-for="type in errorTypes" :key="type" :value="type">{{ c(type) }}</option></select></label><label>{{ c('reviewState') }}<select v-model="reviewEditor.state"><option v-for="state in reviewStates" :key="state" :value="state">{{ c(state) }}</option></select></label></div>
            <label class="reflection-label" :for="reflectionInputId">{{ c('reflection') }}</label><ElInput :id="reflectionInputId" v-model="reviewEditor.reflection" type="textarea" :rows="3" :maxlength="6000" resize="vertical" :placeholder="c('reflectionPlaceholder')" />
            <div class="review-save"><ElButton :disabled="!!busy || loading || staleRecord || !reviewDirty" @click="saveReview">{{ c(busy === 'review' ? 'saving' : 'reviewSave') }}</ElButton><span v-if="reviewSaved" role="status">{{ c('reviewSaved') }}</span></div>
          </section>
        </template>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import "../styles/study-tool-controls.css"
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { ElButton, ElInput } from 'element-plus'
import { ArrowUpRight, PencilLine, History, BookOpenCheck, Lightbulb, BookOpen, ArrowLeft, NotebookPen } from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MathText from './MathText.vue'
import { personalPracticeApi as api, PersonalPracticeApiError, type PersonalPracticeAttempt as Attempt, type PersonalPracticeQuestion as Question, type PracticeIntent, type PracticeReview, type PracticeReviewState } from '../api/personal-practice'
import { practiceCopy as c } from '../shared/study-practice-copy'
import { activeLocale } from '../shared/i18n'
import { getStudyIdentity } from '../utils/study-identity'
import { createUuid } from '../utils/client-id'

const props = defineProps<{ materialId: string; revisionId: string; currentSection: string; initialView?: 'practice' | 'mistakes' }>()
const emit = defineEmits<{ jump: [blockId: string] }>()
const tabIcons = { practice: PencilLine, history: History, mistakes: BookOpenCheck }
const tabs = ['practice', 'history', 'mistakes'] as const, scopes = ['current', 'all'] as const
const errorTypes = ['unknown', 'concept', 'condition', 'method', 'execution', 'expression'] as const
const reviewStates = ['needs_review', 'corrected', 'revisit'] as const
const view = ref<typeof tabs[number]>(props.initialView || 'practice'), scope = ref<typeof scopes[number]>('current')
const reviewFilter = ref<'all' | PracticeReviewState>('all')
const questions = ref<Question[]>([]), attempts = ref<Attempt[]>([]), selectedQuestionId = ref(''), selectedAttemptId = ref('')
const answers = ref<Record<string, string>>({}), reviews = ref<Record<string, PracticeReview>>({}), solutions = ref<Record<string, string>>({}), reviewOpened = ref<Record<string, boolean>>({})
const localAnswerDrafts = ref<Record<string, boolean>>({})
const error = ref(''), busy = ref(''), loading = ref(false), staleRecord = ref(false), storageAvailable = ref(true), lastDisclosure = ref(''), reviewSaved = ref(false)
const answerInputId = `practice-answer-${useId()}`, reflectionInputId = `practice-reflection-${useId()}`
let epoch = 0, cacheScope = '', controller: AbortController | undefined
const requestIds = new Map<string, string>()
const selectedAttempt = computed(() => attempts.value.find(a => a.attempt_id === selectedAttemptId.value))
const currentQuestion = computed(() => selectedAttempt.value ? questions.value.find(q => q.question_revision_id === selectedAttempt.value!.question_revision_id) : questions.value.find(q => q.question_id === selectedQuestionId.value))
const hasAnswer = computed(() => currentQuestion.value?.has_answer ?? selectedAttempt.value?.metadata.has_answer ?? false)
const questionNumber = computed(() => currentQuestion.value ? questions.value.findIndex(q => q.question_id === currentQuestion.value!.question_id) + 1 : 0)
const historical = computed(() => !!selectedAttempt.value && (selectedAttempt.value.can_continue === false || selectedAttempt.value.metadata.revision_id !== props.revisionId || !currentQuestion.value))
const canEdit = computed(() => !!selectedAttempt.value && !historical.value && selectedAttempt.value.status === 'in_progress')
const displayQuestion = computed(() => selectedAttempt.value ? { title: selectedAttempt.value.metadata.title, prompt: selectedAttempt.value.metadata.prompt, blockId: selectedAttempt.value.metadata.block_id, sectionTitle: selectedAttempt.value.node_name } : currentQuestion.value ? { title: currentQuestion.value.title, prompt: currentQuestion.value.prompt, blockId: currentQuestion.value.block_id, sectionTitle: currentQuestion.value.section_title } : null)
const visibleQuestions = computed(() => questions.value.filter(q => scope.value === 'all' || q.section_id === (props.currentSection || questions.value[0]?.section_id)))
function isMistake(attempt: Attempt) { return attempt.status !== 'in_progress' && (attempt.result?.passed !== true || !!attempt.metadata.review_updated || !!attempt.metadata.review?.reflection.trim() || attempt.metadata.review?.state === 'revisit') }
const visibleAttempts = computed(() => attempts.value.filter(a => (scope.value === 'all' || a.node_id === (props.currentSection || questions.value[0]?.section_id)) && (view.value !== 'mistakes' || isMistake(a) && (reviewFilter.value === 'all' || (a.metadata.review?.state || 'needs_review') === reviewFilter.value))).slice().reverse())
const originAttempt = computed(() => attempts.value.find(a => a.attempt_id === selectedAttempt.value?.origin_attempt_id))
const answerText = computed({ get: () => answers.value[selectedAttemptId.value] ?? '', set: (value: string) => { answers.value[selectedAttemptId.value] = value; localAnswerDrafts.value[selectedAttemptId.value] = value !== (selectedAttempt.value ? originalAnswer(selectedAttempt.value) : ''); persist(selectedAttemptId.value) } })
const answerDirty = computed(() => canEdit.value && answerText.value !== (selectedAttempt.value?.answer_payload.text || ''))
const unsubmittedDraft = computed(() => !!selectedAttempt.value && !canEdit.value && !!localAnswerDrafts.value[selectedAttemptId.value] && answerText.value !== originalAnswer(selectedAttempt.value))
const reviewEditor = computed(() => reviews.value[selectedAttemptId.value])
const reviewExpanded = computed(() => !!selectedAttempt.value && (reviewOpened.value[selectedAttemptId.value] || isMistake(selectedAttempt.value)))
const reviewDirty = computed(() => !!reviewEditor.value && JSON.stringify(reviewEditor.value) !== JSON.stringify(selectedAttempt.value?.metadata.review || defaultReview()))
const defaultReview = (): PracticeReview => ({ error_type: 'unknown', reflection: '', state: 'needs_review' })
function originalAnswer(attempt: Attempt) { return attempt.submitted_answer_payload?.text ?? attempt.answer_payload.text }
function statusLabel(attempt: Attempt) {
  if (attempt.status === 'in_progress') return c('inProgress')
  if (attempt.grading_state === 'running') return c('gradingRunningStatus')
  if (attempt.grading_state === 'interrupted') return c('interrupted')
  if (attempt.grading_state === 'pending_review' || attempt.result?.status === 'pending_review') return c('pending')
  if (attempt.status === 'grading') return c('grading')
  return c(attempt.result?.passed === true ? 'passed' : attempt.result?.passed === false ? 'failed' : 'pending')
}
function attemptDate(attempt: Attempt) {
  if (!attempt.created_at) return ''
  const date = new Date(attempt.created_at)
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(activeLocale.value === 'en' ? 'en' : 'zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}
function requestId(key: string) { if (!requestIds.has(key)) requestIds.set(key, createUuid()); return requestIds.get(key)! }
function readDraft(attemptId: string): { answer?: string; review?: PracticeReview } | null {
  if (!cacheScope) return null
  try { return JSON.parse(sessionStorage.getItem(`${cacheScope}:${attemptId}`) || 'null') } catch { storageAvailable.value = false; return null }
}
function persist(attemptId: string) {
  if (!cacheScope || !attemptId) return
  const attempt = attempts.value.find(a => a.attempt_id === attemptId)
  if (!attempt) return
  const answer = localAnswerDrafts.value[attemptId] && answers.value[attemptId] !== originalAnswer(attempt) ? answers.value[attemptId] : undefined
  const review = JSON.stringify(reviews.value[attemptId] || defaultReview()) !== JSON.stringify(attempt.metadata.review || defaultReview()) ? reviews.value[attemptId] : undefined
  try {
    if (answer === undefined && review === undefined) sessionStorage.removeItem(`${cacheScope}:${attemptId}`)
    else sessionStorage.setItem(`${cacheScope}:${attemptId}`, JSON.stringify({ answer, review }))
  }
  catch { storageAvailable.value = false }
}
function initializeDraft(attempt: Attempt) {
  const draft = readDraft(attempt.attempt_id)
  if (!(attempt.attempt_id in answers.value)) {
    answers.value[attempt.attempt_id] = typeof draft?.answer === 'string' ? draft.answer : originalAnswer(attempt)
    localAnswerDrafts.value[attempt.attempt_id] = typeof draft?.answer === 'string' && draft.answer !== originalAnswer(attempt)
  } else if (!localAnswerDrafts.value[attempt.attempt_id]) answers.value[attempt.attempt_id] = originalAnswer(attempt)
  if (answers.value[attempt.attempt_id] === originalAnswer(attempt)) localAnswerDrafts.value[attempt.attempt_id] = false
  if (!(attempt.attempt_id in reviews.value)) {
    const saved = draft?.review
    reviews.value[attempt.attempt_id] = saved && errorTypes.includes(saved.error_type) && reviewStates.includes(saved.state) && typeof saved.reflection === 'string' ? { ...saved } : { ...(attempt.metadata.review || defaultReview()) }
  }
}
function upsert(attempt: Attempt) {
  const index = attempts.value.findIndex(a => a.attempt_id === attempt.attempt_id)
  if (index < 0) attempts.value.push(attempt)
  else attempts.value[index] = attempt
  if (answers.value[attempt.attempt_id] === originalAnswer(attempt)) localAnswerDrafts.value[attempt.attempt_id] = false
}
function openAttempt(attempt: Attempt) {
  selectedAttemptId.value = attempt.attempt_id
  selectedQuestionId.value = questions.value.find(q => q.question_revision_id === attempt.question_revision_id)?.question_id || ''
  initializeDraft(attempt); lastDisclosure.value = ''; reviewSaved.value = false
}
function chooseQuestion(id: string) {
  selectedQuestionId.value = id; selectedAttemptId.value = ''; lastDisclosure.value = ''
  const question = questions.value.find(q => q.question_id === id)
  const active = attempts.value.find(a => a.question_revision_id === question?.question_revision_id && a.status === 'in_progress' && a.can_continue !== false)
  if (active) openAttempt(active)
}
function setView(value: typeof tabs[number]) {
  view.value = value
  if (value === 'practice') chooseQuestion(selectedQuestionId.value || visibleQuestions.value[0]?.question_id || '')
  else selectedAttemptId.value = ''
}
async function load() {
  const context = epoch
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''
  try {
    const result = await api.list(props.materialId, controller.signal)
    if (context !== epoch) return
    questions.value = result.revision_id === props.revisionId ? result.questions : []
    attempts.value = result.attempts; staleRecord.value = false
    if (selectedAttempt.value) initializeDraft(selectedAttempt.value)
    else if (view.value === 'practice') chooseQuestion(visibleQuestions.value.find(q => q.question_id === selectedQuestionId.value)?.question_id || visibleQuestions.value[0]?.question_id || '')
  } catch (failure) { if (context === epoch && !(failure instanceof Error && failure.name === 'AbortError')) error.value = failure instanceof Error ? failure.message : c('error') }
  finally { if (context === epoch) loading.value = false }
}
async function mutate<T>(name: string, operation: () => Promise<T>, accept: (result: T) => void) {
  if (busy.value || staleRecord.value || loading.value) return
  const context = epoch; busy.value = name; error.value = ''; reviewSaved.value = false
  try { const result = await operation(); if (context === epoch) accept(result) }
  catch (failure) {
    if (context !== epoch) return
    if (failure instanceof PersonalPracticeApiError && failure.status === 409) { staleRecord.value = true; error.value = c('conflict') }
    else error.value = failure instanceof Error ? failure.message : c('error')
  } finally { if (context === epoch) busy.value = '' }
}
async function start(intent: PracticeIntent) {
  const question = currentQuestion.value, origin = selectedAttempt.value
  if (!question || historical.value) return
  const originId = intent === 'practice' ? undefined : origin?.attempt_id
  const active = attempts.value.find(a => a.question_revision_id === question.question_revision_id && a.metadata.intent === intent && (a.origin_attempt_id || undefined) === originId && a.status === 'in_progress' && a.can_continue !== false)
  if (active) { openAttempt(active); view.value = 'practice'; return }
  const key = `start:${props.revisionId}:${question.question_id}:${intent}:${originId || ''}`
  await mutate('start', () => api.start(props.materialId, { revision_id: props.revisionId, question_id: question.question_id, request_id: requestId(key), intent, origin_attempt_id: originId, language: activeLocale.value === 'en' ? 'en' : 'zh' }), attempt => { upsert(attempt); openAttempt(attempt); view.value = 'practice'; requestIds.delete(key) })
}
async function saveDraft() {
  const attempt = selectedAttempt.value, answer = answerText.value
  if (!attempt || !canEdit.value) return
  await mutate('draft', () => api.saveDraft(props.materialId, attempt.attempt_id, { expected_revision: attempt.revision, answer }), updated => { upsert(updated); persist(attempt.attempt_id) })
}
async function submit() {
  const attempt = selectedAttempt.value, answer = answerText.value
  if (!attempt || !canEdit.value || !answer.trim()) return
  const key = `submit:${attempt.attempt_id}:${attempt.revision}:${answer}`
  await mutate('submit', () => api.submit(props.materialId, attempt.attempt_id, { expected_revision: attempt.revision, answer, request_id: requestId(key) }), updated => { upsert(updated); requestIds.delete(key); persist(attempt.attempt_id) })
}
async function reveal(kind: 'hint' | 'solution') {
  const attempt = selectedAttempt.value
  if (!attempt || kind === 'hint' && historical.value) return
  await mutate(kind, () => api[kind](props.materialId, attempt.attempt_id, attempt.revision), result => { upsert(result.attempt); lastDisclosure.value = kind; if (kind === 'solution') solutions.value[attempt.attempt_id] = result.content })
}
async function grade() {
  const attempt = selectedAttempt.value
  if (!attempt || historical.value || !attempt.can_request_grade) return
  await mutate('grade', () => api.grade(props.materialId, attempt.attempt_id, attempt.revision), upsert)
}
function openReview() { if (selectedAttempt.value) { initializeDraft(selectedAttempt.value); reviewOpened.value[selectedAttemptId.value] = true } }
async function saveReview() {
  const attempt = selectedAttempt.value, review = reviewEditor.value
  if (!attempt || !review) return
  const snapshot = { ...review }
  await mutate('review', () => api.review(props.materialId, attempt.attempt_id, { ...snapshot, expected_revision: attempt.revision }), updated => { upsert(updated); reviewSaved.value = JSON.stringify(reviews.value[attempt.attempt_id]) === JSON.stringify(snapshot); persist(attempt.attempt_id) })
}
watch(reviews, () => { reviewSaved.value = false; if (selectedAttemptId.value) persist(selectedAttemptId.value) }, { deep: true, flush: 'sync' })
watch(() => props.initialView, value => { if (value) setView(value) })
watch([scope, () => props.currentSection], () => { if (!selectedAttempt.value && view.value === 'practice' && !visibleQuestions.value.some(q => q.question_id === selectedQuestionId.value)) chooseQuestion(visibleQuestions.value[0]?.question_id || '') })
watch([() => props.materialId, () => props.revisionId], () => {
  epoch++; controller?.abort(); questions.value = []; attempts.value = []; answers.value = {}; localAnswerDrafts.value = {}; reviews.value = {}; solutions.value = {}; reviewOpened.value = {}; selectedQuestionId.value = ''; selectedAttemptId.value = ''; busy.value = ''; staleRecord.value = false; requestIds.clear()
  const owner = getStudyIdentity()?.id
  cacheScope = owner ? `lingzhi-personal-practice:${encodeURIComponent(owner)}:${encodeURIComponent(props.materialId)}:${encodeURIComponent(props.revisionId)}` : ''
  storageAvailable.value = !!owner
  if (props.materialId && props.revisionId) void load()
}, { immediate: true })
function beforeUnload(event: BeforeUnloadEvent) {
  if ((answerDirty.value || unsubmittedDraft.value || reviewDirty.value) && !storageAvailable.value) { event.preventDefault(); event.returnValue = c('unsavedPrompt') }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => { epoch++; controller?.abort(); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.personal-practice { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; color:#343c50; background:#fff; font:15px/1.7 var(--study-ui-font); }
.practice-controls { flex:none; padding:0 16px 14px; border-bottom:1px solid #e5e8f0; }
.personal-practice button,.personal-practice select { font:inherit; }
.personal-practice button { cursor:pointer; }
.personal-practice button:focus-visible,.personal-practice select:focus-visible { outline:2px solid #8572ae; outline-offset:2px; }
.practice-tabs { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); margin-bottom:12px; border-bottom:1px solid #e8ebf2; }
.practice-tabs button { min-height:48px; padding:9px 3px; border:0; border-bottom:2px solid transparent; color:#667086; background:none; line-height:1.5; overflow-wrap:anywhere; }
.practice-tabs button[aria-current] { border-bottom-color:#7560a3; color:#615086; font-weight:600; }
.practice-scope { display:grid; grid-template-columns:1fr 1fr; padding:3px; gap:3px; border-radius:9px; background:#f0f2f7; }
.practice-scope button { min-height:44px; padding:7px; border:0; border-radius:7px; color:#616b80; background:none; line-height:1.5; }
.practice-scope button[aria-pressed=true] { background:#fff; color:#615086; font-weight:600; }
.practice-choice { display:block; margin-top:12px; }.practice-choice>span { display:flex; align-items:baseline; justify-content:space-between; margin-bottom:5px; color:#4b566c; }.practice-choice small { font-size:13px; color:#687287; font-variant-numeric:tabular-nums; }
.personal-practice select { box-sizing:border-box; display:block; width:100%; min-height:44px; max-width:100%; padding:8px 28px 8px 10px; border:1px solid #dce1eb; border-radius:8px; color:#3d485d; background:#fff; text-overflow:ellipsis; }
.practice-filter { margin-top:12px; }.practice-results { flex:1; min-height:0; min-width:0; overflow:auto; overscroll-behavior:contain; padding:0 18px 28px; scrollbar-width:thin; scrollbar-color:#d7dce7 transparent; }
.practice-empty { padding:22px 0; color:#657086; }.practice-notice { color:#656079; background:#f5f3f9; padding:10px 12px; border-radius:8px; font-size:14px; line-height:1.7; overflow-wrap:anywhere; }
.practice-error { margin-top:12px; padding:10px 12px; background:#fcf1ef; color:#8d4844; border-radius:8px; overflow-wrap:anywhere; }.practice-error p { margin:0; }.practice-error :deep(.el-button) { color:#8d4844; }
.attempt-list { list-style:none; margin:0; padding:0; }.attempt-list li { border-bottom:1px solid #e8ebf2; }.attempt-list button { width:100%; min-height:72px; text-align:start; padding:12px 6px; border:0; background:none; color:inherit; }.attempt-list button[aria-current] { background:#f4f2f9; }.attempt-list-title { display:flex; align-items:baseline; justify-content:space-between; gap:10px; font-weight:600; overflow-wrap:anywhere; }.attempt-list-title>span:last-child { flex:none; color:#71618c; font-size:13px; font-weight:500; }.attempt-list small { display:block; margin-top:4px; color:#687287; font-size:13px; line-height:1.5; overflow-wrap:anywhere; }
.attempt-list time { display:block; margin-top:4px; color:#697386; font-size:12px; }.practice-back { min-height:44px; padding:8px 0; margin:-8px 0 12px; border:0; color:#675387; background:none; text-align:start; }.practice-question { padding-top:19px; min-width:0; }.question-heading { display:flex; align-items:flex-start; gap:8px; margin-bottom:14px; }.question-heading>div { min-width:0; flex:1; }.question-heading p { margin:0 0 4px; color:#667086; font-size:13px; overflow-wrap:anywhere; }.question-heading h3 { margin:0; color:#38445b; font-size:17px; line-height:1.65; font-weight:600; overflow-wrap:anywhere; }.question-heading h3>span:first-child { display:block; margin-bottom:3px; color:#73648a; font-size:13px; font-weight:500; }.practice-jump { display:grid; place-items:center; flex:none; width:44px; min-height:44px; margin-right:-8px; border:0; border-radius:8px; background:none; color:#726188; }.practice-jump:hover { background:#f1eef7; }
.question-content { margin-bottom:18px; }.start-answer { margin-bottom:10px; }.attempt-heading { display:flex; align-items:baseline; gap:10px; padding-top:18px; margin:20px 0 12px; border-top:1px solid #e5e8ef; }.attempt-heading strong { color:#62517f; font-size:15px; }.attempt-heading span { color:#6a7285; font-size:14px; }
.answer-editor>label,.reflection-label { display:block; margin-bottom:7px; font-weight:600; font-size:15px; }.answer-editor :deep(.el-textarea__inner),.practice-review :deep(.el-textarea__inner) { font:15px/1.7 var(--study-ui-font); padding:12px; border-radius:8px; color:#343c50; box-shadow:0 0 0 1px #d8deea inset; }.answer-editor :deep(.el-textarea__inner::placeholder),.practice-review :deep(.el-textarea__inner::placeholder) { color:#747c8b; }.answer-editor :deep(.el-textarea__inner:focus),.practice-review :deep(.el-textarea__inner:focus) { box-shadow:0 0 0 1px #8875b2 inset; }
.draft-status,.practice-note { font-size:13px; line-height:1.7; color:#697386; margin:8px 0 12px; overflow-wrap:anywhere; }.answer-actions,.feedback-actions { display:flex; flex-wrap:wrap; gap:8px; }.answer-actions :deep(.el-button),.feedback-actions :deep(.el-button) { flex:1; }.personal-practice :deep(.el-button) { min-height:44px; height:auto; max-width:100%; margin-left:0; padding:9px 12px; font-size:15px; line-height:1.5; border-radius:8px; white-space:normal; }.personal-practice :deep(.el-button>span) { white-space:normal; overflow-wrap:anywhere; }.personal-practice :deep(.el-button--primary) { --el-button-bg-color:#74609f; --el-button-border-color:#74609f; --el-button-hover-bg-color:#66518f; --el-button-hover-border-color:#66518f; --el-button-active-bg-color:#5e4a87; --el-button-active-border-color:#5e4a87; }
.answer-record { padding:10px 0; }.answer-record summary,.help-content summary { cursor:pointer; min-height:44px; padding:8px 0; box-sizing:border-box; color:#65547f; }.original-answer { margin-bottom:10px; border-bottom:1px solid #e8ebf2; }.submitted-answer { margin-bottom:8px; }.personal-practice h4 { font-size:15px; line-height:1.7; margin:0 0 8px; font-weight:600; }
.unsubmitted-draft { margin:16px 0; padding:14px 0; border-top:1px solid #e5e8ef; }.unsubmitted-draft :deep(.el-textarea__inner) { font:15px/1.7 var(--study-ui-font); padding:12px; color:#343c50; background:#f8f9fc; border-radius:8px; }
.practice-help { margin:16px 0; }.disclosure-status { margin:0; font-size:13px; color:#667086; }.help-actions { display:flex; flex-wrap:wrap; gap:0 8px; margin-left:0; margin-top:8px; }.help-content { margin-top:10px; padding:10px 12px; border-radius:8px; background:#f7f8fb; }.help-content summary { padding:0; min-height:44px; }.practice-feedback { padding-top:20px; margin-top:20px; border-top:1px solid #e5e8ef; }.feedback-actions { margin-top:14px; }.review-open { min-height:44px; padding:8px 0; border:0; background:none; color:#675387; text-align:start; }
.practice-review { margin-top:24px; padding-top:20px; border-top:1px solid #e5e8ef; }.review-fields { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:12px 0; }.review-fields label { min-width:0; color:#5d687c; font-size:14px; }.review-fields select { margin-top:5px; font-size:15px; }.review-save { margin-top:12px; display:flex; align-items:center; flex-wrap:wrap; gap:8px; }.review-save span { color:#5b7565; font-size:13px; }
.personal-practice :deep(.markdown-renderer) { min-width:0; font-size:15px; line-height:1.8; overflow-wrap:anywhere; }.personal-practice :deep(.markdown-renderer>:first-child) { margin-top:0; }.personal-practice :deep(.markdown-renderer>:last-child) { margin-bottom:0; }.personal-practice :deep(.katex-display),.personal-practice :deep(pre),.personal-practice :deep(.markdown-table-wrapper) { max-width:100%; overflow-x:auto; overflow-y:hidden; }.personal-practice :deep(.katex-display) { padding:4px 0; }.personal-practice :deep(.katex:not(.katex-display .katex)) { display:inline-block; max-width:100%; overflow-x:auto; overflow-y:hidden; vertical-align:middle; }.personal-practice :deep(.code-block-wrapper) { min-width:0; max-width:100%; margin:12px 0; box-shadow:none; }
@media(max-width:480px) { .practice-controls { padding:0 14px 12px; }.practice-results { padding:0 16px 28px; }.review-fields { grid-template-columns:1fr; }.answer-actions,.feedback-actions { gap:8px; }.answer-actions :deep(.el-button),.feedback-actions :deep(.el-button) { flex:1 1 120px; }.attempt-list-title { align-items:flex-start; }.attempt-list-title>span:last-child { flex:0 0 auto; max-width:40%; text-align:end; line-height:1.6; } }
.practice-tabs { gap:4px; padding:4px; border:1px solid #e3dfed; border-radius:11px; background:#f1eff7; }
.practice-tabs button { display:flex; align-items:center; justify-content:center; gap:6px; border:1px solid transparent; border-radius:8px; font-size:14px; }
.practice-tabs button svg { flex:none; }
.practice-tabs button[aria-current] { background:white; border-color:#d9d0e9; box-shadow:0 1px 3px #4234590c; }
.practice-back,.review-open { display:inline-flex; align-items:center; gap:6px; padding:8px 10px; border:1px solid #ded9e9; border-radius:8px; background:#faf9fd; }
.personal-practice :deep(.el-button > span) { gap:6px; }
.personal-practice :deep(.el-button svg) { flex:none; }
@media(max-width:760px) { .practice-tabs button { flex-direction:column; gap:3px; } }
</style>
