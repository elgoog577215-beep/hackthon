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
          <span><FolderTree :size="15" /><strong>{{ t('courseFiles.folderNavigation') }}</strong></span>
          <button type="button" :aria-label="t('common.refresh')" @click="reloadAll"><RefreshCw :size="15" :class="{ spin: busy }" /></button>
        </header>
        <nav class="folder-navigation" :aria-label="t('courseFiles.folderNavigation')">
          <ul role="tree">
            <WorkspaceFolderTreeNode
              v-for="folder in folderTreeData"
              :key="folder.id"
              :node="folder"
              :current-id="currentFolderId"
              :expanded-ids="expandedFolderIds"
              @select="openFolder"
              @toggle="toggleFolder"
            />
          </ul>
        </nav>
        <footer>
          <span>{{ selected.academic_year }} · {{ termLabel(selected.term) }}</span>
          <button type="button" @click="downloadPackage"><Download :size="14" />{{ t('courseFiles.exportCourse') }}</button>
        </footer>
      </aside>

      <section class="file-list-pane">
        <header class="list-toolbar">
          <nav v-if="breadcrumbs.length" :aria-label="t('courseFiles.filePath')">
            <button type="button" @click="openFolder('root')"><Home :size="14" />{{ t('courseFiles.rootName') }}</button>
            <template v-for="crumb in breadcrumbs" :key="crumb.id">
              <ChevronRight :size="13" /><button type="button" @click="openFolder(crumb.id)">{{ crumb.label }}</button>
            </template>
          </nav>
          <div class="toolbar-actions">
            <div class="list-search" role="search">
              <Search :size="15" />
              <input v-model="query" type="search" :placeholder="t('courseFiles.searchCurrent')" :aria-label="t('courseFiles.searchCurrent')" />
              <button v-if="query" type="button" :aria-label="t('courseFiles.clearSearch')" @click="query = ''"><X :size="14" /></button>
            </div>
          </div>
        </header>

        <div class="folder-title">
          <h2>{{ currentFolder?.label || t('courseFiles.rootName') }}</h2>
          <div class="folder-title__actions">
            <span>{{ t('courseFiles.itemCount').replace('{count}', String(filteredChildren.length)) }}</span>
            <button v-if="canAddTeacherFiles" class="add-material-button" type="button" @click="openCreateDialog('material', '', currentFolder?.id)"><Plus :size="14" />{{ t('courseFiles.addMaterial') }}</button>
            <button v-if="canAddTeacherFiles" class="add-folder-button" type="button" :title="t('courseFiles.newFolder')" :aria-label="t('courseFiles.newFolder')" @click="openCreateDialog('folder', '', currentFolder?.id)"><FolderPlus :size="15" /></button>
          </div>
        </div>

        <div class="file-table" role="table" :aria-label="t('courseFiles.fileList')">
          <div class="file-table__head" role="row">
            <span v-for="column in sortColumns" :key="column.key" role="columnheader" :aria-sort="sortAria(column.key)">
              <button type="button" class="sort-button" :class="{ active: sortKey === column.key }" :aria-label="t('courseFiles.sortBy').replace('{name}', column.label)" @click="toggleSort(column.key)">
                {{ column.label }}
                <component :is="sortIcon(column.key)" :size="14" />
              </button>
            </span>
          </div>
          <button
            v-for="node in filteredChildren"
            :key="node.id"
            type="button"
            class="file-row"
            :class="{ selected: selectedNode?.id === node.id }"
            :data-role="assetRole(node)"
            role="row"
            @click="handleNodeClick(node)"
            @dblclick="node.kind !== 'folder' && primaryAction(node)"
          >
            <span class="file-name" role="cell"><span class="file-icon" :data-type="node.type"><component :is="node.kind === 'folder' ? Folder : nodeIcon(node)" :size="18" /></span><strong>{{ node.label }}</strong></span>
            <span role="cell">{{ displayUpdated(node) }}</span>
            <span role="cell">{{ typeLabel(node) }}</span>
            <span role="cell">{{ displaySize(node) }}</span>
            <span role="cell"><i class="status-dot" :data-state="node.status" />{{ statusLabel(node) }}</span>
          </button>
          <div v-if="!filteredChildren.length" class="file-empty">
            <template v-if="query.trim()">
              <SearchX :size="27" /><strong>{{ t('courseFiles.noSearchResults') }}</strong>
              <button type="button" @click="query = ''"><X :size="14" />{{ t('courseFiles.clearSearch') }}</button>
            </template>
            <template v-else>
              <FolderOpen :size="27" /><strong>{{ emptyFolderTitle }}</strong>
            </template>
          </div>
        </div>
        <p v-if="status" class="runtime-note" role="status">{{ status }}</p>
      </section>

      <aside class="file-inspector">
        <template v-if="inspectedNode">
          <header>
            <span class="inspector-icon" :data-type="inspectedNode.type"><component :is="inspectedNode.kind === 'folder' ? FolderOpen : nodeIcon(inspectedNode)" :size="22" /></span>
            <div><small v-if="typeLabel(inspectedNode) !== inspectedNode.label">{{ typeLabel(inspectedNode) }}</small><strong>{{ inspectedNode.label }}</strong></div>
            <button v-if="selectedNode" type="button" :aria-label="t('common.close')" @click="selectedNode = null"><X :size="15" /></button>
          </header>
          <section class="inspector-status" :data-state="inspectedNode.status">
            <span><i />{{ statusLabel(inspectedNode) }}</span>
          </section>
          <section class="inspector-overview">
            <h3>{{ inspectedNode.kind === 'folder' ? t('courseFiles.inspector.folderInfo') : t('courseFiles.inspector.fileInfo') }}</h3>
            <dl>
              <div v-if="inspectedNode.kind === 'folder'"><dt>{{ t('courseFiles.meta.items') }}</dt><dd>{{ folderSummary(inspectedNode) }}</dd></div>
              <div v-if="inspectedNode.lessonId"><dt>{{ t('courseFiles.meta.lesson') }}</dt><dd>{{ lessonLabel(inspectedNode.lessonId) }}</dd></div>
              <div v-if="inspectedNode.kind !== 'folder'"><dt>{{ t('courseFiles.inspector.source') }}</dt><dd>{{ inspectorSource(inspectedNode) }}</dd></div>
              <div v-if="inspectedNode.kind !== 'folder'"><dt>{{ t('courseFiles.inspector.usedFor') }}</dt><dd>{{ inspectorUse(inspectedNode) }}</dd></div>
              <div v-if="inspectedNode.revision"><dt>{{ t('courseFiles.meta.version') }}</dt><dd :title="inspectedNode.revision">{{ shortRevision(inspectedNode.revision) }}</dd></div>
              <div v-if="inspectedNode.kind === 'folder'"><dt>{{ t('courseFiles.meta.location') }}</dt><dd>{{ displayPath(inspectedNode.path) }}</dd></div>
            </dl>
          </section>
          <footer v-if="selectedNode" class="inspector-actions">
            <button class="primary" type="button" :disabled="busy || primaryDisabled(selectedNode)" @click="primaryAction(selectedNode)">
              <LoaderCircle v-if="busy" :size="15" class="spin" /><component :is="primaryIcon(selectedNode)" v-else :size="15" />{{ primaryLabel(selectedNode) }}
            </button>
            <button v-if="selectedNode.asset" type="button" @click="downloadAsset(selectedNode.asset)"><Download :size="14" />{{ t('courseFiles.download') }}</button>
            <button v-else-if="canExportManaged(selectedNode)" type="button" :disabled="exportingNodeId === selectedNode.id" @click="exportManagedNode(selectedNode)"><LoaderCircle v-if="exportingNodeId === selectedNode.id" :size="14" class="spin" /><Download v-else :size="14" />{{ t('courseFiles.exportFile') }}</button>
            <button v-if="selectedNode.asset" class="danger" type="button" @click="deleteAsset(selectedNode.asset)"><Trash2 :size="14" />{{ t('courseFiles.delete') }}</button>
          </footer>
        </template>
      </aside>
    </section>

    <input ref="importInput" class="sr-only" type="file" @change="captureImportFile" />
    <Teleport to="body">
      <div v-if="createOpen" class="asset-create-overlay" role="presentation" @click.self="closeCreateDialog" @keydown.esc="closeCreateDialog">
        <section ref="createDialog" class="asset-create-dialog" role="dialog" aria-modal="true" :aria-labelledby="'asset-create-title'" tabindex="-1">
          <header class="asset-create-header"><strong id="asset-create-title">{{ dialogTitle }}</strong><button type="button" :aria-label="t('common.close')" @click="closeCreateDialog"><X :size="17" /></button></header>
          <div class="create-location"><FolderOpen :size="15" /><span>{{ t('courseFiles.form.saveTo') }}</span><strong>{{ createLocationLabel }}</strong></div>
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
        <section v-if="createType === 'ppt'" class="ppt-origin-picker">
          <span>{{ t('courseFiles.form.pptOrigin') }}</span>
          <div>
            <button type="button" :class="{ active: createForm.mode === 'ai' }" @click="createForm.mode = 'ai'; createForm.file = null">
              <Sparkles :size="15" /><strong>{{ t('courseFiles.form.pptGenerated') }}</strong>
            </button>
            <button type="button" :class="{ active: createForm.mode === 'import' }" @click="createForm.mode = 'import'; createForm.file = null">
              <Upload :size="15" /><strong>{{ t('courseFiles.form.pptUploaded') }}</strong>
            </button>
          </div>
        </section>
        <div v-if="createType === 'ppt' && createForm.mode === 'ai'" class="form-grid">
          <label class="form-field"><span>{{ t('courseFiles.form.slideCount') }}</span><input v-model.number="createForm.count" type="number" min="4" max="80" /></label>
          <label class="form-field"><span>{{ t('courseFiles.form.style') }}</span><select v-model="createForm.style"><option value="simple">{{ t('courseFiles.form.simpleTeaching') }}</option><option value="template">{{ t('courseFiles.form.followTemplate') }}</option></select></label>
        </div>
        <label v-if="createType === 'ppt' && createForm.mode === 'import'" class="form-field">
          <span>{{ t('courseFiles.form.afterUpload') }}</span>
          <select v-model="createForm.pptImportAction">
            <option value="derive_plan">{{ t('courseFiles.form.derivePlanFromPpt') }}</option>
            <option value="store">{{ t('courseFiles.form.storePptOnly') }}</option>
          </select>
        </label>
        <section v-if="createType === 'practice'" class="practice-create-note">
          <ListChecks :size="16" />
          <strong>{{ t('courseFiles.form.practiceScopeTitle') }}</strong>
        </section>
        <section v-if="pptAiBlocked" class="create-prerequisite" role="status">
          <TriangleAlert :size="16" />
          <strong>{{ t('courseFiles.form.pptNeedsPlanTitle') }}</strong>
          <button type="button" @click="createLessonPlanFirst">{{ t('courseFiles.form.createPlanFirst') }}</button>
        </section>
        <label v-if="!['folder', 'outline', 'practice'].includes(createType)" class="form-field">
          <span>{{ t('courseFiles.form.requirements') }}</span>
          <textarea v-model.trim="createForm.requirements" rows="3" :placeholder="requirementsPlaceholder" />
        </label>
        <section v-if="!['folder', 'practice'].includes(createType) && (createType !== 'ppt' || createForm.mode === 'import' || createForm.style === 'template')" class="source-picker">
          <span>{{ sourceFileLabel }}</span>
          <button type="button" @click="importInput?.click()"><Upload :size="14" />{{ createForm.file?.name || t('courseFiles.form.chooseFile') }}</button>
        </section>
            <footer class="dialog-actions">
              <button type="button" @click="closeCreateDialog">{{ t('common.cancel') }}</button>
              <button class="primary" type="submit" :disabled="submitDisabled"><LoaderCircle v-if="busy" class="spin" :size="15" />{{ submitLabel }}</button>
            </footer>
          </form>
        </section>
      </div>
    </Teleport>

    <el-dialog v-model="previewOpen" :title="previewAsset?.filename || t('courseFiles.preview')" :width="previewDialogWidth" top="4vh" destroy-on-close @closed="closePreview">
      <div class="preview-surface">
        <img v-if="previewKind === 'image'" :src="previewUrl" :alt="previewAsset?.filename" />
        <iframe v-else-if="previewKind === 'browser'" :src="previewUrl" :title="previewAsset?.filename" />
        <div v-else class="office-note"><FileText :size="28" /><strong>{{ t('courseFiles.officeSaved') }}</strong><button type="button" @click="previewAsset && downloadAsset(previewAsset)">{{ t('courseFiles.downloadOriginal') }}</button></div>
      </div>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDown, ArrowLeft, ArrowUp, ArrowUpDown, BookOpen, BookOpenText, ChevronRight, ClipboardList, Download, Eye,
  FileText, Folder, FolderOpen, FolderPlus, FolderTree, Home, ListChecks, LoaderCircle,
  Pencil, Plus, Presentation, RefreshCw, Search, SearchX, Sparkles, Trash2, TriangleAlert, Upload, X,
} from 'lucide-vue-next'
import { activeLocale, t } from '../shared/i18n'
import { useCourseStore, type Node } from '../stores/course'
import { useTeacherLessonAuthoringStore, type TeacherLessonProjection } from '../stores/teacherLessonAuthoring'
import http from '../utils/http'
import { runQuestionBankRebuild } from '../utils/question-bank-rebuild'
import WorkspaceFolderTreeNode from '../components/WorkspaceFolderTreeNode.vue'

