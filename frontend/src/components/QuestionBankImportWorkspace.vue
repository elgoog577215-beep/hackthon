<template>
  <section class="question-import" data-testid="question-import-workspace">
    <input
      ref="fileInput"
      data-testid="question-import-file"
      type="file"
      multiple
      accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      @change="handleFileInput"
    />

    <main class="question-import__main">
      <header class="question-import__toolbar">
        <div class="question-import__identity">
          <FileText v-if="session" :size="18" />
          <div>
            <strong>{{ session?.filename || t('questionBank.importFlow.workspaceTitle', '导入题目') }}</strong>
            <small v-if="session">
              {{ t('questionBank.importFlow.recognized', '已识别 {count} 道').replace('{count}', String(session.question_count)) }}
              <template v-if="session.pending_count"> · {{ t('questionBank.importFlow.pending', '{count} 道待确认').replace('{count}', String(session.pending_count)) }}</template>
              <template v-else-if="sessionCommitted"> · {{ t('questionBank.importFlow.status.committed', '已导入题库') }}</template>
            </small>
          </div>
        </div>
        <div class="question-import__actions">
          <button v-if="hasQuestionBank || sessionCommitted" type="button" class="quiet-button" @click="emit('show-bank')">
            <LibraryBig :size="15" />{{ t('questionBank.importFlow.existingBank', '已有题库') }}
          </button>
          <button type="button" class="quiet-button quiet-button--ai" @click="emit('show-ai')">
            <WandSparkles :size="15" />{{ t('questionBank.importFlow.aiGenerate', 'AI 生成题目') }}
          </button>
        </div>
      </header>

      <div v-if="errorMessage" class="question-import__error" role="alert">
        <TriangleAlert :size="16" />
        <span>{{ errorMessage }}</span>
        <button type="button" @click="errorMessage = ''">{{ t('common.close', '关闭') }}</button>
      </div>

      <section
        v-if="!session"
        class="question-import__dropzone"
        :class="{ 'is-dragging': dragging, 'is-uploading': uploading }"
        @dragenter.prevent="dragging = true"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="handleDrop"
      >
        <FileUp :size="32" />
        <strong>{{ t('questionBank.importFlow.dropTitle', '批量导入 PDF 或 Word 试题') }}</strong>
        <span>{{ t('questionBank.importFlow.dropHint', '一次选择多份文件，系统会分别识别并保留原文。') }}</span>
        <button type="button" class="primary-action" data-testid="choose-question-file" :disabled="uploading" @click="openFileDialog">
          <LoaderCircle v-if="uploading" :size="16" class="spin" />
          <Upload v-else :size="16" />
          {{ uploading ? `${uploadProgress}%` : t('questionBank.importFlow.chooseFiles', '选择多份文件') }}
        </button>
        <small>{{ t('questionBank.importFlow.supported', '支持 PDF、DOCX，单文件最大 50 MB') }}</small>
        <i v-if="uploading"><span :style="{ width: `${uploadProgress}%` }" /></i>
      </section>

      <section v-else-if="selectedQuestion" class="question-import__review">
        <article class="source-preview">
          <header>
            <strong>{{ t('questionBank.importFlow.source', '原文') }}</strong>
            <nav>
              <button type="button" :disabled="sourcePageIndex === 0" @click="sourcePageIndex -= 1"><ChevronLeft :size="16" /></button>
              <span>{{ t('questionBank.importFlow.page', '第 {page} / {total} 页').replace('{page}', String(activeSourcePage?.page || 1)).replace('{total}', String(session.source_pages.length || 1)) }}</span>
              <button type="button" :disabled="sourcePageIndex >= session.source_pages.length - 1" @click="sourcePageIndex += 1"><ChevronRight :size="16" /></button>
            </nav>
          </header>
          <div class="source-preview__paper">
            <pre>{{ activeSourcePage?.text || t('questionBank.importFlow.noSourceText', '本页没有可显示的文字') }}</pre>
          </div>
        </article>

        <article class="question-editor">
          <header>
            <strong>{{ t('questionBank.importFlow.result', '识别结果') }}</strong>
            <nav>
              <button type="button" :disabled="selectedIndex === 0" @click="selectQuestion(selectedIndex - 1)"><ChevronLeft :size="15" /></button>
              <span>{{ t('questionBank.importFlow.questionPosition', '第 {current} / {total} 题').replace('{current}', String(selectedIndex + 1)).replace('{total}', String(session.question_count)) }}</span>
              <button type="button" :disabled="selectedIndex >= session.questions.length - 1" @click="selectQuestion(selectedIndex + 1)"><ChevronRight :size="15" /></button>
            </nav>
          </header>

          <div v-if="selectedQuestion.warnings.length && !selectedQuestion.confirmed" class="question-editor__warning">
            <CircleAlert :size="15" />
            <span>{{ warningLabel(selectedQuestion.warnings[0] || '') }}</span>
          </div>

          <form @submit.prevent="saveQuestion(false)">
            <label class="field-row field-row--compact">
              <span>{{ t('questionBank.importFlow.type', '题型') }}</span>
              <select v-model="selectedQuestion.question_type" :disabled="sessionCommitted">
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
              <textarea v-model="selectedQuestion.prompt" rows="3" maxlength="12000" :readonly="sessionCommitted" />
            </label>

            <fieldset v-if="isChoiceQuestion" class="option-editor">
              <legend>{{ t('questionBank.importFlow.options', '选项') }}</legend>
              <label v-for="option in selectedQuestion.options" :key="option.id">
                <input
                  v-if="selectedQuestion.question_type === 'multiple_choice'"
                  type="checkbox"
                  :checked="multipleAnswers.includes(option.id)"
                  :disabled="sessionCommitted"
                  @change="toggleMultipleAnswer(option.id)"
                />
                <input v-else v-model="selectedQuestion.answer" type="radio" :value="option.id" :disabled="sessionCommitted" />
                <b>{{ option.id }}</b>
                <input v-model="option.text" type="text" :readonly="sessionCommitted" />
                <button v-if="!sessionCommitted" type="button" :aria-label="t('questionBank.importFlow.removeOption', '删除选项')" @click="removeOption(option.id)"><MinusCircle :size="16" /></button>
              </label>
              <button v-if="!sessionCommitted && selectedQuestion.options.length < 8" type="button" @click="addOption"><Plus :size="15" />{{ t('questionBank.importFlow.addOption', '添加选项') }}</button>
            </fieldset>

            <label v-else class="field-row">
              <span>{{ t('questionBank.importFlow.answer', '参考答案') }}</span>
              <textarea v-model="selectedQuestion.answer" rows="2" :readonly="sessionCommitted" />
            </label>
            <label class="field-row">
              <span>{{ t('questionBank.importFlow.explanation', '答案解析') }}</span>
              <textarea v-model="selectedQuestion.explanation" rows="3" :readonly="sessionCommitted" />
            </label>
            <footer v-if="!sessionCommitted">
              <button type="submit" class="quiet-button" :disabled="saving">{{ t('questionBank.importFlow.saveDraft', '保存修改') }}</button>
              <button type="button" class="primary-action" data-testid="confirm-import-question" :disabled="saving" @click="saveQuestion(true)">
                <LoaderCircle v-if="saving" :size="15" class="spin" />
                <Check v-else :size="15" />{{ t('questionBank.importFlow.confirmQuestion', '确认本题') }}
              </button>
            </footer>
          </form>
        </article>
      </section>

      <footer v-if="session" class="question-import__commit">
        <div>
          <strong v-if="sessionCommitted">{{ t('questionBank.importFlow.status.committed', '已导入题库') }}</strong>
          <strong v-else-if="session.pending_count">{{ t('questionBank.importFlow.stillPending', '还有 {count} 道待确认').replace('{count}', String(session.pending_count)) }}</strong>
          <strong v-else>{{ t('questionBank.importFlow.readyToImport', '全部题目已确认') }}</strong>
          <span>{{ sessionCommitted
            ? t('questionBank.importFlow.committedHint', '原文与题目来源已经保留。')
            : t('questionBank.importFlow.commitHint', '确认后写入课程正式题库。') }}</span>
        </div>
        <button v-if="sessionCommitted" type="button" class="quiet-button" @click="emit('show-bank')">
          <LibraryBig :size="15" />{{ t('questionBank.importFlow.viewBank', '查看题库') }}
        </button>
        <button v-else type="button" class="primary-action" data-testid="commit-question-import" :disabled="Boolean(session.pending_count) || committing" @click="commitImport">
          <LoaderCircle v-if="committing" :size="16" class="spin" />
          <Check v-else :size="16" />
          {{ t('questionBank.importFlow.commit', '导入 {count} 道题').replace('{count}', String(session.question_count)) }}
        </button>
      </footer>
    </main>

    <aside class="question-import__documents" :aria-label="t('questionBank.importFlow.documents', '导入文档')">
      <header>
        <div>
          <strong>{{ t('questionBank.importFlow.documents', '导入文档') }}</strong>
          <small>{{ recentImports.length }}</small>
        </div>
        <button type="button" data-testid="add-question-files" :aria-label="t('questionBank.importFlow.addFiles', '继续导入')" :disabled="uploading" @click="openFileDialog">
          <Plus :size="17" />
        </button>
      </header>

      <div v-if="uploading" class="question-import__uploading" aria-live="polite">
        <LoaderCircle :size="15" class="spin" />
        <span>
          <strong>{{ t('questionBank.importFlow.importingBatch', '正在识别 {current}/{total}').replace('{current}', String(uploadFileIndex)).replace('{total}', String(uploadFileTotal)) }}</strong>
          <small>{{ uploadFileName }}</small>
        </span>
        <i><span :style="{ width: `${uploadProgress}%` }" /></i>
      </div>
      <p v-else-if="batchResultMessage" class="question-import__batch-result">{{ batchResultMessage }}</p>

      <nav v-if="recentImports.length">
        <button
          v-for="item in recentImports"
          :key="item.import_id"
          type="button"
          :class="{ active: session?.import_id === item.import_id }"
          @click="resumeImport(item.import_id)"
        >
          <FileText :size="17" />
          <span>
            <strong>{{ item.filename }}</strong>
            <small>{{ item.question_count }} {{ t('questionBank.questionUnit', '道') }} · {{ recentStatus(item) }}</small>
          </span>
          <i :data-status="item.status" />
        </button>
      </nav>
      <div v-else class="question-import__documents-empty">
        <Files :size="21" />
        <span>{{ t('questionBank.importFlow.noDocuments', '还没有导入文档') }}</span>
      </div>
    </aside>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  FileText,
  FileUp,
  Files,
  LibraryBig,
  LoaderCircle,
  MinusCircle,
  Plus,
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
const uploadFileName = ref('')
const uploadFileIndex = ref(0)
const uploadFileTotal = ref(0)
const batchResultMessage = ref('')
const errorMessage = ref('')

