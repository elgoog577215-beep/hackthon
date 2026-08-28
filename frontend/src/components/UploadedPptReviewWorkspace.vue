<template>
  <section class="ppt-review" :aria-busy="busy">
    <input ref="fileInput" class="sr-only" type="file" accept=".pptx" @change="handleFile" />

    <div v-if="loading" class="ppt-review-state">
      <LoaderCircle :size="22" class="spin" />
      <span>{{ t('courseWorkbench.pptReview.loading', '正在读取 PPT 审阅状态…') }}</span>
    </div>

    <div v-else-if="!review" class="ppt-review-start">
      <div class="ppt-review-start-actions">
        <button
          class="ppt-generate-primary"
          type="button"
          :disabled="!canGenerate || busy"
          :aria-describedby="!canGenerate ? 'ppt-generate-disabled-hint' : undefined"
          @click="emit('generate')"
        >
          <Sparkles :size="19" />
          {{ t('courseWorkbench.pptReview.aiGenerate', 'AI 生成') }}
        </button>
        <button class="ppt-upload-secondary" type="button" :disabled="busy" @click="fileInput?.click()">
          <LoaderCircle v-if="busy" :size="19" class="spin" />
          <Upload v-else :size="19" />
          {{ busy ? t('courseWorkbench.pptReview.analyzing', '正在解析与建立索引…') : t('courseWorkbench.pptReview.uploadReview', '上传并审阅') }}
        </button>
      </div>
      <small v-if="!canGenerate" id="ppt-generate-disabled-hint">{{ t('courseWorkbench.pptReview.generateDisabled', '上传自有 PPT 不受限制；AI 生成需先确认教案和讲稿。') }}</small>
      <p v-if="error" class="ppt-review-error"><TriangleAlert :size="15" />{{ error }}</p>
    </div>

    <template v-else>
      <header class="ppt-review-toolbar">
        <div>
          <strong>{{ review.source_filename }}</strong>
          <span>{{ review.slides.length }} {{ t('courseWorkbench.pptReview.pages', '页') }} · {{ openFindings.length }} {{ t('courseWorkbench.pptReview.findings', '项建议') }}</span>
        </div>
        <div class="ppt-review-toolbar-actions">
          <button
            class="ppt-report-toggle"
            type="button"
            :class="{ active: reportOpen }"
            :aria-expanded="reportOpen"
            @click="reportOpen = !reportOpen"
          >
            <FileSearch :size="14" />{{ t('courseWorkbench.pptReview.report', '审阅报告') }}
            <i v-if="openFindings.length">{{ openFindings.length }}</i>
          </button>
          <button type="button" :disabled="busy" @click="fileInput?.click()"><RefreshCw :size="14" />{{ t('courseWorkbench.pptReview.replace', '更换原稿') }}</button>
          <button type="button" :disabled="busy" @click="downloadRevision"><Download :size="14" />{{ t('courseWorkbench.pptReview.download', '下载修订稿') }}</button>
          <button class="confirm" type="button" :disabled="busy || review.source_state !== 'current' || review.status === 'confirmed'" @click="confirmReview">
            <Check :size="15" />
            {{ review.status === 'confirmed' ? t('courseWorkbench.pptReview.confirmed', '已确认为当前 PPT') : t('courseWorkbench.pptReview.confirm', '确认为当前 PPT') }}
          </button>
        </div>
      </header>

      <p v-if="review.source_state !== 'current'" class="ppt-review-warning"><TriangleAlert :size="15" />{{ t('courseWorkbench.pptReview.stale', '大纲、教案或讲稿已更新，请更换原稿或重新审阅后再确认。') }}</p>
      <p v-if="error" class="ppt-review-error"><TriangleAlert :size="15" />{{ error }}</p>

      <div class="ppt-review-layout">
        <nav class="ppt-slide-list" :aria-label="t('courseWorkbench.pptReview.slideList', 'PPT 页列表')">
          <button
            v-for="slide in review.slides"
            :key="slide.slide_id"
            type="button"
            :class="{ active: slide.slide_id === selectedSlideId }"
            @click="selectSlide(slide.slide_id)"
          >
            <span>{{ String(slide.slide_number).padStart(2, '0') }}</span>
            <strong>{{ slide.title || t('courseWorkbench.pptReview.untitled', '未命名页面') }}</strong>
            <i v-if="findingCount(slide.slide_id)">{{ findingCount(slide.slide_id) }}</i>
            <Check v-else :size="13" />
          </button>
        </nav>

        <main class="ppt-slide-workarea">
          <header>
            <div>
              <small>{{ t('courseWorkbench.pptReview.contentPreview', '内容预览') }} · {{ t('courseWorkbench.pptReview.slide', '第 {number} 页').replace('{number}', String(selectedSlide?.slide_number || '')) }}</small>
              <span>{{ t('courseWorkbench.pptReview.previewNote', '此处审阅文字与结构，不代替 PowerPoint 原版式预览。') }}</span>
            </div>
            <button type="button" :class="{ active: editing }" :disabled="busy || !editableBlocks.length" @click="toggleEditing">
              <Pencil :size="14" />{{ editing ? t('courseWorkbench.pptReview.exitEdit', '取消编辑') : t('courseWorkbench.pptReview.manualEdit', '手动编辑') }}
            </button>
          </header>

          <article v-if="selectedSlide" class="ppt-slide-canvas">
            <template v-if="editing">
              <label v-for="block in editableBlocks" :key="block.block_id">
                <span>{{ block.kind === 'title' ? t('courseWorkbench.pptReview.titleBlock', '标题') : t('courseWorkbench.pptReview.textBlock', '文字块') }}</span>
                <textarea v-model="editDraft[block.block_id]" :rows="block.kind === 'title' ? 2 : 5" />
              </label>
              <footer>
                <button type="button" @click="toggleEditing">{{ t('common.cancel', '取消') }}</button>
                <button class="save" type="button" :disabled="busy" @click="saveManualEdit"><Check :size="14" />{{ t('courseWorkbench.pptReview.saveEdit', '保存修改') }}</button>
              </footer>
            </template>
            <template v-else>
              <h3>{{ selectedSlide.title || t('courseWorkbench.pptReview.untitled', '未命名页面') }}</h3>
              <div v-for="block in bodyBlocks" :key="block.block_id" :data-kind="block.kind">
                <p v-for="(line, index) in block.text.split('\n')" :key="`${block.block_id}-${index}`">{{ line }}</p>
              </div>
              <span v-if="!selectedSlide.blocks.length" class="ppt-slide-empty">{{ t('courseWorkbench.pptReview.noText', '该页未识别到文字，请回到原 PPT 检查视觉内容。') }}</span>
            </template>
          </article>

          <section v-if="pendingCandidate" class="ppt-ai-candidate">
            <header><Sparkles :size="15" /><strong>{{ t('courseWorkbench.pptReview.aiCandidate', 'AI 修改候选') }}</strong><span>{{ t('courseWorkbench.pptReview.notApplied', '尚未应用') }}</span></header>
            <div>
              <p v-for="block in changedCandidateBlocks" :key="block.block_id">
                <del>{{ originalBlockText(block.block_id) }}</del>
                <ins>{{ block.text }}</ins>
              </p>
            </div>
            <footer>
              <button type="button" :disabled="busy" @click="resolveCandidate(false)">{{ t('courseWorkbench.pptReview.reject', '不采用') }}</button>
              <button class="accept" type="button" :disabled="busy" @click="resolveCandidate(true)"><Check :size="14" />{{ t('courseWorkbench.pptReview.accept', '应用修改') }}</button>
            </footer>
          </section>
        </main>

        <aside v-if="reportOpen" class="ppt-review-report">
          <header>
            <div><FileSearch :size="17" /><strong>{{ t('courseWorkbench.pptReview.report', '审阅报告') }}</strong></div>
            <div class="ppt-review-report-meta">
              <span>{{ selectedFindings.length }} {{ t('courseWorkbench.pptReview.currentSlideFindings', '项当前页建议') }}</span>
              <button type="button" :aria-label="t('common.close', '关闭')" @click="reportOpen = false"><X :size="15" /></button>
            </div>
          </header>
          <section class="ppt-review-sources">
            <small>{{ t('courseWorkbench.pptReview.basis', '本次对照依据') }}</small>
            <p v-if="!review.report.sources.length">{{ t('courseWorkbench.pptReview.noBasis', '当前仅做 PPT 内部检查，未读取到已确认的教学内容。') }}</p>
            <ul v-else>
              <li v-for="source in review.report.sources" :key="`${source.kind}-${source.revision_id}`">
                <CheckCircle2 :size="13" /><span>{{ source.label }}</span><small>{{ source.status === 'confirmed' ? t('courseWorkbench.pptReview.sourceConfirmed', '已确认') : t('courseWorkbench.pptReview.sourceCurrent', '当前版') }}</small>
              </li>
            </ul>
          </section>
          <div v-if="selectedFindings.length" class="ppt-finding-list">
            <article v-for="finding in selectedFindings" :key="finding.finding_id">
              <header><span>{{ confidenceLabel(finding.confidence) }}</span><small>{{ finding.slide_number ? t('courseWorkbench.pptReview.slide', '第 {number} 页').replace('{number}', String(finding.slide_number)) : t('courseWorkbench.pptReview.wholeDeck', '整份 PPT') }}</small></header>
              <strong>{{ finding.title }}</strong>
              <p>{{ finding.detail }}</p>
              <footer>
                <button type="button" :disabled="busy || pendingCandidate?.slide_id === selectedSlideId" @click="requestAiFix(finding)"><Sparkles :size="13" />{{ t('courseWorkbench.pptReview.aiFix', 'AI 修改') }}</button>
                <button type="button" :disabled="!editableBlocks.length" @click="startEditing"><Pencil :size="13" />{{ t('courseWorkbench.pptReview.manualEdit', '手动编辑') }}</button>
              </footer>
            </article>
          </div>
          <div v-else class="ppt-review-clear"><CheckCircle2 :size="20" /><strong>{{ t('courseWorkbench.pptReview.noSlideFindings', '当前页未发现明确问题') }}</strong><span>{{ t('courseWorkbench.pptReview.noSlideFindingsHint', '仍建议在原 PPT 中检查版式、动画和图表。') }}</span></div>
        </aside>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Check, CheckCircle2, Download, FileSearch, LoaderCircle, Pencil, RefreshCw, Sparkles, TriangleAlert, Upload, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import http, { teacherIdentityHeaders, teacherRequestConfig } from '../utils/http'
