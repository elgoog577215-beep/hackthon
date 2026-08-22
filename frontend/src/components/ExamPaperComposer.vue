<template>
  <Teleport to="body">
    <div class="exam-paper-composer" @click.self="emit('close')">
      <section
        ref="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="exam-paper-composer-title"
        tabindex="-1"
      >
        <header>
          <div>
            <small>{{ t('questionBank.examPaper.eyebrow') }}</small>
            <h2 id="exam-paper-composer-title">{{ t('questionBank.examPaper.composeTitle') }}</h2>
            <p>{{ t('questionBank.examPaper.composeHelp').replace('{count}', String(questions.length)) }}</p>
          </div>
          <button type="button" :aria-label="t('common.close')" @click="emit('close')">
            <X :size="18" />
          </button>
        </header>

        <form @submit.prevent="submit">
          <label class="field field--wide">
            <span>{{ t('questionBank.examPaper.title') }}</span>
            <input v-model.trim="form.title" required maxlength="200" autofocus />
          </label>
          <div class="field-grid">
            <label class="field">
              <span>{{ t('questionBank.examPaper.duration') }}</span>
              <input v-model.number="form.durationMinutes" type="number" min="1" max="1440" required />
            </label>
            <label class="field">
              <span>{{ t('questionBank.examPaper.totalScore') }}</span>
              <input v-model.number="form.totalScore" type="number" min="1" max="10000" step="0.5" required />
            </label>
          </div>

          <section class="question-preview" aria-labelledby="selected-question-title">
            <header>
              <strong id="selected-question-title">{{ t('questionBank.examPaper.selectedQuestions') }}</strong>
              <span>{{ questions.length }}</span>
            </header>
            <ol>
              <li v-for="question in questions" :key="question.revision_id">
                <span>{{ question.question_type || t('questionBank.role.candidate') }}</span>
                <p>{{ question.prompt }}</p>
              </li>
            </ol>
          </section>

          <p v-if="error" class="submit-error" role="alert">{{ error }}</p>
          <footer>
            <span>{{ t('questionBank.examPaper.immutableHint') }}</span>
            <div>
              <button type="button" @click="emit('close')">{{ t('common.cancel') }}</button>
              <button class="primary" type="submit" :disabled="submitting || !form.title || !questions.length">
                <LoaderCircle v-if="submitting" :size="16" class="spin" />
                <FileCheck2 v-else :size="16" />
                {{ submitting ? t('questionBank.examPaper.creating') : t('questionBank.examPaper.create') }}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { FileCheck2, LoaderCircle, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import http from '../utils/http'

export type ExamPaperQuestion = {
  revision_id: string
  prompt: string
  question_type?: string
}

const props = defineProps<{
  courseId: string
  bundleRevisionId: string
  questions: ExamPaperQuestion[]
}>()
const emit = defineEmits<{
  (event: 'close'): void
  (event: 'created', paper: Record<string, unknown>): void
}>()
const dialog = ref<HTMLElement | null>(null)
const submitting = ref(false)
const error = ref('')
const form = reactive({
  title: t('questionBank.examPaper.defaultTitle'),
  durationMinutes: 120,
  totalScore: 100,
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !submitting.value) emit('close')
}

async function submit() {
  if (submitting.value || !props.questions.length) return
  submitting.value = true
  error.value = ''
  try {
    const response = await http.post(
      `/api/courses/${props.courseId}/question-bank/exam-papers`,
      {
        title: form.title,
        duration_minutes: form.durationMinutes,
        total_score: form.totalScore,
        question_revision_ids: props.questions.map(item => item.revision_id),
        expected_bundle_revision_id: props.bundleRevisionId,
      },
    )
    emit('created', response.data?.paper || {})
  } catch (reason: any) {
    error.value = Number(reason?.response?.status || 0) === 409
      ? t('questionBank.examPaper.revisionConflict')
      : t('questionBank.examPaper.createFailed')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  void nextTick(() => dialog.value?.focus())
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.exam-paper-composer{position:fixed;inset:0;z-index:1200;display:grid;place-items:center;padding:24px;background:rgba(15,23,42,.42);backdrop-filter:blur(3px)}
.exam-paper-composer>section{width:min(620px,100%);max-height:min(760px,calc(100vh - 48px));overflow:auto;border:1px solid #e2e8f0;border-radius:14px;background:#fff;box-shadow:0 24px 70px rgba(15,23,42,.22)}
.exam-paper-composer>section>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:22px 24px 17px;border-bottom:1px solid #e8ecf2}
.exam-paper-composer>section>header>div{display:grid;gap:3px}.exam-paper-composer small{color:#6366f1;font-size:12px;font-weight:800;letter-spacing:.04em}.exam-paper-composer h2{margin:0;color:#172033;font-size:20px}.exam-paper-composer p{margin:0;color:#64748b;font-size:13px;line-height:1.55}.exam-paper-composer>section>header>button{width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.exam-paper-composer form{display:grid;gap:18px;padding:21px 24px 24px}.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.field{display:grid;gap:7px}.field>span{color:#334155;font-size:12px;font-weight:700}.field input{width:100%;height:42px;padding:0 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px}.field input:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.question-preview{overflow:hidden;border:1px solid #e2e8f0;border-radius:10px}.question-preview>header{height:42px;display:flex;align-items:center;justify-content:space-between;padding:0 12px;background:#f8fafc}.question-preview strong{color:#334155;font-size:12px}.question-preview>header span{min-width:22px;height:22px;display:grid;place-items:center;border-radius:999px;color:#4338ca;background:#eef2ff;font-size:12px;font-weight:800}.question-preview ol{max-height:220px;overflow:auto;margin:0;padding:0;list-style:none}.question-preview li{display:grid;grid-template-columns:92px minmax(0,1fr);gap:10px;padding:10px 12px;border-top:1px solid #edf1f5}.question-preview li>span{overflow:hidden;color:#6366f1;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.question-preview li p{color:#475569;font-size:12px}.submit-error{padding:9px 10px;border-radius:8px;color:#b91c1c!important;background:#fff1f2}.exam-paper-composer form>footer{display:flex;align-items:center;justify-content:space-between;gap:16px}.exam-paper-composer form>footer>span{max-width:300px;color:#64748b;font-size:12px;line-height:1.5}.exam-paper-composer form>footer>div{display:flex;gap:8px}.exam-paper-composer form>footer button{min-height:38px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 13px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.exam-paper-composer form>footer .primary{border-color:#514bdc;color:#fff;background:#514bdc}.exam-paper-composer button:disabled{opacity:.5;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:640px){.exam-paper-composer{padding:12px}.exam-paper-composer>section{max-height:calc(100vh - 24px)}.field-grid{grid-template-columns:1fr}.exam-paper-composer form>footer{align-items:stretch;flex-direction:column}.exam-paper-composer form>footer>div button{flex:1}.question-preview li{grid-template-columns:1fr;gap:4px}}
</style>
