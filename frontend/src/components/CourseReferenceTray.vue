<template>
  <aside class="reference-tray" :aria-label="t('courseWorkbench.references.title', '引用资料')">
    <header>
      <div><strong>{{ t('courseWorkbench.references.title', '引用资料') }}</strong><small>{{ t('courseWorkbench.references.help', '决定本次生成使用哪些老师资料') }}</small></div>
      <button type="button" :aria-label="t('common.refresh', '刷新')" @click="loadMaterials"><RefreshCw :size="15" :class="{ spin: loading }" /></button>
    </header>

    <section class="system-context">
      <span><Database :size="16" /></span>
      <div><strong>{{ t('courseWorkbench.references.systemContext', '课程上下文') }}</strong><small>{{ t('courseWorkbench.references.systemContextHelp', '大纲、课次与已确认内容自动加入') }}</small></div>
      <Check :size="15" />
    </section>

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

    <section v-if="materials.length" class="material-library">
      <div class="group-heading"><strong>{{ t('courseWorkbench.references.courseMaterials', '课程资料') }}</strong><small>{{ materials.length }}</small></div>
      <button v-for="item in availableMaterials" :key="item.asset_id" type="button" @click="addExisting(item)">
        <FileText :size="16" /><span>{{ item.filename }}</span><Plus :size="14" />
      </button>
      <p v-if="!availableMaterials.length">{{ t('courseWorkbench.references.allSelected', '当前资料已全部引用') }}</p>
    </section>

    <p v-if="error" class="tray-error" role="alert">{{ error }}</p>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Check, Database, FileText, Plus, RefreshCw, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import http from '../utils/http'

export type CourseReferenceItem = {
  package_id: string
  asset_id: string
  material_asset_id: string
  filename: string
  relative_path: string
  size_bytes: number
  uploaded_at?: string
  role: 'primary' | 'reference'
}

const props = defineProps<{ courseId: string; modelValue: CourseReferenceItem[] }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: CourseReferenceItem[]): void }>()
const materials = ref<CourseReferenceItem[]>([])
const selected = ref<CourseReferenceItem[]>([])
const loading = ref(false)
const error = ref('')
const dragRole = ref<'' | 'primary' | 'reference'>('')
const primaryInput = ref<HTMLInputElement | null>(null)
const referenceInput = ref<HTMLInputElement | null>(null)
const primarySource = computed(() => selected.value.find(item => item.role === 'primary'))
const referenceSources = computed(() => selected.value.filter(item => item.role === 'reference'))
const availableMaterials = computed(() => {
  const chosen = new Set(selected.value.map(item => item.asset_id))
  return materials.value.filter(item => !chosen.has(item.asset_id))
})

watch(() => props.modelValue, value => { selected.value = value.map(item => ({ ...item })) }, { immediate: true, deep: true })
function commit(value: CourseReferenceItem[]) { selected.value = value; emit('update:modelValue', value) }
function fileSize(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB` }

async function loadMaterials() {
  loading.value = true; error.value = ''
  try {
    const response = await http.get('/api/materials', { params: { course_id: props.courseId }, silentError: true })
    materials.value = (response.data?.assets || []).map((item: CourseReferenceItem) => ({ ...item, role: 'reference' }))
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail || reason?.message || t('courseWorkbench.references.loadFailed', '课程资料读取失败')) }
  finally { loading.value = false }
}

async function uploadFiles(files: File[], role: 'primary' | 'reference') {
  if (!files.length) return
  loading.value = true; error.value = ''
  try {
    const uploaded: CourseReferenceItem[] = []
    for (const file of role === 'primary' ? files.slice(0, 1) : files) {
      const data = new FormData(); data.append('file', file); data.append('course_id', props.courseId)
      const response = await http.post('/api/materials', data, { headers: { 'Content-Type': 'multipart/form-data' }, silentError: true })
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
onMounted(loadMaterials)
</script>

<style scoped>
.reference-tray{min-width:0;min-height:0;overflow:auto;border-left:1px solid #e4e9f1;background:#fbfcfe}.reference-tray>header{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 18px;border-bottom:1px solid #e7ebf2;background:#fff}.reference-tray>header>div{display:grid;gap:3px}.reference-tray>header strong{color:#243047;font-size:14px}.reference-tray>header small{color:#64748b;font-size:12px}.reference-tray>header button{width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:7px;color:#64748b;background:transparent;cursor:pointer}.system-context{display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:10px;margin:16px 16px 4px;padding:11px 12px;border:1px solid #e2e7ef;border-radius:10px;background:#fff}.system-context>span{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;color:#4f46e5;background:#eef2ff}.system-context>div{display:grid;gap:2px}.system-context strong{color:#334155;font-size:12px}.system-context small{color:#64748b;font-size:11px;line-height:1.35}.system-context>svg{color:#16a34a}.source-group,.material-library{display:grid;gap:8px;padding:16px 16px 0}.group-heading{display:flex;align-items:center;justify-content:space-between;color:#334155;font-size:12px}.group-heading small{color:#64748b}.drop-zone{min-height:78px;display:flex;align-items:center;gap:10px;padding:10px;border:1px dashed #b9c3d2;border-radius:10px;color:#64748b;background:#fff}.drop-zone.dragging,.reference-add.dragging{border-color:#5b57e8;background:#f4f4ff}.drop-zone.has-file{border-style:solid}.drop-zone>div,.reference-item>div{min-width:0;display:grid;gap:3px;flex:1}.drop-zone strong,.reference-item strong{overflow:hidden;color:#334155;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.drop-zone small,.reference-item small{color:#64748b;font-size:11px}.drop-zone>button:not(.empty-drop),.reference-item>button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:6px;color:#64748b;background:transparent;cursor:pointer}.empty-drop{width:100%;min-height:58px;display:flex;align-items:center;justify-content:center;gap:7px;border:0;color:#4f46e5;background:transparent;font-size:12px;font-weight:700;cursor:pointer}.reference-list{display:grid;gap:7px}.reference-item{min-height:54px;display:flex;align-items:center;gap:9px;padding:8px 9px;border:1px solid #e2e7ef;border-radius:9px;background:#fff}.reference-item>svg{color:#6366f1}.reference-add{min-height:42px;display:flex;align-items:center;justify-content:center;gap:7px;border:1px dashed #b9c3d2;border-radius:9px;color:#4f46e5;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.material-library{padding-bottom:18px}.material-library>button{min-height:38px;display:grid;grid-template-columns:18px minmax(0,1fr) 16px;align-items:center;gap:7px;padding:0 9px;border:0;border-radius:7px;color:#475569;background:transparent;text-align:left;cursor:pointer}.material-library>button:hover{background:#eef2ff;color:#4338ca}.material-library>button span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.material-library>p{margin:3px 0;color:#64748b;font-size:12px}.tray-error{margin:12px 16px;padding:9px 10px;border-radius:8px;color:#b91c1c;background:#fff1f2;font-size:12px}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
