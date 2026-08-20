<template>
  <main class="file-space" :class="{ 'file-space--embedded': embedded }">
    <header v-if="!embedded" class="standalone-header">
      <div><small>{{ t('courseFiles.spaceLabel') }}</small><h1>{{ courseTitle || t('courseFiles.allCourseFiles') }}</h1></div>
      <button type="button" @click="router.push({ name: 'course-library' })"><ArrowLeft :size="16" />{{ t('courseFiles.backToCalendar') }}</button>
    </header>

    <section v-if="initializing" class="space-state" role="status"><LoaderCircle class="spin" :size="22" />{{ t('courseFiles.preparingSpace') }}</section>
    <section v-else-if="!selected" class="space-state is-error" role="alert">
      <TriangleAlert :size="22" /><strong>{{ t('courseFiles.spaceUnavailable') }}</strong><span>{{ status }}</span>
      <button type="button" @click="refresh">{{ t('common.retry') }}</button>
    </section>

    <section v-else class="file-layout">
      <aside class="file-tree-pane">
        <header class="pane-heading">
          <div><small>{{ t('courseFiles.courseLabel') }}</small><strong>{{ selected.course_name }}</strong></div>
          <button type="button" :aria-label="t('common.refresh')" @click="reloadAll"><RefreshCw :size="15" :class="{ spin: busy }" /></button>
        </header>
        <el-tree
          class="workspace-tree"
          :data="treeData"
          node-key="id"
          :current-node-key="selectedNode?.id || currentFolderId"
          :default-expanded-keys="expandedKeys"
          :expand-on-click-node="false"
          highlight-current
          @node-click="handleTreeClick"
        >
          <template #default="{ data }">
            <span class="tree-node" :class="`is-${data.type}`">
              <FolderOpen v-if="data.kind === 'folder'" :size="15" />
              <component :is="nodeIcon(data)" v-else :size="15" />
              <span>{{ data.label }}</span>
              <i v-if="data.status === 'stale'" :title="t('courseFiles.updateNeeded')" />
            </span>
          </template>
        </el-tree>
        <footer>
          <span>{{ selected.academic_year }} · {{ termLabel(selected.term) }}</span>
          <button type="button" @click="downloadPackage"><Download :size="14" />{{ t('courseFiles.exportCourse') }}</button>
        </footer>
      </aside>

      <section class="file-list-pane">
        <header class="list-toolbar">
          <nav :aria-label="t('courseFiles.filePath')">
            <button type="button" @click="openFolder('root')"><Home :size="14" />{{ t('courseFiles.rootName') }}</button>
            <template v-for="crumb in breadcrumbs" :key="crumb.id">
              <ChevronRight :size="13" /><button type="button" @click="openFolder(crumb.id)">{{ crumb.label }}</button>
            </template>
          </nav>
          <div class="toolbar-actions">
            <label class="list-search"><Search :size="14" /><input v-model="query" type="search" :placeholder="t('courseFiles.searchCurrent')" /></label>
            <el-dropdown trigger="click" @command="openCreateDialog">
              <button class="new-button" type="button"><Plus :size="15" />{{ t('courseFiles.new') }}<ChevronDown :size="14" /></button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="outline"><FileText :size="14" />{{ t('courseFiles.types.outline') }}</el-dropdown-item>
                  <el-dropdown-item command="lesson_plan"><ClipboardList :size="14" />{{ t('courseFiles.types.lessonPlan') }}</el-dropdown-item>
                  <el-dropdown-item command="material"><BookOpen :size="14" />{{ t('courseFiles.types.material') }}</el-dropdown-item>
                  <el-dropdown-item command="ppt"><Presentation :size="14" />{{ t('courseFiles.types.ppt') }}</el-dropdown-item>
                  <el-dropdown-item command="practice"><ListChecks :size="14" />{{ t('courseFiles.types.practice') }}</el-dropdown-item>
                  <el-dropdown-item divided command="folder"><FolderPlus :size="14" />{{ t('courseFiles.types.folder') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </header>

        <div class="folder-title">
          <div><small>{{ currentFolder?.type === 'lesson' ? t('courseFiles.lessonFolder') : t('courseFiles.folder') }}</small><h2>{{ currentFolder?.label || t('courseFiles.rootName') }}</h2></div>
          <span>{{ t('courseFiles.itemCount').replace('{count}', String(filteredChildren.length)) }}</span>
        </div>

        <div class="file-table" role="table" :aria-label="t('courseFiles.fileList')">
          <div class="file-table__head" role="row">
            <span>{{ t('courseFiles.columns.name') }}</span><span>{{ t('courseFiles.columns.type') }}</span><span>{{ t('courseFiles.columns.status') }}</span><span>{{ t('courseFiles.columns.updated') }}</span><span />
          </div>
          <button
            v-for="node in filteredChildren"
            :key="node.id"
            type="button"
            class="file-row"
            :class="{ selected: selectedNode?.id === node.id }"
            role="row"
            @click="selectNode(node)"
            @dblclick="node.kind === 'folder' ? openFolder(node.id) : primaryAction(node)"
          >
            <span class="file-name" role="cell"><span class="file-icon" :data-type="node.type"><component :is="node.kind === 'folder' ? Folder : nodeIcon(node)" :size="17" /></span><span><strong>{{ node.label }}</strong><small v-if="node.subtitle">{{ node.subtitle }}</small></span></span>
            <span role="cell">{{ typeLabel(node) }}</span>
            <span role="cell"><i class="status-dot" :data-state="node.status" />{{ statusLabel(node) }}</span>
            <span role="cell">{{ dateLabel(node.updatedAt) }}</span>
            <span role="cell"><ChevronRight :size="15" /></span>
          </button>
          <div v-if="!filteredChildren.length" class="file-empty">
            <FolderOpen :size="27" /><strong>{{ t('courseFiles.emptyFolder') }}</strong><span>{{ t('courseFiles.emptyFolderHelp') }}</span>
            <button type="button" @click="openCreateDialog(defaultCreateType)"><Plus :size="14" />{{ t('courseFiles.createHere') }}</button>
          </div>
        </div>
        <p v-if="status" class="runtime-note" role="status">{{ status }}</p>
      </section>

      <aside class="file-inspector">
        <template v-if="selectedNode">
          <header>
            <span class="inspector-icon" :data-type="selectedNode.type"><component :is="selectedNode.kind === 'folder' ? Folder : nodeIcon(selectedNode)" :size="22" /></span>
            <div><small>{{ typeLabel(selectedNode) }}</small><strong>{{ selectedNode.label }}</strong></div>
            <button type="button" :aria-label="t('common.close')" @click="selectedNode = null"><X :size="15" /></button>
          </header>
          <section class="inspector-status" :data-state="selectedNode.status">
            <span><i />{{ statusLabel(selectedNode) }}</span>
            <p>{{ statusHelp(selectedNode) }}</p>
          </section>
          <dl class="file-meta">
            <div><dt>{{ t('courseFiles.meta.location') }}</dt><dd>{{ selectedNode.path || t('courseFiles.rootName') }}</dd></div>
            <div v-if="selectedNode.lessonId"><dt>{{ t('courseFiles.meta.lesson') }}</dt><dd>{{ lessonLabel(selectedNode.lessonId) }}</dd></div>
            <div v-if="selectedNode.revision"><dt>{{ t('courseFiles.meta.version') }}</dt><dd>{{ selectedNode.revision }}</dd></div>
            <div v-if="selectedNode.asset"><dt>{{ t('courseFiles.meta.size') }}</dt><dd>{{ size(selectedNode.asset.size_bytes) }}</dd></div>
            <div><dt>{{ t('courseFiles.meta.updated') }}</dt><dd>{{ dateLabel(selectedNode.updatedAt) }}</dd></div>
          </dl>
          <section v-if="selectedNode.kind !== 'folder'" class="relationship-card">
            <small>{{ t('courseFiles.sourceRelationship') }}</small>
            <p>{{ relationship(selectedNode) }}</p>
          </section>
          <footer class="inspector-actions">
            <button class="primary" type="button" :disabled="busy || primaryDisabled(selectedNode)" @click="primaryAction(selectedNode)">
              <LoaderCircle v-if="busy" :size="15" class="spin" /><component :is="primaryIcon(selectedNode)" v-else :size="15" />{{ primaryLabel(selectedNode) }}
            </button>
            <button v-if="selectedNode.asset" type="button" @click="downloadAsset(selectedNode.asset)"><Download :size="14" />{{ t('courseFiles.download') }}</button>
            <button v-if="selectedNode.asset" class="danger" type="button" @click="deleteAsset(selectedNode.asset)"><Trash2 :size="14" />{{ t('courseFiles.delete') }}</button>
          </footer>
        </template>
        <div v-else class="inspector-empty"><MousePointer2 :size="25" /><strong>{{ t('courseFiles.selectFile') }}</strong><span>{{ t('courseFiles.selectFileHelp') }}</span></div>
      </aside>
    </section>

    <input ref="importInput" class="sr-only" type="file" @change="captureImportFile" />
    <el-dialog v-model="createOpen" :title="dialogTitle" width="min(560px, calc(100vw - 28px))" class="asset-create-dialog" destroy-on-close @closed="resetCreateForm">
      <div class="create-intro" :data-type="createType">
        <span><component :is="createIcon" :size="20" /></span>
        <div><strong>{{ dialogTitle }}</strong><p>{{ dialogHelp }}</p></div>
      </div>
      <form class="asset-form" @submit.prevent="submitCreate">
        <label v-if="needsLesson" class="form-field">
          <span>{{ t('courseFiles.form.lesson') }}</span>
          <select v-model="createForm.lessonId" required>
            <option value="" disabled>{{ t('courseFiles.form.selectLesson') }}</option>
            <option v-for="lesson in lessons" :key="lesson.lesson_unit_id" :value="lesson.lesson_unit_id">{{ lesson.number }}. {{ lesson.title }}</option>
          </select>
        </label>
        <label v-if="['material', 'folder'].includes(createType)" class="form-field">
          <span>{{ createType === 'folder' ? t('courseFiles.form.folderName') : t('courseFiles.form.fileName') }}</span>
          <input v-model.trim="createForm.title" required :placeholder="createType === 'folder' ? t('courseFiles.form.folderPlaceholder') : t('courseFiles.form.materialPlaceholder')" />
        </label>
        <div v-if="createType === 'lesson_plan'" class="form-grid">
          <label class="form-field"><span>{{ t('courseFiles.form.classHours') }}</span><select v-model="createForm.hours"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option></select></label>
          <label class="form-field"><span>{{ t('courseFiles.form.generationMode') }}</span><select v-model="createForm.mode"><option value="ai">{{ t('courseFiles.form.aiGenerate') }}</option><option value="import">{{ t('courseFiles.form.importFile') }}</option></select></label>
        </div>
        <div v-if="createType === 'ppt'" class="form-grid">
          <label class="form-field"><span>{{ t('courseFiles.form.slideCount') }}</span><input v-model.number="createForm.count" type="number" min="4" max="80" /></label>
          <label class="form-field"><span>{{ t('courseFiles.form.style') }}</span><select v-model="createForm.style"><option value="simple">{{ t('courseFiles.form.simpleTeaching') }}</option><option value="template">{{ t('courseFiles.form.followTemplate') }}</option></select></label>
        </div>
        <div v-if="createType === 'practice'" class="form-grid">
          <label class="form-field"><span>{{ t('courseFiles.form.exerciseCount') }}</span><input v-model.number="createForm.count" type="number" min="1" max="100" /></label>
          <label class="form-field"><span>{{ t('courseFiles.form.difficulty') }}</span><select v-model="createForm.difficulty"><option value="basic">{{ t('courseFiles.form.basic') }}</option><option value="mixed">{{ t('courseFiles.form.mixed') }}</option><option value="challenge">{{ t('courseFiles.form.challenge') }}</option></select></label>
        </div>
        <label v-if="!['folder', 'outline'].includes(createType)" class="form-field">
          <span>{{ t('courseFiles.form.requirements') }}</span>
          <textarea v-model.trim="createForm.requirements" rows="3" :placeholder="requirementsPlaceholder" />
        </label>
        <section v-if="createType !== 'folder'" class="source-picker">
          <div><span>{{ t('courseFiles.form.sourceFile') }}</span><small>{{ sourceHint }}</small></div>
          <button type="button" @click="importInput?.click()"><Upload :size="14" />{{ createForm.file?.name || t('courseFiles.form.chooseFile') }}</button>
        </section>
        <footer class="dialog-actions">
          <button type="button" @click="createOpen = false">{{ t('common.cancel') }}</button>
          <button class="primary" type="submit" :disabled="busy"><LoaderCircle v-if="busy" class="spin" :size="15" />{{ submitLabel }}</button>
        </footer>
      </form>
    </el-dialog>

    <el-dialog v-model="previewOpen" :title="previewAsset?.filename || t('courseFiles.preview')" :width="previewDialogWidth" top="4vh" destroy-on-close @closed="closePreview">
      <div class="preview-surface">
        <img v-if="previewKind === 'image'" :src="previewUrl" :alt="previewAsset?.filename" />
        <iframe v-else-if="previewKind === 'browser'" :src="previewUrl" :title="previewAsset?.filename" />
        <div v-else class="office-note"><FileText :size="28" /><strong>{{ t('courseFiles.officeSaved') }}</strong><span>{{ t('courseFiles.officeSavedHelp') }}</span><button type="button" @click="previewAsset && downloadAsset(previewAsset)">{{ t('courseFiles.downloadOriginal') }}</button></div>
      </div>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, BookOpen, ChevronDown, ChevronRight, ClipboardList, Download, Eye,
  FileText, Folder, FolderOpen, FolderPlus, Home, ListChecks, LoaderCircle, MousePointer2,
  Pencil, Plus, Presentation, RefreshCw, Search, Sparkles, Trash2, TriangleAlert, Upload, X,
} from 'lucide-vue-next'
import { activeLocale, t } from '../shared/i18n'
import { useCourseStore } from '../stores/course'
import { useTeacherLessonAuthoringStore, type TeacherLessonProjection } from '../stores/teacherLessonAuthoring'
import http from '../utils/http'

type Asset = { asset_id: string; filename: string; relative_path: string; extension: string; size_bytes: number; category: string; uploaded_at?: string; updated_at?: string }
type Package = { package_id: string; course_id?: string; course_name: string; academic_year: string; term: string; asset_count: number; assets: Asset[]; entries: Array<{ name: string; path?: string; kind: 'folder' }>; updated_at?: string }
type NodeKind = 'folder' | 'managed' | 'asset'
type NodeType = 'root' | 'reference' | 'outline' | 'lesson' | 'lesson_plan' | 'material' | 'ppt' | 'practice' | 'folder' | 'file'
type NodeStatus = 'ready' | 'draft' | 'missing' | 'working' | 'stale' | 'uploaded'
type WorkspaceNode = {
  id: string; label: string; kind: NodeKind; type: NodeType; path: string; status: NodeStatus; subtitle?: string;
  lessonId?: string; revision?: string; updatedAt?: string; asset?: Asset; children?: WorkspaceNode[]; parentId?: string
}
type CreateType = 'outline' | 'lesson_plan' | 'material' | 'ppt' | 'practice' | 'folder'

const props = withDefaults(defineProps<{ embedded?: boolean; courseId?: string; courseTitle?: string }>(), { embedded: false, courseId: '', courseTitle: '' })
const emit = defineEmits<{ (event: 'openOutline'): void; (event: 'openTeachingPlan', lessonId: string): void; (event: 'openTasks'): void }>()
const router = useRouter()
const courseStore = useCourseStore()
const lessonStore = useTeacherLessonAuthoringStore()
const embedded = computed(() => props.embedded)
const courseTitle = computed(() => props.courseTitle)
const selected = ref<Package | null>(null)
const initializing = ref(true)
const busy = ref(false)
const status = ref('')
const currentFolderId = ref('root')
const selectedNode = ref<WorkspaceNode | null>(null)
const query = ref('')
const createOpen = ref(false)
const createType = ref<CreateType>('material')
const importInput = ref<HTMLInputElement>()
const createForm = ref({ lessonId: '', title: '', hours: '2', mode: 'ai', count: 12, style: 'simple', difficulty: 'mixed', requirements: '', file: null as File | null })
const previewOpen = ref(false)
const previewAsset = ref<Asset | null>(null)
const previewUrl = ref('')

const lessons = computed<TeacherLessonProjection[]>(() => {
  if (lessonStore.lessons.length) return lessonStore.lessons
  return courseStore.nodes
    .filter(node => node.node_level === 1 || node.parent_node_id === 'root')
    .map((node, index) => ({
      lesson_unit_id: node.node_id,
      number: index + 1,
      title: node.node_name.replace(/^第\s*\d+\s*讲\s*/, ''),
      duration_minutes: Number((node as any).estimated_minutes || 45),
      sections: [],
      plan: {
        lesson_unit_id: node.node_id,
        working_revision_id: '',
        confirmed_revision_id: '',
        source_state: 'current',
        revisions: [],
        ppt_assets: [],
      },
    }))
})
const termLabel = (term: string) => ({ 春季: t('teacherCourseSpace.terms.spring', '春季'), 秋季: t('teacherCourseSpace.terms.autumn', '秋季'), 夏季: t('teacherCourseSpace.terms.summer', '夏季') }[term] || term)
const safePart = (value: string) => value.replace(/[\\/:*?"<>|]/g, '_').trim()
const lessonPath = (lesson: TeacherLessonProjection) => `课次/${String(lesson.number).padStart(2, '0')}_${safePart(lesson.title)}`
const localizedError = (error: any, fallback: string) => activeLocale.value === 'zh' && error?.response?.data?.detail ? String(error.response.data.detail) : fallback

function physicalChildren(basePath: string, parentId: string): WorkspaceNode[] {
  const result = new Map<string, WorkspaceNode>()
  const prefix = basePath ? `${basePath}/` : ''
  const knownPaths = [
    ...((selected.value?.entries || []).map(item => item.path || item.name)),
    ...((selected.value?.assets || []).map(item => item.relative_path)),
  ]
  for (const fullPath of knownPaths) {
    if (basePath && fullPath !== basePath && !fullPath.startsWith(prefix)) continue
    if (!basePath && !fullPath) continue
    const remaining = basePath ? fullPath.slice(prefix.length) : fullPath
    if (!remaining || remaining.startsWith('../')) continue
    const [first, ...rest] = remaining.split('/').filter(Boolean)
    if (!first) continue
    if (rest.length) {
      const path = basePath ? `${basePath}/${first}` : first
      if (!result.has(`folder:${path}`)) result.set(`folder:${path}`, { id: `folder:${path}`, label: first, kind: 'folder', type: 'folder', path, status: 'ready', parentId, children: [] })
    } else {
      const asset = selected.value?.assets.find(item => item.relative_path === fullPath)
      if (asset) result.set(`asset:${asset.asset_id}`, { id: `asset:${asset.asset_id}`, label: asset.filename, kind: 'asset', type: 'file', path: asset.relative_path, status: 'uploaded', updatedAt: asset.updated_at || asset.uploaded_at || selected.value?.updated_at, asset, parentId })
      else if (fullPath !== basePath) {
        const path = basePath ? `${basePath}/${first}` : first
        result.set(`folder:${path}`, { id: `folder:${path}`, label: first, kind: 'folder', type: 'folder', path, status: 'ready', parentId, children: [] })
      }
    }
  }
  return [...result.values()].map(node => node.kind === 'folder' ? { ...node, children: physicalChildren(node.path, node.id) } : node)
}

const managedPaths = computed(() => new Set([
  '参考资料',
  ...lessons.value.flatMap(lesson => [lessonPath(lesson), `${lessonPath(lesson)}/资料`]),
]))
const otherRootChildren = computed(() => physicalChildren('', 'folder:other').filter(node => ![...managedPaths.value].some(path => node.path === path || path.startsWith(`${node.path}/`) || node.path.startsWith(`${path}/`))))

const treeData = computed<WorkspaceNode[]>(() => {
  const outline: WorkspaceNode = {
    id: 'managed:outline', label: t('courseFiles.names.outline'), kind: 'managed', type: 'outline', path: t('courseFiles.names.outline'),
    status: courseStore.currentDocumentRevision ? 'ready' : courseStore.nodes.length ? 'draft' : 'missing', revision: courseStore.currentDocumentRevision || '',
  }
  const reference: WorkspaceNode = { id: 'folder:reference', label: t('courseFiles.names.reference'), kind: 'folder', type: 'reference', path: '参考资料', status: 'ready', parentId: 'root', children: physicalChildren('参考资料', 'folder:reference') }
  const lessonNodes: WorkspaceNode[] = lessons.value.map(lesson => {
    const working = lesson.plan.revisions.find(item => item.revision_id === lesson.plan.working_revision_id)
    const ppt = lesson.plan.ppt_assets.find(item => item.role === 'primary') || lesson.plan.ppt_assets[0]
    const activeJob = lessonStore.activeJobByLesson(lesson.lesson_unit_id)
    const base = lessonPath(lesson)
    return {
      id: `lesson:${lesson.lesson_unit_id}`, label: `${String(lesson.number).padStart(2, '0')}  ${lesson.title}`, kind: 'folder', type: 'lesson', path: base, status: 'ready', lessonId: lesson.lesson_unit_id, parentId: 'root',
      subtitle: t('courseFiles.lessonHours').replace('{hours}', String(Math.max(1, Math.round(lesson.duration_minutes / 45)))),
      children: [
        { id: `plan:${lesson.lesson_unit_id}`, label: t('courseFiles.names.lessonPlan'), kind: 'managed', type: 'lesson_plan', path: `${base}/教案`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: activeJob?.type?.includes('plan') ? 'working' : lesson.plan.source_state === 'stale' ? 'stale' : working ? (working.status === 'confirmed' ? 'ready' : 'draft') : 'missing', revision: working?.revision_id || '', updatedAt: working?.created_at },
        { id: `material:${lesson.lesson_unit_id}`, label: t('courseFiles.names.material'), kind: 'folder', type: 'material', path: `${base}/资料`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: physicalChildren(`${base}/资料`, `material:${lesson.lesson_unit_id}`).length ? 'ready' : 'missing', children: physicalChildren(`${base}/资料`, `material:${lesson.lesson_unit_id}`) },
        { id: `ppt:${lesson.lesson_unit_id}`, label: t('courseFiles.names.ppt'), kind: 'managed', type: 'ppt', path: `${base}/PPT`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: activeJob?.type?.includes('ppt') ? 'working' : ppt?.source_state === 'stale' ? 'stale' : ppt ? 'ready' : 'missing', revision: ppt?.working_revision_id || '', updatedAt: ppt?.revisions?.at(-1)?.created_at },
        { id: `practice:${lesson.lesson_unit_id}`, label: t('courseFiles.names.practice'), kind: 'managed', type: 'practice', path: `${base}/练习`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: 'missing' },
      ],
    }
  })
  const other: WorkspaceNode | null = otherRootChildren.value.length ? { id: 'folder:other', label: t('courseFiles.names.other'), kind: 'folder', type: 'folder', path: '', status: 'ready', parentId: 'root', children: otherRootChildren.value } : null
  return [{ id: 'root', label: t('courseFiles.rootName'), kind: 'folder', type: 'root', path: '', status: 'ready', children: [outline, reference, ...lessonNodes, ...(other ? [other] : [])] }]
})

const flatNodes = computed(() => {
  const map = new Map<string, WorkspaceNode>()
  const visit = (node: WorkspaceNode) => { map.set(node.id, node); node.children?.forEach(visit) }
  treeData.value.forEach(visit)
  return map
})
const currentFolder = computed(() => flatNodes.value.get(currentFolderId.value) || treeData.value[0])
const filteredChildren = computed(() => {
  const value = query.value.trim().toLocaleLowerCase()
  return (currentFolder.value?.children || []).filter(item => !value || item.label.toLocaleLowerCase().includes(value))
})
const breadcrumbs = computed(() => {
  const values: WorkspaceNode[] = []
  let node = currentFolder.value
  while (node?.parentId) { values.unshift(node); node = flatNodes.value.get(node.parentId) }
  return values
})
const expandedKeys = computed(() => ['root', currentFolderId.value, ...breadcrumbs.value.map(item => item.id)])
const defaultCreateType = computed<CreateType>(() => currentFolder.value?.type === 'material' || currentFolder.value?.type === 'reference' ? 'material' : currentFolder.value?.type === 'lesson' ? 'lesson_plan' : 'folder')

const typeLabel = (node: WorkspaceNode) => t(`courseFiles.types.${node.type === 'lesson_plan' ? 'lessonPlan' : node.type}`)
const statusLabel = (node: WorkspaceNode) => t(`courseFiles.status.${node.status}`)
const statusHelp = (node: WorkspaceNode) => t(`courseFiles.statusHelp.${node.status}`)
const nodeIcon = (node: WorkspaceNode) => markRaw(node.type === 'ppt' ? Presentation : node.type === 'practice' ? ListChecks : node.type === 'lesson_plan' ? ClipboardList : node.type === 'material' || node.type === 'reference' ? BookOpen : FileText)
const lessonLabel = (id: string) => lessons.value.find(item => item.lesson_unit_id === id)?.title || id
const dateLabel = (value?: string) => value ? new Intl.DateTimeFormat(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value)) : t('courseFiles.notUpdated')
const size = (value: number) => value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`

function relationship(node: WorkspaceNode) {
  if (node.type === 'outline') return t('courseFiles.relationship.outline')
  if (node.type === 'lesson_plan') return t('courseFiles.relationship.lessonPlan')
  if (node.type === 'material' || node.type === 'file') return t('courseFiles.relationship.material')
  if (node.type === 'ppt') return t('courseFiles.relationship.ppt')
  if (node.type === 'practice') return t('courseFiles.relationship.practice')
  return t('courseFiles.relationship.file')
}

function openFolder(id: string) { const node = flatNodes.value.get(id); if (node?.kind === 'folder') { currentFolderId.value = id; selectedNode.value = node; query.value = '' } }
function selectNode(node: WorkspaceNode) { selectedNode.value = node; if (node.kind === 'folder') openFolder(node.id) }
function handleTreeClick(node: WorkspaceNode) { node.kind === 'folder' ? openFolder(node.id) : selectedNode.value = node }

function primaryLabel(node: WorkspaceNode) {
  if (node.kind === 'folder') return t('courseFiles.openFolder')
  if (node.asset) return t('courseFiles.preview')
  if (node.type === 'outline' || node.type === 'lesson_plan') return node.status === 'missing' ? t('courseFiles.create') : t('courseFiles.openEdit')
  if (node.type === 'ppt') return node.status === 'missing' ? t('courseFiles.createPpt') : t('courseFiles.openPpt')
  if (node.type === 'practice') return node.status === 'missing' ? t('courseFiles.createPractice') : t('courseFiles.openPractice')
  return t('courseFiles.open')
}
function primaryIcon(node: WorkspaceNode) { return markRaw(node.kind === 'folder' ? FolderOpen : node.asset ? Eye : node.status === 'missing' ? Sparkles : Pencil) }
function primaryDisabled(node: WorkspaceNode) { return node.type === 'ppt' && node.status === 'missing' && !lessonPlanRevision(node.lessonId || '') }
function lessonPlanRevision(lessonId: string) { return lessons.value.find(item => item.lesson_unit_id === lessonId)?.plan.working_revision_id || '' }

async function primaryAction(node: WorkspaceNode) {
  selectedNode.value = node
  if (node.kind === 'folder') { openFolder(node.id); return }
  if (node.asset) { await previewFile(node.asset); return }
  if (node.type === 'outline') { node.status === 'missing' ? openCreateDialog('outline') : emit('openOutline'); return }
  if (node.type === 'lesson_plan') { node.status === 'missing' ? openCreateDialog('lesson_plan', node.lessonId) : emit('openTeachingPlan', node.lessonId || ''); return }
  if (node.type === 'ppt') { node.status === 'missing' ? openCreateDialog('ppt', node.lessonId) : router.push({ name: 'ppt-workspace', params: { courseId: props.courseId }, query: { lesson: node.lessonId } }); return }
  if (node.type === 'practice') { node.status === 'missing' ? openCreateDialog('practice', node.lessonId) : openPractice(node.lessonId || ''); return }
}

async function refresh() {
  initializing.value = true
  status.value = ''
  try {
    let packages = (await http.get<Package[]>('/api/teacher-course-spaces', { params: embedded.value && props.courseId ? { course_id: props.courseId } : undefined })).data
    let match = embedded.value ? packages.find(item => String(item.course_id || '') === props.courseId) : packages[0]
    if (embedded.value && !match && props.courseTitle) {
      const allPackages = (await http.get<Package[]>('/api/teacher-course-spaces')).data
      const legacyMatches = allPackages.filter((item: any) => !item.course_id && String(item.course_name).trim() === props.courseTitle.trim())
      if (legacyMatches.length === 1 && props.courseId) {
        match = (await http.patch(`/api/teacher-course-spaces/${legacyMatches[0]!.package_id}`, { course_id: props.courseId })).data
      }
    }
    if (embedded.value && !match && props.courseTitle) {
      const now = new Date()
      const startYear = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1
      match = (await http.post('/api/teacher-course-spaces', { course_name: props.courseTitle, academic_year: `${startYear}-${startYear + 1}`, term: now.getMonth() >= 7 ? '秋季' : '春季', template: 'blank', course_id: props.courseId })).data
    }
    if (match) selected.value = (await http.get(`/api/teacher-course-spaces/${match.package_id}`)).data
    if (props.courseId) await lessonStore.load(props.courseId).catch(() => undefined)
    selectedNode.value = flatNodes.value.get('managed:outline') || null
  } catch (error: any) {
    status.value = localizedError(error, t('courseFiles.spaceUnavailable'))
  } finally { initializing.value = false }
}
async function reloadAll() { busy.value = true; try { await Promise.all([refresh(), props.courseId ? courseStore.loadCourse(props.courseId, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true }) : Promise.resolve()]) } finally { busy.value = false } }
async function reloadPackage() { if (selected.value) selected.value = (await http.get(`/api/teacher-course-spaces/${selected.value.package_id}`)).data }

function openCreateDialog(command: CreateType | string, lessonId = '') {
  createType.value = command as CreateType
  createForm.value.lessonId = lessonId || currentFolder.value?.lessonId || ''
  createOpen.value = true
}
const dialogTitle = computed(() => t(`courseFiles.dialog.${createType.value}.title`))
const dialogHelp = computed(() => t(`courseFiles.dialog.${createType.value}.help`))
const createIcon = computed(() => markRaw(createType.value === 'ppt' ? Presentation : createType.value === 'practice' ? ListChecks : createType.value === 'lesson_plan' ? ClipboardList : createType.value === 'folder' ? FolderPlus : createType.value === 'material' ? BookOpen : FileText))
const needsLesson = computed(() => ['lesson_plan', 'ppt', 'practice'].includes(createType.value) || createType.value === 'material' && currentFolder.value?.type !== 'reference')
const requirementsPlaceholder = computed(() => t(`courseFiles.dialog.${createType.value}.requirements`))
const sourceHint = computed(() => t(`courseFiles.dialog.${createType.value}.sourceHint`))
const submitLabel = computed(() => createForm.value.file ? t('courseFiles.form.importAndCreate') : createType.value === 'folder' ? t('courseFiles.createFolder') : createType.value === 'material' ? t('courseFiles.createFile') : t('courseFiles.form.startCreate'))
function captureImportFile(event: Event) { const input = event.target as HTMLInputElement; createForm.value.file = input.files?.[0] || null; input.value = '' }
function resetCreateForm() { createForm.value = { lessonId: '', title: '', hours: '2', mode: 'ai', count: 12, style: 'simple', difficulty: 'mixed', requirements: '', file: null } }

function targetPath(type: CreateType, lessonId: string) {
  const lesson = lessons.value.find(item => item.lesson_unit_id === lessonId)
  if (type === 'material') return currentFolder.value?.type === 'reference' ? '参考资料' : lesson ? `${lessonPath(lesson)}/资料` : '参考资料'
  if (type === 'lesson_plan') return lesson ? `${lessonPath(lesson)}/教案` : '教案'
  if (type === 'ppt') return lesson ? `${lessonPath(lesson)}/PPT` : 'PPT'
  if (type === 'practice') return lesson ? `${lessonPath(lesson)}/练习` : '练习'
  return currentFolder.value?.path || ''
}
async function uploadFile(file: File, path: string) {
  if (!selected.value) return
  const data = new FormData(); data.append('files', file); data.append('relative_paths', path ? `${path}/${file.name}` : file.name)
  const result = (await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/imports`, data)).data
  selected.value = result.package
}
async function submitCreate() {
  if (!selected.value) return
  busy.value = true
  try {
    if (createType.value === 'folder') {
      const path = targetPath('folder', '')
      await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/folders`, { name: path ? `${path}/${createForm.value.title}` : createForm.value.title })
    } else if (createForm.value.file) {
      await uploadFile(createForm.value.file, targetPath(createType.value, createForm.value.lessonId))
    } else if (createType.value === 'outline') {
      emit('openOutline')
    } else if (createType.value === 'lesson_plan') {
      await lessonStore.generateLesson(props.courseId, createForm.value.lessonId)
    } else if (createType.value === 'ppt') {
      const revision = lessonPlanRevision(createForm.value.lessonId)
      if (!revision) throw new Error(t('courseFiles.errors.createLessonFirst'))
      await lessonStore.generatePpt(props.courseId, createForm.value.lessonId, revision)
    } else if (createType.value === 'practice') {
      openPractice(createForm.value.lessonId)
    } else if (createType.value === 'material') {
      const name = `${safePart(createForm.value.title || t('courseFiles.names.newMaterial'))}.md`
      await uploadFile(new File([`# ${createForm.value.title}\n\n${createForm.value.requirements}\n`], name, { type: 'text/markdown' }), targetPath('material', createForm.value.lessonId))
    }
    await reloadPackage()
    await lessonStore.load(props.courseId).catch(() => undefined)
    createOpen.value = false
    ElMessage.success(t('courseFiles.created'))
  } catch (error: any) { ElMessage.error(localizedError(error, String(error?.message || t('courseFiles.errors.createFailed')))) } finally { busy.value = false }
}
function openPractice(lessonId: string) { createOpen.value = false; router.push({ name: 'learning', params: { courseId: props.courseId, nodeId: lessonId }, query: { workspace: 'practice' } }) }

