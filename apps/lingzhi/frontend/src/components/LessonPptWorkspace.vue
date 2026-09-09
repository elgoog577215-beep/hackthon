<template>
  <section class="lesson-ppt-workspace" data-testid="lesson-ppt-workspace">
    <header class="lesson-ppt-header">
      <div class="lesson-ppt-title">
        <h1>{{ title }}</h1>
        <span v-if="state.manuscript" class="lesson-ppt-page-count">{{ pageCountLabel }}</span>
      </div>
      <TeacherDocumentCommandBar class="lesson-ppt-toolbar" :label="t('pptWorkspace.editor.actions')" :show-status="dirty || saving" :status-label="saving ? t('pptWorkspace.savingManuscript') : t('pptWorkspace.manuscriptUnsaved')" :status-tone="saving ? 'busy' : 'warning'">
      <template #context><UiSegmentedControl v-model="tab" :options="tabs" size="compact" :accessibility-label="t('pptWorkspace.pageEditing')" /></template>
      <button v-if="state.manuscript && tab === 'manuscript'" type="button" :disabled="busy || state.source_state === 'stale'" data-testid="ppt-live-edit" @click="editor?.editing ? editor?.finishEditing() : editor?.beginEditing()"><Check v-if="editor?.editing" :size="16" /><Pencil v-else :size="16" />{{ editor?.editing ? t('pptWorkspace.editor.finishEditing') : t('pptLive.edit') }}</button>
      <button type="button" :disabled="!state.can_export || dirty || busy" :title="t('pptProject.export')" :aria-label="t('pptProject.export')" @click="download"><Download :size="16" /></button>
      <button type="button" :disabled="dirty || saving" :title="t('pptProject.originalReview')" :aria-label="t('pptProject.originalReview')" @click="openOriginal"><FileCheck2 :size="16" /></button>
      </TeacherDocumentCommandBar>
    </header>
      <section v-if="error" class="lesson-ppt-error" role="alert">
        <div><strong>{{ errorTitle }}</strong><p>{{ errorSummary }}</p></div>
        <button type="button" :disabled="saving || busy" @click="retry"><RefreshCw :size="16" />{{ t('common.retry') }}</button>
        <details v-if="errorTechnical"><summary>{{ t('pptLive.errors.technicalDetails') }}</summary><code>{{ errorTechnical }}</code></details>
      </section>
      <p v-if="state.manuscript && state.source_state === 'stale'" class="lesson-ppt-notice" role="status">{{ t('pptLive.stale') }}<button type="button" :disabled="busy || dirty" @click="sync"><RefreshCw :size="16" />{{ t('pptLive.sync') }}</button></p>
      <section v-if="progressVisible" class="lesson-ppt-progress" data-testid="ppt-manuscript-progress" :aria-label="t('pptLive.progress.title')" aria-live="polite">
        <header>
          <div><strong>{{ t('pptLive.progress.title') }}</strong><span>{{ progressMessage }}</span><small v-if="progressMeta">{{ progressMeta }}</small></div>
          <b>{{ progressPercent }}%</b>
        </header>
        <div class="lesson-ppt-progress__track" role="progressbar" :aria-label="progressMessage" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100"><i :style="{ transform: `scaleX(${progressPercent / 100})` }" /></div>
        <ol>
          <li v-for="step in progressSteps" :key="step.id" :data-step="step.id" :data-state="step.state">
            <span><Check v-if="step.state === 'done'" :size="15" /><TriangleAlert v-else-if="step.state === 'failed'" :size="15" /><LoaderCircle v-else-if="step.state === 'current'" :size="15" class="spinning" /><Circle v-else :size="15" /></span>
            <strong>{{ step.label }}</strong>
          </li>
        </ol>
      </section>
      <section v-if="state.sync_candidate" class="lesson-ppt-candidate">
        <header><strong>{{ t('pptLive.candidate') }}</strong><button type="button" :disabled="busy" @click="resolveSync(true)"><Check :size="16" />{{ t('pptLive.accept') }}</button><button type="button" :disabled="busy" @click="resolveSync(false)">{{ t('pptLive.reject') }}</button></header>
        <PptManuscriptWorkflow :title="title" :state="candidateState" continuous review-only embedded external-actions />
      </section>
      <template v-if="state.manuscript">
        <PptManuscriptWorkflow v-show="tab === 'manuscript'" ref="editor" :title="title" :state="state" embedded external-actions continuous
          :allow-page-regeneration="false" :saving="saving" :busy="state.source_state === 'stale'"
          @dirty-change="dirty = $event" @pending-change="scheduleSave" @save-manuscript="save" @page-change="selectPage" />
        <section v-if="tab === 'render'" class="lesson-ppt-preview">
          <nav class="lesson-ppt-page-strip" :aria-label="t('pptWorkspace.sidebar.selectPage')">
            <button v-for="page in pages" :key="page.page_id" type="button" :class="{ active: selectedPage === page.page_id }" :aria-current="selectedPage === page.page_id ? 'page' : undefined" @click="selectPage(page.page_id)"><span>{{ page.page_number }}</span><strong>{{ page.title }}</strong></button>
          </nav>
          <div class="lesson-ppt-canvas">
            <p v-if="previewError" class="lesson-ppt-error" role="alert">{{ previewError }}<button type="button" @click="loadPreview([selectedPage])"><RefreshCw :size="16" />{{ t('common.retry') }}</button></p>
            <p v-if="previewRevisions[selectedPage] !== state.revision && visibleSlides.length" class="lesson-ppt-notice">{{ t('pptLive.previousPreview') }}</p>
            <SlideCanvas v-for="slide in visibleSlides" :key="slide.unit_id" :slide="slide as any" :page-number="Number(slide.position) + 1" :page-count="state.manuscript.page_count" :deck-title="title" :theme="state.theme" :course-id="courseId" />
            <p v-if="!visibleSlides.length" class="lesson-ppt-notice"><LoaderCircle v-if="previewBusy" :size="18" class="spinning" />{{ previewBusy ? t('pptLive.previewing') : t('pptLive.previewUnavailable') }}</p>
          </div>
        </section>
      </template>
      <div v-else-if="!progressVisible" class="lesson-ppt-empty">
        <div class="lesson-ppt-empty-mark"><Presentation :size="24" /></div>
        <h2>{{ loading ? t('common.loading') : t('pptLive.missing') }}</h2>
        <p>{{ loading ? t('pptProject.preparing') : emptyDescription }}</p>
        <p v-for="(issue, index) in state.page_errors || []" :key="index" class="lesson-ppt-error">{{ issue.message }}</p>
        <button type="button" :disabled="loading || busy || !state.source_script_revision_id" @click="complete"><RefreshCw :size="16" />{{ t('pptLive.complete') }}</button>
      </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Check, Circle, Download, FileCheck2, LoaderCircle, Pencil, Presentation, RefreshCw, TriangleAlert } from 'lucide-vue-next'