import { postGenerationStream } from '../shared/generation-stream'

type PptBlock = { block_id: string; shape_index: number; kind: 'title' | 'text' | 'table'; text: string; original_text: string; editable: boolean }
type PptSlide = { slide_id: string; slide_number: number; title: string; blocks: PptBlock[]; content_hash: string }
type ReviewSource = { kind: string; label: string; revision_id: string; status: string }
type ReviewFinding = { finding_id: string; code: string; title: string; detail: string; severity: string; confidence: 'high' | 'medium' | 'low'; slide_id: string; slide_number?: number; status: string }
type AiCandidate = { candidate_id: string; base_revision_id: string; slide_id: string; instruction: string; proposed_blocks: PptBlock[]; status: string }
type PptReview = {
  review_id: string
  source_filename: string
  source_state: 'current' | 'stale'
  status: 'reviewing' | 'confirmed'
  revision_id: string
  slides: PptSlide[]
  report: { sources: ReviewSource[]; findings: ReviewFinding[]; summary: Record<string, number> }
  ai_candidates: AiCandidate[]
}

const props = withDefaults(defineProps<{ courseId: string; courseTitle: string; lessonId: string; lessonTitle: string; canGenerate: boolean; referenceCount?: number; prepareSources?: () => Promise<void> }>(), {
  referenceCount: 0,
})
const emit = defineEmits<{ generate: []; confirmed: [] }>()
const fileInput = ref<HTMLInputElement | null>(null)
const review = ref<PptReview | null>(null)
const selectedSlideId = ref('')
const loading = ref(true)
const busy = ref(false)
const editing = ref(false)
const reportOpen = ref(false)
const error = ref('')
const editDraft = reactive<Record<string, string>>({})