type Asset = { asset_id: string; filename: string; relative_path: string; extension: string; size_bytes: number; category: string; uploaded_at?: string; updated_at?: string }
type Package = { package_id: string; course_id?: string; course_name: string; academic_year: string; term: string; asset_count: number; assets: Asset[]; entries: Array<{ name: string; path?: string; kind: 'folder' }>; updated_at?: string }
type NodeKind = 'folder' | 'managed' | 'asset'
type NodeType = 'root' | 'reference' | 'outline' | 'lesson' | 'lesson_plan' | 'content' | 'material' | 'ppt' | 'practice' | 'folder' | 'file'
type NodeStatus = 'ready' | 'draft' | 'missing' | 'working' | 'stale' | 'uploaded' | 'empty'
type WorkspaceNode = {
  id: string; label: string; kind: NodeKind; type: NodeType; path: string; status: NodeStatus;
  lessonId?: string; revision?: string; updatedAt?: string; sizeBytes?: number; asset?: Asset; children?: WorkspaceNode[]; parentId?: string; origin?: 'generated' | 'uploaded'
}
type WorkspaceFolderTreeItem = { id: string; label: string; attention?: boolean; children?: WorkspaceFolderTreeItem[] }
type CreateType = 'outline' | 'lesson_plan' | 'material' | 'ppt' | 'practice' | 'folder'
type SortKey = 'name' | 'updated' | 'type' | 'size' | 'status'
type SortDirection = 'ascending' | 'descending'

const props = withDefaults(defineProps<{ embedded?: boolean; courseId?: string; courseTitle?: string }>(), { embedded: false, courseId: '', courseTitle: '' })
const emit = defineEmits<{
  (event: 'openOutline'): void
  (event: 'createOutline'): void
  (event: 'openTeachingPlan', lessonId: string): void
  (event: 'openTasks'): void
  (event: 'openPractice', lessonId: string): void
  (event: 'contextChange', context: { lessonId: string; nodeId: string; label: string; type: NodeType; path: string }): void
  (event: 'readinessChange', summary: { required: number; ready: number; pending: number }): void
}>()
const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const lessonStore = useTeacherLessonAuthoringStore()
const embedded = computed(() => props.embedded)
const courseTitle = computed(() => props.courseTitle)
const selected = ref<Package | null>(null)
const initializing = ref(true)
const busy = ref(false)
const exportingNodeId = ref('')
const status = ref('')
const currentFolderId = ref('root')
const expandedFolderIds = ref<string[]>(['root'])
const selectedNode = ref<WorkspaceNode | null>(null)
const query = ref('')
const sortKey = ref<SortKey>('name')
const sortDirection = ref<SortDirection>('ascending')
const createOpen = ref(false)
const createType = ref<CreateType>('material')
const createTargetFolderId = ref('')
const importInput = ref<HTMLInputElement>()
const createDialog = ref<HTMLElement>()
const createForm = ref({ lessonId: '', title: '', hours: '2', mode: 'ai', count: 12, style: 'simple', difficulty: 'mixed', requirements: '', pptImportAction: 'derive_plan', file: null as File | null })
const previewOpen = ref(false)
const previewAsset = ref<Asset | null>(null)
const previewUrl = ref('')
const questionBankItems = ref<Array<{ node_id?: string; lifecycle_status?: string }>>([])
const practiceWorkingLessonIds = ref<string[]>([])

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
const textSize = (value: string) => new TextEncoder().encode(value).byteLength || undefined
const displayPath = (value: string) => {
  if (!value) return t('courseFiles.rootName')
  const labels = activeLocale.value === 'en'
    ? { 课次: 'Sessions', 教案: 'Lesson plan', 正文: 'Lesson body', 资料: 'Materials', 练习: 'Practice', 参考资料: 'References' }
    : { 课次: '课次', 教案: '教案', 正文: '正文', 资料: '资料', 练习: '练习', 参考资料: '参考资料' }
  return value.split('/').filter(Boolean).map(part => (labels as Record<string, string>)[part] || part.replace(/^(\d+)_/, '$1 ')).join(' / ')
}