async function previewFile(asset: Asset) {
  if (!selected.value) return
  try {
    const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${asset.asset_id}/preview`, { responseType: 'blob' })
    previewUrl.value = URL.createObjectURL(response.data); previewAsset.value = asset; previewOpen.value = true
  } catch { ElMessage.error(t('courseFiles.errors.previewFailed')) }
}
const previewKind = computed(() => {
  const ext = previewAsset.value?.extension.toLowerCase() || ''
  if (['.png', '.jpg', '.jpeg', '.webp', '.bmp'].includes(ext)) return 'image'
  if (['.pdf', '.md', '.markdown', '.txt', '.csv', '.json', '.html'].includes(ext)) return 'browser'
  return 'office'
})
const previewDialogWidth = computed(() => `${Math.min(typeof window === 'undefined' ? 920 : window.innerWidth - 40, 1100)}px`)
function closePreview() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = ''; previewAsset.value = null }
async function downloadAsset(asset: Asset) { if (!selected.value) return; const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${asset.asset_id}/download`, { responseType: 'blob' }); downloadBlob(response.data, asset.filename) }
async function downloadPackage() { if (!selected.value) return; const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/export`, { responseType: 'blob' }); downloadBlob(response.data, `${selected.value.course_name}-${t('courseFiles.archiveName')}.zip`) }
function downloadBlob(blob: Blob, name: string) { const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 100) }
async function deleteAsset(asset: Asset) {
  if (!selected.value) return
  try {
    await ElMessageBox.confirm(t('courseFiles.deleteConfirm').replace('{name}', asset.filename), t('courseFiles.delete'), { type: 'warning', confirmButtonText: t('courseFiles.delete'), cancelButtonText: t('common.cancel') })
    await http.delete(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${asset.asset_id}`)
    selectedNode.value = null; await reloadPackage(); ElMessage.success(t('courseFiles.deleted'))
  } catch (error: any) { if (error !== 'cancel' && error !== 'close') ElMessage.error(t('courseFiles.errors.deleteFailed')) }
}

