<template>
  <section class="lesson-ppt-workspace" data-testid="lesson-ppt-workspace">
    <TeacherDocumentCommandBar class="lesson-ppt-toolbar" :label="t('pptWorkspace.editor.actions')" :show-status="dirty || saving" :status-label="saving ? t('pptWorkspace.savingManuscript') : t('pptWorkspace.manuscriptUnsaved')" :status-tone="saving ? 'busy' : 'warning'">
      <template #context><UiSegmentedControl v-model="tab" :options="tabs" :accessibility-label="t('pptWorkspace.pageEditing')" /></template>
      <button v-if="state.manuscript && tab === 'manuscript' && !historyOpen" type="button" :disabled="busy || state.source_state === 'stale'" data-testid="ppt-live-edit" @click="editor?.editing ? editor?.finishEditing() : editor?.beginEditing()"><Check v-if="editor?.editing" :size="16" /><Pencil v-else :size="16" />{{ editor?.editing ? t('pptWorkspace.editor.finishEditing') : t('pptLive.edit') }}</button>
      <button type="button" :disabled="!state.can_export || dirty || busy" :title="t('pptProject.export')" :aria-label="t('pptProject.export')" @click="download"><Download :size="16" /></button>
      <button type="button" :disabled="dirty || saving" :title="t('pptLive.history')" :aria-label="t('pptLive.history')" :aria-pressed="historyOpen" @click="toggleHistory"><History :size="16" /></button>
      <button type="button" :disabled="dirty || saving" :title="t('pptProject.originalReview')" :aria-label="t('pptProject.originalReview')" @click="openOriginal"><FileCheck2 :size="16" /></button>
    </TeacherDocumentCommandBar>
    <PptProjectWorkspace v-if="historyOpen" ref="historyWorkspace" :course-id="courseId" :initial-lesson-id="initialLessonId" embedded />
    <template v-else>
      <p v-if="error" class="lesson-ppt-error" role="alert">{{ error }}<button type="button" :disabled="saving || busy" @click="retry"><RefreshCw :size="16" />{{ t('common.retry') }}</button></p>
      <p v-if="state.source_state === 'stale'" class="lesson-ppt-notice" role="status">{{ t('pptLive.stale') }}<button type="button" :disabled="busy || dirty" @click="sync"><RefreshCw :size="16" />{{ t('pptLive.sync') }}</button></p>
      <p v-if="job && ['pending', 'running'].includes(job.status)" class="lesson-ppt-notice" role="status"><LoaderCircle :size="16" class="spinning" />{{ job.message || t('pptProject.preparing') }}</p>
      <section v-if="state.sync_candidate" class="lesson-ppt-candidate">
        <header><strong>{{ t('pptLive.candidate') }}</strong><button type="button" :disabled="busy" @click="resolveSync(true)"><Check :size="16" />{{ t('pptLive.accept') }}</button><button type="button" :disabled="busy" @click="resolveSync(false)">{{ t('pptLive.reject') }}</button></header>
        <PptManuscriptWorkflow :title="title" :state="candidateState" continuous review-only embedded external-actions />
      </section>
      <template v-if="state.manuscript">
        <PptManuscriptWorkflow v-show="tab === 'manuscript'" ref="editor" :title="title" :state="state" embedded external-actions continuous
          :allow-page-regeneration="false" :saving="saving" :busy="state.source_state === 'stale'"
          @dirty-change="dirty = $event" @pending-change="scheduleSave" @save-manuscript="save" @page-change="selectPage" />
        <section v-if="tab === 'render'" class="lesson-ppt-preview">
          <label class="lesson-ppt-page-picker"><span>{{ t('pptWorkspace.sidebar.selectPage') }}</span><select :value="selectedPage" @change="selectPage(($event.target as HTMLSelectElement).value)"><option v-for="page in pages" :key="page.page_id" :value="page.page_id">{{ page.page_number }}. {{ page.title }}</option></select></label>
          <div class="lesson-ppt-canvas">
            <p v-if="previewError" class="lesson-ppt-error" role="alert">{{ previewError }}<button type="button" @click="loadPreview([selectedPage])"><RefreshCw :size="16" />{{ t('common.retry') }}</button></p>
            <p v-if="previewRevisions[selectedPage] !== state.revision && visibleSlides.length" class="lesson-ppt-notice">{{ t('pptLive.previousPreview') }}</p>
            <SlideCanvas v-for="slide in visibleSlides" :key="slide.unit_id" :slide="slide as any" :page-number="Number(slide.position) + 1" :page-count="state.manuscript.page_count" :deck-title="title" :theme="state.theme" :course-id="courseId" />
            <p v-if="!visibleSlides.length" class="lesson-ppt-notice"><LoaderCircle v-if="previewBusy" :size="18" class="spinning" />{{ previewBusy ? t('pptLive.previewing') : t('pptLive.previewUnavailable') }}</p>
          </div>
        </section>
      </template>
      <div v-else class="lesson-ppt-empty">
        <p>{{ loading ? t('common.loading') : t('pptLive.missing') }}</p>
        <p v-for="(issue, index) in state.page_errors || []" :key="index" class="lesson-ppt-error">{{ issue.message }}</p>
        <button type="button" :disabled="loading || busy || !state.source_script_revision_id" @click="complete"><RefreshCw :size="16" />{{ t('pptLive.complete') }}</button>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Check, Download, FileCheck2, History, LoaderCircle, Pencil, RefreshCw } from 'lucide-vue-next'