import http, { identityRequestConfig, teacherIdentityHeaders, withApiBase } from '../utils/http'
import { consumeEventStream } from '../shared/generation-stream'
import { t } from '../shared/i18n'
import { adaptSlideDeckV6ForWeb } from '../utils/slide-deck-v6-adapter'
import UiSegmentedControl from './UiSegmentedControl.vue'
import PptManuscriptWorkflow from './PptManuscriptWorkflow.vue'
import SlideCanvas from './SlideCanvas.vue'
import TeacherDocumentCommandBar from './TeacherDocumentCommandBar.vue'

const props = defineProps<{ courseId: string; initialLessonId: string; title: string; sourceRevision?: string; embedded?: boolean }>()
const emit = defineEmits<{ (event: 'legacy'): void }>()
const state = ref<Record<string, any>>({}), job = ref<Record<string, any> | null>(null)
const editor = ref<InstanceType<typeof PptManuscriptWorkflow> | null>(null)
const tab = ref('manuscript'), selectedPage = ref('')
const dirty = ref(false), saving = ref(false), loading = ref(false), exporting = ref(false), syncing = ref(false)
const error = ref(''), previewError = ref(''), previewBusy = ref(false), previewRevisions = ref<Record<string, string>>({})
const physicalPages = ref<Record<string, any>>({}), manifest = ref<Record<string, any>[]>([])
const tabs = computed(() => [{ value: 'manuscript', label: t('pptLive.manuscript') }, { value: 'render', label: t('pptLive.render') }])
const pages = computed(() => state.value.manuscript?.pages || [])
const pageCountLabel = computed(() => t('pptWorkspace.sidebar.pageCount', '{count} 页').replace('{count}', String(state.value.manuscript?.page_count || 0)))
const emptyDescription = computed(() => t('pptLive.missingDescription', '讲义已独立保存。点击生成，将当前讲义整理为 PPT 页面内容稿。'))
const busy = computed(() => exporting.value || syncing.value || ['pending', 'running'].includes(job.value?.status || ''))
const jobFailure = computed(() => job.value?.error && typeof job.value.error === 'object' ? job.value.error : null)
const progressVisible = computed(() => !!job.value && ['pending', 'running', 'failed'].includes(job.value.status || '') && !state.value.manuscript)
const progressPercent = computed(() => Math.max(0, Math.min(100, Number(job.value?.progress || 0))))
const progressMessage = computed(() => job.value?.message || (job.value?.status === 'failed' ? t('pptLive.progress.failed') : t('pptProject.preparing')))
const progressMeta = computed(() => {
  const parts: string[] = []
  const attempt = Number(job.value?.attempt_number || 1)
  if (attempt > 1) parts.push(t('pptLive.progress.attempt').replace('{attempt}', String(attempt)))
  const updatedAt = Date.parse(String(job.value?.updated_at || ''))
  if (job.value?.status === 'running' && Number.isFinite(updatedAt)) {
    const seconds = Math.max(0, Math.floor((Date.now() - updatedAt) / 1000))
    if (seconds >= 10) parts.push(t('pptLive.progress.waiting').replace('{seconds}', String(seconds)))
  }
  return parts.join(' · ')
})
const stepDefinitions = computed(() => [
  { id: 'prepare', label: t('pptLive.progress.steps.prepare') },
  { id: 'pages', label: t('pptLive.progress.steps.pages') },
  { id: 'sources', label: t('pptLive.progress.steps.sources') },
  { id: 'save', label: t('pptLive.progress.steps.save') },
])
const currentStepId = computed(() => {
  const phase = String(job.value?.phase || '')
  if (phase.includes('source_validation')) return 'prepare'
  if (phase.includes('page_generation') || phase.includes('content_repair')) return 'pages'
  if (phase.includes('page_validation')) return 'sources'
  if (phase.includes('manuscript_compil') || phase.includes('manuscript_sav')) return 'save'
  return 'prepare'
})
const progressSteps = computed(() => {
  const currentIndex = stepDefinitions.value.findIndex(step => step.id === currentStepId.value)
  const failedStep = String(jobFailure.value?.failed_step || '')
  return stepDefinitions.value.map((step, index) => ({ ...step, state: failedStep === step.id
    ? 'failed'
    : job.value?.status === 'failed'
      ? index < currentIndex ? 'done' : index === currentIndex ? 'failed' : 'pending'
      : index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'pending' }))
})
const errorTitle = computed(() => jobFailure.value?.failed_step === 'sources'
  ? t('pptLive.progress.steps.sources')
  : t('pptLive.errors.title'))