const selectedQuestion = computed(() => session.value?.questions[selectedIndex.value] || null)
const activeSourcePage = computed(() => session.value?.source_pages[sourcePageIndex.value] || null)
const isChoiceQuestion = computed(() => ['single_choice', 'multiple_choice'].includes(selectedQuestion.value?.question_type || ''))
const multipleAnswers = computed<string[]>(() => (selectedQuestion.value?.answer || '').toUpperCase().match(/[A-H]/g) || [])
const sessionCommitted = computed(() => session.value?.status === 'committed')

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
    const recent = await http.get(
      `/api/courses/${props.courseId}/question-bank/imports`,
      teacherRequestConfig({ silentError: true }),
    )
    recentImports.value = recent.data?.imports || []
    const rememberedImportId = readRememberedImportId()
    if (rememberedImportId && recentImports.value.some(item => item.import_id === rememberedImportId)) {
      await resumeImport(rememberedImportId, true)
    }
  } catch (error) {
    errorMessage.value = apiError(error, t('questionBank.importFlow.loadFailed', '未能读取导入记录'))
  }
}

function importStorageKey() {
  return `lingzhi:question-import:${props.courseId}`
}

function readRememberedImportId() {
  try { return window.sessionStorage.getItem(importStorageKey()) || '' } catch { return '' }
}

