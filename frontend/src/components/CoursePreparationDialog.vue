<template>
  <Teleport to="body">
    <dialog
      v-if="visible"
      ref="dialogRef"
      class="preparation-dialog"
      :class="{ 'is-choice': step === 'choice' }"
      :aria-labelledby="titleId"
      tabindex="-1"
      @cancel.prevent
      @keydown.esc.prevent.stop
    >
      <section v-if="step === 'choice'" class="preparation-step preparation-choice">
        <header>
          <span><Sparkles :size="20" /></span>
          <h2 :id="titleId">{{ t('courseFiles.preparation.startTitle') }}</h2>
        </header>
        <div class="start-options">
          <button type="button" :disabled="busy" @click="startBlank">
            <div class="mode-illustration blank-route" aria-hidden="true">
              <div class="route-subject">
                <FilePlus2 :size="17" />
                <b>{{ t('courseFiles.preparation.routeGoal') }}</b>
                <span><i /><i /><i /></span>
              </div>
              <span class="route-node"><Sparkles :size="17" /></span>
              <div class="route-files route-results">
                <span><ListTree :size="14" /><b>{{ t('courseFiles.preparation.documentTypes.outline') }}</b></span>
                <span><BookOpenCheck :size="14" /><b>{{ t('courseFiles.preparation.documentTypes.lessonPlan') }}</b></span>
                <span><Presentation :size="14" /><b>{{ t('courseFiles.preparation.documentTypes.ppt') }}</b></span>
              </div>
            </div>
            <div class="mode-copy">
              <span>
                <strong>{{ t('courseFiles.preparation.blankMode') }}</strong>
                <small>{{ t('courseFiles.preparation.blankModeHint') }}</small>
              </span>
              <span class="mode-enter"><ArrowRight :size="17" /></span>
            </div>
          </button>
          <button class="existing-course" type="button" :disabled="busy" @click="step = 'import'">
            <div class="mode-illustration existing-route" aria-hidden="true">
              <div class="route-files route-sources">
                <span><BookOpenCheck :size="14" /><b>{{ t('courseFiles.preparation.documentTypes.lessonPlan') }}</b></span>
                <span><Presentation :size="14" /><b>{{ t('courseFiles.preparation.documentTypes.ppt') }}</b></span>
                <span><Files :size="14" /><b>{{ t('courseFiles.preparation.routeMaterials') }}</b></span>
              </div>
              <span class="route-node is-scan"><ScanSearch :size="17" /></span>
              <div class="matched-folder">
                <span><FolderOpen :size="16" /><b>{{ t('courseFiles.preparation.routeAutoMatch') }}</b></span>
                <i><Check :size="11" /><em /></i>
                <i><Check :size="11" /><em /></i>
                <i><Check :size="11" /><em /></i>
              </div>
            </div>
            <div class="mode-copy">
              <span>
                <strong>{{ t('courseFiles.preparation.existingMode') }}</strong>
                <small>{{ t('courseFiles.preparation.existingModeHint') }}</small>
              </span>
              <span class="mode-enter"><ArrowRight :size="17" /></span>
            </div>
          </button>
        </div>
        <p v-if="error" class="dialog-error" role="alert"><TriangleAlert :size="15" />{{ error }}</p>
      </section>

      <section
        v-else-if="step === 'import'"
        class="preparation-step preparation-import"
        @dragenter.prevent="dragging = true"
        @dragover.prevent="dragging = true"
        @dragleave.self.prevent="dragging = false"
        @drop.prevent="handleDrop"
      >
        <header>
          <button type="button" :aria-label="t('common.back', '返回')" :disabled="busy" @click="step = 'choice'"><ArrowLeft :size="18" /></button>
          <h2 :id="titleId">{{ t('courseFiles.preparation.importTitle') }}</h2>
        </header>
        <div class="preparation-dropzone" :class="{ dragging, busy }">
          <LoaderCircle v-if="busy" :size="29" class="spin" />
          <FolderOpen v-else :size="29" />
          <strong>{{ busy ? t('courseFiles.preparation.scanning') : t('courseFiles.preparation.dropTitle') }}</strong>
          <div>
            <button class="primary" type="button" :disabled="busy" @click="folderInput?.click()"><FolderInput :size="16" />{{ t('courseFiles.preparation.chooseFolder') }}</button>
            <button type="button" :disabled="busy" @click="fileInput?.click()"><Files :size="16" />{{ t('courseFiles.preparation.chooseFiles') }}</button>
          </div>
        </div>
        <p v-if="error" class="dialog-error" role="alert"><TriangleAlert :size="15" />{{ error }}</p>
      </section>

      <section v-else class="preparation-step preparation-review">
        <header>
          <div>
            <span><FileCheck2 :size="20" /></span>
            <h2 :id="titleId">{{ t('courseFiles.preparation.reviewStructure') }}</h2>
          </div>
          <small>{{ t('courseFiles.preparation.reviewCount').replace('{count}', String(coursePackage?.asset_count || 0)) }}</small>
        </header>

        <div class="recognized-structure">
          <section v-for="group in documentGroups" :key="group.type" class="recognized-group">
            <header><strong>{{ group.label }}</strong><small>{{ group.assets.length }}</small></header>
            <div class="recognized-files">
              <label v-for="asset in group.assets" :key="asset.asset_id" class="recognized-file">
                <FileText :size="17" />
                <span><strong>{{ asset.filename }}</strong><small>{{ asset.relative_path }}</small></span>
                <select
                  :value="asset.document_type || 'other'"
                  :disabled="busy || updatingIds.has(asset.asset_id)"
                  :aria-label="t('courseFiles.preparation.changeType').replace('{name}', asset.filename)"
                  @change="changeDocumentType(asset, $event)"
                >
                  <option v-for="option in documentTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </label>
            </div>
          </section>
        </div>

        <p v-if="importWarning" class="import-warning" role="status"><TriangleAlert :size="15" />{{ importWarning }}</p>
        <p v-if="error" class="dialog-error" role="alert"><TriangleAlert :size="15" />{{ error }}</p>
        <footer>
          <button type="button" :disabled="busy" @click="step = 'import'"><Plus :size="15" />{{ t('courseFiles.preparation.continueImport') }}</button>
          <button class="primary" type="button" :disabled="busy || updatingIds.size > 0" @click="finish">
            <LoaderCircle v-if="busy" :size="15" class="spin" />
            <ArrowRight v-else :size="15" />
            {{ t('courseFiles.preparation.enterWorkbench') }}
          </button>
        </footer>
      </section>

      <input ref="folderInput" class="visually-hidden" type="file" multiple webkitdirectory tabindex="-1" aria-hidden="true" @change="captureFolder" />
      <input ref="fileInput" class="visually-hidden" type="file" multiple tabindex="-1" aria-hidden="true" @change="captureFiles" />
    </dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  ArrowLeft, ArrowRight, BookOpenCheck, Check, FileCheck2, FilePlus2, Files,
  FileText, FolderInput, FolderOpen, ListTree, LoaderCircle, Plus, Presentation,
  ScanSearch, Sparkles, TriangleAlert,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'
