<template>
  <section class="question-import" data-testid="question-import-workspace">
    <header class="question-import__topbar">
      <span />
      <div>
        <button v-if="hasQuestionBank" type="button" class="quiet-button" @click="emit('show-bank')">
          <LibraryBig :size="15" />{{ t('questionBank.importFlow.existingBank', '已有题库') }}
        </button>
        <button type="button" class="quiet-button quiet-button--ai" @click="emit('show-ai')">
          <WandSparkles :size="15" />{{ t('questionBank.importFlow.aiGenerate', 'AI 生成题目') }}
        </button>
      </div>
    </header>

    <ol class="question-import__steps" :aria-label="t('questionBank.importFlow.progress', '导入进度')">
      <li v-for="(step, index) in steps" :key="step" :class="stepState(index + 1)">
        <span><Check v-if="stepState(index + 1) === 'done'" :size="14" /><template v-else>{{ index + 1 }}</template></span>
        <strong>{{ step }}</strong>
      </li>
    </ol>

    <div v-if="errorMessage" class="question-import__error" role="alert">
      <TriangleAlert :size="17" />
      <span>{{ errorMessage }}</span>
      <button type="button" @click="errorMessage = ''">{{ t('common.close', '关闭') }}</button>
    </div>

    <template v-if="!session">
      <section
        class="question-import__dropzone"
        :class="{ 'is-dragging': dragging, 'is-uploading': uploading }"
        @dragenter.prevent="dragging = true"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="handleDrop"
      >
        <input
          ref="fileInput"
          data-testid="question-import-file"
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          @change="handleFileInput"
        />
        <FileUp :size="34" />
        <strong>{{ uploading
          ? t('questionBank.importFlow.uploading', '正在读取并识别题目')
          : t('questionBank.importFlow.dropTitle', '上传 PDF 或 Word 试题') }}</strong>
        <p>{{ t('questionBank.importFlow.dropHint', '系统会识别题号、题型、选项、答案和解析，原文始终保留可对照。') }}</p>
        <button type="button" class="primary-action" data-testid="choose-question-file" :disabled="uploading" @click="openFileDialog">
          <LoaderCircle v-if="uploading" :size="16" class="spin" />
          <Upload v-else :size="16" />
          {{ uploading ? `${uploadProgress}%` : t('questionBank.importFlow.chooseFile', '选择文件') }}
        </button>
        <small>{{ t('questionBank.importFlow.supported', '支持 .pdf、.docx，单文件最大 50 MB') }}</small>
        <i v-if="uploading"><span :style="{ width: `${uploadProgress}%` }" /></i>
      </section>

      <section v-if="recentImports.length" class="question-import__recent">
        <header>
          <strong>{{ t('questionBank.importFlow.recent', '最近导入') }}</strong>
          <small>{{ t('questionBank.importFlow.recoverHint', '未完成的校对可以继续') }}</small>
        </header>
        <button
          v-for="item in recentImports.slice(0, 3)"
          :key="item.import_id"
          type="button"
          @click="resumeImport(item.import_id)"
        >
          <FileText :size="18" />
          <span><strong>{{ item.filename }}</strong><small>{{ recentStatus(item) }}</small></span>
          <ChevronRight :size="17" />
        </button>
      </section>
    </template>

    <template v-else>
      <section class="question-import__filebar">
        <FileText :size="19" />
        <strong>{{ session.filename }}</strong>
        <span>{{ t('questionBank.importFlow.recognized', '已识别 {count} 道').replace('{count}', String(session.question_count)) }}</span>
        <b v-if="session.pending_count">{{ t('questionBank.importFlow.pending', '{count} 道待确认').replace('{count}', String(session.pending_count)) }}</b>
        <button type="button" class="quiet-button" @click="resetImport">
          <RotateCcw :size="15" />{{ t('questionBank.importFlow.reupload', '重新上传') }}
        </button>
        <label>
          <List :size="15" />
          <select v-model.number="selectedIndex" :aria-label="t('questionBank.importFlow.questionList', '题目列表')">
            <option v-for="(question, index) in session.questions" :key="question.draft_id" :value="index">
              {{ index + 1 }}. {{ question.prompt.slice(0, 26) }}
            </option>
          </select>
        </label>
      </section>

      <section v-if="selectedQuestion" class="question-import__review">
        <article class="source-preview">
          <header><strong>{{ t('questionBank.importFlow.source', '原文') }}</strong></header>
          <nav>
            <button type="button" :disabled="sourcePageIndex === 0" @click="sourcePageIndex -= 1"><ChevronLeft :size="17" /></button>
            <span>{{ t('questionBank.importFlow.page', '第 {page} / {total} 页').replace('{page}', String(activeSourcePage?.page || 1)).replace('{total}', String(session.source_pages.length || 1)) }}</span>
            <button type="button" :disabled="sourcePageIndex >= session.source_pages.length - 1" @click="sourcePageIndex += 1"><ChevronRight :size="17" /></button>
          </nav>
          <div class="source-preview__paper">
            <pre>{{ activeSourcePage?.text || t('questionBank.importFlow.noSourceText', '本页没有可显示的文字') }}</pre>
          </div>
        </article>

        <article class="question-editor">
          <header>
            <strong>{{ t('questionBank.importFlow.result', '识别结果') }}</strong>
            <nav>
              <button type="button" :disabled="selectedIndex === 0" @click="selectQuestion(selectedIndex - 1)"><ChevronLeft :size="15" />{{ t('common.previous', '上一题') }}</button>
              <span>{{ t('questionBank.importFlow.questionPosition', '第 {current} / {total} 题').replace('{current}', String(selectedIndex + 1)).replace('{total}', String(session.question_count)) }}</span>
              <button type="button" :disabled="selectedIndex >= session.questions.length - 1" @click="selectQuestion(selectedIndex + 1)">{{ t('common.next', '下一题') }}<ChevronRight :size="15" /></button>
            </nav>
          </header>

          <div v-if="selectedQuestion.warnings.length && !selectedQuestion.confirmed" class="question-editor__warning">
            <CircleAlert :size="16" />
            <span>{{ warningLabel(selectedQuestion.warnings[0] || '') }}</span>
          </div>
          <div v-else class="question-editor__confirmed">
            <CircleCheck :size="16" />{{ t('questionBank.importFlow.recognitionReady', '识别结果已可用') }}
          </div>

          <form @submit.prevent="saveQuestion(false)">
            <label class="field-row field-row--compact">
              <span>{{ t('questionBank.importFlow.type', '题型') }}</span>
              <select v-model="selectedQuestion.question_type">
                <option value="single_choice">{{ t('questionBank.importFlow.types.singleChoice', '单选题') }}</option>
                <option value="multiple_choice">{{ t('questionBank.importFlow.types.multipleChoice', '多选题') }}</option>
                <option value="true_false">{{ t('questionBank.importFlow.types.trueFalse', '判断题') }}</option>
                <option value="fill_blank">{{ t('questionBank.importFlow.types.fillBlank', '填空题') }}</option>
                <option value="short_answer">{{ t('questionBank.importFlow.types.shortAnswer', '简答题') }}</option>
                <option value="calculation">{{ t('questionBank.importFlow.types.calculation', '计算题') }}</option>
                <option value="essay">{{ t('questionBank.importFlow.types.essay', '论述题') }}</option>
              </select>
            </label>
            <label class="field-row">
              <span>{{ t('questionBank.importFlow.prompt', '题目') }}</span>
              <textarea v-model="selectedQuestion.prompt" rows="3" maxlength="12000" />
            </label>

            <fieldset v-if="isChoiceQuestion" class="option-editor">
              <legend>{{ t('questionBank.importFlow.options', '选项') }}</legend>
              <label v-for="option in selectedQuestion.options" :key="option.id">
                <input
                  v-if="selectedQuestion.question_type === 'multiple_choice'"
                  type="checkbox"
                  :checked="multipleAnswers.includes(option.id)"
                  @change="toggleMultipleAnswer(option.id)"
                />
                <input v-else v-model="selectedQuestion.answer" type="radio" :value="option.id" />
                <b>{{ option.id }}</b>
                <input v-model="option.text" type="text" />
                <button type="button" :aria-label="t('questionBank.importFlow.removeOption', '删除选项')" @click="removeOption(option.id)"><MinusCircle :size="17" /></button>
              </label>
              <button v-if="selectedQuestion.options.length < 8" type="button" @click="addOption"><Plus :size="15" />{{ t('questionBank.importFlow.addOption', '添加选项') }}</button>
            </fieldset>

            <label v-else class="field-row">
              <span>{{ t('questionBank.importFlow.answer', '参考答案') }}</span>
              <textarea v-model="selectedQuestion.answer" rows="2" />
            </label>
            <label class="field-row">
              <span>{{ t('questionBank.importFlow.explanation', '答案解析') }}</span>
              <textarea v-model="selectedQuestion.explanation" rows="3" />
            </label>
            <footer>
              <button type="submit" class="quiet-button" :disabled="saving">{{ t('questionBank.importFlow.saveDraft', '保存修改') }}</button>
              <button type="button" class="primary-action" data-testid="confirm-import-question" :disabled="saving" @click="saveQuestion(true)">
                <LoaderCircle v-if="saving" :size="15" class="spin" />
                <Check v-else :size="15" />{{ t('questionBank.importFlow.confirmQuestion', '确认本题') }}
              </button>
            </footer>
          </form>
        </article>
      </section>

      <footer class="question-import__commit">
        <div>
          <strong v-if="session.pending_count">{{ t('questionBank.importFlow.stillPending', '还有 {count} 道待确认').replace('{count}', String(session.pending_count)) }}</strong>
          <strong v-else>{{ t('questionBank.importFlow.readyToImport', '全部题目已确认') }}</strong>
          <span>{{ t('questionBank.importFlow.commitHint', '导入后将保留原文来源，并写入课程正式题库。') }}</span>
        </div>
        <button type="button" class="primary-action" data-testid="commit-question-import" :disabled="Boolean(session.pending_count) || committing" @click="commitImport">
          <LoaderCircle v-if="committing" :size="16" class="spin" />
          <LockKeyhole v-else :size="16" />
          {{ t('questionBank.importFlow.commit', '确认并导入 {count} 道题').replace('{count}', String(session.question_count)) }}
        </button>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  FileText,
  FileUp,
  LibraryBig,
  List,
  LoaderCircle,
  LockKeyhole,
  MinusCircle,
  Plus,
  RotateCcw,
  TriangleAlert,
  Upload,
  WandSparkles,
} from 'lucide-vue-next'
import http, { teacherRequestConfig } from '@/utils/http'
import { t } from '@/shared/i18n'