function rememberImport(importId: string) {
  try {
    if (importId) window.sessionStorage.setItem(importStorageKey(), importId)
    else window.sessionStorage.removeItem(importStorageKey())
  } catch { /* storage can be unavailable */ }
}

function applySession(value: ImportSession | null) {
  session.value = value
  selectedIndex.value = Math.max(0, value?.questions.findIndex(item => !item.confirmed) ?? 0)
  syncSourcePage()
  rememberImport(value?.import_id || '')
}

function openFileDialog() { fileInput.value?.click() }
function handleFileInput(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files || [])
  if (files.length) void uploadFiles(files)
}
function handleDrop(event: DragEvent) {
  dragging.value = false
  const files = Array.from(event.dataTransfer?.files || [])
  if (files.length) void uploadFiles(files)
}

function importSummary(value: ImportSession): ImportSummary {
  const { questions: _questions, source_pages: _sourcePages, ...summary } = value
  return summary
}

function upsertRecentImport(value: ImportSession) {
  recentImports.value = [
    importSummary(value),
    ...recentImports.value.filter(item => item.import_id !== value.import_id),
  ]
}

async function uploadFiles(files: File[]) {
  const supported = files.filter(file => ['pdf', 'docx'].includes(file.name.toLowerCase().split('.').pop() || ''))
  const unsupportedCount = files.length - supported.length
  if (!supported.length) {
    errorMessage.value = t('questionBank.importFlow.unsupported', '请选择 PDF 或 .docx 文件')
    return
  }
  uploading.value = true
  uploadFileTotal.value = supported.length
  uploadFileIndex.value = 0
  uploadProgress.value = 0
  batchResultMessage.value = ''
  errorMessage.value = ''
  const created: ImportSession[] = []
  const failures: string[] = []
  for (const [index, file] of supported.entries()) {
    uploadFileIndex.value = index + 1
    uploadFileName.value = file.name
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
            const currentRatio = progress.total ? progress.loaded / progress.total : 0.35
            uploadProgress.value = Math.round((index + Math.min(0.9, currentRatio * 0.9)) / supported.length * 100)
          },
        }),
      )
      const imported = response.data as ImportSession
      created.push(imported)
      upsertRecentImport(imported)
      uploadProgress.value = Math.round((index + 1) / supported.length * 100)
    } catch (error) {
      failures.push(`${file.name}：${apiError(error, t('questionBank.importFlow.uploadFailed', '识别失败'))}`)
    }
  }
  if (created.length) {
    applySession(created[0] || null)
    batchResultMessage.value = t('questionBank.importFlow.batchComplete', '已加入 {count} 份文档').replace('{count}', String(created.length))
    try { await loadRecentImports() } catch { /* local summaries already show successful files */ }
  }
  if (unsupportedCount || failures.length) {
    const parts = [...failures]
    if (unsupportedCount) parts.push(t('questionBank.importFlow.unsupportedCount', '{count} 份文件格式不支持').replace('{count}', String(unsupportedCount)))
    errorMessage.value = parts.join('；')
  }
  uploading.value = false
  uploadFileName.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