const errorSummary = computed(() => {
  const failure = jobFailure.value
  if (!failure) return error.value
  const block = String(failure.failed_block_id || '')
  const messageText = String(failure.message || error.value)
  return block ? `${messageText} ${t('pptLive.errors.block').replace('{block}', block)}` : messageText
})
const errorTechnical = computed(() => String(jobFailure.value?.technical_detail || ''))
const candidateState = computed(() => ({ revision: state.value.sync_candidate?.candidate_id, manuscript: { ...state.value.sync_candidate?.manuscript, pages: (state.value.sync_candidate?.manuscript?.pages || []).filter((p: any) => state.value.sync_candidate.affected_page_ids.includes(p.page_id)) } }))
const visibleSlides = computed(() => {
  const item = manifest.value.find(p => p.page_id === selectedPage.value)
  return adaptSlideDeckV6ForWeb({ schema_version: 'slide_deck_v6', pages: (item?.physical_page_ids || []).map((id: string) => physicalPages.value[id]).filter(Boolean) })
})
const sources = computed(() => ({ lectures: [{ lesson_id: props.initialLessonId, title: props.title }], files: [] as {asset_id:string;filename:string}[] }))
const context = computed(() => ({ phase: error.value ? 'failed' as const : busy.value ? 'during' as const : state.value.manuscript ? 'after' as const : 'before' as const,
  preparing: false, label: busy.value ? t('pptProject.preparing') : state.value.manuscript ? t('courseWorkbench.contextPane.ready') : t('pptLive.missing'),
  detail: error.value, progress: busy.value ? job.value?.progress ?? null : null,
  actions: state.value.manuscript && state.value.source_state === 'stale' ? [{ id: 'sync', label: t('pptLive.sync'), disabled: busy.value || dirty.value, primary: false, reason: '' }]
    : state.value.manuscript ? [] : [{ id: 'complete', label: t('pptLive.complete'), disabled: busy.value || !state.value.source_script_revision_id, primary: true, reason: '' }] }))