interface ImportOption { id: string; text: string }
interface ImportQuestion {
  draft_id: string
  prompt: string
  question_type: string
  options: ImportOption[]
  answer: string
  explanation: string
  score: number | null
  node_id: string
  source_page: number | null
  warnings: string[]
  confirmed: boolean
}
interface ImportSession {
  import_id: string
  filename: string
  extension: string
  size_bytes: number
  status: string
  step: string
  question_count: number
  pending_count: number
  questions: ImportQuestion[]
  source_pages: Array<{ page: number; text: string }>
  updated_at: string
}
interface ImportSummary extends Omit<ImportSession, 'questions' | 'source_pages'> {}

const props = withDefaults(defineProps<{
  courseId: string
  initialNodeIds?: string[]
  hasQuestionBank?: boolean
}>(), {
  initialNodeIds: () => [],
  hasQuestionBank: false,
})
const emit = defineEmits<{
  'show-ai': []
  'show-bank': []
  imported: [bundleRevisionId: string]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const session = ref<ImportSession | null>(null)
const recentImports = ref<ImportSummary[]>([])
const selectedIndex = ref(0)
const sourcePageIndex = ref(0)
const dragging = ref(false)
const uploading = ref(false)
const saving = ref(false)
const committing = ref(false)
const uploadProgress = ref(0)
const errorMessage = ref('')

const steps = computed(() => [
  t('questionBank.importFlow.steps.upload', '上传文件'),
  t('questionBank.importFlow.steps.recognize', '识别题目'),
  t('questionBank.importFlow.steps.review', '校对确认'),
  t('questionBank.importFlow.steps.import', '导入题库'),
])
const selectedQuestion = computed(() => session.value?.questions[selectedIndex.value] || null)
const activeSourcePage = computed(() => session.value?.source_pages[sourcePageIndex.value] || null)
const isChoiceQuestion = computed(() => ['single_choice', 'multiple_choice'].includes(selectedQuestion.value?.question_type || ''))
const multipleAnswers = computed<string[]>(() => (selectedQuestion.value?.answer || '').toUpperCase().match(/[A-H]/g) || [])

onMounted(() => { void loadWorkspace() })
watch(() => props.courseId, () => {
  session.value = null
  selectedIndex.value = 0
  sourcePageIndex.value = 0
  void loadWorkspace()
})
watch(selectedIndex, () => syncSourcePage())

function apiError(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  return detail?.message || fallback
}

async function loadWorkspace() {
  errorMessage.value = ''
  try {
    const [active, recent] = await Promise.all([
      http.get(`/api/courses/${props.courseId}/question-bank/imports/active`, teacherRequestConfig({ silentError: true })),
      http.get(`/api/courses/${props.courseId}/question-bank/imports`, teacherRequestConfig({ silentError: true })),
    ])
    session.value = active.data?.session || null
    recentImports.value = recent.data?.imports || []
    selectedIndex.value = Math.max(
      0,
      session.value?.questions.findIndex(item => !item.confirmed) ?? 0,
    )
    syncSourcePage()
  } catch (error) {
    errorMessage.value = apiError(error, t('questionBank.importFlow.loadFailed', '未能读取导入记录'))
  }
}

function stepState(step: number) {
  if (!session.value) return step === 1 ? 'active' : 'upcoming'
  if (step <= 2) return 'done'
  if (step === 3) return 'active'
  return 'upcoming'
}

function openFileDialog() { fileInput.value?.click() }
function handleFileInput(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) void uploadFile(file)
}
function handleDrop(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void uploadFile(file)
}