const selectedSlide = computed(() => review.value?.slides.find(item => item.slide_id === selectedSlideId.value) || review.value?.slides[0] || null)
const editableBlocks = computed(() => selectedSlide.value?.blocks.filter(item => item.editable) || [])
const bodyBlocks = computed(() => selectedSlide.value?.blocks.filter(item => item.kind !== 'title') || [])
const openFindings = computed(() => review.value?.report.findings.filter(item => item.status === 'open') || [])
const selectedFindings = computed(() => openFindings.value.filter(item => !item.slide_id || item.slide_id === selectedSlideId.value))
const pendingCandidate = computed(() => review.value?.ai_candidates.find(item => item.status === 'pending') || null)
const changedCandidateBlocks = computed(() => pendingCandidate.value?.proposed_blocks.filter(item => item.text !== originalBlockText(item.block_id)) || [])
function apiError(value: unknown, fallback: string) {
  const candidate = value as { response?: { status?: number; data?: { detail?: { message?: string } | string } }; message?: string }
  if (candidate?.response?.status === 502) {
    return t('courseWorkbench.pptReview.serviceUnavailable', 'PPT 服务暂时不可用，请稍后重试。')
  }
  const detail = candidate?.response?.data?.detail
  return (typeof detail === 'object' ? detail?.message : detail) || candidate?.message || fallback
}
function selectSlide(slideId: string) { selectedSlideId.value = slideId; editing.value = false; hydrateDraft() }
function findingCount(slideId: string) { return openFindings.value.filter(item => item.slide_id === slideId).length }
function originalBlockText(blockId: string) { return selectedSlide.value?.blocks.find(item => item.block_id === blockId)?.text || '' }
function confidenceLabel(confidence: ReviewFinding['confidence']) {
  if (confidence === 'high') return t('courseWorkbench.pptReview.highConfidence', '高置信建议')
  if (confidence === 'medium') return t('courseWorkbench.pptReview.mediumConfidence', '需要确认')
  return t('courseWorkbench.pptReview.lowConfidence', '仅供检查')
}
function hydrateDraft() { editableBlocks.value.forEach(block => { editDraft[block.block_id] = block.text }) }
function toggleEditing() { editing.value = !editing.value; if (editing.value) hydrateDraft() }
function startEditing() { editing.value = true; hydrateDraft() }

