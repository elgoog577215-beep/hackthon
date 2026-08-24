<template>
  <aside class="reference-tray" :class="{ 'is-compact': compact }" :aria-label="t('courseWorkbench.references.title', '信息来源')">
    <header class="reference-tray__header">
      <strong>{{ t('courseWorkbench.references.title', '信息来源') }}</strong>
      <button v-if="showClose" type="button" :title="t('common.close', '关闭')" :aria-label="t('common.close', '关闭')" @click="emit('close')"><X :size="16" /></button>
    </header>

    <button type="button" class="system-context" @click="emit('open-course-information')">
      <span><Database :size="16" /></span>
      <div><strong>{{ t('courseWorkbench.references.systemContext', '课程上下文') }}</strong><small>{{ t('courseWorkbench.references.systemContextHelp', '课时、课型与教学设置') }}</small></div>
      <ChevronRight :size="15" />
    </button>

    <button
      v-if="previousAvailableSources.length"
      type="button"
      class="reuse-previous"
      :disabled="loading || saving"
      @click="reusePreviousSources"
    >
      <CopyPlus :size="15" />
      <span>{{ t('courseWorkbench.references.reusePrevious', '沿用上一讲资料') }}</span>
      <small>{{ previousAvailableSources.length }}</small>
    </button>

    <section class="source-group">
      <div class="group-heading"><strong>{{ t('courseWorkbench.references.primary', '主来源') }}</strong><small>{{ t('courseWorkbench.references.primaryLimit', '最多 1 份') }}</small></div>
      <div
        class="drop-zone"
        :class="{ 'has-file': primarySource, dragging: dragRole === 'primary' }"
        @dragover.prevent="dragRole = 'primary'"
        @dragleave="dragRole = ''"
        @drop.prevent="handleDrop($event, 'primary')"
      >
        <template v-if="primarySource">
          <FileText :size="19" />
          <div><strong>{{ primarySource.filename }}</strong><small>{{ fileSize(primarySource.size_bytes) }}</small></div>
          <button type="button" :aria-label="t('common.remove', '移除')" @click="removeSource(primarySource.asset_id)"><X :size="15" /></button>
        </template>
        <button v-else type="button" class="empty-drop" @click="primaryInput?.click()"><Plus :size="18" /><span>{{ t('courseWorkbench.references.addPrimary', '添加主来源') }}</span></button>
      </div>
      <input ref="primaryInput" class="visually-hidden" type="file" @change="handleInput($event, 'primary')" />
    </section>

    <section class="source-group source-group--references">
      <div class="group-heading"><strong>{{ t('courseWorkbench.references.supporting', '参考资料') }}</strong><small>{{ referenceSources.length }}</small></div>
      <div class="reference-list">
        <div v-for="item in referenceSources" :key="item.asset_id" class="reference-item">
          <FileText :size="17" /><div><strong>{{ item.filename }}</strong><small>{{ fileSize(item.size_bytes) }}</small></div><button type="button" :aria-label="t('common.remove', '移除')" @click="removeSource(item.asset_id)"><X :size="14" /></button>
        </div>
        <button
          type="button"
          class="reference-add"
          :class="{ dragging: dragRole === 'reference' }"
          @click="referenceInput?.click()"
          @dragover.prevent="dragRole = 'reference'"
          @dragleave="dragRole = ''"
          @drop.prevent="handleDrop($event, 'reference')"
        ><Plus :size="16" />{{ t('courseWorkbench.references.addSupporting', '添加或拖入资料') }}</button>
      </div>
      <input ref="referenceInput" class="visually-hidden" type="file" multiple @change="handleInput($event, 'reference')" />
    </section>

    <section class="source-group source-group--web">
      <div class="group-heading"><strong>{{ t('courseWorkbench.references.webSources', '联网来源') }}</strong><small>{{ webSources.length }}</small></div>
      <div class="web-source-list">
        <div v-for="item in webSources" :key="item.asset_id" class="web-source-item">
          <Globe2 :size="17" />
          <div><strong>{{ item.source_label || item.filename }}</strong><a v-if="item.source_metadata?.url" :href="String(item.source_metadata.url)" target="_blank" rel="noopener noreferrer">{{ item.source_metadata.domain || item.source_metadata.url }}<ExternalLink :size="11" /></a><small v-else>{{ item.filename }}</small></div>
          <button type="button" :aria-label="t('common.remove', '移除')" @click="removeSource(item.asset_id)"><X :size="14" /></button>
        </div>
        <button type="button" class="web-research-open" @click="researchVisible = true"><Search :size="16" />{{ webSources.length ? t('courseWorkbench.references.continueWebResearch', '继续检索') : t('courseWorkbench.references.startWebResearch', '添加联网来源') }}</button>
      </div>
    </section>

    <section v-if="materials.length" class="material-library">
      <div class="group-heading"><strong>{{ t('courseWorkbench.references.courseMaterials', '课程资料') }}</strong><small>{{ materials.length }}</small></div>
      <button v-for="item in availableMaterials" :key="item.asset_id" type="button" @click="addExisting(item)">
        <FileText :size="16" /><span>{{ item.filename }}</span><Plus :size="14" />
      </button>
      <p v-if="!availableMaterials.length">{{ t('courseWorkbench.references.allSelected', '当前资料已全部引用') }}</p>
    </section>

    <p v-if="error" class="tray-error" role="alert">{{ error }}</p>
    <WebResearchDialog :visible="researchVisible" :course-id="courseId" :stage="stage" :lesson-id="lessonId" @close="researchVisible = false" @saved="handleWebSaved" />
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ChevronRight, CopyPlus, Database, ExternalLink, FileText, Globe2, Plus, Search, X } from 'lucide-vue-next'
import WebResearchDialog from './WebResearchDialog.vue'
import { t } from '../shared/i18n'
import http, { teacherRequestConfig } from '../utils/http'