import http, { identityRequestConfig, teacherIdentityHeaders, withApiBase } from '../utils/http'
import { consumeEventStream } from '../shared/generation-stream'
import { t } from '../shared/i18n'
import { adaptSlideDeckV6ForWeb } from '../utils/slide-deck-v6-adapter'
import UiSegmentedControl from './UiSegmentedControl.vue'
import PptManuscriptWorkflow from './PptManuscriptWorkflow.vue'
import PptProjectWorkspace from './PptProjectWorkspace.vue'
import SlideCanvas from './SlideCanvas.vue'
import TeacherDocumentCommandBar from './TeacherDocumentCommandBar.vue'

const props = defineProps<{ courseId: string; initialLessonId: string; title: string; sourceRevision?: string; embedded?: boolean }>()
const emit = defineEmits<{ (event: 'legacy'): void }>()
const state = ref<Record<string, any>>({}), job = ref<Record<string, any> | null>(null)
const editor = ref<InstanceType<typeof PptManuscriptWorkflow> | null>(null)
const historyWorkspace = ref<InstanceType<typeof PptProjectWorkspace> | null>(null)
const tab = ref('manuscript'), historyOpen = ref(false), selectedPage = ref('')
const dirty = ref(false), saving = ref(false), loading = ref(false), exporting = ref(false), syncing = ref(false)
const error = ref(''), previewError = ref(''), previewBusy = ref(false), previewRevisions = ref<Record<string, string>>({})
const physicalPages = ref<Record<string, any>>({}), manifest = ref<Record<string, any>[]>([])
const tabs = computed(() => [{ value: 'manuscript', label: t('pptLive.manuscript') }, { value: 'render', label: t('pptLive.render') }])
const pages = computed(() => state.value.manuscript?.pages || [])
const busy = computed(() => exporting.value || syncing.value || ['pending', 'running'].includes(job.value?.status || ''))
const candidateState = computed(() => ({ revision: state.value.sync_candidate?.candidate_id, manuscript: { ...state.value.sync_candidate?.manuscript, pages: (state.value.sync_candidate?.manuscript?.pages || []).filter((p: any) => state.value.sync_candidate.affected_page_ids.includes(p.page_id)) } }))
const visibleSlides = computed(() => {
  const item = manifest.value.find(p => p.page_id === selectedPage.value)
  return adaptSlideDeckV6ForWeb({ schema_version: 'slide_deck_v6', pages: (item?.physical_page_ids || []).map((id: string) => physicalPages.value[id]).filter(Boolean) })
})
const sources = computed(() => ({ lectures: [{ lesson_id: props.initialLessonId, title: props.title }], files: [] as {asset_id:string;filename:string}[] }))
const context = computed(() => ({ phase: error.value ? 'failed' as const : busy.value ? 'during' as const : state.value.manuscript ? 'after' as const : 'before' as const,
  preparing: false, label: busy.value ? t('pptProject.preparing') : state.value.manuscript ? t('courseWorkbench.contextPane.ready') : t('pptLive.missing'),
  detail: error.value, progress: busy.value ? job.value?.progress ?? null : null,
  actions: state.value.source_state === 'stale' ? [{ id: 'sync', label: t('pptLive.sync'), disabled: busy.value || dirty.value, primary: false, reason: '' }]
    : state.value.manuscript ? [] : [{ id: 'complete', label: t('pptLive.complete'), disabled: busy.value || !state.value.source_script_revision_id, primary: true, reason: '' }] }))