function lessonContentNodes(lesson: TeacherLessonProjection): Node[] {
  const includedIds = new Set([
    lesson.lesson_unit_id,
    ...lesson.sections.map(section => section.section_node_id),
  ])
  const matchingTitle = courseStore.nodes.find(node => (
    node.node_level === 1
    && node.node_name.replace(/^第\s*\d+\s*[讲章节]\s*/, '').trim() === lesson.title.replace(/^第\s*\d+\s*[讲章节]\s*/, '').trim()
  ))
  if (matchingTitle) includedIds.add(matchingTitle.node_id)
  let expanded = true
  while (expanded) {
    expanded = false
    courseStore.nodes.forEach(node => {
      if (!includedIds.has(node.node_id) && includedIds.has(node.parent_node_id)) {
        includedIds.add(node.node_id)
        expanded = true
      }
    })
  }
  return courseStore.nodes.filter(node => includedIds.has(node.node_id))
}

const hasUsableContent = (node: Node) => Boolean(
  node.node_content?.trim()
  || node.content_blocks?.some(block => block.content?.trim())
  || node.course_blocks?.length,
)

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
function uploadedPptAssets(base: string) {
  const prefix = `${base}/PPT/`
  return (selected.value?.assets || []).filter(asset => asset.relative_path.startsWith(prefix) && ['ppt', 'pptx'].includes(asset.extension.toLowerCase().replace(/^\./, '')))
}
function practiceNodeIds(lesson: TeacherLessonProjection) {
  return lessonContentNodes(lesson)
    .filter(node => Number(node.node_level || 0) === 2)
    .map(node => node.node_id)
}
function practiceStatus(lesson: TeacherLessonProjection): NodeStatus {
  if (practiceWorkingLessonIds.value.includes(lesson.lesson_unit_id)) return 'working'
  const nodeIds = new Set(practiceNodeIds(lesson))
  return questionBankItems.value.some(item => item.lifecycle_status !== 'retired' && item.node_id && nodeIds.has(item.node_id))
    ? 'ready'
    : 'missing'
}
const otherRootChildren = computed(() => physicalChildren('', 'folder:other').filter(node => ![...managedPaths.value].some(path => node.path === path || path.startsWith(`${node.path}/`) || node.path.startsWith(`${path}/`))))

const treeData = computed<WorkspaceNode[]>(() => {
  const outline: WorkspaceNode = {
    id: 'managed:outline', label: t('courseFiles.names.outline'), kind: 'managed', type: 'outline', path: t('courseFiles.names.outline'),
    status: courseStore.currentDocumentRevision ? 'ready' : courseStore.nodes.length ? 'draft' : 'missing', revision: courseStore.currentDocumentRevision || '', parentId: 'root',
    sizeBytes: courseStore.nodes.length ? textSize(outlineMarkdown()) : undefined,
  }
  const referenceChildren = physicalChildren('参考资料', 'folder:reference')
  const reference: WorkspaceNode = { id: 'folder:reference', label: t('courseFiles.names.reference'), kind: 'folder', type: 'reference', path: '参考资料', status: referenceChildren.length ? 'ready' : 'empty', parentId: 'root', children: referenceChildren }
  const lessonNodes: WorkspaceNode[] = lessons.value.map(lesson => {
    const working = lesson.plan.revisions.find(item => item.revision_id === lesson.plan.working_revision_id)
    const ppt = lesson.plan.ppt_assets.find(item => item.role === 'primary') || lesson.plan.ppt_assets[0]
    const activeJob = lessonStore.activeJobByLesson(lesson.lesson_unit_id)
    const base = lessonPath(lesson)
    const uploadedPpts = uploadedPptAssets(base)
    const contentNodes = lessonContentNodes(lesson)
    const contentReady = contentNodes.some(hasUsableContent)
    const materialChildren = physicalChildren(`${base}/资料`, `material:${lesson.lesson_unit_id}`)
    const children: WorkspaceNode[] = [
        { id: `plan:${lesson.lesson_unit_id}`, label: t('courseFiles.names.lessonPlan'), kind: 'managed', type: 'lesson_plan', path: `${base}/教案`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: activeJob?.type?.includes('plan') ? 'working' : lesson.plan.source_state === 'stale' ? 'stale' : working ? (working.status === 'confirmed' ? 'ready' : 'draft') : 'missing', revision: working?.revision_id || '', updatedAt: working?.created_at, sizeBytes: working ? textSize(lessonPlanMarkdown(lesson)) : undefined },
        { id: `content:${lesson.lesson_unit_id}`, label: t('courseFiles.names.content'), kind: 'managed', type: 'content', path: `${base}/正文`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: contentReady ? 'ready' : contentNodes.length ? 'draft' : 'missing', revision: courseStore.currentDocumentRevision, sizeBytes: contentReady ? textSize(lessonContentMarkdown(lesson)) : undefined },
        { id: `practice:${lesson.lesson_unit_id}`, label: t('courseFiles.names.practice'), kind: 'managed', type: 'practice', path: `${base}/练习`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: practiceStatus(lesson) },
        { id: `ppt:${lesson.lesson_unit_id}`, label: t('courseFiles.names.ppt'), kind: 'managed', type: 'ppt', path: `${base}/PPT`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: activeJob?.type?.includes('ppt') ? 'working' : ppt?.source_state === 'stale' ? 'stale' : ppt ? 'ready' : 'missing', revision: ppt?.working_revision_id || '', updatedAt: ppt?.revisions?.at(-1)?.created_at, origin: (ppt || activeJob?.type?.includes('ppt') ? 'generated' : undefined) as 'generated' | undefined },
        ...uploadedPpts.map(asset => ({ id: `ppt-upload:${asset.asset_id}`, label: asset.filename, kind: 'asset' as const, type: 'ppt' as const, path: asset.relative_path, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: 'uploaded' as const, updatedAt: asset.updated_at || asset.uploaded_at, asset, origin: 'uploaded' as const })),
        { id: `material:${lesson.lesson_unit_id}`, label: t('courseFiles.names.material'), kind: 'folder', type: 'material', path: `${base}/资料`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: materialChildren.length ? 'ready' : 'empty', children: materialChildren },
      ]
    const requiredStates = children.filter(item => ['lesson_plan', 'content', 'practice'].includes(item.type)).map(item => item.status)
    const lessonStatus: NodeStatus = requiredStates.includes('working') ? 'working'
      : requiredStates.includes('stale') ? 'stale'
        : requiredStates.every(state => state === 'ready') ? 'ready'
          : requiredStates.some(state => state === 'ready' || state === 'draft') ? 'draft' : 'missing'
    return {
      id: `lesson:${lesson.lesson_unit_id}`, label: `${String(lesson.number).padStart(2, '0')}  ${lesson.title}`, kind: 'folder', type: 'lesson', path: base, status: lessonStatus, lessonId: lesson.lesson_unit_id, parentId: 'root',
      children,
    }
  })
  const other: WorkspaceNode | null = otherRootChildren.value.length ? { id: 'folder:other', label: t('courseFiles.names.other'), kind: 'folder', type: 'folder', path: '', status: 'ready', parentId: 'root', children: otherRootChildren.value } : null
  const courseRoot: WorkspaceNode = {
    id: 'root', label: t('courseFiles.rootName'), kind: 'folder', type: 'root', path: '', status: outline.status === 'ready' && lessonNodes.every(item => item.status === 'ready') ? 'ready' : 'draft',
    children: [outline, reference, ...lessonNodes, ...(other ? [other] : [])],
  }
  return [courseRoot]
})

function toFolderTreeItem(node: WorkspaceNode): WorkspaceFolderTreeItem | null {
  if (node.kind !== 'folder') return null
  const children = (node.children || []).map(toFolderTreeItem).filter((item): item is WorkspaceFolderTreeItem => Boolean(item))
  const attention = (node.children || []).some(item => item.status === 'stale' || item.status === 'working' || item.kind === 'folder' && toFolderTreeItem(item)?.attention)
  return { id: node.id, label: node.label, attention, children }
}
const folderTreeData = computed(() => treeData.value.map(toFolderTreeItem).filter((item): item is WorkspaceFolderTreeItem => Boolean(item)))