async function loadReview() {
  if (!props.courseId || !props.lessonId) { review.value = null; loading.value = false; return }
  loading.value = true
  error.value = ''
  try {
    const response = await http.get(`/api/teacher/courses/${props.courseId}/lessons/${props.lessonId}/ppt-import/reviews/current`, teacherRequestConfig({ silentError: true }))
    review.value = response.data?.review || null
    selectedSlideId.value = review.value?.slides[0]?.slide_id || ''
  } catch (value) {
    error.value = apiError(value, t('courseWorkbench.pptReview.loadFailed', '暂时无法读取 PPT 审阅状态。'))
  } finally {
    loading.value = false
  }
}

async function ensurePackage() {
  const packages = (await http.get('/api/teacher-course-spaces', teacherRequestConfig({ params: { course_id: props.courseId }, silentError: true }))).data || []
  if (packages[0]?.package_id) return packages[0]
  const now = new Date(); const startYear = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1
  return (await http.post('/api/teacher-course-spaces', {
    course_name: props.courseTitle,
    academic_year: `${startYear}-${startYear + 1}`,
    term: now.getMonth() >= 7 ? '秋季' : '春季',
    template: 'blank',
    course_id: props.courseId,
  }, teacherRequestConfig({ silentError: true }))).data
}

async function handleFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.pptx')) { error.value = t('courseWorkbench.pptReview.pptxOnly', '请选择 .pptx 文件。'); return }
  busy.value = true
  error.value = ''
  try {
    if (props.prepareSources) await props.prepareSources()
    const coursePackage = await ensurePackage()
    const relativePath = `资料库/${props.lessonTitle}/PPT/${file.name}`
    const data = new FormData(); data.append('files', file); data.append('relative_paths', relativePath)
    const imported = (await http.post(`/api/teacher-course-spaces/${coursePackage.package_id}/imports`, data, teacherRequestConfig({ silentError: true }))).data
    const outcome = imported.outcomes?.find((item: { relative_path?: string }) => item.relative_path === relativePath)
    if (!outcome?.asset_id || outcome.outcome === 'rejected') throw new Error(outcome?.error || t('courseWorkbench.pptReview.uploadFailed', 'PPT 上传失败。'))
    const response = await http.post(`/api/teacher/courses/${props.courseId}/lessons/${props.lessonId}/ppt-import/reviews`, {
      package_id: coursePackage.package_id,
      asset_id: outcome.asset_id,
    }, teacherRequestConfig({ silentError: true }))
    review.value = response.data.review
    selectedSlideId.value = review.value?.slides[0]?.slide_id || ''
  } catch (value) {
    error.value = apiError(value, t('courseWorkbench.pptReview.uploadFailed', 'PPT 上传或审阅失败。'))
  } finally {
    busy.value = false
  }
}