import http, { teacherRequestConfig } from '../utils/http'

type DocumentType = 'outline' | 'lesson_plan' | 'script' | 'ppt' | 'question_bank' | 'school_material' | 'other'
type PreparationStatus = 'pending' | 'review' | 'completed' | 'skipped'
type CourseAsset = {
  asset_id: string
  filename: string
  relative_path: string
  document_type?: DocumentType
}
type CoursePackage = {
  package_id: string
  course_id?: string
  course_name: string
  academic_year: string
  term: string
  asset_count: number
  assets: CourseAsset[]
  preparation_status?: PreparationStatus
}
type ImportOutcome = {
  relative_path: string
  outcome: 'imported' | 'duplicate' | 'rejected'
  error?: string
  analysis_error?: string
}

const props = defineProps<{ courseId: string; courseTitle: string }>()
const emit = defineEmits<{ completed: [] }>()
const titleId = 'course-preparation-title'
const dialogRef = ref<HTMLDialogElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const coursePackage = ref<CoursePackage | null>(null)
const step = ref<'choice' | 'import' | 'review'>('choice')
const busy = ref(false)
const dragging = ref(false)
const outcomes = ref<ImportOutcome[]>([])
const updatingIds = ref(new Set<string>())
const error = ref('')

const visible = computed(() => ['pending', 'review'].includes(String(coursePackage.value?.preparation_status || '')))
const documentTypeOptions = computed(() => [
  { value: 'outline' as const, label: t('courseFiles.preparation.documentTypes.outline') },
  { value: 'lesson_plan' as const, label: t('courseFiles.preparation.documentTypes.lessonPlan') },
  { value: 'script' as const, label: t('courseFiles.preparation.documentTypes.script') },
  { value: 'ppt' as const, label: t('courseFiles.preparation.documentTypes.ppt') },
  { value: 'question_bank' as const, label: t('courseFiles.preparation.documentTypes.questionBank') },
  { value: 'school_material' as const, label: t('courseFiles.preparation.documentTypes.schoolMaterial') },
  { value: 'other' as const, label: t('courseFiles.preparation.documentTypes.other') },
])
const documentGroups = computed(() => documentTypeOptions.value.flatMap(option => {
  const assets = (coursePackage.value?.assets || []).filter(asset => (asset.document_type || 'other') === option.value)
  return assets.length ? [{ type: option.value, label: option.label, assets }] : []
}))
const importWarning = computed(() => {
  const rejected = outcomes.value.filter(item => item.outcome === 'rejected').length
  const analysisFailed = outcomes.value.filter(item => item.analysis_error).length
  if (rejected) return t('courseFiles.preparation.rejectedHint').replace('{count}', String(rejected))
  if (analysisFailed) return t('courseFiles.preparation.analysisWarning').replace('{count}', String(analysisFailed))
  return ''
})