const flatNodes = computed(() => {
  const map = new Map<string, WorkspaceNode>()
  const visit = (node: WorkspaceNode) => { map.set(node.id, node); node.children?.forEach(visit) }
  treeData.value.forEach(visit)
  return map
})
const currentFolder = computed(() => flatNodes.value.get(currentFolderId.value) || treeData.value[0])
const inspectedNode = computed(() => selectedNode.value || currentFolder.value || null)
const sortColumns = computed<Array<{ key: SortKey; label: string }>>(() => [
  { key: 'name', label: t('courseFiles.columns.name') },
  { key: 'updated', label: t('courseFiles.columns.updated') },
  { key: 'type', label: t('courseFiles.columns.type') },
  { key: 'size', label: t('courseFiles.columns.size') },
  { key: 'status', label: t('courseFiles.columns.status') },
])
const collator = computed(() => new Intl.Collator(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { numeric: true, sensitivity: 'base' }))
const filteredChildren = computed(() => {
  const value = query.value.trim().toLocaleLowerCase()
  return (currentFolder.value?.children || [])
    .filter(item => !value || item.label.toLocaleLowerCase().includes(value))
    .slice()
    .sort(compareNodes)
})
const readinessSummary = computed(() => {
  const required = [...flatNodes.value.values()].filter(node => node.kind === 'managed' && ['outline', 'lesson_plan', 'content', 'practice'].includes(node.type))
  const ready = required.filter(node => node.status === 'ready').length
  return { required: required.length, ready, pending: required.length - ready }
})
const breadcrumbs = computed(() => {
  const values: WorkspaceNode[] = []
  let node = currentFolder.value
  while (node?.parentId) { values.unshift(node); node = flatNodes.value.get(node.parentId) }
  return values
})
const createTargetFolder = computed(() => flatNodes.value.get(createTargetFolderId.value) || currentFolder.value)
const canAddTeacherFiles = computed(() => Boolean(currentFolder.value && ['reference', 'material', 'folder'].includes(currentFolder.value.type)))
const emptyFolderTitle = computed(() => currentFolder.value?.type === 'material' || currentFolder.value?.type === 'reference' ? t('courseFiles.emptyMaterials') : t('courseFiles.emptyFolder'))

const typeLabel = (node: WorkspaceNode) => t(`courseFiles.types.${node.type === 'lesson_plan' ? 'lessonPlan' : node.type}`)
function assetRole(node: WorkspaceNode) {
  if (node.kind === 'managed' && ['outline', 'lesson_plan', 'content', 'practice'].includes(node.type)) return 'required'
  if (node.type === 'ppt') return 'companion'
  if (node.type === 'reference' || node.type === 'material' || node.type === 'folder' || node.kind === 'asset' || node.type === 'file') return 'teacher'
  return 'navigation'
}
const statusLabel = (node: WorkspaceNode) => t(`courseFiles.status.${node.status}`)
const nodeIcon = (node: WorkspaceNode) => markRaw(node.type === 'ppt' ? Presentation : node.type === 'practice' ? ListChecks : node.type === 'lesson_plan' ? ClipboardList : node.type === 'content' ? BookOpenText : node.type === 'material' || node.type === 'reference' ? BookOpen : FileText)
const lessonLabel = (id: string) => lessons.value.find(item => item.lesson_unit_id === id)?.title || id
const dateLabel = (value?: string) => value ? new Intl.DateTimeFormat(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value)) : t('courseFiles.notUpdated')
const size = (value: number) => value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`
const displayUpdated = (node: WorkspaceNode) => dateLabel(node.updatedAt)
const displaySize = (node: WorkspaceNode) => node.asset ? size(node.asset.size_bytes) : node.sizeBytes ? size(node.sizeBytes) : t('courseFiles.unknownSize')

function compareNodes(left: WorkspaceNode, right: WorkspaceNode) {
  if (left.kind === 'folder' && right.kind !== 'folder') return -1
  if (left.kind !== 'folder' && right.kind === 'folder') return 1

  const direction = sortDirection.value === 'ascending' ? 1 : -1
  let result = 0
  if (sortKey.value === 'updated') {
    if (!left.updatedAt && right.updatedAt) return 1
    if (left.updatedAt && !right.updatedAt) return -1
    result = (left.updatedAt ? Date.parse(left.updatedAt) : 0) - (right.updatedAt ? Date.parse(right.updatedAt) : 0)
  } else if (sortKey.value === 'type') {
    result = collator.value.compare(typeLabel(left), typeLabel(right))
  } else if (sortKey.value === 'size') {
    const leftSize = left.asset?.size_bytes ?? left.sizeBytes
    const rightSize = right.asset?.size_bytes ?? right.sizeBytes
    if (leftSize === undefined && rightSize !== undefined) return 1
    if (leftSize !== undefined && rightSize === undefined) return -1
    result = (leftSize || 0) - (rightSize || 0)
  } else if (sortKey.value === 'status') {
    result = collator.value.compare(statusLabel(left), statusLabel(right))
  } else {
    result = collator.value.compare(left.label, right.label)
  }
  return result === 0 ? collator.value.compare(left.label, right.label) : result * direction
}

function toggleSort(key: SortKey) {
  if (sortKey.value === key) sortDirection.value = sortDirection.value === 'ascending' ? 'descending' : 'ascending'
  else {
    sortKey.value = key
    sortDirection.value = 'ascending'
  }
}

function sortAria(key: SortKey) {
  return sortKey.value === key ? sortDirection.value : 'none'
}

function sortIcon(key: SortKey) {
  if (sortKey.value !== key) return markRaw(ArrowUpDown)
  return markRaw(sortDirection.value === 'ascending' ? ArrowUp : ArrowDown)
}

function folderSummary(node: WorkspaceNode) {
  const children = node.children || []
  const pending = children.filter(item => ['missing', 'stale', 'working'].includes(item.status)).length
  const total = t('courseFiles.itemCount').replace('{count}', String(children.length))
  return pending ? `${total} · ${t('courseFiles.inspector.pendingCount').replace('{count}', String(pending))}` : total
}

function shortRevision(revision: string) {
  return revision.length > 14 ? `${revision.slice(0, 8)}…${revision.slice(-5)}` : revision
}

function inspectorSource(node: WorkspaceNode) {
  if (node.type === 'outline') return t('courseFiles.inspector.sources.courseStructure')
  if (node.type === 'lesson_plan') return t('courseFiles.inspector.sources.outlineAndMaterials')
  if (node.type === 'content') {
    const lesson = lessons.value.find(item => item.lesson_unit_id === node.lessonId)
    const count = lesson ? lessonContentNodes(lesson).filter(hasUsableContent).length : 0
    return t('courseFiles.inspector.sources.contentBlocks').replace('{count}', String(count))
  }
  if (node.type === 'practice') {
    const lesson = lessons.value.find(item => item.lesson_unit_id === node.lessonId)
    const ids = new Set(lesson ? practiceNodeIds(lesson) : [])
    const count = questionBankItems.value.filter(item => item.lifecycle_status !== 'retired' && item.node_id && ids.has(item.node_id)).length
    return t('courseFiles.inspector.sources.questionBank').replace('{count}', String(count))
  }
  if (node.type === 'ppt') {
    if (node.origin === 'uploaded') return t('courseFiles.inspector.sources.uploadedDeck')
    if (node.origin === 'generated') return t('courseFiles.inspector.sources.generatedDeck')
    return t('courseFiles.inspector.sources.notSelected')
  }
  return t('courseFiles.inspector.sources.teacherFile')
}

function inspectorUse(node: WorkspaceNode) {
  if (node.type === 'outline') return t('courseFiles.inspector.uses.outline')
  if (node.type === 'lesson_plan') return t('courseFiles.inspector.uses.lessonPlan')
  if (node.type === 'content') return t('courseFiles.inspector.uses.content')
  if (node.type === 'practice') return t('courseFiles.inspector.uses.practice')
  if (node.type === 'ppt') return t('courseFiles.inspector.uses.ppt')
  return t('courseFiles.inspector.uses.material')
}

function folderPath(id: string) {
  const values: string[] = []
  let node = flatNodes.value.get(id)
  while (node) { if (node.kind === 'folder') values.unshift(node.id); node = node.parentId ? flatNodes.value.get(node.parentId) : undefined }
  return values
}
function toggleFolder(id: string) {
  expandedFolderIds.value = expandedFolderIds.value.includes(id)
    ? expandedFolderIds.value.filter(value => value !== id)
    : [...expandedFolderIds.value, id]
}
function openFolder(id: string) {
  const node = flatNodes.value.get(id)
  if (node?.kind !== 'folder') return
  currentFolderId.value = id
  selectedNode.value = null
  query.value = ''
  expandedFolderIds.value = [...new Set([...expandedFolderIds.value, ...folderPath(id)])]
  const lessonId = node.lessonId || ''
  const nextQuery = { ...route.query }
  if (lessonId) nextQuery.lesson = lessonId
  else delete nextQuery.lesson
  void router.replace({ query: nextQuery })
  emit('contextChange', { lessonId, nodeId: node.id, label: node.label, type: node.type, path: node.path })
}
function selectNode(node: WorkspaceNode) {
  selectedNode.value = node
  emit('contextChange', { lessonId: node.lessonId || '', nodeId: node.id, label: node.label, type: node.type, path: node.path })
}
function handleNodeClick(node: WorkspaceNode) {
  if (node.kind === 'folder') { openFolder(node.id); return }
  selectNode(node)
}

function primaryLabel(node: WorkspaceNode) {
  if (node.kind === 'folder') return t('courseFiles.openFolder')
  if (node.asset) return t('courseFiles.preview')
  if (node.type === 'outline' || node.type === 'lesson_plan') return node.status === 'missing' ? t('courseFiles.create') : t('courseFiles.openEdit')
  if (node.type === 'content') return node.status === 'missing' ? t('courseFiles.createContent') : t('courseFiles.openContent')
  if (node.type === 'ppt') return node.status === 'missing' ? t('courseFiles.createPpt') : t('courseFiles.openPpt')
  if (node.type === 'practice') return node.status === 'missing' ? t('courseFiles.createPractice') : t('courseFiles.openPractice')
  return t('courseFiles.open')
}
function primaryIcon(node: WorkspaceNode) { return markRaw(node.kind === 'folder' ? FolderOpen : node.asset ? Eye : node.status === 'missing' ? Sparkles : Pencil) }
function primaryDisabled(_node: WorkspaceNode) { return false }
function lessonPlanRevision(lessonId: string) { return lessons.value.find(item => item.lesson_unit_id === lessonId)?.plan.working_revision_id || '' }

async function primaryAction(node: WorkspaceNode) {
  selectNode(node)
  if (node.kind === 'folder') { openFolder(node.id); return }
  if (node.asset) { await previewFile(node.asset); return }
  if (node.type === 'outline') { node.status === 'missing' ? openCreateDialog('outline') : emit('openOutline'); return }
  if (node.type === 'lesson_plan') { node.status === 'missing' ? openCreateDialog('lesson_plan', node.lessonId) : emit('openTeachingPlan', node.lessonId || ''); return }
  if (node.type === 'content') {
    node.status === 'missing'
      ? emit('openTasks')
      : router.push({
        name: 'learning',
        params: { courseId: props.courseId, nodeId: node.lessonId },
        query: { teacherPreview: '1', returnTo: workspaceReturnTo(node.lessonId || '') },
      })
    return
  }
  if (node.type === 'ppt') { node.status === 'missing' ? openCreateDialog('ppt', node.lessonId) : router.push({ name: 'ppt-workspace', params: { courseId: props.courseId }, query: { lesson: node.lessonId } }); return }
  if (node.type === 'practice') { node.status === 'missing' ? openCreateDialog('practice', node.lessonId) : emit('openPractice', node.lessonId || ''); return }
}

function workspaceReturnTo(lessonId = '') {
  return router.resolve({
    name: 'course-workspace',
    params: { courseId: props.courseId, mode: 'setup' },
    query: { ...route.query, ...(lessonId ? { lesson: lessonId } : {}) },
  }).fullPath
}

const canExportManaged = (node: WorkspaceNode) => node.kind === 'managed'
  && node.status !== 'missing'
  && ['outline', 'lesson_plan', 'content', 'ppt'].includes(node.type)

function readableNodeContent(node: Node) {
  if (node.node_content?.trim()) return node.node_content.trim()
  return (node.content_blocks || [])
    .filter(block => block.content?.trim())
    .map(block => `${block.title ? `### ${block.title}\n\n` : ''}${block.content.trim()}`)
    .join('\n\n')
}

function outlineMarkdown() {
  const title = selected.value?.course_name || courseTitle.value || t('courseFiles.names.outline')
  const lines = [`# ${title}`, '']
  courseStore.nodes.forEach(node => {
    const level = Math.min(6, Math.max(2, Number(node.node_level || 1) + 1))
    lines.push(`${'#'.repeat(level)} ${node.node_name}`, '')
    if (node.learning_objective) lines.push(`> ${node.learning_objective}`, '')
  })
  return `${lines.join('\n').trim()}\n`
}