onMounted(refresh)
</script>

<style scoped>
.file-space,.file-space * { box-sizing:border-box; }
.file-space { height:100%; min-height:0; color:var(--lz-text-strong); background:#f8fafc; }
.standalone-header { height:64px; display:flex; align-items:center; justify-content:space-between; padding:0 24px; border-bottom:1px solid var(--lz-border); background:#fff; }
.standalone-header small,.standalone-header h1 { display:block; margin:0; }.standalone-header small { color:var(--lz-text-muted); }.standalone-header h1 { font-size:18px; }.standalone-header button { display:flex; gap:7px; border:0; background:transparent; }
.file-layout { height:100%; min-height:0; display:grid; grid-template-columns:224px minmax(440px,1fr) 302px; overflow:hidden; background:#fff; }
.file-tree-pane,.file-list-pane,.file-inspector { min-height:0; overflow:hidden; }
.file-tree-pane { display:grid; grid-template-rows:auto minmax(0,1fr) auto; border-right:1px solid var(--lz-border); background:#f8fafc; }
.pane-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:16px 14px 12px; }
.pane-heading div { min-width:0; display:grid; gap:2px; }.pane-heading small { color:var(--lz-text-muted); font-size:10px; text-transform:uppercase; }.pane-heading strong { overflow:hidden; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }.pane-heading button,.file-inspector header>button { border:0; background:transparent; color:var(--lz-text-muted); cursor:pointer; }
.workspace-tree { overflow:auto; padding:0 8px 12px; background:transparent; --el-tree-node-hover-bg-color:#eef2ff; }
.tree-node { min-width:0; display:flex; align-items:center; gap:7px; font-size:12px; }.tree-node span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.tree-node svg { flex:none; color:#64748b; }.tree-node.is-outline svg,.tree-node.is-lesson_plan svg,.tree-node.is-ppt svg { color:#5b5ce2; }.tree-node i { width:6px; height:6px; margin-left:auto; border-radius:50%; background:#f97316; }
.file-tree-pane footer { display:grid; gap:8px; padding:12px 14px; border-top:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:10px; }.file-tree-pane footer button { display:flex; align-items:center; gap:6px; padding:0; border:0; background:transparent; color:var(--lz-text-secondary); font-size:11px; font-weight:700; cursor:pointer; }
.file-list-pane { display:grid; grid-template-rows:54px 72px minmax(0,1fr) auto; background:#fff; }
.list-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 16px; border-bottom:1px solid var(--lz-border); }.list-toolbar nav { min-width:0; display:flex; align-items:center; gap:3px; overflow:hidden; }.list-toolbar nav button { display:flex; align-items:center; gap:5px; min-width:0; padding:4px; border:0; background:transparent; color:var(--lz-text-secondary); font-size:11px; white-space:nowrap; cursor:pointer; }.list-toolbar nav svg { flex:none; color:#94a3b8; }
.toolbar-actions { display:flex; align-items:center; gap:8px; }.list-search { width:180px; height:32px; display:flex; align-items:center; gap:6px; padding:0 9px; border:1px solid var(--lz-border); border-radius:8px; color:#94a3b8; }.list-search input { width:100%; border:0; outline:0; font-size:11px; }.new-button { height:34px; display:flex; align-items:center; gap:6px; padding:0 11px; border:1px solid #4f46e5; border-radius:8px; background:#4f46e5; color:#fff; font-size:11px; font-weight:700; cursor:pointer; }
.folder-title { display:flex; align-items:center; justify-content:space-between; padding:10px 18px 8px; }.folder-title small { color:var(--lz-text-muted); font-size:10px; }.folder-title h2 { margin:3px 0 0; font-size:18px; }.folder-title>span { color:var(--lz-text-muted); font-size:11px; }
.file-table { min-height:0; overflow:auto; padding:0 12px 20px; }.file-table__head,.file-row { display:grid; grid-template-columns:minmax(190px,1.6fr) 92px 96px 105px 24px; align-items:center; gap:8px; }.file-table__head { min-height:32px; padding:0 10px; border-bottom:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:10px; font-weight:700; }.file-row { width:100%; min-height:55px; padding:6px 10px; border:0; border-bottom:1px solid #f1f5f9; background:transparent; color:var(--lz-text-secondary); text-align:left; font-size:11px; cursor:pointer; }.file-row:hover,.file-row.selected { border-radius:8px; background:#f5f7ff; }.file-row.selected { box-shadow:inset 2px 0 #6366f1; }.file-name { min-width:0; display:flex; align-items:center; gap:10px; }.file-name>span:last-child { min-width:0; display:grid; gap:3px; }.file-name strong,.file-name small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.file-name strong { color:var(--lz-text-strong); font-size:12px; }.file-name small { color:var(--lz-text-muted); font-size:10px; }.file-icon { width:30px; height:30px; flex:none; display:grid; place-items:center; border-radius:8px; background:#f1f5f9; color:#64748b; }.file-icon[data-type="outline"],.file-icon[data-type="lesson_plan"],.file-icon[data-type="ppt"] { background:#eef2ff; color:#4f46e5; }.status-dot { width:6px; height:6px; display:inline-block; margin-right:5px; border-radius:50%; background:#94a3b8; }.status-dot[data-state="ready"],.status-dot[data-state="uploaded"] { background:#10b981; }.status-dot[data-state="working"] { background:#6366f1; }.status-dot[data-state="stale"] { background:#f97316; }.status-dot[data-state="missing"] { background:#cbd5e1; }
.file-empty { min-height:260px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:7px; color:var(--lz-text-muted); text-align:center; }.file-empty strong { color:var(--lz-text-secondary); font-size:13px; }.file-empty span { font-size:11px; }.file-empty button { display:flex; align-items:center; gap:5px; margin-top:6px; padding:7px 10px; border:1px solid var(--lz-border); border-radius:7px; background:#fff; color:#4f46e5; font-size:11px; }
.runtime-note { margin:0; padding:8px 16px; border-top:1px solid var(--lz-border); color:#9a3412; background:#fff7ed; font-size:11px; }
.file-inspector { display:flex; flex-direction:column; border-left:1px solid var(--lz-border); background:#fbfcfe; }.file-inspector>header { display:grid; grid-template-columns:38px minmax(0,1fr) auto; align-items:center; gap:9px; padding:16px 14px 13px; border-bottom:1px solid var(--lz-border); }.inspector-icon { width:38px; height:38px; display:grid; place-items:center; border-radius:10px; background:#eef2ff; color:#4f46e5; }.file-inspector header div { min-width:0; display:grid; gap:2px; }.file-inspector header small { color:var(--lz-text-muted); font-size:10px; }.file-inspector header strong { overflow:hidden; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }
.inspector-status { margin:13px 14px 0; padding:11px; border:1px solid #e2e8f0; border-radius:9px; background:#fff; }.inspector-status>span { display:flex; align-items:center; gap:6px; color:var(--lz-text-secondary); font-size:11px; font-weight:700; }.inspector-status i { width:7px; height:7px; border-radius:50%; background:#94a3b8; }.inspector-status[data-state="ready"] i,.inspector-status[data-state="uploaded"] i { background:#10b981; }.inspector-status[data-state="working"] i { background:#6366f1; }.inspector-status[data-state="stale"] i { background:#f97316; }.inspector-status p { margin:6px 0 0; color:var(--lz-text-muted); font-size:10px; line-height:1.5; }
.file-meta { display:grid; gap:0; margin:12px 14px 0; }.file-meta div { display:grid; grid-template-columns:66px minmax(0,1fr); gap:8px; padding:8px 0; border-bottom:1px solid #eef2f7; font-size:10px; }.file-meta dt { color:var(--lz-text-muted); }.file-meta dd { margin:0; overflow-wrap:anywhere; color:var(--lz-text-secondary); }
.relationship-card { margin:14px; padding:11px; border:1px solid #e0e7ff; border-radius:9px; background:#f5f7ff; }.relationship-card small { color:#6366f1; font-size:10px; font-weight:700; }.relationship-card p { margin:5px 0 0; color:#596579; font-size:10px; line-height:1.55; }
.inspector-actions { display:grid; gap:7px; margin-top:auto; padding:14px; border-top:1px solid var(--lz-border); }.inspector-actions button { min-height:34px; display:flex; align-items:center; justify-content:center; gap:6px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; color:var(--lz-text-secondary); font-size:11px; font-weight:700; cursor:pointer; }.inspector-actions button.primary { border-color:#4f46e5; background:#4f46e5; color:#fff; }.inspector-actions button.danger { color:#b91c1c; }.inspector-actions button:disabled { opacity:.45; cursor:not-allowed; }
.inspector-empty,.space-state { height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; color:var(--lz-text-muted); text-align:center; }.inspector-empty strong,.space-state strong { color:var(--lz-text-secondary); font-size:13px; }.inspector-empty span,.space-state span { max-width:220px; font-size:11px; line-height:1.5; }.space-state button { padding:7px 12px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; }
.create-intro { display:flex; align-items:flex-start; gap:11px; padding:12px; border:1px solid #e0e7ff; border-radius:10px; background:#f5f7ff; }.create-intro>span { width:38px; height:38px; display:grid; place-items:center; border-radius:9px; background:#fff; color:#4f46e5; }.create-intro div { display:grid; gap:4px; }.create-intro strong { font-size:13px; }.create-intro p { margin:0; color:var(--lz-text-secondary); font-size:11px; line-height:1.5; }
.asset-form { display:grid; gap:13px; padding-top:15px; }.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:11px; }.form-field { display:grid; gap:6px; }.form-field>span,.source-picker>div>span { color:var(--lz-text-secondary); font-size:10px; font-weight:700; }.form-field input,.form-field select,.form-field textarea { width:100%; min-height:38px; padding:8px 10px; border:1px solid var(--lz-border); border-radius:8px; outline:0; color:var(--lz-text-strong); background:#fff; font:inherit; font-size:11px; }.form-field textarea { resize:vertical; }.form-field input:focus,.form-field select:focus,.form-field textarea:focus { border-color:#6366f1; box-shadow:0 0 0 3px rgba(99,102,241,.1); }.source-picker { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:11px; border:1px dashed #cbd5e1; border-radius:9px; }.source-picker>div { display:grid; gap:3px; }.source-picker small { color:var(--lz-text-muted); font-size:9px; }.source-picker button { max-width:220px; display:flex; align-items:center; gap:6px; overflow:hidden; padding:7px 9px; border:1px solid var(--lz-border); border-radius:7px; background:#fff; color:#4f46e5; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.dialog-actions { display:flex; justify-content:flex-end; gap:8px; padding-top:4px; }.dialog-actions button { min-height:34px; padding:0 13px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; color:var(--lz-text-secondary); font-size:11px; font-weight:700; }.dialog-actions button.primary { border-color:#4f46e5; background:#4f46e5; color:#fff; }
.preview-surface { min-height:420px; display:grid; place-items:center; }.preview-surface img { max-width:100%; max-height:75vh; }.preview-surface iframe { width:100%; min-height:72vh; border:0; }.office-note { display:flex; flex-direction:column; align-items:center; gap:8px; color:var(--lz-text-muted); text-align:center; }.office-note strong { color:var(--lz-text-strong); }.office-note button { padding:7px 10px; border:1px solid var(--lz-border); border-radius:7px; background:#fff; }
.sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); }.spin { animation:spin 1s linear infinite; }@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:1080px) { .file-layout { grid-template-columns:200px minmax(380px,1fr) 260px; }.list-search { display:none; }.file-table__head,.file-row { grid-template-columns:minmax(180px,1.6fr) 78px 88px 24px; }.file-table__head span:nth-child(4),.file-row>span:nth-child(4) { display:none; } }
@media (max-width:760px) { .file-layout { grid-template-columns:1fr; grid-template-rows:46px minmax(0,1fr) auto; }.file-tree-pane { display:block; overflow:auto; border-right:0; border-bottom:1px solid var(--lz-border); }.pane-heading { height:46px; padding:0 12px; }.workspace-tree,.file-tree-pane footer { display:none; }.file-list-pane { grid-template-rows:46px 58px minmax(0,1fr) auto; }.file-inspector { max-height:42vh; border-left:0; border-top:1px solid var(--lz-border); }.file-inspector .file-meta,.relationship-card { display:none; }.inspector-actions { grid-template-columns:1fr auto auto; }.list-toolbar { padding:0 10px; }.list-toolbar nav button { max-width:100px; }.folder-title { padding:8px 12px; }.folder-title h2 { font-size:16px; }.file-table { padding:0 6px 12px; }.file-table__head,.file-row { grid-template-columns:minmax(170px,1fr) 78px 24px; }.file-table__head span:nth-child(3),.file-row>span:nth-child(3),.file-table__head span:nth-child(4),.file-row>span:nth-child(4) { display:none; }.form-grid { grid-template-columns:1fr; } }
</style>