async function saveManualEdit() {
  if (!review.value || !selectedSlide.value) return
  busy.value = true; error.value = ''
  try {
    const response = await http.patch(`/api/teacher/courses/${props.courseId}/lessons/${props.lessonId}/ppt-import/reviews/${review.value.review_id}/slides/${selectedSlide.value.slide_id}`, {
      base_revision_id: review.value.revision_id,
      blocks: editableBlocks.value.map(block => ({ block_id: block.block_id, text: editDraft[block.block_id] ?? block.text })),
    }, teacherRequestConfig({ silentError: true }))
    review.value = response.data.review
    editing.value = false
  } catch (value) { error.value = apiError(value, t('courseWorkbench.pptReview.saveFailed', '修改保存失败。')) }
  finally { busy.value = false }
}

async function requestAiFix(finding: ReviewFinding) {
  if (!review.value || !selectedSlide.value) return
  busy.value = true; error.value = ''
  try {
    const data = await postGenerationStream<{ candidate: AiCandidate }>(`/api/teacher/courses/${props.courseId}/lessons/${props.lessonId}/ppt-import/reviews/${review.value.review_id}/ai-candidates`, {
      base_revision_id: review.value.revision_id,
      slide_id: selectedSlide.value.slide_id,
      instruction: `针对审阅建议修改当前页：${finding.title}。${finding.detail}`,
    }, { headers: teacherIdentityHeaders() })
    review.value.ai_candidates = [...(review.value.ai_candidates || []).filter(item => item.status !== 'pending'), data.candidate]
  } catch (value) { error.value = apiError(value, t('courseWorkbench.pptReview.aiFailed', 'AI 修改候选生成失败。')) }
  finally { busy.value = false }
}

async function resolveCandidate(accept: boolean) {
  if (!review.value || !pendingCandidate.value) return
  busy.value = true; error.value = ''
  try {
    const response = await http.post(`/api/teacher/courses/${props.courseId}/lessons/${props.lessonId}/ppt-import/reviews/${review.value.review_id}/ai-candidates/${pendingCandidate.value.candidate_id}/resolve`, { accept }, teacherRequestConfig({ silentError: true }))
    review.value = response.data.review
  } catch (value) { error.value = apiError(value, t('courseWorkbench.pptReview.resolveFailed', '无法处理 AI 修改候选。')) }
  finally { busy.value = false }
}