function lessonContentMarkdown(lesson: TeacherLessonProjection) {
  const nodes = lessonContentNodes(lesson)
  const minimumLevel = Math.min(...nodes.map(node => Number(node.node_level || 1)), 1)
  const lines = [`# ${lesson.title}`, '']
  nodes.forEach(node => {
    const content = readableNodeContent(node)
    const isLessonRoot = node.node_id === lesson.lesson_unit_id || node.node_name === lesson.title
    if (!isLessonRoot) {
      const level = Math.min(6, Math.max(2, Number(node.node_level || 1) - minimumLevel + 2))
      lines.push(`${'#'.repeat(level)} ${node.node_name}`, '')
    }
    if (content) lines.push(content, '')
  })
  return `${lines.join('\n').trim()}\n`
}

const exportKeyLabel = (key: string) => ({
  objectives: t('courseFiles.exportLabels.objectives'),
  key_points: t('courseFiles.exportLabels.keyPoints'),
  difficult_points: t('courseFiles.exportLabels.difficultPoints'),
  teaching_process: t('courseFiles.exportLabels.teachingProcess'),
  activities: t('courseFiles.exportLabels.activities'),
  assessment: t('courseFiles.exportLabels.assessment'),
  homework: t('courseFiles.exportLabels.homework'),
}[key] || key.replace(/_/g, ' '))

function planValueMarkdown(value: unknown, depth = 2): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value !== 'object') return `${String(value)}\n\n`
  if (Array.isArray(value)) {
    if (value.every(item => typeof item !== 'object' || item === null)) return `${value.map(item => `- ${String(item)}`).join('\n')}\n\n`
    return value.map((item, index) => `${'#'.repeat(Math.min(6, depth))} ${index + 1}\n\n${planValueMarkdown(item, depth + 1)}`).join('')
  }
  return Object.entries(value as Record<string, unknown>).map(([key, item]) => {
    const body = planValueMarkdown(item, depth + 1)
    return body ? `${'#'.repeat(Math.min(6, depth))} ${exportKeyLabel(key)}\n\n${body}` : ''
  }).join('')
}

function lessonPlanMarkdown(lesson: TeacherLessonProjection) {
  const revision = lesson.plan.revisions.find(item => item.revision_id === lesson.plan.working_revision_id)
  return `# ${lesson.title} · ${t('courseFiles.names.lessonPlan')}\n\n${planValueMarkdown(revision?.plan || {})}`.trimEnd() + '\n'
}

async function exportManagedNode(node: WorkspaceNode) {
  exportingNodeId.value = node.id
  try {
    const lesson = node.lessonId ? lessons.value.find(item => item.lesson_unit_id === node.lessonId) : undefined
    if (node.type === 'outline') {
      downloadBlob(new Blob([outlineMarkdown()], { type: 'text/markdown;charset=utf-8' }), `${safePart(selected.value?.course_name || t('courseFiles.names.outline'))}-${t('courseFiles.names.outline')}.md`)
    } else if (node.type === 'content' && lesson) {
      downloadBlob(new Blob([lessonContentMarkdown(lesson)], { type: 'text/markdown;charset=utf-8' }), `${safePart(lesson.title)}-${t('courseFiles.names.content')}.md`)
    } else if (node.type === 'lesson_plan' && lesson) {
      downloadBlob(new Blob([lessonPlanMarkdown(lesson)], { type: 'text/markdown;charset=utf-8' }), `${safePart(lesson.title)}-${t('courseFiles.names.lessonPlan')}.md`)
    } else if (node.type === 'ppt' && lesson) {
      const ppt = lesson.plan.ppt_assets.find(item => item.role === 'primary') || lesson.plan.ppt_assets[0]
      if (!ppt) throw new Error(t('courseFiles.errors.exportUnavailable'))
      const useV6 = ppt.engine === 'slide_deck_v6' && ppt.working_representation_id
      const response = await http.get(
        useV6
          ? `/api/teacher/courses/${props.courseId}/lessons/${lesson.lesson_unit_id}/ppt-v6/${ppt.working_representation_id}/export.pptx`
          : `/api/teacher/courses/${props.courseId}/lessons/${lesson.lesson_unit_id}/ppt/export.pptx`,
        {
          ...(useV6 ? {} : { params: { asset_id: ppt.asset_id, revision_id: ppt.working_revision_id } }),
          responseType: 'blob',
        },
      )
      downloadBlob(response.data, `${safePart(lesson.title)}-${t('courseFiles.names.ppt')}.pptx`)
    } else {
      throw new Error(t('courseFiles.errors.exportUnavailable'))
    }
    ElMessage.success(t('courseFiles.exported'))
  } catch (error: any) {
    ElMessage.error(localizedError(error, String(error?.message || t('courseFiles.errors.exportFailed'))))
  } finally {
    exportingNodeId.value = ''
  }
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
    if (props.courseId) {
      await lessonStore.load(props.courseId).catch(() => undefined)
      await loadQuestionBankSummary()
    }
    const requestedLessonId = String(route.query.lesson || '')
    currentFolderId.value = requestedLessonId && flatNodes.value.has(`lesson:${requestedLessonId}`)
      ? `lesson:${requestedLessonId}`
      : 'root'
    expandedFolderIds.value = folderPath(currentFolderId.value)
    selectedNode.value = null
  } catch (error: any) {
    status.value = localizedError(error, t('courseFiles.spaceUnavailable'))
  } finally { initializing.value = false }
}
async function reloadAll() {
  busy.value = true
  try {
    if (props.courseId) await courseStore.loadCourse(props.courseId, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true })
    await refresh()
  } finally { busy.value = false }
}
async function reloadPackage() { if (selected.value) selected.value = (await http.get(`/api/teacher-course-spaces/${selected.value.package_id}`)).data }