async function loadRecentImports() {
  const response = await http.get(
    `/api/courses/${props.courseId}/question-bank/imports`,
    teacherRequestConfig({ silentError: true }),
  )
  recentImports.value = response.data?.imports || []
}

async function resumeImport(importId: string, silent = false) {
  if (!silent) errorMessage.value = ''
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/question-bank/imports/${importId}`,
      teacherRequestConfig({ silentError: true }),
    )
    applySession(response.data)
  } catch (error) {
    rememberImport('')
    if (!silent) errorMessage.value = apiError(error, t('questionBank.importFlow.loadFailed', '未能读取导入记录'))
  }
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
    upsertRecentImport(response.data)
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
    applySession(response.data?.session || session.value)
    upsertRecentImport(session.value!)
    try { await loadRecentImports() } catch { /* committed state is already current */ }
    emit('imported', String(response.data?.bundle_revision_id || ''))
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
.question-import {
  height: calc(100vh - 196px);
  min-height: 500px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 264px;
  overflow: hidden;
  border: 1px solid #e1e6ee;
  border-radius: 10px;
  color: #263147;
  background: #fff;
}
.question-import > input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.question-import__main {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  background: #fff;
}
.question-import__toolbar {
  grid-row: 1;
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 0 18px;
  border-bottom: 1px solid #e7ebf1;
}
.question-import__identity {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 9px;
}
.question-import__identity > svg {
  flex: 0 0 auto;
  color: #6366f1;
}
.question-import__identity > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}
.question-import__identity strong {
  overflow: hidden;
  color: #202a3d;
  font-size: 13px;
  font-weight: 750;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.question-import__identity small {
  color: #667085;
  font-size: 10.5px;
  line-height: 1.35;
}
.question-import__actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 6px;
}
.quiet-button,
.primary-action {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 11px;
  border: 1px solid #d8dee8;
  border-radius: 7px;
  color: #475569;
  background: #fff;
  font: inherit;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
}
.quiet-button:hover:not(:disabled) {
  border-color: #b8b6ed;
  color: #4338ca;
  background: #f8f8ff;
}
.quiet-button--ai {
  border-color: transparent;
  color: #5552c8;
  background: transparent;
}
.primary-action {
  border-color: #514bdc;
  color: #fff;
  background: #514bdc;
  box-shadow: 0 6px 14px rgba(81, 75, 220, .14);
}
.primary-action:hover:not(:disabled) {
  background: #4338ca;
}
.quiet-button:focus-visible,
.primary-action:focus-visible,
.question-import__documents button:focus-visible,
.source-preview button:focus-visible,
.question-editor button:focus-visible {
  outline: 2px solid #6366f1;
  outline-offset: 2px;
}
.quiet-button:disabled,
.primary-action:disabled {
  opacity: .48;
  cursor: not-allowed;
}
.question-import__error {
  grid-row: 2;
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 16px;
  border-bottom: 1px solid #fed7aa;
  color: #9a3412;
  background: #fffaf4;
  font-size: 11px;
}
.question-import__error button {
  margin-left: auto;
  border: 0;
  color: inherit;
  background: transparent;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}
.question-import__dropzone {
  grid-row: 3;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  margin: 28px;
  border: 1px dashed #b9c3d1;
  border-radius: 10px;
  color: #64748b;
  background: #fbfcfe;
  transition: border-color .16s ease, background-color .16s ease;
}
.question-import__dropzone.is-dragging {
  border-color: #6366f1;
  background: #f6f6ff;
}
.question-import__dropzone > svg {
  color: #5b57e8;
}
.question-import__dropzone > strong {
  color: #263147;
  font-size: 17px;
}
.question-import__dropzone > span {
  color: #667085;
  font-size: 11.5px;
}
.question-import__dropzone > small {
  color: #7a8699;
  font-size: 10.5px;
}
.question-import__dropzone > i {
  width: min(340px, 72%);
  height: 3px;
  overflow: hidden;
  border-radius: 3px;
  background: #e4e8ef;
}
.question-import__dropzone > i span {
  height: 100%;
  display: block;
  background: #5b57e8;
}
.question-import__review {
  grid-row: 3;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, .44fr) minmax(0, .56fr);
  overflow: hidden;
}
.source-preview,
.question-editor {
  min-width: 0;
  min-height: 0;
}
.source-preview {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  border-right: 1px solid #e1e6ee;
}
.source-preview > header,
.question-editor > header {
  min-height: 46px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 15px;
  border-bottom: 1px solid #e8ecf2;
}
.source-preview > header strong,
.question-editor > header strong {
  color: #2d3748;
  font-size: 12.5px;
}
.source-preview nav,
.question-editor nav {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #667085;
  font-size: 10.5px;
}
.source-preview nav button,
.question-editor nav button {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 6px;
  color: #5552c8;
  background: transparent;
  cursor: pointer;
}
.source-preview nav button:hover:not(:disabled),
.question-editor nav button:hover:not(:disabled) {
  background: #f0f1fa;
}
.source-preview nav button:disabled,
.question-editor nav button:disabled {
  color: #b6c0ce;
  cursor: default;
}
.source-preview__paper {
  min-height: 0;
  overflow: auto;
  padding: 20px;
  background: #f3f5f8;
}
.source-preview__paper pre {
  min-height: 100%;
  box-sizing: border-box;
  margin: 0;
  padding: 25px 23px;
  border: 1px solid #e3e7ed;
  color: #364152;
  background: #fff;
  box-shadow: 0 8px 20px rgba(30, 41, 59, .06);
  font: 12px/1.9 ui-serif, STSong, SimSun, serif;
  white-space: pre-wrap;
}
.question-editor {
  display: flex;
  flex-direction: column;
}
.question-editor__warning {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 16px;
  border-bottom: 1px solid #ffedd5;
  color: #b45309;
  background: #fffaf4;
  font-size: 10.5px;
}
.question-editor form {
  min-height: 0;
  flex: 1;
  overflow: auto;
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 14px 17px 18px;
}
.field-row {
  display: grid;
  gap: 5px;
}
.field-row > span,
.option-editor legend {
  color: #475569;
  font-size: 10.5px;
  font-weight: 750;
}
.field-row--compact {
  grid-template-columns: 38px 144px;
  align-items: center;
}
.field-row textarea,
.field-row select,
.option-editor label > input[type="text"] {
  width: 100%;
  box-sizing: border-box;
  padding: 7px 8px;
  border: 1px solid #d8dee8;
  border-radius: 6px;
  outline: 0;
  color: #273244;
  background: #fff;
  font: inherit;
  font-size: 11.5px;
  line-height: 1.5;
  resize: vertical;
}
.field-row textarea:focus,
.field-row select:focus,
.option-editor label > input[type="text"]:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, .09);
}
.field-row textarea[readonly],
.field-row select:disabled,
.option-editor input[readonly] {
  color: #536176;
  background: #f8fafc;
}
.option-editor {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  border: 0;
}
.option-editor label {
  display: grid;
  grid-template-columns: auto 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
}
.option-editor label > b {
  height: 29px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: #475569;
  background: #f0f2f6;
  font-size: 10.5px;
}
.option-editor label > button,
.option-editor > button {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px;
  border: 0;
  color: #778397;
  background: transparent;
  font: inherit;
  font-size: 10.5px;
  cursor: pointer;
}
.option-editor > button {
  justify-self: start;
  color: #5552c8;
}
.question-editor form > footer {
  display: flex;
  justify-content: flex-end;
  gap: 7px;
  padding-top: 2px;
}
.question-import__commit {
  grid-row: 4;
  min-height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 17px;
  border-top: 1px solid #e1e6ee;
  background: #fff;
}
.question-import__commit > div {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.question-import__commit strong {
  color: #263147;
  font-size: 12px;
}
.question-import__commit span {
  color: #667085;
  font-size: 10px;
}
.question-import__documents {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #dfe5ed;
  background: #fafbfc;
}
.question-import__documents > header {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 13px 0 15px;
  border-bottom: 1px solid #e5e9ef;
}
.question-import__documents > header > div {
  display: flex;
  align-items: center;
  gap: 7px;
}
.question-import__documents > header strong {
  color: #2f3a4d;
  font-size: 12.5px;
}
.question-import__documents > header small {
  min-width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: #6366f1;
  background: #eeefff;
  font-size: 9.5px;
  font-weight: 750;
}
.question-import__documents > header button {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 7px;
  color: #5552c8;
  background: transparent;
  cursor: pointer;
}
.question-import__documents > header button:hover:not(:disabled) {
  background: #eef0f7;
}
.question-import__documents > nav {
  min-height: 0;
  overflow: auto;
}
.question-import__documents > nav > button {
  position: relative;
  width: 100%;
  min-height: 62px;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 8px;
  align-items: center;
  gap: 9px;
  padding: 9px 13px 9px 15px;
  border: 0;
  border-bottom: 1px solid #e9edf2;
  color: #738095;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.question-import__documents > nav > button:hover {
  background: #f4f5f8;
}
.question-import__documents > nav > button.active {
  color: #5552c8;
  background: #f0f1ff;
}
.question-import__documents > nav > button.active::before {
  position: absolute;
  inset-block: 10px;
  left: 0;
  width: 2px;
  border-radius: 2px;
  background: #6366f1;
  content: "";
}
.question-import__documents > nav > button > span {
  min-width: 0;
  display: grid;
  gap: 3px;
}
.question-import__documents > nav strong {
  overflow: hidden;
  color: #344054;
  font-size: 11.5px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.question-import__documents > nav small {
  overflow: hidden;
  color: #748197;
  font-size: 9.5px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.question-import__documents > nav i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f59e0b;
}
.question-import__documents > nav i[data-status="ready"] {
  background: #6366f1;
}
.question-import__documents > nav i[data-status="committed"] {
  background: #16a34a;
}
.question-import__uploading {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 11px 14px;
  border-bottom: 1px solid #e5e9ef;
  color: #5b57e8;
}
.question-import__uploading > span {
  min-width: 0;
  display: grid;
  gap: 2px;
}
.question-import__uploading strong {
  color: #3f3b8f;
  font-size: 10.5px;
}
.question-import__uploading small {
  overflow: hidden;
  color: #748197;
  font-size: 9.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.question-import__uploading > i {
  grid-column: 1 / -1;
  height: 2px;
  overflow: hidden;
  border-radius: 2px;
  background: #e3e5ee;
}
.question-import__uploading > i span {
  height: 100%;
  display: block;
  background: #6366f1;
}
.question-import__batch-result {
  margin: 0;
  padding: 9px 14px;
  border-bottom: 1px solid #e5e9ef;
  color: #047857;
  font-size: 10px;
}
.question-import__documents-empty {
  flex: 1;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 8px;
  color: #98a2b3;
  font-size: 10.5px;
}
.spin {
  animation: question-import-spin .9s linear infinite;
}
@keyframes question-import-spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 1180px) {
  .question-import {
    grid-template-columns: minmax(0, 1fr) 232px;
  }
  .question-import__actions .quiet-button {
    padding-inline: 8px;
  }
  .question-import__review {
    grid-template-columns: minmax(0, .4fr) minmax(0, .6fr);
  }
}
</style>