watch(visible, async show => {
  if (!show) {
    if (dialogRef.value?.open) dialogRef.value.close()
    return
  }
  await nextTick()
  if (!dialogRef.value?.open) dialogRef.value?.showModal()
  dialogRef.value?.focus({ preventScroll: true })
})

async function loadPackage() {
  const packages = (await http.get<CoursePackage[]>('/api/teacher-course-spaces', teacherRequestConfig({
    params: { course_id: props.courseId },
    silentError: true,
  }))).data
  const match = packages.find(item => String(item.course_id || '') === props.courseId) || packages[0]
  if (!match) return
  coursePackage.value = (await http.get<CoursePackage>(`/api/teacher-course-spaces/${match.package_id}`, teacherRequestConfig({ silentError: true }))).data
  step.value = coursePackage.value.preparation_status === 'review' ? 'review' : 'choice'
}

async function updateStatus(status: 'completed' | 'skipped') {
  if (!coursePackage.value) return
  busy.value = true
  error.value = ''
  try {
    coursePackage.value = (await http.patch<CoursePackage>(
      `/api/teacher-course-spaces/${coursePackage.value.package_id}/preparation`,
      { status },
      teacherRequestConfig(),
    )).data
    emit('completed')
  } catch {
    error.value = t('courseFiles.preparation.statusFailed')
  } finally {
    busy.value = false
  }
}

function startBlank() { void updateStatus('skipped') }
function finish() { void updateStatus('completed') }

const preparationRoot = '辅助资料/其他资料'
function preparationPath(value: string) {
  const normalized = String(value || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '')
  return normalized ? `${preparationRoot}/${normalized}` : preparationRoot
}
function folderPathsForFiles(items: Array<{ path: string }>) {
  const folders = new Set<string>()
  items.forEach(item => {
    const parts = item.path.split('/').filter(Boolean).slice(0, -1)
    for (let index = 1; index <= parts.length; index += 1) folders.add(parts.slice(0, index).join('/'))
  })
  return [...folders]
}