let version = 0, disposed = false, previewRequest = 0
let timer: ReturnType<typeof setTimeout> | undefined, pollTimer: ReturnType<typeof setTimeout> | undefined
let controller = new AbortController(), savePromise: Promise<boolean> | null = null
const base = () => `/api/teacher/courses/${encodeURIComponent(props.courseId)}/lessons/${encodeURIComponent(props.initialLessonId)}/ppt-v6`
const config = () => identityRequestConfig('teacher', { signal: controller.signal })
const current = (v: number) => !disposed && v === version
function message(e: any) { const detail = e?.response?.data?.detail; return (typeof detail === 'string' ? detail : detail?.message) || e?.message || t('pptProject.failed') }
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
  if (historyOpen.value && historyWorkspace.value?.prepareToLeave() === false) return false
  if (timer) clearTimeout(timer)
  if (!await save()) return false
  await nextTick()
  if (editor.value?.pendingChanges().updates.length || editor.value?.pendingChanges().pacing) return save()
  return !error.value || !dirty.value
}
async function toggleHistory() { if (await prepareToLeave()) historyOpen.value = !historyOpen.value }
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
  try { const { data } = await http.post(`${base()}/manuscript/complete`, { source_script_revision_id: state.value.source_script_revision_id, task_id: state.value.task_id || '' }, config()); if (current(v)) { job.value = data.job; void poll(data.job.id, v) } }
  catch (e: any) { if (current(v)) error.value = message(e) }
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
function protect(event: BeforeUnloadEvent) { if (dirty.value || saving.value || historyWorkspace.value?.dirty) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', protect)
watch(() => [props.courseId, props.initialLessonId], () => {
  version++; controller.abort(); controller = new AbortController()
  if (timer) clearTimeout(timer); if (pollTimer) clearTimeout(pollTimer)
  state.value = {}; job.value = null; physicalPages.value = {}; manifest.value = []; selectedPage.value = ''; previewRevisions.value = {}
  error.value = ''; previewError.value = ''; dirty.value = false; saving.value = false; savePromise = null; exporting.value = false
  tab.value = 'manuscript'; historyOpen.value = false
  void load()
}, { immediate: true })
watch(() => props.sourceRevision, () => { if (!dirty.value && !saving.value) void load() })
onBeforeUnmount(() => { disposed = true; version++; controller.abort(); if (timer) clearTimeout(timer); if (pollTimer) clearTimeout(pollTimer); window.removeEventListener('beforeunload', protect) })
defineExpose({ context, sources, runContextAction, prepareToLeave })
</script>

<style scoped>
.lesson-ppt-workspace{min-width:0;display:flex;flex-direction:column;gap:16px;color:var(--lz-text-primary);font-size:16px}
.lesson-ppt-toolbar{position:sticky;top:0;z-index:8;max-width:none;margin:0;padding:12px 0;background:var(--teacher-component-tint,#f5f6f8)}
.lesson-ppt-tools{display:flex;gap:8px;align-items:center}
button{display:inline-flex;align-items:center;gap:7px;min-height:36px;padding:7px 10px;border:1px solid var(--lz-border);border-radius:6px;background:var(--lz-bg-surface,#fff);color:inherit;font:inherit;cursor:pointer}
button:hover:not(:disabled){background:var(--lz-bg-page)}button:focus-visible{outline:2px solid var(--lz-brand-strong);outline-offset:2px}button:disabled{opacity:.5;cursor:not-allowed}
.lesson-ppt-error,.lesson-ppt-notice{margin:0;display:flex;gap:12px;align-items:center;line-height:1.7;overflow-wrap:anywhere}.lesson-ppt-error{color:#a13131}.lesson-ppt-notice{color:var(--lz-text-secondary)}
.lesson-ppt-empty{padding:32px 0}.lesson-ppt-preview{display:grid;grid-template-columns:170px minmax(0,1fr);gap:20px;align-items:start}.lesson-ppt-preview>nav{display:grid;gap:6px;max-height:70vh;overflow:auto}.lesson-ppt-preview>nav button{display:flex;align-items:baseline;text-align:left;overflow-wrap:anywhere;border-color:transparent;line-height:1.6}.lesson-ppt-preview>nav button[aria-current]{background:var(--lz-bg-page);color:var(--lz-brand-strong)}.lesson-ppt-preview>nav span{flex:0 0 24px;font-variant-numeric:tabular-nums}.lesson-ppt-canvas{display:grid;gap:16px;min-width:0}.lesson-ppt-canvas :deep(.slide-canvas){aspect-ratio:16/9;width:100%}
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages){display:block}.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages>article){padding:24px 0;border-bottom:1px solid var(--lz-border)}
.lesson-ppt-preview{display:flex;flex-direction:column}.lesson-ppt-page-picker{display:flex;align-items:center;gap:12px;max-width:100%;color:#526077}.lesson-ppt-page-picker select{min-width:0;max-width:520px;font:inherit;padding:6px 10px;border:1px solid #d6dce6;border-radius:6px;background:#fff}.lesson-ppt-canvas{width:100%}
.lesson-ppt-workspace :deep(.ppt-manuscript-workflow){height:auto;overflow:visible;padding:0;background:transparent}.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages){overflow:visible;background:transparent}.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__pages>article){overflow:visible;scroll-margin-top:80px}.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__page-meta:empty){display:none}.lesson-ppt-workspace :deep(.ppt-manuscript-workflow__page-copy){max-width:860px}
.spinning{animation:ppt-spin 1s linear infinite}@keyframes ppt-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.spinning{animation:none}}
</style>