let version = 0, disposed = false, previewRequest = 0
let timer: ReturnType<typeof setTimeout> | undefined, pollTimer: ReturnType<typeof setTimeout> | undefined
let controller = new AbortController(), savePromise: Promise<boolean> | null = null
const base = () => `/api/teacher/courses/${encodeURIComponent(props.courseId)}/lessons/${encodeURIComponent(props.initialLessonId)}/ppt-v6`
const config = () => identityRequestConfig('teacher', { signal: controller.signal })
const current = (v: number) => !disposed && v === version
function message(e: any) { const detail = e?.response?.data?.detail; return (typeof detail === 'string' ? detail : detail?.message) || e?.message || t('pptProject.failed') }
function errorCode(e: any) { const detail = e?.response?.data?.detail; return String((typeof detail === 'object' ? detail?.code : '') || e?.code || '') }
async function load() {
  const v = version
  loading.value = true
  try {
    const { data } = await http.get(`${base()}/manuscript`, config())
    if (!current(v) || dirty.value || saving.value) return
    if (!data.ppt_manuscript_state) throw new Error(t('pptProject.failed'))
    state.value = data.ppt_manuscript_state
    if (state.value.task_id && !job.value) void poll(state.value.task_id, v)
    if (!pages.value.some((p: any) => p.page_id === selectedPage.value)) selectedPage.value = pages.value[0]?.page_id || ''
    if (state.value.can_preview) void loadPreview([selectedPage.value])
  } catch (e: any) { if (current(v) && e?.code !== 'ERR_CANCELED') error.value = message(e) }
  finally { if (current(v)) loading.value = false }
}
async function loadPreview(ids: string[]) {
  if (!state.value.can_preview || !ids.length || !ids[0]) return
  const v = version, request = ++previewRequest, revision = state.value.revision
  previewBusy.value = true
  try {
    const { data } = await http.post(`${base()}/preview`, { expected_manuscript_revision: revision, page_ids: ids }, config())
    if (!current(v) || request !== previewRequest || state.value.revision !== data.manuscript_revision) return
    manifest.value = data.manifest
    for (const page of data.deck.pages) physicalPages.value[page.page_id] = page
    for (const id of ids) previewRevisions.value[id] = revision
    previewError.value = ''
  } catch (e: any) { if (current(v) && request === previewRequest && e?.code !== 'ERR_CANCELED') previewError.value = message(e) }
  finally { if (current(v) && request === previewRequest) previewBusy.value = false }
}
function selectPage(id: string) {
  if (!id) return
  selectedPage.value = id
  if (tab.value === 'render') void loadPreview([id])
}
watch(tab, value => { if (value === 'render') void loadPreview([selectedPage.value]); else editor.value?.selectPage(selectedPage.value) })
function scheduleSave() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { if (!error.value) void save() }, 400)
}
async function save(): Promise<boolean> {
  if (savePromise) return savePromise
  const pending = editor.value?.pendingChanges()
  if (!pending?.updates.length && !pending?.pacing) return true
  const payload = JSON.parse(JSON.stringify(pending)), v = version, revision = state.value.revision
  saving.value = true
  savePromise = (async () => {
    try {
      const { data } = await http.patch(`${base()}/manuscript`, { expected_manuscript_revision: revision, page_updates: payload.updates, ...(payload.pacing ? { pacing: payload.pacing } : {}) }, config())
      if (!current(v)) return false
      editor.value?.acknowledgeSave(payload.updates, payload.pacing)
      state.value = data.ppt_manuscript_state
      error.value = ''
      await nextTick()
      const remaining = editor.value?.pendingChanges()
      dirty.value = !!remaining?.updates.length || !!remaining?.pacing
      void loadPreview([...new Set([selectedPage.value, ...(data.affected_page_ids || [])])].filter(Boolean))
      return true
    } catch (e: any) { if (current(v) && e?.code !== 'ERR_CANCELED') error.value = message(e); return false }
    finally { if (current(v)) { saving.value = false; savePromise = null; if (!error.value && dirty.value) scheduleSave() } }
  })()
  return savePromise
}
async function prepareToLeave(): Promise<boolean> {
  if (timer) clearTimeout(timer)
  if (!await save()) return false
  await nextTick()
  if (editor.value?.pendingChanges().updates.length || editor.value?.pendingChanges().pacing) return save()
  return !error.value || !dirty.value
}
async function openOriginal() { if (await prepareToLeave()) emit('legacy') }
async function poll(id: string, v: number) {
  try {
    const { data } = await http.get(`/api/teacher/courses/${encodeURIComponent(props.courseId)}/lesson-jobs/${encodeURIComponent(id)}`, config())
    if (!current(v)) return
    job.value = data.job || data
    if (['pending', 'running'].includes(job.value?.status || '')) pollTimer = setTimeout(() => void poll(id, v), 1000)
    else { if (job.value?.error) error.value = job.value.error.message; await load() }
  } catch (e: any) { if (current(v)) error.value = message(e) }
}
async function complete() {
  const v = version
  error.value = ''
  const prior = job.value
  const taskId = String(state.value.task_id || prior?.id || '')
  job.value = { ...prior, id: taskId, status: 'pending', phase: 'ppt_source_validation', progress: 0,
    message: t('pptLive.progress.starting'), error: null, updated_at: new Date().toISOString() }
  try {
    const { data } = await http.post(`${base()}/manuscript/complete`, { source_script_revision_id: state.value.source_script_revision_id, task_id: taskId }, config())
    if (current(v)) { job.value = data.job; void poll(data.job.id, v) }
  } catch (e: any) {
    if (!current(v)) return
    if (errorCode(e) === 'lesson_ppt_job_running') {
      job.value = null
      error.value = ''
      await load()
      return
    }
    const failureMessage = message(e)
    job.value = { ...job.value, status: 'failed', phase: 'ppt_start_failed',
      error: { code: errorCode(e), message: failureMessage } }
    error.value = failureMessage
  }
}
async function download() {
  if (!await prepareToLeave()) return
  const v = version, url = base(), revision = state.value.revision
  exporting.value = true
  error.value = ''
  try {
    const response = await fetch(withApiBase(`${url}/build/stream`), { method: 'POST', headers: teacherIdentityHeaders({ 'Content-Type': 'application/json' }), signal: controller.signal,
      body: JSON.stringify({ expected_manuscript_revision: revision }) })
    if (!response.ok) throw new Error((await response.json())?.detail?.message || t('pptProject.failed'))
    let representation = ''
    await consumeEventStream(response, ({ data }) => {
      if (!current(v)) return
      const event = data as any
      if (event.job) job.value = event.job
      if (event.event === 'build_complete') representation = event.build?.representation_id || ''
      if (event.failure || event.event === 'build_paused') error.value = event.message || t('pptProject.failed')
    })
    if (!current(v)) return
    if (!representation) throw new Error(error.value || t('pptProject.failed'))
    const file = await http.get(`${url}/${encodeURIComponent(representation)}/export.pptx`, { ...config(), responseType: 'blob' })
    if (!current(v)) return
    const link = document.createElement('a'), objectUrl = URL.createObjectURL(file.data)
    link.href = objectUrl; link.download = `${props.title}.pptx`; link.click(); URL.revokeObjectURL(objectUrl)
  } catch (e: any) { if (current(v) && e?.name !== 'AbortError') error.value = message(e) }
  finally { if (current(v)) exporting.value = false }
}
async function runContextAction(id: string) { if (id === 'complete') return complete(); if (id === 'sync') return sync() }
async function sync() {
  if (!await prepareToLeave()) return
  const v = version
  syncing.value = true
  error.value = ''
  try { const { data } = await http.post(`${base()}/manuscript/regenerate-pages`, { expected_manuscript_revision: state.value.revision, target_page_ids: [], changed_source_block_ids: [], candidate_only: true }, config()); if (current(v)) state.value = { ...state.value, sync_candidate: data.candidate } }
  catch (e: any) { if (current(v)) error.value = message(e) }
  finally { if (current(v)) syncing.value = false }
}
async function resolveSync(accept: boolean) {
  const v = version
  syncing.value = true
  try { const { data } = await http.post(`${base()}/manuscript/sync-candidates/${encodeURIComponent(state.value.sync_candidate.candidate_id)}/resolve`, { accept }, config()); if (current(v)) { state.value = data.ppt_manuscript_state; if (accept) void loadPreview([selectedPage.value]) } }
  catch (e: any) { if (current(v)) error.value = message(e) }
  finally { if (current(v)) syncing.value = false }
}
async function retry() { error.value = ''; if (dirty.value) await save(); else if (!state.value.manuscript) await complete(); else await load() }
function protect(event: BeforeUnloadEvent) { if (dirty.value || saving.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', protect)
watch(() => [props.courseId, props.initialLessonId], () => {
  version++; controller.abort(); controller = new AbortController()
  if (timer) clearTimeout(timer); if (pollTimer) clearTimeout(pollTimer)
  state.value = {}; job.value = null; physicalPages.value = {}; manifest.value = []; selectedPage.value = ''; previewRevisions.value = {}
  error.value = ''; previewError.value = ''; dirty.value = false; saving.value = false; savePromise = null; exporting.value = false
  tab.value = 'manuscript'
  void load()
}, { immediate: true })
watch(() => props.sourceRevision, () => { if (!dirty.value && !saving.value) void load() })
onBeforeUnmount(() => { disposed = true; version++; controller.abort(); if (timer) clearTimeout(timer); if (pollTimer) clearTimeout(pollTimer); window.removeEventListener('beforeunload', protect) })
defineExpose({ context, sources, runContextAction, prepareToLeave })
</script>

<style scoped>
.lesson-ppt-workspace {
  --ppt-surface:#ffffff;
  --ppt-ground:#f5f6f9;
  --ppt-hover:#f0f2f7;
  --ppt-ink:#1f2937;
  --ppt-muted:#667085;
  --ppt-soft:#8a94a6;
  --ppt-line:#e1e6ee;
  --ppt-accent:#4f46c8;
  --ppt-accent-soft:#f0efff;
  min-width:0;
  min-height:100%;
  display:flex;
  flex-direction:column;
  gap:14px;
  padding:0 0 44px;
  color:var(--ppt-ink);
  background:var(--ppt-ground);
  font-size:16px;
}
.lesson-ppt-header {
  position:sticky;
  top:0;
  z-index:8;
  min-height:64px;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:center;
  gap:18px;
  margin:0 0 4px;
  padding:10px 18px;
  background:rgba(245,246,249,.92);
  backdrop-filter:blur(18px);
  border-bottom:1px solid rgba(218,224,233,.82);
}
.lesson-ppt-title {
  min-width:0;
  display:flex;
  align-items:baseline;
  gap:12px;
}
.lesson-ppt-title h1 {
  min-width:0;
  margin:0;
  overflow:hidden;
  color:#20283a;
  font-size:20px;
  font-weight:760;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.lesson-ppt-page-count {
  flex:none;
  color:var(--ppt-muted);
  font-size:15px;
  font-weight:650;
  white-space:nowrap;
}
.lesson-ppt-toolbar {
  min-width:0;
  max-width:none;
  margin:0;
  padding:0;
}
.lesson-ppt-header :deep(.teacher-document-command-bar-row) {
  width:auto;
  max-width:none;
  min-height:40px;
  margin:0;
  padding:0;
  gap:10px;
}
.lesson-ppt-header :deep(.teacher-document-command-bar__context) { gap:10px; }
.lesson-ppt-header :deep(.teacher-document-command-bar__status) {
  color:var(--ppt-muted);
  font-size:15px;
}
.lesson-ppt-header :deep(.teacher-document-command-bar__actions) { gap:3px; }
.lesson-ppt-header :deep(.teacher-document-command-bar__actions button) {
  min-width:36px;
  min-height:36px;
  padding:0 10px;
  border:1px solid transparent;
  border-radius:9px;
  color:#4f5d73;
  background:transparent;
  font-size:15px;
  font-weight:750;
}
.lesson-ppt-header :deep(.teacher-document-command-bar__actions button:hover:not(:disabled)) {
  color:#3730a3;
  background:var(--ppt-hover);
}
.lesson-ppt-header :deep(.teacher-document-command-bar__actions button:focus-visible),
.lesson-ppt-workspace button:focus-visible {
  outline:2px solid rgba(79,70,200,.55);
  outline-offset:2px;
}
.lesson-ppt-header :deep(.ui-segmented-control) {
  height:36px;
  border-color:#dbe1ea;
  border-radius:10px;
  background:#eef1f6;
}
.lesson-ppt-header :deep(.ui-segmented-control__indicator) {
  border-radius:7px;
  box-shadow:0 2px 7px rgba(30,41,59,.12);
}
.lesson-ppt-header :deep(.ui-segmented-control button) {
  height:28px;
  min-height:28px;
  padding:0 13px;
  border-radius:7px;
  font-size:15px;
}
.lesson-ppt-error,
.lesson-ppt-notice {
  width:min(100% - 36px, 980px);
  min-height:42px;
  display:flex;
  align-items:center;
  gap:12px;
  margin:0 auto;
  padding:9px 13px;
  box-sizing:border-box;
  border-radius:10px;
  line-height:1.55;
  overflow-wrap:anywhere;
}
.lesson-ppt-notice {
  color:#596579;
  background:#fff;
  box-shadow:inset 0 0 0 1px var(--ppt-line);
}
.lesson-ppt-error {
  flex-wrap:wrap;
  color:#9f3344;
  background:#fff7f8;
  box-shadow:inset 0 0 0 1px #efd2d8;
}
.lesson-ppt-error>div { min-width:0; display:grid; gap:2px; }
.lesson-ppt-error strong { font-size:15px; }
.lesson-ppt-error p { margin:0; color:#a34b59; font-size:15px; }
.lesson-ppt-error details {
  width:100%;
  padding:8px 0 2px;
  border-top:1px solid #efd2d8;
  color:#7b4650;
  font-size:14px;
}
.lesson-ppt-error summary { cursor:pointer; font-weight:700; }
.lesson-ppt-error code { display:block; margin-top:7px; white-space:pre-wrap; overflow-wrap:anywhere; }
.lesson-ppt-progress {
  width:min(100% - 36px, 980px);
  display:grid;
  gap:15px;
  margin:0 auto;
  padding:18px 20px;
  box-sizing:border-box;
  border:1px solid var(--ppt-line);
  border-radius:12px;
  background:#fff;
  box-shadow:0 1px 3px rgba(30,41,59,.04);
}
.lesson-ppt-progress>header { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; }
.lesson-ppt-progress>header>div { min-width:0; display:grid; gap:3px; }
.lesson-ppt-progress>header strong { color:#273247; font-size:16px; }
.lesson-ppt-progress>header span { color:var(--ppt-muted); font-size:15px; line-height:1.5; }
.lesson-ppt-progress>header small { color:var(--ppt-soft); font-size:14px; line-height:1.4; }
.lesson-ppt-progress>header b { color:var(--ppt-accent); font-size:17px; font-variant-numeric:tabular-nums; }
.lesson-ppt-progress__track { height:5px; overflow:hidden; border-radius:3px; background:#e8eaf1; }
.lesson-ppt-progress__track i { width:100%; height:100%; display:block; background:var(--ppt-accent); transform-origin:left; transition:transform .25s ease; }
.lesson-ppt-progress ol { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin:0; padding:0; list-style:none; }
.lesson-ppt-progress li { min-width:0; display:flex; align-items:center; gap:8px; color:#8a94a6; font-size:14px; }
.lesson-ppt-progress li>span { width:24px; height:24px; flex:none; display:grid; place-items:center; border-radius:50%; background:#f1f3f7; }
.lesson-ppt-progress li strong { overflow-wrap:anywhere; font-weight:700; line-height:1.35; }
.lesson-ppt-progress li[data-state="done"] { color:#287a50; }
.lesson-ppt-progress li[data-state="done"]>span { background:#e9f7ef; }
.lesson-ppt-progress li[data-state="current"] { color:#3730a3; }
.lesson-ppt-progress li[data-state="current"]>span { background:var(--ppt-accent-soft); }
.lesson-ppt-progress li[data-state="failed"] { color:#a33b4a; }
.lesson-ppt-progress li[data-state="failed"]>span { background:#fdebed; }
.lesson-ppt-notice button,
.lesson-ppt-error button,
.lesson-ppt-candidate button,
.lesson-ppt-empty button {
  min-height:34px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 11px;
  border:1px solid #d7dde7;
  border-radius:8px;
  color:#4f5d73;
  background:#fff;
  font:inherit;
  font-size:15px;
  font-weight:730;
  cursor:pointer;
}
.lesson-ppt-notice button,
.lesson-ppt-error button { margin-left:auto; }
.lesson-ppt-workspace button:hover:not(:disabled) { background:#f7f8fc; }
.lesson-ppt-workspace button:disabled { opacity:.48; cursor:not-allowed; }
@media (prefers-reduced-motion:reduce) {
  .lesson-ppt-progress__track i { transition:none; }
}
.lesson-ppt-candidate {
  width:min(100% - 36px, 980px);
  display:grid;
  gap:12px;
  margin:0 auto;
  padding:14px;
  border-radius:12px;
  background:#fff;
  box-shadow:0 1px 3px rgba(30,41,59,.05);
}
.lesson-ppt-candidate>header { display:flex; align-items:center; gap:8px; }
.lesson-ppt-candidate>header strong { margin-right:auto; font-size:15px; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow) {
  width:min(100% - 36px, 980px);
  height:auto;
  overflow:visible;
  margin:0 auto;
  padding:0;
  background:transparent;
}
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__content) { padding:0; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages) {
  min-height:0;
  display:block;
  overflow:visible;
  border:0;
  border-radius:0;
  background:transparent;
}
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages>article) {
  overflow:visible;
  padding:0;
  scroll-margin-top:82px;
  border:0;
}
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages>article+article) { margin-top:1px; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__page-copy) {
  max-width:none;
  min-height:180px;
  margin:0;
  padding:30px 42px 34px;
  background:var(--ppt-surface);
  box-shadow:inset 0 -1px var(--ppt-line);
}
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages>article:first-of-type .ppt-manuscript-workflow__page-copy) { border-radius:14px 14px 0 0; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages>article:last-of-type .ppt-manuscript-workflow__page-copy) { border-radius:0 0 14px 14px; box-shadow:none; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages>article:only-of-type .ppt-manuscript-workflow__page-copy) { border-radius:14px; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__page-meta:empty) { display:none; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__page-meta) { margin-bottom:14px; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__reading h2) {
  max-width:760px;
  margin:0 0 16px;
  color:#20283a;
  font-size:23px;
  font-weight:760;
  line-height:1.45;
}
.lesson-ppt-workspace :deep(.ppt-page-reading-copy),
.lesson-ppt-workspace :deep(.ppt-teaching-editor) {
  max-width:760px;
  color:#344055;
  font-size:17px;
  line-height:1.82;
}
.lesson-ppt-workspace :deep(.ppt-page-reading-copy p) { margin:0 0 14px; }
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__teaching-notes),
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__sources) {
  max-width:760px;
  color:var(--ppt-muted);
}
.lesson-ppt-workspace :deep(input:not([type=checkbox])),
.lesson-ppt-workspace :deep(textarea),
.lesson-ppt-workspace :deep(select) {
  border-color:#d5dce7;
  border-radius:8px;
}
.lesson-ppt-preview {
  width:min(100% - 36px, 1120px);
  display:grid;
  grid-template-rows:auto minmax(0,1fr);
  gap:12px;
  margin:0 auto;
}
.lesson-ppt-page-strip {
  min-height:42px;
  display:flex;
  align-items:center;
  gap:6px;
  overflow-x:auto;
  padding:2px 1px 6px;
  scrollbar-width:thin;
}
.lesson-ppt-page-strip button {
  flex:0 0 auto;
  min-height:36px;
  max-width:240px;
  display:flex;
  align-items:center;
  gap:8px;
  padding:0 11px;
  border:0;
  border-radius:9px;
  color:#5f6b80;
  background:transparent;
  font:inherit;
  font-size:15px;
  cursor:pointer;
}
.lesson-ppt-page-strip button span {
  color:#8b96a8;
  font-weight:760;
  font-variant-numeric:tabular-nums;
}
.lesson-ppt-page-strip button strong {
  min-width:0;
  overflow:hidden;
  font-size:15px;
  font-weight:660;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.lesson-ppt-page-strip button:hover { background:#eceff5; }
.lesson-ppt-page-strip button.active {
  color:#3730a3;
  background:#fff;
  box-shadow:0 1px 4px rgba(30,41,59,.1);
}
.lesson-ppt-page-strip button.active span { color:var(--ppt-accent); }
.lesson-ppt-canvas {
  min-width:0;
  display:grid;
  gap:14px;
  padding:18px;
  border-radius:14px;
  background:#e8ebf1;
  box-shadow:inset 0 0 0 1px #dbe1eb;
}
.lesson-ppt-canvas :deep(.slide-canvas) {
  width:100%;
  aspect-ratio:16/9;
  border-radius:8px;
  box-shadow:0 14px 30px rgba(25,33,50,.16),0 1px 2px rgba(25,33,50,.1);
}
.lesson-ppt-empty {
  width:min(100% - 36px, 560px);
  display:grid;
  justify-items:center;
  gap:10px;
  margin:54px auto 0;
  padding:34px 28px;
  box-sizing:border-box;
  border-radius:14px;
  color:var(--ppt-muted);
  background:#fff;
  text-align:center;
  box-shadow:0 1px 4px rgba(30,41,59,.06);
}
.lesson-ppt-empty-mark {
  width:48px;
  height:48px;
  display:grid;
  place-items:center;
  border-radius:13px;
  color:var(--ppt-accent);
  background:var(--ppt-accent-soft);
}
.lesson-ppt-empty h2 {
  margin:4px 0 0;
  color:#20283a;
  font-size:20px;
  font-weight:760;
  line-height:1.35;
}
.lesson-ppt-empty p {
  max-width:38ch;
  margin:0 0 6px;
  font-size:15px;
  line-height:1.65;
}
.lesson-ppt-empty .lesson-ppt-error {
  width:auto;
  min-height:0;
  margin:0;
  padding:0;
  color:#9f3344;
  background:transparent;
  box-shadow:none;
}
.spinning { animation:ppt-spin 1s linear infinite; }
@keyframes ppt-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion:reduce) { .spinning { animation:none; } }
</style>