async function confirmReview() {
  if (!review.value) return
  busy.value = true; error.value = ''
  try {
    const response = await http.post(`/api/teacher/courses/${props.courseId}/lessons/${props.lessonId}/ppt-import/reviews/${review.value.review_id}/confirm`, { revision_id: review.value.revision_id }, teacherRequestConfig({ silentError: true }))
    review.value = response.data.review
    emit('confirmed')
  } catch (value) { error.value = apiError(value, t('courseWorkbench.pptReview.confirmFailed', '当前 PPT 确认失败。')) }
  finally { busy.value = false }
}

async function downloadRevision() {
  if (!review.value) return
  busy.value = true; error.value = ''
  try {
    const response = await http.get(`/api/teacher/courses/${props.courseId}/lessons/${props.lessonId}/ppt-import/reviews/${review.value.review_id}/export.pptx`, teacherRequestConfig({ responseType: 'blob', silentError: true }))
    const url = URL.createObjectURL(response.data); const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `${review.value.source_filename.replace(/\.pptx$/i, '')}-已审阅.pptx`; anchor.click(); URL.revokeObjectURL(url)
  } catch (value) { error.value = apiError(value, t('courseWorkbench.pptReview.downloadFailed', '修订稿下载失败。')) }
  finally { busy.value = false }
}

watch(() => [props.courseId, props.lessonId], loadReview)
onMounted(loadReview)
</script>