async function loadQuestionBankSummary() {
  if (!props.courseId) return
  try {
    const response = await http.get(`/api/courses/${props.courseId}/question-bank`, { silentError: true })
    questionBankItems.value = Array.isArray(response.data?.items) ? response.data.items : []
  } catch (error: any) {
    if (Number(error?.response?.status || 0) === 404) questionBankItems.value = []
  }
}

function openCreateDialog(command: CreateType | string, lessonId: unknown = '', targetFolderId = '') {
  const type = command as CreateType
  if (type === 'outline') {
    const outline = flatNodes.value.get('managed:outline')
    if (outline?.status === 'missing') emit('createOutline')
    else emit('openOutline')
    return
  }
  const targetLessonId = typeof lessonId === 'string' && lessonId ? lessonId : currentFolder.value?.lessonId || ''
  if (['lesson_plan', 'ppt', 'practice'].includes(type) && targetLessonId) {
    const existing = [...flatNodes.value.values()].find(node => node.type === type && node.lessonId === targetLessonId && node.status !== 'missing')
    if (existing) {
      selectedNode.value = existing
      void primaryAction(existing)
      return
    }
  }
  const targetFolder = flatNodes.value.get(targetFolderId) || currentFolder.value
  if (type === 'folder' && targetFolder?.kind !== 'folder') return
  resetCreateForm()
  createType.value = type
  createTargetFolderId.value = targetFolder?.id || ''
  createForm.value.lessonId = targetLessonId
  createOpen.value = true
  void nextTick(() => createDialog.value?.focus())
}
function closeCreateDialog() { createOpen.value = false; resetCreateForm() }
const dialogTitle = computed(() => t(`courseFiles.dialog.${createType.value}.title`))
const needsLesson = computed(() => ['lesson_plan', 'ppt', 'practice'].includes(createType.value) && !createForm.value.lessonId)
const createLocationLabel = computed(() => {
  if (needsLesson.value && !createForm.value.lessonId) {
    const typeKey = createType.value === 'lesson_plan' ? 'lessonPlan' : createType.value
    return `${t('courseFiles.rootName')} / ${t('courseFiles.form.selectLesson')} / ${t(`courseFiles.types.${typeKey}`)}`
  }
  const path = targetPath(createType.value, createForm.value.lessonId)
  return path ? `${t('courseFiles.rootName')} / ${displayPath(path)}` : t('courseFiles.rootName')
})
const requirementsPlaceholder = computed(() => t(`courseFiles.dialog.${createType.value}.requirements`))
const sourceFileLabel = computed(() => createType.value === 'ppt'
  ? createForm.value.mode === 'import' ? t('courseFiles.form.oldDeckFile') : t('courseFiles.form.templateFile')
  : t('courseFiles.form.sourceFile'))
const submitLabel = computed(() => {
  if (createType.value === 'ppt') return createForm.value.mode === 'import' ? t('courseFiles.form.importOldDeck') : t('courseFiles.form.generatePpt')
  if (createForm.value.file) return t('courseFiles.form.importAndCreate')
  if (createType.value === 'folder') return t('courseFiles.createFolder')
  if (createType.value === 'material') return t('courseFiles.createFile')
  return t('courseFiles.form.startCreate')
})
const pptAiBlocked = computed(() => createType.value === 'ppt'
  && createForm.value.mode === 'ai'
  && Boolean(createForm.value.lessonId)
  && !lessonPlanRevision(createForm.value.lessonId))
const submitDisabled = computed(() => busy.value
  || needsLesson.value && !createForm.value.lessonId
  || createType.value === 'ppt' && createForm.value.mode === 'import' && !createForm.value.file
  || pptAiBlocked.value)
function captureImportFile(event: Event) { const input = event.target as HTMLInputElement; createForm.value.file = input.files?.[0] || null; input.value = '' }
function resetCreateForm() {
  createTargetFolderId.value = ''
  createForm.value = { lessonId: '', title: '', hours: '2', mode: 'ai', count: 12, style: 'simple', difficulty: 'mixed', requirements: '', pptImportAction: 'derive_plan', file: null }
}
function createLessonPlanFirst() {
  const lessonId = createForm.value.lessonId
  closeCreateDialog()
  openCreateDialog('lesson_plan', lessonId)
}

function targetPath(type: CreateType, lessonId: string) {
  const lesson = lessons.value.find(item => item.lesson_unit_id === lessonId)
  const folder = createTargetFolder.value
  if (type === 'material') {
    if (folder?.type === 'lesson') return `${folder.path}/资料`
    if (folder && (folder.type === 'reference' || folder.type === 'material' || folder.type === 'folder')) return folder.path
    return lesson ? `${lessonPath(lesson)}/资料` : '参考资料'
  }
  if (type === 'lesson_plan') return lesson ? `${lessonPath(lesson)}/教案` : '教案'
  if (type === 'ppt') return lesson ? `${lessonPath(lesson)}/PPT` : 'PPT'
  if (type === 'practice') return lesson ? `${lessonPath(lesson)}/练习` : '练习'
  return folder?.path || ''
}
async function uploadFile(file: File, path: string): Promise<Asset | null> {
  if (!selected.value) return null
  const data = new FormData(); data.append('files', file); data.append('relative_paths', path ? `${path}/${file.name}` : file.name)
  const result = (await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/imports`, data)).data
  selected.value = result.package
  const relativePath = path ? `${path}/${file.name}` : file.name
  const outcome = result.outcomes?.find((item: Asset & { outcome?: string; error?: string }) => item.relative_path === relativePath)
  if (outcome?.outcome === 'rejected') throw new Error(outcome.error || t('courseFiles.errors.createFailed'))
  return outcome?.asset_id ? outcome : selected.value?.assets.find(item => item.relative_path === relativePath) || null
}
async function submitCreate() {
  if (!selected.value) return
  busy.value = true
  try {
    if (createType.value === 'folder') {
      const path = targetPath('folder', '')
      await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/folders`, { name: path ? `${path}/${createForm.value.title}` : createForm.value.title })
    } else if (createType.value === 'ppt') {
      if (createForm.value.mode === 'import') {
        if (!createForm.value.file) throw new Error(t('courseFiles.errors.selectOldDeck'))
        const uploaded = await uploadFile(createForm.value.file, targetPath('ppt', createForm.value.lessonId))
        if (createForm.value.pptImportAction === 'derive_plan' && uploaded) {
          await lessonStore.generateLesson(props.courseId, createForm.value.lessonId, {
            packageId: selected.value.package_id,
            assetId: uploaded.asset_id,
          })
        }
      } else {
        const revision = lessonPlanRevision(createForm.value.lessonId)
        if (!revision) throw new Error(t('courseFiles.errors.createLessonFirst'))
        if (createForm.value.style === 'template' && createForm.value.file) {
          await uploadFile(createForm.value.file, `${targetPath('ppt', createForm.value.lessonId)}/风格参考`)
        }
        await lessonStore.generatePpt(props.courseId, createForm.value.lessonId, revision)
      }
    } else if (createForm.value.file) {
      await uploadFile(createForm.value.file, targetPath(createType.value, createForm.value.lessonId))
    } else if (createType.value === 'outline') {
      emit('openOutline')
    } else if (createType.value === 'lesson_plan') {
      await lessonStore.generateLesson(props.courseId, createForm.value.lessonId)
    } else if (createType.value === 'practice') {
      await createPractice(createForm.value.lessonId)
    } else if (createType.value === 'material') {
      const name = `${safePart(createForm.value.title || t('courseFiles.names.newMaterial'))}.md`
      await uploadFile(new File([`# ${createForm.value.title}\n\n${createForm.value.requirements}\n`], name, { type: 'text/markdown' }), targetPath('material', createForm.value.lessonId))
    }
    await reloadPackage()
    await lessonStore.load(props.courseId).catch(() => undefined)
    closeCreateDialog()
    ElMessage.success(t('courseFiles.created'))
  } catch (error: any) { ElMessage.error(localizedError(error, String(error?.message || t('courseFiles.errors.createFailed')))) } finally { busy.value = false }
}
async function createPractice(lessonId: string) {
  const lesson = lessons.value.find(item => item.lesson_unit_id === lessonId)
  if (!lesson) throw new Error(t('courseFiles.errors.selectLesson'))
  const nodeIds = practiceNodeIds(lesson)
  if (!nodeIds.length) throw new Error(t('courseFiles.errors.practiceNeedsSections'))
  practiceWorkingLessonIds.value = [...new Set([...practiceWorkingLessonIds.value, lessonId])]
  try {
    await runQuestionBankRebuild(
      props.courseId,
      {
        request_id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `practice-${Date.now()}`,
        scope: 'nodes',
        node_ids: nodeIds,
        mode: 'incremental',
        retrieval_enabled: false,
      },
      { maxPolls: 450 },
    )
    await loadQuestionBankSummary()
    emit('openPractice', lessonId)
  } finally {
    practiceWorkingLessonIds.value = practiceWorkingLessonIds.value.filter(id => id !== lessonId)
  }
}

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