async function uploadBatch(items: Array<{ file: File; path: string }>, emptyFolders: string[] = []) {
  if (!coursePackage.value || (!items.length && !emptyFolders.length)) return
  busy.value = true
  dragging.value = false
  error.value = ''
  try {
    const normalizedItems = items.map(item => ({ file: item.file, path: preparationPath(item.path) }))
    const normalizedFolders = [...folderPathsForFiles(normalizedItems), ...emptyFolders.map(preparationPath)]
    const form = new FormData()
    normalizedItems.forEach(item => {
      form.append('files', item.file, item.file.name)
      form.append('relative_paths', item.path)
    })
    ;[...new Set(normalizedFolders)].forEach(path => form.append('folder_paths', path))
    const response = await http.post(
      `/api/teacher-course-spaces/${coursePackage.value.package_id}/imports`,
      form,
      teacherRequestConfig(),
    )
    outcomes.value = response.data?.outcomes || []
    coursePackage.value = response.data.package
    step.value = 'review'
  } catch {
    error.value = t('courseFiles.preparation.importFailed')
  } finally {
    busy.value = false
  }
}

function captureFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const items = [...(input.files || [])].map(file => ({ file, path: file.name }))
  input.value = ''
  void uploadBatch(items)
}
function captureFolder(event: Event) {
  const input = event.target as HTMLInputElement
  const items = [...(input.files || [])].map(file => ({
    file,
    path: (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name,
  }))
  input.value = ''
  void uploadBatch(items)
}
function readFileEntry(entry: any) { return new Promise<File>((resolve, reject) => entry.file(resolve, reject)) }
async function readDirectoryEntries(reader: any) {
  const entries: any[] = []
  while (true) {
    const batch = await new Promise<any[]>((resolve, reject) => reader.readEntries(resolve, reject))
    if (!batch.length) return entries
    entries.push(...batch)
  }
}
async function collectDroppedEntry(entry: any, parent: string, files: Array<{ file: File; path: string }>, folders: string[]) {
  const path = [parent, entry.name].filter(Boolean).join('/')
  if (entry.isFile) {
    files.push({ file: await readFileEntry(entry), path })
    return
  }
  if (!entry.isDirectory) return
  folders.push(path)
  const children = await readDirectoryEntries(entry.createReader())
  await Promise.all(children.map(child => collectDroppedEntry(child, path, files, folders)))
}
async function handleDrop(event: DragEvent) {
  dragging.value = false
  const items = [...(event.dataTransfer?.items || [])]
  const files: Array<{ file: File; path: string }> = []
  const folders: string[] = []
  const entries = items.map(item => (item as DataTransferItem & { webkitGetAsEntry?: () => any }).webkitGetAsEntry?.()).filter(Boolean)
  if (entries.length) {
    try {
      await Promise.all(entries.map(entry => collectDroppedEntry(entry, '', files, folders)))
    } catch {
      error.value = t('courseFiles.preparation.readFolderFailed')
      return
    }
  } else {
    ;[...(event.dataTransfer?.files || [])].forEach(file => files.push({ file, path: file.name }))
  }
  await uploadBatch(files, folders)
}

async function changeDocumentType(asset: CourseAsset, event: Event) {
  if (!coursePackage.value) return
  const select = event.target as HTMLSelectElement
  const documentType = select.value as DocumentType
  const nextUpdating = new Set(updatingIds.value)
  nextUpdating.add(asset.asset_id)
  updatingIds.value = nextUpdating
  error.value = ''
  try {
    const updated = (await http.patch<CourseAsset>(
      `/api/teacher-course-spaces/${coursePackage.value.package_id}/assets/${asset.asset_id}`,
      { document_type: documentType },
      teacherRequestConfig(),
    )).data
    coursePackage.value.assets = coursePackage.value.assets.map(item => item.asset_id === asset.asset_id ? { ...item, ...updated } : item)
  } catch {
    select.value = asset.document_type || 'other'
    error.value = t('courseFiles.preparation.classificationFailed')
  } finally {
    const remaining = new Set(updatingIds.value)
    remaining.delete(asset.asset_id)
    updatingIds.value = remaining
  }
}

onMounted(() => { void loadPackage() })
</script>

<style scoped>
.preparation-dialog{width:min(760px,calc(100vw - 40px));max-width:none;max-height:min(760px,calc(100dvh - 40px));margin:auto;padding:0;overflow:hidden;border:0;border-radius:16px;color:var(--lz-text-primary);background:#fff;box-shadow:0 28px 76px rgba(15,23,42,.24);animation:preparation-in .24s cubic-bezier(.16,1,.3,1)}
.preparation-dialog.is-choice{width:min(940px,calc(100vw - 48px));max-height:min(620px,calc(100dvh - 40px));border:1px solid #dfe5ee;background:#fff;box-shadow:0 28px 76px rgba(15,23,42,.24)}
.preparation-dialog::backdrop{background:rgba(30,41,59,.38);backdrop-filter:blur(2px);animation:preparation-backdrop-in .2s ease-out}
.preparation-step{min-height:420px;display:grid;background:#fff}.preparation-step>header{display:flex;align-items:center;gap:12px;padding:24px 26px;border-bottom:1px solid #e8edf4}.preparation-step>header>span,.preparation-review>header>div>span{width:38px;height:38px;display:grid;place-items:center;flex:none;border-radius:10px;color:#514bdc;background:#eeefff}.preparation-step h2{margin:0;color:#172033;font-size:22px;letter-spacing:-.02em}.preparation-step>header>button{width:36px;height:36px;display:grid;place-items:center;flex:none;border:1px solid #dbe1ea;border-radius:9px;color:#475569;background:#fff;cursor:pointer}
.preparation-choice{min-height:455px;grid-template-rows:auto minmax(0,1fr);background:#fff}
.preparation-choice>header{padding:24px 28px;border-bottom:1px solid #e8edf4}
.preparation-choice>header>span{width:40px;height:40px;border:1px solid #e0e7ff;border-radius:11px;color:#514bdc;background:linear-gradient(145deg,#f8f9ff,#eef2ff)}
.preparation-choice h2{color:#172033;font-size:22px;letter-spacing:-.02em}
.start-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding:24px 28px 30px}
.start-options>button{position:relative;min-width:0;min-height:300px;display:grid;grid-template-rows:154px minmax(0,1fr);overflow:hidden;padding:0;border:1px solid #dce2eb;border-radius:14px;color:#334155;background:#fff;text-align:left;cursor:pointer;transition:transform .18s cubic-bezier(.16,1,.3,1),border-color .18s ease,box-shadow .18s ease}
.start-options>button.existing-course{border-color:#d5d7f7}
.start-options>button:hover:not(:disabled){transform:translateY(-2px);border-color:#aaa7f2;box-shadow:0 12px 28px rgba(79,70,229,.1)}
.start-options>button:active:not(:disabled){transform:translateY(0)}
.mode-illustration{min-width:0;display:grid;grid-template-columns:minmax(88px,1fr) 40px minmax(116px,1.25fr);align-items:center;gap:14px;padding:19px 22px;border-bottom:1px solid #e8edf4;background:#f8fafc}
.existing-route{background:linear-gradient(145deg,#fafaff,#f3f2ff)}
.route-subject{height:94px;display:grid;grid-template-columns:20px minmax(0,1fr);grid-template-rows:auto 1fr;align-items:center;gap:8px;padding:12px;border:1px solid #e1e7ef;border-radius:12px;color:#6366f1;background:#fff}
.route-subject>b{color:#475569;font-size:10px}.route-subject>span{grid-column:1/-1;display:grid;align-content:center;gap:5px}.route-subject i{height:4px;border-radius:3px;background:#e2e8f0}.route-subject i:nth-child(2){width:82%}.route-subject i:nth-child(3){width:62%;background:#e0e7ff}
.route-node{position:relative;z-index:1;width:36px;height:36px;display:grid;place-items:center;border:1px solid #d8ddff;border-radius:11px;color:#4f46e5;background:#fff}.route-node::before,.route-node::after{position:absolute;top:50%;z-index:-1;width:15px;height:1px;background:#cbd5e1;content:""}.route-node::before{right:100%}.route-node::after{left:100%}.route-node.is-scan{color:#5b57e8;background:#eeefff}
.route-files{display:grid;gap:6px}.route-files>span{min-width:0;height:28px;display:grid;grid-template-columns:15px minmax(0,1fr);align-items:center;gap:6px;padding:0 8px;border:1px solid #e1e7ef;border-radius:8px;color:#6366f1;background:#fff}.route-files b{overflow:hidden;color:#475569;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.route-results>span:nth-child(2),.route-sources>span:nth-child(2){margin-left:7px}.route-results>span:nth-child(3),.route-sources>span:nth-child(3){margin-left:14px}
.matched-folder{height:94px;display:grid;align-content:center;gap:6px;padding:10px 12px;border:1px solid #d8ddff;border-radius:12px;background:#fff}.matched-folder>span{display:flex;align-items:center;gap:6px;color:#4f46e5}.matched-folder>span b{color:#4338ca;font-size:10px}.matched-folder>i{display:grid;grid-template-columns:11px minmax(0,1fr);align-items:center;gap:5px;color:#22a06b}.matched-folder em{height:3px;border-radius:2px;background:#e0e7ff}
.mode-copy{min-width:0;display:grid;grid-template-columns:minmax(0,1fr) 36px;align-items:center;gap:16px;padding:19px 22px 21px;background:#fff}.existing-course .mode-copy{background:#fdfdff}.mode-copy>span:first-child{min-width:0;display:grid;gap:7px}.mode-copy strong{color:#263147;font-size:18px;letter-spacing:-.02em;line-height:1.25}.mode-copy small{max-width:310px;color:#64748b;font-size:12.5px;line-height:1.55}.mode-enter{width:36px;height:36px;display:grid;place-items:center;border:1px solid #e2e8f0;border-radius:10px;color:#94a3b8;background:#f8fafc;transition:transform .18s cubic-bezier(.16,1,.3,1),border-color .18s ease,color .18s ease,background .18s ease}.existing-course .mode-enter{border-color:#d8ddff;color:#6366f1;background:#fff}.start-options>button:hover:not(:disabled) .mode-enter{transform:translateX(2px);border-color:#bab8ef;color:#4f46e5;background:#fff}
.preparation-import{grid-template-rows:auto 1fr}.preparation-dropzone{min-height:290px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;margin:28px;padding:34px;border:1px dashed #aeb8c8;border-radius:14px;color:#5b57e8;background:#fbfcff}.preparation-dropzone.dragging{border-color:#5b57e8;background:#f2f2ff}.preparation-dropzone>strong{color:#334155;font-size:16px}.preparation-dropzone>div{display:flex;gap:9px;margin-top:12px}.preparation-dropzone button,.preparation-review footer button{min-height:40px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 14px;border:1px solid #d7dde7;border-radius:9px;color:#475569;background:#fff;font-size:13px;font-weight:700;cursor:pointer}.preparation-dropzone button.primary,.preparation-review footer button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.preparation-dropzone button:disabled,.preparation-review footer button:disabled,.start-options>button:disabled{opacity:.5;cursor:not-allowed}
.preparation-review{max-height:min(760px,calc(100dvh - 40px));grid-template-rows:auto minmax(0,1fr) auto auto}.preparation-review>header{justify-content:space-between}.preparation-review>header>div{display:flex;align-items:center;gap:12px}.preparation-review>header>small{color:#64748b;font-size:12px;font-weight:700}.recognized-structure{min-height:0;overflow:auto;padding:10px 26px 18px}.recognized-group{padding-top:14px}.recognized-group>header{min-height:34px;display:flex;align-items:center;justify-content:space-between;color:#334155}.recognized-group>header strong{font-size:13px}.recognized-group>header small{min-width:24px;text-align:right;color:#64748b;font-size:12px}.recognized-files{border-top:1px solid #e8edf4}.recognized-file{min-height:58px;display:grid;grid-template-columns:20px minmax(0,1fr) 132px;align-items:center;gap:10px;border-bottom:1px solid #edf1f5;color:#6366f1}.recognized-file>span{min-width:0;display:grid;gap:3px}.recognized-file strong,.recognized-file small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.recognized-file strong{color:#334155;font-size:13px}.recognized-file small{color:#7b8798;font-size:11px}.recognized-file select{width:100%;min-height:34px;padding:0 8px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:12px}.recognized-file select:focus{outline:2px solid #6366f1;outline-offset:2px}.import-warning,.dialog-error{display:flex;align-items:center;gap:7px;margin:0;padding:10px 26px;font-size:12px}.import-warning{color:#9a3412;background:#fff7ed}.dialog-error{color:#b42318;background:#fef3f2}.preparation-choice>.dialog-error,.preparation-import>.dialog-error{align-self:end}.preparation-review>footer{display:flex;justify-content:flex-end;gap:9px;padding:15px 26px;border-top:1px solid #e8edf4;background:#fbfcfe}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.preparation-step>header>button:hover:not(:disabled),.preparation-dropzone button:hover:not(:disabled),.preparation-review footer button:hover:not(:disabled){border-color:#bab8ef;color:#4338ca;background:#f7f7ff}.preparation-dropzone button.primary:hover:not(:disabled),.preparation-review footer button.primary:hover:not(:disabled){border-color:#4338ca;color:#fff;background:#4338ca}.preparation-step>header>button:active:not(:disabled),.preparation-dropzone button:active:not(:disabled),.preparation-review footer button:active:not(:disabled){transform:translateY(1px)}
.start-options>button:focus-visible,.preparation-step>header>button:focus-visible,.preparation-dropzone button:focus-visible,.preparation-review footer button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.spin{animation:preparation-spin .85s linear infinite}@keyframes preparation-spin{to{transform:rotate(360deg)}}@keyframes preparation-in{from{opacity:.35;transform:translateY(10px) scale(.992)}to{opacity:1;transform:none}}@keyframes preparation-backdrop-in{from{background:rgba(30,41,59,0);backdrop-filter:blur(0)}to{background:rgba(30,41,59,.38);backdrop-filter:blur(2px)}}
@media(max-width:820px){.preparation-dialog.is-choice{width:calc(100vw - 24px);max-height:calc(100dvh - 24px)}.preparation-choice{min-height:0}.start-options{grid-template-columns:1fr;overflow:auto}.start-options>button{min-height:286px}}
@media(max-width:700px){.preparation-dialog,.preparation-dialog.is-choice{width:calc(100vw - 16px);max-height:calc(100dvh - 16px)}.preparation-step>header,.recognized-structure,.preparation-review>footer{padding-inline:18px}.preparation-choice>header{padding-top:22px}.start-options{padding:14px 18px 22px}.start-options>button{min-height:276px}.mode-illustration{grid-template-columns:minmax(78px,1fr) 36px minmax(108px,1.2fr);padding:16px}.mode-copy{padding:17px 18px 19px}.preparation-dropzone{margin:20px}.recognized-file{grid-template-columns:20px minmax(0,1fr)}.recognized-file select{grid-column:2}.preparation-review>footer{display:grid;grid-template-columns:1fr 1fr}}
@media(prefers-reduced-motion:reduce){.preparation-dialog,.preparation-dialog::backdrop,.spin{animation:none}.start-options>button{transition:none}}
</style>