<style scoped>
.ppt-review{min-height:0;color:#263147;background:#fff}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.ppt-review-state,.ppt-review-start{min-height:340px;display:flex;align-items:center;justify-content:center;flex-direction:column}.ppt-review-state{gap:10px;color:#64748b;font-size:13px}.ppt-review-start{gap:16px;padding:44px;text-align:center}.ppt-review-start-actions{display:flex;align-items:center;gap:14px}.ppt-review-start-actions button,.ppt-review-toolbar button,.ppt-slide-workarea>header button,.ppt-slide-canvas footer button,.ppt-ai-candidate button,.ppt-finding-list button,.ppt-review-report>header button{min-height:38px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 13px;border:1px solid #d8dee8;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.ppt-review-start-actions button{min-width:196px;min-height:58px;gap:10px;padding:0 24px;border-radius:12px;font-size:15px;transition:transform .16s cubic-bezier(.16,1,.3,1),border-color .16s ease,background-color .16s ease,box-shadow .16s ease}.ppt-review-start-actions button:hover:not(:disabled){transform:translateY(-1px)}.ppt-review-start-actions button:focus-visible{outline:3px solid rgba(91,87,232,.18);outline-offset:3px}.ppt-review-start-actions button:disabled,.ppt-review-toolbar button:disabled,.ppt-slide-workarea button:disabled,.ppt-finding-list button:disabled{opacity:.48;cursor:not-allowed}.ppt-generate-primary{border-color:#514bdc!important;color:#fff!important;background:#514bdc!important;box-shadow:0 8px 18px rgba(81,75,220,.2)}.ppt-generate-primary:hover:not(:disabled){background:#4338ca!important;box-shadow:0 10px 24px rgba(81,75,220,.24)}.ppt-upload-secondary{border-color:#cfd5df!important;color:#3f4b60!important;background:#fff!important}.ppt-upload-secondary:hover:not(:disabled){border-color:#aaa7e8!important;color:#37348c!important;background:#fafaff!important}.ppt-review-start>small{color:#697589;font-size:11px}.ppt-review-error,.ppt-review-warning{display:flex;align-items:center;gap:7px;margin:0;padding:10px 16px;color:#b42335;background:#fff1f2;font-size:12px}.ppt-review-warning{color:#9a6700;background:#fff8e5}
.ppt-review-toolbar{min-height:62px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:0 18px;border-bottom:1px solid #e5eaf1}.ppt-review-toolbar>div:first-child{min-width:0;display:grid;gap:3px}.ppt-review-toolbar strong{overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.ppt-review-toolbar span{color:#7b8798;font-size:11px}.ppt-review-toolbar-actions{display:flex;align-items:center;gap:8px}.ppt-review-toolbar .confirm{border-color:#514bdc;color:#fff;background:#514bdc}.ppt-report-toggle.active{border-color:#c7c4fa;color:#4338ca;background:#f3f2ff}.ppt-report-toggle i{min-width:17px;height:17px;display:grid;place-items:center;padding:0 4px;border-radius:999px;color:#fff;background:#8a5a00;font-size:9px;font-style:normal}.ppt-review-layout{position:relative;isolation:isolate;min-height:calc(100vh - 224px);display:grid;grid-template-columns:190px minmax(420px,1fr)}.ppt-slide-list{min-width:0;overflow:auto;padding:10px 8px;border-right:1px solid #e5eaf1;background:#f8f9fb}.ppt-slide-list button{width:100%;min-height:48px;display:grid;grid-template-columns:25px minmax(0,1fr) 19px;align-items:center;gap:7px;padding:6px 8px;border:0;border-radius:7px;color:#657286;background:transparent;text-align:left;cursor:pointer}.ppt-slide-list button:hover{background:#f0f2f7}.ppt-slide-list button.active{color:#37348c;background:#eaeaff}.ppt-slide-list button>span{font-size:10px;font-weight:750}.ppt-slide-list strong{overflow:hidden;font-size:11.5px;font-weight:620;text-overflow:ellipsis;white-space:nowrap}.ppt-slide-list i{width:18px;height:18px;display:grid;place-items:center;border-radius:50%;color:#8a4b00;background:#fff0c2;font-size:9px;font-style:normal;font-weight:800}.ppt-slide-list svg{color:#219653}
.ppt-slide-workarea{min-width:0;overflow:auto;padding:18px 24px 34px;background:#f3f5f9}.ppt-slide-workarea>header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px}.ppt-slide-workarea>header>div{display:grid;gap:3px}.ppt-slide-workarea>header small{color:#5c6678;font-size:11px;font-weight:750}.ppt-slide-workarea>header span{color:#8a96a8;font-size:10px}.ppt-slide-workarea>header button.active{color:#4338ca;background:#f0efff}.ppt-slide-canvas{box-sizing:border-box;width:min(100%,780px);min-height:420px;margin:0 auto;padding:52px 58px;border:1px solid #dfe4eb;background:#fff;box-shadow:0 12px 30px rgba(30,41,59,.08)}.ppt-slide-canvas h3{margin:0 0 30px;color:#172033;font-size:26px;line-height:1.3}.ppt-slide-canvas>div{margin-bottom:18px}.ppt-slide-canvas p{margin:0 0 9px;color:#465469;font-size:15px;line-height:1.7}.ppt-slide-canvas label{display:grid;gap:7px;margin-bottom:16px}.ppt-slide-canvas label>span{color:#566276;font-size:11px;font-weight:750}.ppt-slide-canvas textarea{box-sizing:border-box;width:100%;padding:10px 12px;border:1px solid #cbd4e1;border-radius:8px;outline:0;color:#263147;background:#fbfcfe;font:inherit;font-size:13px;line-height:1.55;resize:vertical}.ppt-slide-canvas textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.ppt-slide-canvas footer,.ppt-ai-candidate footer{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}.ppt-slide-canvas .save,.ppt-ai-candidate .accept{border-color:#514bdc;color:#fff;background:#514bdc}.ppt-slide-empty{display:block;padding-top:90px;color:#8a96a8;font-size:12px;text-align:center}.ppt-ai-candidate{width:min(100%,780px);margin:14px auto 0;border:1px solid #d9d7fa;border-radius:10px;background:#fff}.ppt-ai-candidate>header{min-height:44px;display:flex;align-items:center;gap:7px;padding:0 14px;border-bottom:1px solid #ecebfa;color:#4f46e5}.ppt-ai-candidate>header strong{font-size:12px}.ppt-ai-candidate>header span{margin-left:auto;color:#8a96a8;font-size:10px}.ppt-ai-candidate>div{padding:12px 14px}.ppt-ai-candidate p{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 8px}.ppt-ai-candidate del,.ppt-ai-candidate ins{padding:8px 10px;border-radius:6px;font-size:11px;line-height:1.5;text-decoration:none;white-space:pre-wrap}.ppt-ai-candidate del{color:#9f4450;background:#fff1f2}.ppt-ai-candidate ins{color:#2c6e49;background:#edf8f1}.ppt-ai-candidate footer{margin:0;padding:0 14px 12px}
.ppt-review-report{position:absolute;z-index:4;top:0;right:0;bottom:0;width:min(360px,calc(100% - 190px));min-width:0;overflow:auto;border-left:1px solid #dce2eb;background:#fff;box-shadow:-16px 0 30px rgba(30,41,59,.12)}.ppt-review-report>header{min-height:61px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 10px 0 16px;border-bottom:1px solid #e5eaf1}.ppt-review-report>header>div{display:flex;align-items:center;gap:7px}.ppt-review-report>header strong{font-size:13px}.ppt-review-report>header span{color:#7b8798;font-size:10px}.ppt-review-report-meta{flex:none}.ppt-review-report>header button{width:32px;min-height:32px;padding:0;border-color:transparent}.ppt-review-sources{padding:14px 16px;border-bottom:1px solid #e9edf3}.ppt-review-sources>small{color:#7b8798;font-size:10px;font-weight:750}.ppt-review-sources>p{margin:8px 0 0;color:#7b8798;font-size:11px;line-height:1.5}.ppt-review-sources ul{display:grid;gap:7px;margin:9px 0 0;padding:0;list-style:none}.ppt-review-sources li{display:grid;grid-template-columns:15px minmax(0,1fr) auto;align-items:center;gap:5px;color:#526075;font-size:11px}.ppt-review-sources li svg{color:#219653}.ppt-review-sources li small{color:#8a96a8;font-size:9px}.ppt-finding-list{display:grid}.ppt-finding-list article{padding:16px;border-bottom:1px solid #edf0f4}.ppt-finding-list article>header{display:flex;justify-content:space-between;gap:10px;margin-bottom:9px}.ppt-finding-list article>header span{color:#6b5e1a;font-size:9px;font-weight:750}.ppt-finding-list article>header small{color:#8a96a8;font-size:9px}.ppt-finding-list article>strong{display:block;color:#2c374a;font-size:12.5px;line-height:1.45}.ppt-finding-list article>p{margin:7px 0 12px;color:#657286;font-size:11px;line-height:1.65}.ppt-finding-list footer{display:flex;gap:7px}.ppt-finding-list button{min-height:32px;padding-inline:9px;font-size:10px}.ppt-review-clear{min-height:210px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:7px;padding:24px;color:#219653;text-align:center}.ppt-review-clear strong{color:#465469;font-size:12px}.ppt-review-clear span{max-width:230px;color:#8a96a8;font-size:10px;line-height:1.5}
@media(max-width:1180px){.ppt-review-layout{grid-template-columns:160px minmax(360px,1fr)}.ppt-review-report{width:min(340px,calc(100% - 160px))}.ppt-slide-canvas{padding:40px}.ppt-review-toolbar-actions button{font-size:0}.ppt-review-toolbar-actions button svg{display:block}.ppt-report-toggle i{display:grid}}
@media(max-width:760px){.ppt-review-start{padding:28px 18px}.ppt-review-start-actions{width:100%;flex-direction:column}.ppt-review-start-actions button{width:100%}.ppt-review-toolbar{align-items:flex-start;flex-direction:column;padding:12px}.ppt-review-toolbar-actions{width:100%}.ppt-review-toolbar-actions button{flex:1}.ppt-review-layout{display:block}.ppt-slide-list{display:flex;overflow:auto;border-right:0;border-bottom:1px solid #e5eaf1}.ppt-slide-list button{min-width:150px}.ppt-slide-workarea{padding:14px 12px}.ppt-slide-canvas{min-height:360px;padding:32px 24px}.ppt-review-report{top:0;width:min(92vw,360px);border-top:0}}
@media(prefers-reduced-motion:reduce){.ppt-review-start-actions button{transition:none}}
</style>