watch(readinessSummary, summary => emit('readinessChange', summary), { immediate: true })
onMounted(refresh)
</script>

<style scoped>
.file-space,.file-space *{box-sizing:border-box}.file-space{height:100%;min-height:0;color:var(--lz-text-strong);background:#f8fafc;font-size:14px}.standalone-header{height:68px;display:flex;align-items:center;justify-content:space-between;padding:0 24px;border-bottom:1px solid var(--lz-border);background:#fff}.standalone-header small,.standalone-header h1{display:block;margin:0}.standalone-header small{color:var(--lz-text-muted);font-size:13px}.standalone-header h1{font-size:20px}.standalone-header button{display:flex;align-items:center;gap:7px;border:0;background:transparent;font-size:14px}
.file-layout{height:100%;min-height:0;display:grid;grid-template-columns:260px minmax(560px,1fr) 312px;overflow:hidden;background:#fff}.file-tree-pane,.file-list-pane,.file-inspector{min-height:0;overflow:hidden}.file-tree-pane{display:grid;grid-template-rows:auto minmax(0,1fr) auto;border-right:1px solid var(--lz-border);background:#f8fafc}.pane-heading{min-height:56px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 14px;border-bottom:1px solid #e8edf4}.pane-heading>span{min-width:0;display:flex;align-items:center;gap:8px;color:#475569}.pane-heading>span>svg{color:#64748b}.pane-heading strong{overflow:hidden;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.pane-heading button,.file-inspector header>button{width:32px;height:32px;display:grid;place-items:center;padding:0;border:0;border-radius:7px;background:transparent;color:var(--lz-text-muted);cursor:pointer}.pane-heading button:hover,.file-inspector header>button:hover{color:var(--lz-text-strong);background:#eef2f7}.folder-navigation{min-height:0;overflow:auto;padding:9px 8px 16px}.folder-navigation>ul{margin:0;padding:0;list-style:none}.file-tree-pane footer{display:grid;gap:9px;padding:14px;border-top:1px solid var(--lz-border);color:var(--lz-text-muted);font-size:12px}.file-tree-pane footer button{display:flex;align-items:center;gap:7px;padding:0;border:0;background:transparent;color:var(--lz-text-secondary);font-size:13px;font-weight:700;cursor:pointer}
.file-list-pane{display:flex;flex-direction:column;background:#fff}.list-toolbar{min-height:58px;flex:none;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 18px;border-bottom:1px solid var(--lz-border)}.list-toolbar nav{min-width:0;display:flex;align-items:center;gap:4px;overflow:hidden}.list-toolbar nav button{display:flex;align-items:center;gap:6px;min-width:0;padding:5px;border:0;background:transparent;color:var(--lz-text-secondary);font-size:13px;white-space:nowrap;cursor:pointer}.list-toolbar nav svg{flex:none;color:#94a3b8}.toolbar-actions{display:flex;align-items:center;gap:8px}.list-search{width:248px;height:40px;display:flex;align-items:center;gap:8px;padding:0 10px 0 12px;border:1px solid transparent;border-radius:10px;color:#94a3b8;background:#f1f5f9;transition:border-color .15s ease,background .15s ease,box-shadow .15s ease}.list-search:focus-within{border-color:var(--lz-brand-border);background:#fff;box-shadow:0 0 0 3px var(--lz-brand-soft)}.list-search input{min-width:0;width:100%;border:0;outline:0;color:var(--lz-text-strong);background:transparent;font-size:13px}.list-search input::-webkit-search-cancel-button{display:none}.list-search button{width:26px;height:26px;flex:none;display:grid;place-items:center;padding:0;border:0;border-radius:6px;color:#64748b;background:transparent;cursor:pointer}.list-search button:hover{color:var(--lz-text-strong);background:#e2e8f0}.list-search button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.folder-title{min-height:66px;flex:none;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 18px}.folder-title h2{min-width:0;margin:0;overflow:hidden;font-size:20px;text-overflow:ellipsis;white-space:nowrap}.folder-title__actions{flex:none;display:flex;align-items:center;gap:7px}.folder-title__actions>span{margin-right:3px;color:var(--lz-text-muted);font-size:13px}.folder-title__actions button{height:36px;display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-secondary);background:#fff;font-size:13px;font-weight:700;cursor:pointer}.folder-title__actions button:hover{border-color:var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.add-material-button{padding:0 12px}.add-folder-button{width:36px;padding:0}
.file-table{min-height:0;flex:1;overflow:auto;padding:0 12px 20px}.file-table__head,.file-row{display:grid;grid-template-columns:minmax(230px,1.65fr) 126px 88px 76px 98px;align-items:center;gap:10px}.file-table__head{min-height:42px;padding:0 10px;border-bottom:1px solid var(--lz-border);color:var(--lz-text-muted);font-size:12px;font-weight:700}.sort-button{height:40px;display:inline-flex;align-items:center;gap:5px;padding:0;border:0;color:inherit;background:transparent;font:inherit;cursor:pointer}.sort-button svg{opacity:.55}.sort-button:hover,.sort-button.active{color:var(--lz-text-secondary)}.sort-button.active svg{opacity:1}.sort-button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}.file-table__head span:nth-child(4),.file-row>span:nth-child(4){text-align:right}.file-table__head span:nth-child(4) .sort-button{width:100%;justify-content:flex-end}.file-row{width:100%;min-height:58px;padding:7px 10px;border:0;border-bottom:1px solid #edf1f6;background:transparent;color:var(--lz-text-secondary);text-align:left;font-size:13px;cursor:pointer}.file-row:hover,.file-row:focus-visible{outline:0;background:#f7f9fc}.file-row.selected{background:#e9eeff}.file-name{min-width:0;display:flex;align-items:center;gap:10px}.file-name strong{overflow:hidden;color:var(--lz-text-strong);font-size:14px;text-overflow:ellipsis;white-space:nowrap}.file-icon{width:34px;height:34px;flex:none;display:grid;place-items:center;border-radius:8px;background:#f1f5f9;color:#64748b}.file-icon[data-type="outline"],.file-icon[data-type="lesson_plan"],.file-icon[data-type="ppt"]{background:#eef2ff;color:#4f46e5}.status-dot{width:7px;height:7px;display:inline-block;margin-right:6px;border-radius:50%;background:#94a3b8}.status-dot[data-state="ready"],.status-dot[data-state="uploaded"]{background:#10b981}.status-dot[data-state="working"]{background:#6366f1}.status-dot[data-state="stale"]{background:#f97316}.status-dot[data-state="missing"],.status-dot[data-state="empty"]{background:#cbd5e1}
.file-empty{min-height:260px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:var(--lz-text-muted);text-align:center}.file-empty strong{color:var(--lz-text-secondary);font-size:15px}.file-empty span{max-width:320px;font-size:13px;line-height:1.55}.file-empty button{display:flex;align-items:center;gap:6px;padding:8px 12px;border:1px solid var(--lz-border);border-radius:8px;background:#fff;color:#4f46e5;font-size:13px;cursor:pointer}.file-empty button:hover{border-color:var(--lz-brand-border);background:var(--lz-brand-soft)}.runtime-note{margin:0;padding:9px 18px;border-top:1px solid var(--lz-border);color:#9a3412;background:#fff7ed;font-size:13px}
.file-inspector{display:flex;flex-direction:column;border-left:1px solid var(--lz-border);background:#fbfcfe}.file-inspector>header{display:grid;grid-template-columns:44px minmax(0,1fr) auto;align-items:center;gap:11px;padding:17px 16px 15px;border-bottom:1px solid var(--lz-border)}.inspector-icon{width:44px;height:44px;display:grid;place-items:center;border-radius:11px;background:#eef2ff;color:#4f46e5}.file-inspector header div{min-width:0;display:grid;gap:3px}.file-inspector header small{color:var(--lz-text-muted);font-size:12px}.file-inspector header strong{overflow:hidden;font-size:16px;text-overflow:ellipsis;white-space:nowrap}.inspector-status{padding:13px 16px;border-bottom:1px solid #e8edf4}.inspector-status>span{display:flex;align-items:center;gap:7px;color:var(--lz-text-secondary);font-size:13px;font-weight:700}.inspector-status i{width:8px;height:8px;border-radius:50%;background:#94a3b8}.inspector-status[data-state="ready"] i,.inspector-status[data-state="uploaded"] i{background:#10b981}.inspector-status[data-state="working"] i{background:#6366f1}.inspector-status[data-state="stale"] i{background:#f97316}.inspector-status[data-state="empty"] i{background:#cbd5e1}.inspector-overview{min-height:0;overflow:auto;padding:18px 16px}.inspector-overview h3{margin:0 0 8px;color:var(--lz-text-secondary);font-size:14px}.inspector-overview dl{margin:0}.inspector-overview dl>div{display:grid;grid-template-columns:72px minmax(0,1fr);gap:10px;padding:12px 0;border-bottom:1px solid #e8edf4}.inspector-overview dt{color:var(--lz-text-muted);font-size:12px}.inspector-overview dd{margin:0;overflow-wrap:anywhere;color:var(--lz-text-secondary);font-size:13px;line-height:1.5}.inspector-actions{display:grid;gap:8px;margin-top:auto;padding:16px;border-top:1px solid var(--lz-border)}.inspector-actions button{min-height:40px;display:flex;align-items:center;justify-content:center;gap:7px;border:1px solid var(--lz-border);border-radius:9px;background:#fff;color:var(--lz-text-secondary);font-size:13px;font-weight:700;cursor:pointer}.inspector-actions button.primary{border-color:#4f46e5;background:#4f46e5;color:#fff}.inspector-actions button.danger{color:#b91c1c}.inspector-actions button:disabled{opacity:.45;cursor:not-allowed}
.space-state{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;color:var(--lz-text-muted);text-align:center;font-size:13px}.space-state strong{color:var(--lz-text-secondary);font-size:15px}.space-state span{max-width:240px;font-size:13px;line-height:1.5}.space-state button{padding:8px 13px;border:1px solid var(--lz-border);border-radius:8px;background:#fff;font-size:13px}
.asset-create-overlay{position:fixed;inset:0;z-index:2600;display:grid;place-items:center;padding:14px;background:rgba(15,23,42,.38);backdrop-filter:blur(2px)}.asset-create-dialog{width:min(580px,calc(100vw - 28px));max-height:calc(100vh - 28px);overflow:auto;padding:0 20px 20px;border:1px solid rgba(255,255,255,.65);border-radius:14px;background:#fff;box-shadow:0 24px 70px rgba(15,23,42,.22)}.asset-create-header{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;min-height:54px;margin:0 -20px 15px;padding:0 20px;border-bottom:1px solid #eef2f7;background:rgba(255,255,255,.96)}.asset-create-header strong{font-size:16px}.asset-create-header button{width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.asset-create-header button:hover{background:#f1f5f9;color:var(--lz-text-strong)}.asset-create-help{margin:0 0 15px;color:var(--lz-text-secondary);font-size:13px;line-height:1.55}.create-location{min-height:40px;display:grid;grid-template-columns:18px auto minmax(0,1fr);align-items:center;gap:7px;padding:0 11px;border:1px solid #e2e8f0;border-radius:8px;color:#64748b;background:#f8fafc;font-size:12px}.create-location strong{overflow:hidden;color:#334155;font-weight:650;text-overflow:ellipsis;white-space:nowrap}.asset-form{display:grid;gap:14px;padding-top:16px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.form-field{display:grid;gap:7px}.form-field>span,.source-picker>div>span{color:var(--lz-text-secondary);font-size:13px;font-weight:700}.form-field>small{color:var(--lz-text-muted);font-size:12px;line-height:1.5}.form-field input,.form-field select,.form-field textarea{width:100%;min-height:42px;padding:9px 11px;border:1px solid var(--lz-border);border-radius:8px;outline:0;color:var(--lz-text-strong);background:#fff;font:inherit;font-size:13px}.form-field textarea{resize:vertical}.form-field input:focus,.form-field select:focus,.form-field textarea:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.1)}.source-picker{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px;border:1px dashed #cbd5e1;border-radius:9px}.source-picker>div{display:grid;gap:4px}.source-picker small{color:var(--lz-text-muted);font-size:12px}.source-picker button{max-width:220px;display:flex;align-items:center;gap:6px;overflow:hidden;padding:8px 10px;border:1px solid var(--lz-border);border-radius:7px;background:#fff;color:#4f46e5;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.ppt-origin-picker{display:grid;gap:8px}.ppt-origin-picker>span{color:var(--lz-text-secondary);font-size:13px;font-weight:700}.ppt-origin-picker>div{display:grid;grid-template-columns:1fr 1fr;gap:9px}.ppt-origin-picker button{min-width:0;display:grid;grid-template-columns:20px minmax(0,1fr);gap:2px 8px;padding:11px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-secondary);background:#fff;text-align:left;cursor:pointer}.ppt-origin-picker button svg{grid-row:1/3;align-self:center;color:#64748b}.ppt-origin-picker button strong{font-size:13px}.ppt-origin-picker button small{overflow:hidden;color:var(--lz-text-muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.ppt-origin-picker button.active{border-color:var(--lz-brand);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.ppt-origin-picker button.active svg{color:var(--lz-brand)}.ppt-origin-note{display:flex;align-items:flex-start;gap:7px;margin:0;padding:10px 11px;border:1px solid #e0e7ff;border-radius:8px;color:#4f46e5;background:#f8faff;font-size:12px;line-height:1.5}.ppt-origin-note[data-mode="import"]{border-color:#e2e8f0;color:#475569;background:#f8fafc}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;padding-top:5px}.dialog-actions button{min-height:38px;padding:0 14px;border:1px solid var(--lz-border);border-radius:8px;background:#fff;color:var(--lz-text-secondary);font-size:13px;font-weight:700;cursor:pointer}.dialog-actions button.primary{border-color:#4f46e5;background:#4f46e5;color:#fff}.dialog-actions button:disabled{opacity:.45;cursor:not-allowed}.practice-create-note,.create-prerequisite{display:grid;grid-template-columns:20px minmax(0,1fr);align-items:start;gap:9px;padding:12px;border:1px solid #e2e8f0;border-radius:9px;color:#475569;background:#f8fafc}.practice-create-note>div,.create-prerequisite>div{display:grid;gap:4px}.practice-create-note strong,.create-prerequisite strong{font-size:13px}.practice-create-note small,.create-prerequisite small{color:var(--lz-text-muted);font-size:12px;line-height:1.5}.create-prerequisite{grid-template-columns:20px minmax(0,1fr) auto;border-color:#fed7aa;color:#9a3412;background:#fff7ed}.create-prerequisite button{align-self:center;padding:7px 9px;border:1px solid #fdba74;border-radius:7px;color:#9a3412;background:#fff;font-size:12px;font-weight:700;cursor:pointer}
.source-picker>span{color:var(--lz-text-secondary);font-size:13px;font-weight:700}.ppt-origin-picker button{align-items:center;gap:8px}.ppt-origin-picker button svg{grid-row:auto}.practice-create-note,.create-prerequisite{align-items:center}
.preview-surface{min-height:420px;display:grid;place-items:center}.preview-surface img{max-width:100%;max-height:75vh}.preview-surface iframe{width:100%;min-height:72vh;border:0}.office-note{display:flex;flex-direction:column;align-items:center;gap:8px;color:var(--lz-text-muted);text-align:center;font-size:13px}.office-note strong{color:var(--lz-text-strong);font-size:15px}.office-note button{padding:8px 11px;border:1px solid var(--lz-border);border-radius:7px;background:#fff;font-size:13px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media (max-width:1080px){.file-layout{grid-template-columns:220px minmax(440px,1fr) 270px}.list-search{display:none}.file-table__head,.file-row{grid-template-columns:minmax(190px,1.5fr) 104px 78px 90px}.file-table__head span:nth-child(4),.file-row>span:nth-child(4){display:none}}
@media (max-width:760px){.file-layout{grid-template-columns:1fr;grid-template-rows:170px minmax(0,1fr) auto}.file-tree-pane{display:grid;grid-template-rows:46px minmax(0,1fr);overflow:hidden;border-right:0;border-bottom:1px solid var(--lz-border)}.pane-heading{min-height:46px;padding:0 11px}.folder-navigation{overflow:auto;padding:6px 8px 11px}.file-tree-pane footer{display:none}.file-inspector{max-height:48vh;border-left:0;border-top:1px solid var(--lz-border)}.inspector-actions{grid-template-columns:1fr auto auto}.list-toolbar{min-height:50px;padding:0 11px}.list-toolbar nav button{max-width:110px}.folder-title{min-height:58px;padding:8px 12px}.folder-title h2{font-size:17px}.folder-title__actions>span{display:none}.add-material-button{padding:0 10px}.file-table{padding:0 7px 12px}.file-table__head,.file-row{grid-template-columns:minmax(180px,1fr) 94px}.file-table__head span:nth-child(2),.file-row>span:nth-child(2),.file-table__head span:nth-child(3),.file-row>span:nth-child(3),.file-table__head span:nth-child(4),.file-row>span:nth-child(4){display:none}.form-grid{grid-template-columns:1fr}}
</style>