export type CourseReferenceItem = {
  package_id: string
  asset_id: string
  material_asset_id: string
  filename: string
  relative_path: string
  size_bytes: number
  uploaded_at?: string
  role: 'primary' | 'reference'
  origin?: 'material' | 'web_search'
  source_label?: string
  reuse_policy?: 'verbatim_allowed' | 'reference_only' | 'original_generation'
  rights_basis?: 'teacher_asserted' | 'open_license' | 'license_unknown' | 'platform_owned'
  source_metadata?: Record<string, any>
  usages?: Array<{
    target_id?: string
    target_type?: string
    target_label?: string
    role?: 'primary' | 'reference'
  }>
}

const props = withDefaults(defineProps<{
  courseId: string
  modelValue: CourseReferenceItem[]
  stage?: string
  lessonId?: string
  scopeTargetId?: string
  scopeTargetType?: string
  scopeTargetLabel?: string
  previousScopeTargetId?: string
  showClose?: boolean
  compact?: boolean
}>(), {
  stage: 'foundation',
  lessonId: '',
  scopeTargetId: '',
  scopeTargetType: '',
  scopeTargetLabel: '',
  previousScopeTargetId: '',
  showClose: false,
  compact: false,
})
const emit = defineEmits<{
  (event: 'update:modelValue', value: CourseReferenceItem[]): void
  (event: 'open-course-information'): void
  (event: 'close'): void
}>()
const materials = ref<CourseReferenceItem[]>([])
const selected = ref<CourseReferenceItem[]>([])
const storedWebReferences = ref<CourseReferenceItem[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const researchVisible = ref(false)
const dragRole = ref<'' | 'primary' | 'reference'>('')
const primaryInput = ref<HTMLInputElement | null>(null)
const referenceInput = ref<HTMLInputElement | null>(null)
const primarySource = computed(() => selected.value.find(item => item.role === 'primary'))
const referenceSources = computed(() => selected.value.filter(item => item.role === 'reference' && item.origin !== 'web_search'))
const webSources = computed(() => selected.value.filter(item => item.role === 'reference' && item.origin === 'web_search'))
const availableMaterials = computed(() => {
  const chosen = new Set(selected.value.map(item => item.asset_id))
  return materials.value.filter(item => !chosen.has(item.asset_id))
})
const previousAvailableSources = computed(() => {
  if (!props.previousScopeTargetId) return []
  const chosen = new Set(selected.value.map(item => item.asset_id))
  return materials.value.flatMap(item => {
    if (chosen.has(item.asset_id)) return []
    const usage = item.usages?.find(link => link.target_id === props.previousScopeTargetId)
    if (!usage) return []
    return [{ ...item, role: usage.role === 'primary' ? 'primary' as const : 'reference' as const }]
  })
})

watch(() => props.modelValue, value => { selected.value = value.map(item => ({ ...item })) }, { immediate: true, deep: true })
function applySelection(value: CourseReferenceItem[], persist: boolean) {
  selected.value = value
  emit('update:modelValue', value)
  if (persist && props.scopeTargetId && props.scopeTargetType) void persistScopedSelection(value)
}
function commit(value: CourseReferenceItem[]) { applySelection(value, true) }
function fileSize(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB` }

async function resolvePackageId(value: CourseReferenceItem[]) {
  const direct = value[0]?.package_id || materials.value[0]?.package_id
  if (direct) return direct
  const response = await http.get('/api/teacher-course-spaces', teacherRequestConfig({ params: { course_id: props.courseId }, silentError: true }))
  return String(response.data?.[0]?.package_id || '')
}

async function persistScopedSelection(value: CourseReferenceItem[]) {
  const targetId = props.scopeTargetId
  const targetType = props.scopeTargetType
  if (!targetId || !targetType) return
  saving.value = true
  error.value = ''
  try {
    const packageId = await resolvePackageId(value)
    if (!packageId) return
    await http.put(`/api/teacher-course-spaces/${packageId}/relationships`, {
      target_id: targetId,
      target_type: targetType,
      target_label: props.scopeTargetLabel || targetId,
      sources: value.map(item => ({ source_asset_id: item.asset_id, role: item.role })),
    }, teacherRequestConfig({ silentError: true }))
  } catch (reason: any) {
    if (targetId === props.scopeTargetId) error.value = String(reason?.response?.data?.detail || reason?.message || t('courseWorkbench.references.saveFailed', '本讲资料保存失败'))
  } finally {
    if (targetId === props.scopeTargetId) saving.value = false
  }
}

async function loadMaterials() {
  try {
    const response = await http.get('/api/materials', teacherRequestConfig({ params: { course_id: props.courseId }, silentError: true }))
    const webByMaterialId = new Map([...storedWebReferences.value, ...webSources.value].map(item => [item.material_asset_id, item]))
    materials.value = (response.data?.assets || []).map((item: CourseReferenceItem) => ({ ...item, ...(webByMaterialId.get(item.material_asset_id) || {}), role: 'reference' }))
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail || reason?.message || t('courseWorkbench.references.loadFailed', '课程资料读取失败')) }
}

function mergeWebReferences(references: CourseReferenceItem[]) {
  const next = [...selected.value]
  for (const reference of references) {
    const normalized = { ...reference, role: 'reference' as const, origin: 'web_search' as const }
    const index = next.findIndex(item => item.asset_id === normalized.asset_id || item.material_asset_id === normalized.material_asset_id)
    if (index >= 0) next[index] = normalized; else next.push(normalized)
  }
  commit(next)
}

async function loadWebReferences() {
  try {
    const response = await http.get(`/api/courses/${props.courseId}/web-research`, teacherRequestConfig({ params: { stage: props.stage, lesson_id: props.lessonId }, silentError: true }))
    storedWebReferences.value = response.data?.accepted_references || []
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail?.message || reason?.response?.data?.detail || reason?.message || t('courseWorkbench.webResearch.loadFailed', '调研记录读取失败')) }
}

async function loadAll() {
  const targetId = props.scopeTargetId
  loading.value = true; error.value = ''
  try {
    await loadWebReferences()
    await loadMaterials()
    if (targetId && targetId === props.scopeTargetId) {
      const webByMaterialId = new Map(storedWebReferences.value.map(item => [item.material_asset_id, item]))
      const scoped = materials.value.flatMap(item => {
        const usage = item.usages?.find(link => link.target_id === targetId)
        if (!usage) return []
        return [{
          ...item,
          ...(webByMaterialId.get(item.material_asset_id) || {}),
          role: usage.role === 'primary' ? 'primary' as const : 'reference' as const,
        }]
      })
      applySelection(scoped, false)
    }
  }
  finally { loading.value = false }
}

async function uploadFiles(files: File[], role: 'primary' | 'reference') {
  if (!files.length) return
  loading.value = true; error.value = ''
  try {
    const uploaded: CourseReferenceItem[] = []
    for (const file of role === 'primary' ? files.slice(0, 1) : files) {
      const data = new FormData(); data.append('file', file); data.append('course_id', props.courseId)
      const response = await http.post('/api/materials', data, teacherRequestConfig({ headers: { 'Content-Type': 'multipart/form-data' }, silentError: true }))
      const payload = response.data
      if (!payload?.course_space?.course_asset_id) throw new Error(t('courseWorkbench.references.registerFailed', '资料已上传，但未能加入当前课程'))
      uploaded.push({ package_id: payload.course_space.package_id, asset_id: payload.course_space.course_asset_id, material_asset_id: payload.asset_id, filename: payload.filename, relative_path: payload.course_space.relative_path, size_bytes: payload.size_bytes || file.size, uploaded_at: payload.uploaded_at, role })
    }
    let next = selected.value.filter(item => role !== 'primary' || item.role !== 'primary')
    for (const item of uploaded) next = [...next.filter(current => current.asset_id !== item.asset_id), item]
    commit(next); await loadMaterials()
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail || reason?.message || t('courseWorkbench.references.uploadFailed', '资料上传失败')) }
  finally { loading.value = false }
}

function handleInput(event: Event, role: 'primary' | 'reference') {
  const input = event.target as HTMLInputElement
  void uploadFiles(Array.from(input.files || []), role)
  input.value = ''
}
function handleDrop(event: DragEvent, role: 'primary' | 'reference') { dragRole.value = ''; void uploadFiles(Array.from(event.dataTransfer?.files || []), role) }
function removeSource(assetId: string) { commit(selected.value.filter(item => item.asset_id !== assetId)) }
function addExisting(item: CourseReferenceItem) { commit([...selected.value, { ...item, role: 'reference' }]) }
function reusePreviousSources() {
  let hasPrimary = selected.value.some(item => item.role === 'primary')
  const reused = previousAvailableSources.value.map(item => {
    const role = item.role === 'primary' && !hasPrimary ? 'primary' as const : 'reference' as const
    if (role === 'primary') hasPrimary = true
    return { ...item, role }
  })
  if (reused.length) commit([...selected.value, ...reused])
}
function handleWebSaved(references: CourseReferenceItem[]) { storedWebReferences.value = references; mergeWebReferences(references); void loadMaterials() }
watch(() => [props.courseId, props.stage, props.lessonId], () => { void loadAll() })
onMounted(loadAll)
</script>

<style scoped>
.reference-tray{min-width:0;min-height:0;overflow:auto;border-left:1px solid #e4e9f1;background:#fbfcfe}.reference-tray__header{min-height:54px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px 0 16px;border-bottom:1px solid #e7ebf2;background:#fff}.reference-tray__header strong{color:#243047;font-size:14px}.reference-tray__header button{width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.reference-tray__header button:hover{color:#334155;background:#f3f5f8}.reference-tray__header button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.system-context{width:calc(100% - 32px);display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:10px;margin:16px 16px 4px;padding:11px 12px;border:1px solid #e2e7ef;border-radius:10px;color:inherit;background:#fff;text-align:left;font:inherit;cursor:pointer}.system-context:hover{border-color:#c9c8f7;background:#fafaff}.system-context:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.system-context>span{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;color:#4f46e5;background:#eef2ff}.system-context>div{min-width:0;display:grid;gap:2px}.system-context strong{color:#334155;font-size:12px}.system-context small{overflow-wrap:anywhere;color:#64748b;font-size:11px;line-height:1.35}.system-context>svg{color:#7b8798}.reference-tray.is-compact .system-context{min-height:46px}.reference-tray.is-compact .system-context small{display:none}.reuse-previous{min-height:34px;display:flex;align-items:center;gap:7px;margin:8px 16px 0;padding:0;border:0;color:#4f46e5;background:transparent;font:inherit;font-size:12px;font-weight:700;cursor:pointer}.reuse-previous small{min-width:20px;height:20px;display:grid;place-items:center;border-radius:10px;color:#4338ca;background:#eef2ff;font-size:11px}.reuse-previous:hover:not(:disabled){color:#3730a3}.reuse-previous:focus-visible{outline:2px solid #6366f1;outline-offset:3px}.reuse-previous:disabled{opacity:.5;cursor:not-allowed}.source-group,.material-library{display:grid;gap:8px;padding:16px 16px 0}.group-heading{display:flex;align-items:center;justify-content:space-between;color:#334155;font-size:12px}.group-heading small{color:#64748b}.drop-zone{min-height:78px;display:flex;align-items:center;gap:10px;padding:10px;border:1px dashed #b9c3d2;border-radius:10px;color:#64748b;background:#fff}.drop-zone.dragging,.reference-add.dragging{border-color:#5b57e8;background:#f4f4ff}.drop-zone.has-file{border-style:solid}.drop-zone>div,.reference-item>div{min-width:0;display:grid;gap:3px;flex:1}.drop-zone strong,.reference-item strong{overflow:hidden;color:#334155;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.drop-zone small,.reference-item small{color:#64748b;font-size:11px}.drop-zone>button:not(.empty-drop),.reference-item>button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:6px;color:#64748b;background:transparent;cursor:pointer}.empty-drop{width:100%;min-height:58px;display:flex;align-items:center;justify-content:center;gap:7px;border:0;color:#4f46e5;background:transparent;font-size:12px;font-weight:700;cursor:pointer}.reference-list{display:grid;gap:7px}.reference-item{min-height:54px;display:flex;align-items:center;gap:9px;padding:8px 9px;border:1px solid #e2e7ef;border-radius:9px;background:#fff}.reference-item>svg{color:#6366f1}.reference-add{min-height:42px;display:flex;align-items:center;justify-content:center;gap:7px;border:1px dashed #b9c3d2;border-radius:9px;color:#4f46e5;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.material-library{padding-bottom:18px}.material-library>button{min-height:38px;display:grid;grid-template-columns:18px minmax(0,1fr) 16px;align-items:center;gap:7px;padding:0 9px;border:0;border-radius:7px;color:#475569;background:transparent;text-align:left;cursor:pointer}.material-library>button:hover{background:#eef2ff;color:#4338ca}.material-library>button span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.material-library>p{margin:3px 0;color:#64748b;font-size:12px}.tray-error{margin:12px 16px;padding:9px 10px;border-radius:8px;color:#b91c1c;background:#fff1f2;font-size:12px}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.source-group--web{padding-top:18px}.web-source-list{display:grid;gap:7px}.web-source-item{min-height:56px;display:grid;grid-template-columns:18px minmax(0,1fr) 28px;align-items:center;gap:9px;padding:8px 9px;border:1px solid #dce5f0;border-radius:9px;background:#fff}.web-source-item>svg{color:#0f766e}.web-source-item>div{min-width:0;display:grid;gap:3px}.web-source-item strong{overflow:hidden;color:#334155;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.web-source-item a{display:flex;align-items:center;gap:4px;overflow:hidden;color:#0f766e;font-size:12px;text-decoration:none;text-overflow:ellipsis;white-space:nowrap}.web-source-item small{color:#64748b;font-size:12px}.web-source-item>button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:6px;color:#64748b;background:transparent;cursor:pointer}.web-research-open{min-height:42px;display:flex;align-items:center;justify-content:center;gap:7px;border:1px dashed #8fbab5;border-radius:9px;color:#0f766e;background:#f4fbfa;font-size:12px;font-weight:750;cursor:pointer}
</style>