async function uploadFile(file: File) {
  const extension = file.name.toLowerCase().split('.').pop()
  if (!['pdf', 'docx'].includes(extension || '')) {
    errorMessage.value = t('questionBank.importFlow.unsupported', '请选择 PDF 或 .docx 文件')
    return
  }
  uploading.value = true
  uploadProgress.value = 5
  errorMessage.value = ''
  const form = new FormData()
  form.append('file', file)
  props.initialNodeIds.forEach(nodeId => form.append('node_ids', nodeId))
  try {
    const response = await http.post(
      `/api/courses/${props.courseId}/question-bank/imports`,
      form,
      teacherRequestConfig({
        silentError: true,
        onUploadProgress: progress => {
          uploadProgress.value = progress.total
            ? Math.max(5, Math.round(progress.loaded / progress.total * 70))
            : 35
        },
      }),
    )
    uploadProgress.value = 100
    session.value = response.data
    selectedIndex.value = Math.max(0, response.data.questions.findIndex((item: ImportQuestion) => !item.confirmed))
    syncSourcePage()
    await loadRecentImports()
  } catch (error) {
    errorMessage.value = apiError(error, t('questionBank.importFlow.uploadFailed', '文件未能导入，请检查格式后重试'))
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function loadRecentImports() {
  const response = await http.get(
    `/api/courses/${props.courseId}/question-bank/imports`,
    teacherRequestConfig({ silentError: true }),
  )
  recentImports.value = response.data?.imports || []
}

async function resumeImport(importId: string) {
  errorMessage.value = ''
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/question-bank/imports/${importId}`,
      teacherRequestConfig({ silentError: true }),
    )
    session.value = response.data
    selectedIndex.value = Math.max(0, response.data.questions.findIndex((item: ImportQuestion) => !item.confirmed))
    syncSourcePage()
  } catch (error) {
    errorMessage.value = apiError(error, t('questionBank.importFlow.loadFailed', '未能读取导入记录'))
  }
}

function resetImport() {
  session.value = null
  selectedIndex.value = 0
  sourcePageIndex.value = 0
  errorMessage.value = ''
}

function selectQuestion(index: number) {
  selectedIndex.value = Math.max(0, Math.min((session.value?.questions.length || 1) - 1, index))
}

function syncSourcePage() {
  const page = selectedQuestion.value?.source_page
  const index = session.value?.source_pages.findIndex(item => item.page === page) ?? -1
  sourcePageIndex.value = index >= 0 ? index : 0
}

async function saveQuestion(confirm: boolean) {
  if (!session.value || !selectedQuestion.value) return
  saving.value = true
  errorMessage.value = ''
  const currentId = selectedQuestion.value.draft_id
  try {
    const response = await http.patch(
      `/api/courses/${props.courseId}/question-bank/imports/${session.value.import_id}/items/${currentId}`,
      {
        prompt: selectedQuestion.value.prompt,
        question_type: selectedQuestion.value.question_type,
        options: selectedQuestion.value.options,
        answer: selectedQuestion.value.answer,
        explanation: selectedQuestion.value.explanation,
        score: selectedQuestion.value.score,
        node_id: selectedQuestion.value.node_id,
        ...(confirm ? { confirmed: true } : {}),
      },
      teacherRequestConfig({ silentError: true }),
    )
    session.value = response.data
    if (confirm) {
      const nextPending = session.value!.questions.findIndex((item, index) => index > selectedIndex.value && !item.confirmed)
      if (nextPending >= 0) selectedIndex.value = nextPending
      else if (selectedIndex.value < session.value!.questions.length - 1) selectedIndex.value += 1
    }
  } catch (error) {
    errorMessage.value = apiError(error, t('questionBank.importFlow.saveFailed', '未能保存这道题'))
  } finally {
    saving.value = false
  }
}

async function commitImport() {
  if (!session.value || session.value.pending_count) return
  committing.value = true
  errorMessage.value = ''
  try {
    const response = await http.post(
      `/api/courses/${props.courseId}/question-bank/imports/${session.value.import_id}/commit`,
      {},
      teacherRequestConfig({ silentError: true }),
    )
    emit('imported', String(response.data?.bundle_revision_id || ''))
    emit('show-bank')
  } catch (error) {
    errorMessage.value = apiError(error, t('questionBank.importFlow.commitFailed', '未能写入正式题库'))
  } finally {
    committing.value = false
  }
}

function addOption() {
  if (!selectedQuestion.value) return
  const id = String.fromCharCode(65 + selectedQuestion.value.options.length)
  selectedQuestion.value.options.push({ id, text: '' })
}
function removeOption(id: string) {
  if (!selectedQuestion.value) return
  selectedQuestion.value.options = selectedQuestion.value.options.filter(option => option.id !== id)
  if (multipleAnswers.value.includes(id)) toggleMultipleAnswer(id)
  if (selectedQuestion.value.answer === id) selectedQuestion.value.answer = ''
}
function toggleMultipleAnswer(id: string) {
  if (!selectedQuestion.value) return
  const current = new Set(multipleAnswers.value)
  if (current.has(id)) current.delete(id)
  else current.add(id)
  selectedQuestion.value.answer = [...current].sort().join(',')
}

function warningLabel(code: string) {
  const labels: Record<string, string> = {
    answer_missing: t('questionBank.importFlow.warnings.answerMissing', '未识别到答案，请确认'),
    options_incomplete: t('questionBank.importFlow.warnings.optionsIncomplete', '选项识别不完整，请确认'),
    prompt_missing: t('questionBank.importFlow.warnings.promptMissing', '题干识别不完整，请确认'),
    source_parse_degraded: t('questionBank.importFlow.warnings.degraded', '原文解析质量较低，请对照检查'),
  }
  return labels[code] || t('questionBank.importFlow.warnings.review', '这道题需要人工确认')
}

function recentStatus(item: ImportSummary) {
  if (item.status === 'committed') return t('questionBank.importFlow.status.committed', '已导入题库')
  if (item.pending_count) return t('questionBank.importFlow.pending', '{count} 道待确认').replace('{count}', String(item.pending_count))
  return t('questionBank.importFlow.status.ready', '可导入')
}
</script>

<style scoped>
.question-import{display:grid;gap:14px;min-width:0;color:#1f2937}.question-import__topbar{min-height:40px;display:flex;align-items:center;justify-content:space-between}.question-import__topbar>div{display:flex;gap:8px}.quiet-button,.primary-action{min-height:36px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 12px;border:1px solid #d8dee8;border-radius:8px;color:#475569;background:#fff;font:inherit;font-size:12px;font-weight:700;cursor:pointer}.quiet-button:hover:not(:disabled){border-color:#a5b4fc;color:#4338ca;background:#fafaff}.quiet-button--ai{color:#4338ca}.primary-action{border-color:#4f46e5;color:#fff;background:#4f46e5;box-shadow:0 7px 16px rgba(79,70,229,.14)}.primary-action:hover:not(:disabled){background:#4338ca}.quiet-button:disabled,.primary-action:disabled{opacity:.5;cursor:not-allowed}.question-import__steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0;padding:13px 24px;border:1px solid #dfe5ee;border-radius:12px;background:#fff;list-style:none}.question-import__steps li{position:relative;display:flex;align-items:center;justify-content:center;gap:9px;color:#8b95a7;font-size:12px}.question-import__steps li:not(:last-child)::after{position:absolute;top:50%;left:calc(50% + 48px);width:calc(100% - 96px);height:1px;background:#dce2eb;content:""}.question-import__steps li>span{position:relative;z-index:1;width:27px;height:27px;display:grid;place-items:center;border:1px solid #cbd3df;border-radius:50%;background:#fff;font-weight:800}.question-import__steps li.active{color:#4338ca}.question-import__steps li.active>span,.question-import__steps li.done>span{border-color:#4f46e5;color:#fff;background:#4f46e5}.question-import__steps li.done{color:#374151}.question-import__error{display:flex;align-items:center;gap:8px;padding:10px 12px;border:1px solid #fed7aa;border-radius:8px;color:#9a3412;background:#fff7ed;font-size:12px}.question-import__error button{margin-left:auto;border:0;color:inherit;background:transparent;cursor:pointer}.question-import__dropzone{min-height:390px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;padding:44px;border:1px dashed #bbc4d2;border-radius:14px;background:#fff;transition:border-color .16s ease,background-color .16s ease}.question-import__dropzone.is-dragging{border-color:#6366f1;background:#f7f7ff}.question-import__dropzone>svg{color:#5b57e8}.question-import__dropzone strong{font-size:18px}.question-import__dropzone p{max-width:560px;margin:0;color:#64748b;font-size:12px;line-height:1.7;text-align:center}.question-import__dropzone small{color:#94a3b8;font-size:11px}.question-import__dropzone input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}.question-import__dropzone>i{width:min(420px,80%);height:4px;overflow:hidden;border-radius:4px;background:#e5e7eb}.question-import__dropzone>i span{height:100%;display:block;background:#4f46e5;transition:width .2s}.question-import__recent{overflow:hidden;border:1px solid #dfe5ee;border-radius:12px;background:#fff}.question-import__recent>header{display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-bottom:1px solid #edf0f4}.question-import__recent>header strong{font-size:13px}.question-import__recent>header small{color:#94a3b8;font-size:11px}.question-import__recent>button{width:100%;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:11px;padding:12px 16px;border:0;border-bottom:1px solid #edf0f4;color:#64748b;background:#fff;text-align:left;cursor:pointer}.question-import__recent>button:last-child{border-bottom:0}.question-import__recent>button:hover{background:#fafbff}.question-import__recent>button span{display:grid;gap:2px}.question-import__recent>button strong{color:#334155;font-size:12px}.question-import__recent>button small{font-size:10px}.question-import__filebar{min-height:54px;display:grid;grid-template-columns:auto auto minmax(0,1fr) auto auto auto;align-items:center;gap:10px;padding:8px 14px;border:1px solid #dfe5ee;border-radius:10px;background:#fff}.question-import__filebar>svg{color:#e05252}.question-import__filebar>strong{font-size:12px}.question-import__filebar>span{padding-left:14px;border-left:1px solid #e5e7eb;color:#059669;font-size:11px}.question-import__filebar>b{color:#ea580c;font-size:11px}.question-import__filebar label{min-width:142px;display:flex;align-items:center;gap:6px;padding:0 8px;border:1px solid #d8dee8;border-radius:8px;color:#4f46e5;background:#fff}.question-import__filebar select{width:100%;min-height:34px;border:0;outline:0;color:#4338ca;background:transparent;font-size:11px}.question-import__review{min-height:560px;display:grid;grid-template-columns:minmax(0,.92fr) minmax(0,1.08fr);overflow:hidden;border:1px solid #dfe5ee;border-radius:12px;background:#fff}.source-preview,.question-editor{min-width:0;display:grid;grid-template-rows:auto auto minmax(0,1fr)}.source-preview{border-right:1px solid #dfe5ee}.source-preview>header,.question-editor>header{min-height:48px;display:flex;align-items:center;justify-content:space-between;padding:0 16px;border-bottom:1px solid #e7ebf2}.source-preview>header strong,.question-editor>header>strong{font-size:13px}.source-preview>nav{min-height:42px;display:flex;align-items:center;justify-content:center;gap:12px;border-bottom:1px solid #edf0f4;color:#64748b;font-size:11px}.source-preview>nav button,.question-editor>header button{display:flex;align-items:center;gap:3px;border:0;color:#5552c8;background:transparent;font-size:11px;cursor:pointer}.source-preview>nav button:disabled,.question-editor>header button:disabled{color:#b3bdca;cursor:not-allowed}.source-preview__paper{min-height:0;overflow:auto;padding:26px;background:#f3f5f8}.source-preview__paper pre{min-height:100%;box-sizing:border-box;margin:0;padding:30px 28px;border:1px solid #e3e6eb;color:#303846;background:#fff;box-shadow:0 7px 22px rgba(30,41,59,.07);font:13px/1.95 ui-serif,STSong,SimSun,serif;white-space:pre-wrap}.question-editor{grid-template-rows:auto auto minmax(0,1fr)}.question-editor>header nav{display:flex;align-items:center;gap:9px;color:#334155;font-size:11px}.question-editor__warning,.question-editor__confirmed{display:flex;align-items:center;gap:7px;margin:10px 14px 0;padding:8px 10px;border:1px solid #fed7aa;border-radius:7px;color:#ea580c;background:#fff7ed;font-size:11px}.question-editor__confirmed{border-color:#bbf7d0;color:#047857;background:#f0fdf4}.question-editor form{min-height:0;overflow:auto;display:grid;align-content:start;gap:13px;padding:14px 18px 18px}.field-row{display:grid;gap:6px}.field-row>span,.option-editor legend{color:#374151;font-size:11px;font-weight:750}.field-row--compact{grid-template-columns:44px 150px;align-items:center}.field-row textarea,.field-row select,.option-editor label>input[type="text"]{width:100%;box-sizing:border-box;padding:8px 9px;border:1px solid #d8dee8;border-radius:7px;outline:0;color:#273244;background:#fff;font:inherit;font-size:12px;line-height:1.55;resize:vertical}.field-row textarea:focus,.field-row select:focus,.option-editor label>input[type="text"]:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.09)}.option-editor{display:grid;gap:7px;margin:0;padding:0;border:0}.option-editor label{display:grid;grid-template-columns:auto 25px minmax(0,1fr) auto;align-items:center;gap:6px}.option-editor label>b{height:30px;display:grid;place-items:center;border-radius:7px;color:#374151;background:#f0f2f6;font-size:11px}.option-editor label>button,.option-editor>button{display:flex;align-items:center;gap:5px;border:0;color:#64748b;background:transparent;font-size:11px;cursor:pointer}.option-editor>button{justify-self:start;color:#4f46e5}.question-editor form>footer{display:flex;justify-content:flex-end;gap:8px;padding-top:3px}.question-import__commit{min-height:62px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:10px 16px;border:1px solid #dfe5ee;border-radius:10px;background:#fff}.question-import__commit>div{display:grid;grid-template-columns:auto auto;align-items:center;gap:5px 18px}.question-import__commit strong{color:#1f2937;font-size:13px}.question-import__commit span{color:#64748b;font-size:10px}.spin{animation:question-import-spin .9s linear infinite}@keyframes question-import-spin{to{transform:rotate(360deg)}}
.question-import__review{height:max(480px,calc(100vh - 442px));min-height:480px}
@media(max-width:1050px){.question-import__review{height:auto;grid-template-columns:1fr}.source-preview{min-height:420px;border-right:0;border-bottom:1px solid #dfe5ee}.question-import__filebar{grid-template-columns:auto minmax(0,1fr) auto}.question-import__filebar>span,.question-import__filebar>b{display:none}.question-import__commit{align-items:stretch;flex-direction:column}.question-import__commit .primary-action{align-self:flex-end}}
</style>
