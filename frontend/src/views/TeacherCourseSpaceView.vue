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
            <el-dropdown trigger="click" @command="handleCreateCommand">
              <button class="new-button" type="button"><Plus :size="15" />{{ t('courseFiles.new') }}<ChevronDown :size="14" /></button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-for="option in createOptions" :key="option.type" :command="option.type" :divided="option.divided">
                    <component :is="createOptionIcons[option.type]" :size="14" />{{ option.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </header>

        <div class="folder-title">
          <h2>{{ currentFolder?.label || t('courseFiles.rootName') }}</h2>
          <span>{{ t('courseFiles.itemCount').replace('{count}', String(filteredChildren.length)) }}</span>
        </div>

        <div class="file-table" role="table" :aria-label="t('courseFiles.fileList')">
          <div class="file-table__head" role="row">
            <span>{{ t('courseFiles.columns.name') }}</span>
            <span>{{ t('courseFiles.columns.updated') }}</span>
            <span>{{ t('courseFiles.columns.type') }}</span>
            <span>{{ t('courseFiles.columns.size') }}</span>
            <span>{{ t('courseFiles.columns.status') }}</span>
          </div>
          <button
            v-for="node in filteredChildren"
            :key="node.id"
            type="button"
            class="file-row"
            :class="{ selected: selectedNode?.id === node.id }"
            role="row"
            @click="node.kind === 'folder' ? openFolder(node.id) : selectNode(node)"
            @dblclick="node.kind !== 'folder' && primaryAction(node)"
          >
            <span class="file-name" role="cell"><span class="file-icon" :data-type="node.type"><component :is="node.kind === 'folder' ? Folder : nodeIcon(node)" :size="17" /></span><span><strong>{{ node.label }}</strong><small v-if="node.subtitle">{{ node.subtitle }}</small></span></span>
            <span role="cell">{{ displayUpdated(node) }}</span>
            <span role="cell">{{ typeLabel(node) }}</span>
            <span role="cell">{{ displaySize(node) }}</span>
            <span role="cell"><i class="status-dot" :data-state="node.status" />{{ statusLabel(node) }}</span>
          </button>
          <div v-if="!filteredChildren.length" class="file-empty">
            <template v-if="query.trim()">
              <SearchX :size="27" /><strong>{{ t('courseFiles.noSearchResults') }}</strong><span>{{ t('courseFiles.noSearchResultsHelp') }}</span>
              <button type="button" @click="query = ''"><X :size="14" />{{ t('courseFiles.clearSearch') }}</button>
            </template>
            <template v-else>
              <FolderOpen :size="27" /><strong>{{ emptyFolderTitle }}</strong><span>{{ emptyFolderHelp }}</span>
              <button type="button" @click="handleCreateCommand(defaultCreateType)"><Plus :size="14" />{{ t('courseFiles.createHere') }}</button>
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
            <p>{{ statusHelp(inspectedNode) }}</p>
          </section>
          <dl class="file-meta">
            <div><dt>{{ t('courseFiles.meta.location') }}</dt><dd>{{ displayPath(inspectedNode.path) }}</dd></div>
            <div v-if="inspectedNode.kind === 'folder'"><dt>{{ t('courseFiles.meta.items') }}</dt><dd>{{ t('courseFiles.itemCount').replace('{count}', String(inspectedNode.children?.length || 0)) }}</dd></div>
            <div v-if="inspectedNode.lessonId"><dt>{{ t('courseFiles.meta.lesson') }}</dt><dd>{{ lessonLabel(inspectedNode.lessonId) }}</dd></div>
            <div v-if="inspectedNode.revision"><dt>{{ t('courseFiles.meta.version') }}</dt><dd>{{ inspectedNode.revision }}</dd></div>
            <div v-if="inspectedNode.type === 'ppt' && inspectedNode.origin"><dt>{{ t('courseFiles.meta.origin') }}</dt><dd>{{ inspectedNode.origin === 'uploaded' ? t('courseFiles.ppt.uploadedOrigin') : t('courseFiles.ppt.generatedOrigin') }}</dd></div>
            <div v-if="inspectedNode.kind !== 'folder'"><dt>{{ t('courseFiles.meta.size') }}</dt><dd>{{ displaySize(inspectedNode) }}</dd></div>
            <div><dt>{{ t('courseFiles.meta.updated') }}</dt><dd>{{ displayUpdated(inspectedNode) }}</dd></div>
          </dl>
          <section v-if="inspectedNode.kind !== 'folder'" class="relationship-card">
            <small>{{ activeLocale === 'en' ? 'Content source' : '内容来源' }}</small>
            <p>{{ relationship(inspectedNode) }}</p>
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
          <p class="asset-create-help">{{ dialogHelp }}</p>
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
              <Sparkles :size="15" /><strong>{{ t('courseFiles.form.pptGenerated') }}</strong><small>{{ t('courseFiles.form.pptGeneratedHelp') }}</small>
            </button>
            <button type="button" :class="{ active: createForm.mode === 'import' }" @click="createForm.mode = 'import'; createForm.file = null">
              <Upload :size="15" /><strong>{{ t('courseFiles.form.pptUploaded') }}</strong><small>{{ t('courseFiles.form.pptUploadedHelp') }}</small>
            </button>
          </div>
        </section>
        <div v-if="createType === 'ppt' && createForm.mode === 'ai'" class="form-grid">
          <label class="form-field"><span>{{ t('courseFiles.form.slideCount') }}</span><input v-model.number="createForm.count" type="number" min="4" max="80" /></label>
          <label class="form-field"><span>{{ t('courseFiles.form.style') }}</span><select v-model="createForm.style"><option value="simple">{{ t('courseFiles.form.simpleTeaching') }}</option><option value="template">{{ t('courseFiles.form.followTemplate') }}</option></select></label>
        </div>
        <p v-if="createType === 'ppt'" class="ppt-origin-note" :data-mode="createForm.mode">
          <GitBranch :size="14" />{{ createForm.mode === 'ai' ? t('courseFiles.dialog.ppt.generatedPolicy') : t('courseFiles.dialog.ppt.uploadedPolicy') }}
        </p>
        <label v-if="createType === 'ppt' && createForm.mode === 'import'" class="form-field">
          <span>{{ t('courseFiles.form.afterUpload') }}</span>
          <select v-model="createForm.pptImportAction">
            <option value="derive_plan">{{ t('courseFiles.form.derivePlanFromPpt') }}</option>
            <option value="store">{{ t('courseFiles.form.storePptOnly') }}</option>
          </select>
          <small>{{ createForm.pptImportAction === 'derive_plan' ? t('courseFiles.form.derivePlanHelp') : t('courseFiles.form.storePptHelp') }}</small>
        </label>
        <div v-if="createType === 'practice'" class="form-grid">
          <label class="form-field"><span>{{ t('courseFiles.form.exerciseCount') }}</span><input v-model.number="createForm.count" type="number" min="1" max="100" /></label>
          <label class="form-field"><span>{{ t('courseFiles.form.difficulty') }}</span><select v-model="createForm.difficulty"><option value="basic">{{ t('courseFiles.form.basic') }}</option><option value="mixed">{{ t('courseFiles.form.mixed') }}</option><option value="challenge">{{ t('courseFiles.form.challenge') }}</option></select></label>
        </div>
        <label v-if="!['folder', 'outline'].includes(createType)" class="form-field">
          <span>{{ t('courseFiles.form.requirements') }}</span>
          <textarea v-model.trim="createForm.requirements" rows="3" :placeholder="requirementsPlaceholder" />
        </label>
        <section v-if="createType !== 'folder' && (createType !== 'ppt' || createForm.mode === 'import' || createForm.style === 'template')" class="source-picker">
          <div><span>{{ sourceFileLabel }}</span><small>{{ sourceHint }}</small></div>
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
        <div v-else class="office-note"><FileText :size="28" /><strong>{{ t('courseFiles.officeSaved') }}</strong><span>{{ t('courseFiles.officeSavedHelp') }}</span><button type="button" @click="previewAsset && downloadAsset(previewAsset)">{{ t('courseFiles.downloadOriginal') }}</button></div>
      </div>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, BookOpen, BookOpenText, ChevronDown, ChevronRight, ClipboardList, Download, Eye,
  FileText, Folder, FolderOpen, FolderPlus, FolderTree, Home, ListChecks, LoaderCircle,
  GitBranch, Pencil, Plus, Presentation, RefreshCw, Search, SearchX, Sparkles, Trash2, TriangleAlert, Upload, X,
} from 'lucide-vue-next'
import { activeLocale, t } from '../shared/i18n'
import { useCourseStore, type Node } from '../stores/course'
import { useTeacherLessonAuthoringStore, type TeacherLessonProjection } from '../stores/teacherLessonAuthoring'
import http from '../utils/http'
import WorkspaceFolderTreeNode from '../components/WorkspaceFolderTreeNode.vue'

type Asset = { asset_id: string; filename: string; relative_path: string; extension: string; size_bytes: number; category: string; uploaded_at?: string; updated_at?: string }
type Package = { package_id: string; course_id?: string; course_name: string; academic_year: string; term: string; asset_count: number; assets: Asset[]; entries: Array<{ name: string; path?: string; kind: 'folder' }>; updated_at?: string }
type NodeKind = 'folder' | 'managed' | 'asset'
type NodeType = 'root' | 'reference' | 'outline' | 'lesson' | 'lesson_plan' | 'content' | 'material' | 'ppt' | 'practice' | 'folder' | 'file'
type NodeStatus = 'ready' | 'draft' | 'missing' | 'working' | 'stale' | 'uploaded'
type WorkspaceNode = {
  id: string; label: string; kind: NodeKind; type: NodeType; path: string; status: NodeStatus; subtitle?: string;
  lessonId?: string; revision?: string; updatedAt?: string; sizeBytes?: number; asset?: Asset; children?: WorkspaceNode[]; parentId?: string; origin?: 'generated' | 'uploaded'
}
type WorkspaceFolderTreeItem = { id: string; label: string; attention?: boolean; children?: WorkspaceFolderTreeItem[] }
type CreateType = 'outline' | 'lesson_plan' | 'material' | 'ppt' | 'practice' | 'folder'

const props = withDefaults(defineProps<{ embedded?: boolean; courseId?: string; courseTitle?: string }>(), { embedded: false, courseId: '', courseTitle: '' })
const emit = defineEmits<{ (event: 'openOutline'): void; (event: 'createOutline'): void; (event: 'openTeachingPlan', lessonId: string): void; (event: 'openTasks'): void }>()
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
const createOpen = ref(false)
const createType = ref<CreateType>('material')
const createTargetFolderId = ref('')
const importInput = ref<HTMLInputElement>()
const createDialog = ref<HTMLElement>()
const createForm = ref({ lessonId: '', title: '', hours: '2', mode: 'ai', count: 12, style: 'simple', difficulty: 'mixed', requirements: '', pptImportAction: 'derive_plan', file: null as File | null })
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
const otherRootChildren = computed(() => physicalChildren('', 'folder:other').filter(node => ![...managedPaths.value].some(path => node.path === path || path.startsWith(`${node.path}/`) || node.path.startsWith(`${path}/`))))

const treeData = computed<WorkspaceNode[]>(() => {
  const outline: WorkspaceNode = {
    id: 'managed:outline', label: t('courseFiles.names.outline'), kind: 'managed', type: 'outline', path: t('courseFiles.names.outline'),
    status: courseStore.currentDocumentRevision ? 'ready' : courseStore.nodes.length ? 'draft' : 'missing', revision: courseStore.currentDocumentRevision || '', parentId: 'root',
    sizeBytes: courseStore.nodes.length ? textSize(outlineMarkdown()) : undefined,
  }
  const reference: WorkspaceNode = { id: 'folder:reference', label: t('courseFiles.names.reference'), kind: 'folder', type: 'reference', path: '参考资料', status: 'ready', parentId: 'root', children: physicalChildren('参考资料', 'folder:reference') }
  const lessonNodes: WorkspaceNode[] = lessons.value.map(lesson => {
    const working = lesson.plan.revisions.find(item => item.revision_id === lesson.plan.working_revision_id)
    const ppt = lesson.plan.ppt_assets.find(item => item.role === 'primary') || lesson.plan.ppt_assets[0]
    const activeJob = lessonStore.activeJobByLesson(lesson.lesson_unit_id)
    const base = lessonPath(lesson)
    const uploadedPpts = uploadedPptAssets(base)
    const contentNodes = lessonContentNodes(lesson)
    const contentReady = contentNodes.some(hasUsableContent)
    return {
      id: `lesson:${lesson.lesson_unit_id}`, label: `${String(lesson.number).padStart(2, '0')}  ${lesson.title}`, kind: 'folder', type: 'lesson', path: base, status: 'ready', lessonId: lesson.lesson_unit_id, parentId: 'root',
      subtitle: t('courseFiles.lessonHours').replace('{hours}', String(Math.max(1, Math.round(lesson.duration_minutes / 45)))),
      children: [
        { id: `plan:${lesson.lesson_unit_id}`, label: t('courseFiles.names.lessonPlan'), kind: 'managed', type: 'lesson_plan', path: `${base}/教案`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: activeJob?.type?.includes('plan') ? 'working' : lesson.plan.source_state === 'stale' ? 'stale' : working ? (working.status === 'confirmed' ? 'ready' : 'draft') : 'missing', revision: working?.revision_id || '', updatedAt: working?.created_at, sizeBytes: working ? textSize(lessonPlanMarkdown(lesson)) : undefined },
        { id: `content:${lesson.lesson_unit_id}`, label: t('courseFiles.names.content'), kind: 'managed', type: 'content', path: `${base}/正文`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: contentReady ? 'ready' : contentNodes.length ? 'draft' : 'missing', revision: courseStore.currentDocumentRevision, updatedAt: selected.value?.updated_at, sizeBytes: contentReady ? textSize(lessonContentMarkdown(lesson)) : undefined },
        { id: `material:${lesson.lesson_unit_id}`, label: t('courseFiles.names.material'), kind: 'folder', type: 'material', path: `${base}/资料`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: 'ready', children: physicalChildren(`${base}/资料`, `material:${lesson.lesson_unit_id}`) },
        ...(ppt || !uploadedPpts.length ? [{ id: `ppt:${lesson.lesson_unit_id}`, label: t('courseFiles.names.ppt'), kind: 'managed' as const, type: 'ppt' as const, path: `${base}/PPT`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: activeJob?.type?.includes('ppt') ? 'working' as const : ppt?.source_state === 'stale' ? 'stale' as const : ppt ? 'ready' as const : 'missing' as const, revision: ppt?.working_revision_id || '', updatedAt: ppt?.revisions?.at(-1)?.created_at, origin: (ppt || activeJob?.type?.includes('ppt') ? 'generated' : undefined) as 'generated' | undefined, subtitle: ppt || activeJob?.type?.includes('ppt') ? t('courseFiles.ppt.generatedSubtitle') : t('courseFiles.ppt.chooseMethodSubtitle') }] : []),
        ...uploadedPpts.map(asset => ({ id: `ppt-upload:${asset.asset_id}`, label: asset.filename, kind: 'asset' as const, type: 'ppt' as const, path: asset.relative_path, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: 'uploaded' as const, updatedAt: asset.updated_at || asset.uploaded_at, asset, origin: 'uploaded' as const, subtitle: t('courseFiles.ppt.uploadedSubtitle') })),
        { id: `practice:${lesson.lesson_unit_id}`, label: t('courseFiles.names.practice'), kind: 'managed', type: 'practice', path: `${base}/练习`, lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: 'missing' },
      ],
    }
  })
  const other: WorkspaceNode | null = otherRootChildren.value.length ? { id: 'folder:other', label: t('courseFiles.names.other'), kind: 'folder', type: 'folder', path: '', status: 'ready', parentId: 'root', children: otherRootChildren.value } : null
  const courseRoot: WorkspaceNode = {
    id: 'root', label: t('courseFiles.rootName'), kind: 'folder', type: 'root', path: '', status: 'ready',
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
const createOptionIcons = {
  outline: markRaw(FileText), lesson_plan: markRaw(ClipboardList), material: markRaw(BookOpen),
  ppt: markRaw(Presentation), practice: markRaw(ListChecks), folder: markRaw(FolderPlus),
}
type CreateOption = { type: CreateType; label: string; divided?: boolean; targetFolderId?: string }
const createOptions = computed<CreateOption[]>(() => {
  const folder = currentFolder.value
  if (!folder) return []
  if (folder.type === 'root') {
    const outline = folder.children?.find(item => item.type === 'outline')
    const options: CreateOption[] = outline?.status === 'missing'
      ? [{ type: 'outline', label: t('courseFiles.types.outline') }]
      : []
    options.push(
      { type: 'material', label: t('courseFiles.types.material'), divided: Boolean(options.length), targetFolderId: 'folder:reference' },
      { type: 'folder', label: t('courseFiles.types.folder'), targetFolderId: 'folder:reference' },
    )
    return options
  }
  if (folder.type === 'lesson') {
    const options: CreateOption[] = []
    const singletonTypes: CreateType[] = ['lesson_plan', 'ppt', 'practice']
    singletonTypes.forEach(type => {
      const existing = folder.children?.find(item => item.type === type && item.status !== 'missing')
      if (!existing) options.push({ type, label: typeLabel({ type } as WorkspaceNode) })
    })
    options.push({ type: 'material', label: t('courseFiles.types.material'), divided: Boolean(options.length) })
    return options
  }
  return [
    { type: 'material', label: t('courseFiles.types.material') },
    { type: 'folder', label: t('courseFiles.types.folder'), divided: true },
  ]
})
const defaultCreateType = computed<CreateType>(() => createOptions.value[0]?.type || 'material')
const createTargetFolder = computed(() => flatNodes.value.get(createTargetFolderId.value) || currentFolder.value)
const emptyFolderTitle = computed(() => currentFolder.value?.type === 'material' || currentFolder.value?.type === 'reference' ? t('courseFiles.emptyMaterials') : t('courseFiles.emptyFolder'))
const emptyFolderHelp = computed(() => currentFolder.value?.type === 'material'
  ? t('courseFiles.emptyLessonMaterialsHelp')
  : currentFolder.value?.type === 'reference'
    ? t('courseFiles.emptyReferenceHelp')
    : t('courseFiles.emptyFolderHelp'))

const typeLabel = (node: WorkspaceNode) => t(`courseFiles.types.${node.type === 'lesson_plan' ? 'lessonPlan' : node.type}`)
const statusLabel = (node: WorkspaceNode) => t(`courseFiles.status.${node.status}`)
const statusHelp = (node: WorkspaceNode) => t(`courseFiles.statusHelp.${node.status}`)
const nodeIcon = (node: WorkspaceNode) => markRaw(node.type === 'ppt' ? Presentation : node.type === 'practice' ? ListChecks : node.type === 'lesson_plan' ? ClipboardList : node.type === 'content' ? BookOpenText : node.type === 'material' || node.type === 'reference' ? BookOpen : FileText)
const lessonLabel = (id: string) => lessons.value.find(item => item.lesson_unit_id === id)?.title || id
const dateLabel = (value?: string) => value ? new Intl.DateTimeFormat(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value)) : t('courseFiles.notUpdated')
const size = (value: number) => value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`
const displayUpdated = (node: WorkspaceNode) => dateLabel(node.updatedAt || selected.value?.updated_at)
const displaySize = (node: WorkspaceNode) => node.asset ? size(node.asset.size_bytes) : node.sizeBytes ? size(node.sizeBytes) : t('courseFiles.unknownSize')

function relationship(node: WorkspaceNode) {
  if (node.type === 'outline') return t('courseFiles.relationship.outline')
  if (node.type === 'lesson_plan') return t('courseFiles.relationship.lessonPlan')
  if (node.type === 'content') return t('courseFiles.relationship.content')
  if (node.type === 'material' || node.type === 'file') return t('courseFiles.relationship.material')
  if (node.type === 'ppt') return node.origin === 'uploaded' ? t('courseFiles.relationship.pptUploaded') : node.origin === 'generated' ? t('courseFiles.relationship.pptGenerated') : t('courseFiles.relationship.pptPending')
  if (node.type === 'practice') return t('courseFiles.relationship.practice')
  return t('courseFiles.relationship.file')
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
}
function selectNode(node: WorkspaceNode) { selectedNode.value = node }

function primaryLabel(node: WorkspaceNode) {
  if (node.kind === 'folder') return t('courseFiles.openFolder')
  if (node.asset) return t('courseFiles.preview')
  if (node.type === 'outline' || node.type === 'lesson_plan') return node.status === 'missing' ? t('courseFiles.create') : t('courseFiles.openEdit')
  if (node.type === 'content') return t('courseFiles.openContent')
  if (node.type === 'ppt') return node.status === 'missing' ? t('courseFiles.createPpt') : t('courseFiles.openPpt')
  if (node.type === 'practice') return node.status === 'missing' ? t('courseFiles.createPractice') : t('courseFiles.openPractice')
  return t('courseFiles.open')
}
function primaryIcon(node: WorkspaceNode) { return markRaw(node.kind === 'folder' ? FolderOpen : node.asset ? Eye : node.status === 'missing' ? Sparkles : Pencil) }
function primaryDisabled(_node: WorkspaceNode) { return false }
function lessonPlanRevision(lessonId: string) { return lessons.value.find(item => item.lesson_unit_id === lessonId)?.plan.working_revision_id || '' }

async function primaryAction(node: WorkspaceNode) {
  selectedNode.value = node
  if (node.kind === 'folder') { openFolder(node.id); return }
  if (node.asset) { await previewFile(node.asset); return }
  if (node.type === 'outline') { node.status === 'missing' ? openCreateDialog('outline') : emit('openOutline'); return }
  if (node.type === 'lesson_plan') { node.status === 'missing' ? openCreateDialog('lesson_plan', node.lessonId) : emit('openTeachingPlan', node.lessonId || ''); return }
  if (node.type === 'content') { router.push({ name: 'learning', params: { courseId: props.courseId, nodeId: node.lessonId } }); return }
  if (node.type === 'ppt') { node.status === 'missing' ? openCreateDialog('ppt', node.lessonId) : router.push({ name: 'ppt-workspace', params: { courseId: props.courseId }, query: { lesson: node.lessonId } }); return }
  if (node.type === 'practice') { node.status === 'missing' ? openCreateDialog('practice', node.lessonId) : openPractice(node.lessonId || ''); return }
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
    if (props.courseId) await lessonStore.load(props.courseId).catch(() => undefined)
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
async function reloadAll() { busy.value = true; try { await Promise.all([refresh(), props.courseId ? courseStore.loadCourse(props.courseId, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true }) : Promise.resolve()]) } finally { busy.value = false } }
async function reloadPackage() { if (selected.value) selected.value = (await http.get(`/api/teacher-course-spaces/${selected.value.package_id}`)).data }

function handleCreateCommand(command: unknown) {
  const type = String(command || '') as CreateType
  const option = createOptions.value.find(item => item.type === type)
  if (!option) return
  if (type === 'outline') {
    const outline = flatNodes.value.get('managed:outline')
    if (outline?.status === 'missing') emit('createOutline')
    else emit('openOutline')
    return
  }
  openCreateDialog(type, '', option.targetFolderId)
}
function openCreateDialog(command: CreateType | string, lessonId: unknown = '', targetFolderId = '') {
  const type = command as CreateType
  if (type === 'outline') {
    handleCreateCommand(type)
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
const dialogHelp = computed(() => t(`courseFiles.dialog.${createType.value}.help`))
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
const sourceHint = computed(() => createType.value === 'ppt'
  ? createForm.value.mode === 'import' ? t('courseFiles.dialog.ppt.uploadSourceHint') : t('courseFiles.dialog.ppt.generatedSourceHint')
  : t(`courseFiles.dialog.${createType.value}.sourceHint`))
const submitLabel = computed(() => {
  if (createType.value === 'ppt') return createForm.value.mode === 'import' ? t('courseFiles.form.importOldDeck') : t('courseFiles.form.generatePpt')
  if (createForm.value.file) return t('courseFiles.form.importAndCreate')
  if (createType.value === 'folder') return t('courseFiles.createFolder')
  if (createType.value === 'material') return t('courseFiles.createFile')
  return t('courseFiles.form.startCreate')
})
const submitDisabled = computed(() => busy.value || needsLesson.value && !createForm.value.lessonId || createType.value === 'ppt' && createForm.value.mode === 'import' && !createForm.value.file)
function captureImportFile(event: Event) { const input = event.target as HTMLInputElement; createForm.value.file = input.files?.[0] || null; input.value = '' }
function resetCreateForm() {
  createTargetFolderId.value = ''
  createForm.value = { lessonId: '', title: '', hours: '2', mode: 'ai', count: 12, style: 'simple', difficulty: 'mixed', requirements: '', pptImportAction: 'derive_plan', file: null }
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
      openPractice(createForm.value.lessonId)
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
.file-layout { height:100%; min-height:0; display:grid; grid-template-columns:260px minmax(520px,1fr) 288px; overflow:hidden; background:#fff; }
.file-tree-pane,.file-list-pane,.file-inspector { min-height:0; overflow:hidden; }
.file-tree-pane { display:grid; grid-template-rows:auto minmax(0,1fr) auto; border-right:1px solid var(--lz-border); background:#f8fafc; }
.pane-heading { min-height:52px; display:flex; align-items:center; justify-content:space-between; gap:8px; padding:0 13px; border-bottom:1px solid #e8edf4; }
.pane-heading>span { min-width:0; display:flex; align-items:center; gap:7px; color:#475569; }.pane-heading>span>svg{color:#64748b}.pane-heading strong { overflow:hidden; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }.pane-heading button,.file-inspector header>button { width:28px; height:28px; display:grid; place-items:center; padding:0; border:0; border-radius:6px; background:transparent; color:var(--lz-text-muted); cursor:pointer; }.pane-heading button:hover,.file-inspector header>button:hover{color:var(--lz-text-strong);background:#eef2f7}
.folder-navigation { min-height:0; overflow:auto; padding:8px 7px 14px; }
.folder-navigation>ul { margin:0; padding:0; list-style:none; }
.file-tree-pane footer { display:grid; gap:8px; padding:12px 14px; border-top:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:10px; }.file-tree-pane footer button { display:flex; align-items:center; gap:6px; padding:0; border:0; background:transparent; color:var(--lz-text-secondary); font-size:11px; font-weight:700; cursor:pointer; }
.file-list-pane { display:flex; flex-direction:column; background:#fff; }
.list-toolbar { min-height:54px; flex:none; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 16px; border-bottom:1px solid var(--lz-border); }.list-toolbar nav { min-width:0; display:flex; align-items:center; gap:3px; overflow:hidden; }.list-toolbar nav button { display:flex; align-items:center; gap:5px; min-width:0; padding:4px; border:0; background:transparent; color:var(--lz-text-secondary); font-size:11px; white-space:nowrap; cursor:pointer; }.list-toolbar nav svg { flex:none; color:#94a3b8; }
.toolbar-actions { display:flex; align-items:center; gap:8px; }.list-search { width:226px; height:36px; display:flex; align-items:center; gap:7px; padding:0 9px 0 11px; border:1px solid transparent; border-radius:9px; color:#94a3b8; background:#f1f5f9; transition:border-color .15s ease,background .15s ease,box-shadow .15s ease; }.list-search:focus-within { border-color:var(--lz-brand-border); background:#fff; box-shadow:0 0 0 3px var(--lz-brand-soft); }.list-search input { min-width:0; width:100%; border:0; outline:0; color:var(--lz-text-strong); background:transparent; font-size:11px; }.list-search input::-webkit-search-cancel-button { display:none; }.list-search button { width:24px; height:24px; flex:none; display:grid; place-items:center; padding:0; border:0; border-radius:6px; color:#64748b; background:transparent; cursor:pointer; }.list-search button:hover { color:var(--lz-text-strong); background:#e2e8f0; }.new-button { height:36px; display:flex; align-items:center; gap:6px; padding:0 12px; border:1px solid #4f46e5; border-radius:9px; background:#4f46e5; color:#fff; font-size:11px; font-weight:700; cursor:pointer; }.new-button:hover { background:#4338ca; }.new-button:focus-visible,.list-search button:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.folder-title { min-height:58px; flex:none; display:flex; align-items:center; justify-content:space-between; padding:8px 16px; }.folder-title h2 { margin:0; font-size:16px; }.folder-title>span { color:var(--lz-text-muted); font-size:10px; }
.file-table { min-height:0; flex:1; overflow:auto; padding:0 10px 18px; }.file-table__head,.file-row { display:grid; grid-template-columns:minmax(220px,1.65fr) 112px 82px 68px 88px; align-items:center; gap:10px; }.file-table__head { min-height:34px; padding:0 9px; border-bottom:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:9px; font-weight:700; }.file-table__head span:nth-child(4),.file-row>span:nth-child(4){text-align:right}.file-row { width:100%; min-height:48px; padding:5px 9px; border:0; border-bottom:1px solid #edf1f6; background:transparent; color:var(--lz-text-secondary); text-align:left; font-size:10px; cursor:pointer; }.file-row:hover,.file-row:focus-visible{outline:0;background:#f7f9fc}.file-row.selected { background:#e9eeff; }.file-name { min-width:0; display:flex; align-items:center; gap:9px; }.file-name>span:last-child { min-width:0; display:grid; gap:2px; }.file-name strong,.file-name small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.file-name strong { color:var(--lz-text-strong); font-size:11px; }.file-name small { color:var(--lz-text-muted); font-size:9px; }.file-icon { width:28px; height:28px; flex:none; display:grid; place-items:center; border-radius:7px; background:#f1f5f9; color:#64748b; }.file-icon[data-type="outline"],.file-icon[data-type="lesson_plan"],.file-icon[data-type="ppt"] { background:#eef2ff; color:#4f46e5; }.status-dot { width:6px; height:6px; display:inline-block; margin-right:5px; border-radius:50%; background:#94a3b8; }.status-dot[data-state="ready"],.status-dot[data-state="uploaded"] { background:#10b981; }.status-dot[data-state="working"] { background:#6366f1; }.status-dot[data-state="stale"] { background:#f97316; }.status-dot[data-state="missing"] { background:#cbd5e1; }
.file-empty { min-height:260px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:7px; color:var(--lz-text-muted); text-align:center; }.file-empty strong { color:var(--lz-text-secondary); font-size:13px; }.file-empty span { max-width:300px; font-size:11px; line-height:1.55; }.file-empty button { display:flex; align-items:center; gap:5px; margin-top:6px; padding:7px 10px; border:1px solid var(--lz-border); border-radius:7px; background:#fff; color:#4f46e5; font-size:11px; cursor:pointer; }.file-empty button:hover { border-color:var(--lz-brand-border); background:var(--lz-brand-soft); }
.runtime-note { margin:0; padding:8px 16px; border-top:1px solid var(--lz-border); color:#9a3412; background:#fff7ed; font-size:11px; }
.file-inspector { display:flex; flex-direction:column; border-left:1px solid var(--lz-border); background:#fbfcfe; }.file-inspector>header { display:grid; grid-template-columns:38px minmax(0,1fr) auto; align-items:center; gap:9px; padding:16px 14px 13px; border-bottom:1px solid var(--lz-border); }.inspector-icon { width:38px; height:38px; display:grid; place-items:center; border-radius:10px; background:#eef2ff; color:#4f46e5; }.file-inspector header div { min-width:0; display:grid; gap:2px; }.file-inspector header small { color:var(--lz-text-muted); font-size:10px; }.file-inspector header strong { overflow:hidden; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }
.inspector-status { padding:12px 14px; border-bottom:1px solid #e8edf4; }.inspector-status>span { display:flex; align-items:center; gap:6px; color:var(--lz-text-secondary); font-size:10px; font-weight:700; }.inspector-status i { width:7px; height:7px; border-radius:50%; background:#94a3b8; }.inspector-status[data-state="ready"] i,.inspector-status[data-state="uploaded"] i { background:#10b981; }.inspector-status[data-state="working"] i { background:#6366f1; }.inspector-status[data-state="stale"] i { background:#f97316; }.inspector-status p { margin:5px 0 0; color:var(--lz-text-muted); font-size:9px; line-height:1.5; }
.file-meta { display:grid; gap:0; margin:8px 14px 0; }.file-meta div { display:grid; grid-template-columns:66px minmax(0,1fr); gap:8px; padding:8px 0; border-bottom:1px solid #e8edf4; font-size:10px; }.file-meta dt { color:var(--lz-text-muted); }.file-meta dd { margin:0; overflow-wrap:anywhere; color:var(--lz-text-secondary); }
.relationship-card { margin:4px 14px 0; padding:12px 0; border-bottom:1px solid #e8edf4; }.relationship-card small { color:#4f46e5; font-size:9px; font-weight:700; }.relationship-card p { margin:5px 0 0; color:#596579; font-size:9px; line-height:1.6; }
.inspector-actions { display:grid; gap:7px; margin-top:auto; padding:14px; border-top:1px solid var(--lz-border); }.inspector-actions button { min-height:34px; display:flex; align-items:center; justify-content:center; gap:6px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; color:var(--lz-text-secondary); font-size:11px; font-weight:700; cursor:pointer; }.inspector-actions button.primary { border-color:#4f46e5; background:#4f46e5; color:#fff; }.inspector-actions button.danger { color:#b91c1c; }.inspector-actions button:disabled { opacity:.45; cursor:not-allowed; }
.inspector-empty,.space-state { height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; color:var(--lz-text-muted); text-align:center; }.inspector-empty strong,.space-state strong { color:var(--lz-text-secondary); font-size:13px; }.inspector-empty span,.space-state span { max-width:220px; font-size:11px; line-height:1.5; }.space-state button { padding:7px 12px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; }
.asset-create-overlay { position:fixed; inset:0; z-index:2600; display:grid; place-items:center; padding:14px; background:rgba(15,23,42,.38); backdrop-filter:blur(2px); }.asset-create-dialog { width:min(560px,calc(100vw - 28px)); max-height:calc(100vh - 28px); overflow:auto; padding:0 18px 18px; border:1px solid rgba(255,255,255,.65); border-radius:14px; background:#fff; box-shadow:0 24px 70px rgba(15,23,42,.22); }.asset-create-header { position:sticky; top:0; z-index:1; display:flex; align-items:center; justify-content:space-between; min-height:48px; margin:0 -18px 14px; padding:0 18px; border-bottom:1px solid #eef2f7; background:rgba(255,255,255,.96); }.asset-create-header strong { font-size:14px; }.asset-create-header button { width:30px; height:30px; display:grid; place-items:center; border:0; border-radius:7px; color:var(--lz-text-muted); background:transparent; cursor:pointer; }.asset-create-header button:hover { background:#f1f5f9; color:var(--lz-text-strong); }
.asset-create-help { margin:0 0 14px; color:var(--lz-text-secondary); font-size:11px; line-height:1.55; }
.create-location{min-height:36px;display:grid;grid-template-columns:18px auto minmax(0,1fr);align-items:center;gap:6px;padding:0 10px;border:1px solid #e2e8f0;border-radius:8px;color:#64748b;background:#f8fafc;font-size:10px}.create-location strong{overflow:hidden;color:#334155;font-weight:650;text-overflow:ellipsis;white-space:nowrap}.asset-form { display:grid; gap:13px; padding-top:15px; }.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:11px; }.form-field { display:grid; gap:6px; }.form-field>span,.source-picker>div>span { color:var(--lz-text-secondary); font-size:10px; font-weight:700; }.form-field>small { color:var(--lz-text-muted); font-size:9px; line-height:1.5; }.form-field input,.form-field select,.form-field textarea { width:100%; min-height:38px; padding:8px 10px; border:1px solid var(--lz-border); border-radius:8px; outline:0; color:var(--lz-text-strong); background:#fff; font:inherit; font-size:11px; }.form-field textarea { resize:vertical; }.form-field input:focus,.form-field select:focus,.form-field textarea:focus { border-color:#6366f1; box-shadow:0 0 0 3px rgba(99,102,241,.1); }.source-picker { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:11px; border:1px dashed #cbd5e1; border-radius:9px; }.source-picker>div { display:grid; gap:3px; }.source-picker small { color:var(--lz-text-muted); font-size:9px; }.source-picker button { max-width:220px; display:flex; align-items:center; gap:6px; overflow:hidden; padding:7px 9px; border:1px solid var(--lz-border); border-radius:7px; background:#fff; color:#4f46e5; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.ppt-origin-picker { display:grid; gap:7px; }.ppt-origin-picker>span { color:var(--lz-text-secondary); font-size:10px; font-weight:700; }.ppt-origin-picker>div { display:grid; grid-template-columns:1fr 1fr; gap:8px; }.ppt-origin-picker button { min-width:0; display:grid; grid-template-columns:20px minmax(0,1fr); gap:1px 7px; padding:9px; border:1px solid var(--lz-border); border-radius:9px; color:var(--lz-text-secondary); background:#fff; text-align:left; cursor:pointer; }.ppt-origin-picker button svg { grid-row:1/3; align-self:center; color:#64748b; }.ppt-origin-picker button strong { font-size:11px; }.ppt-origin-picker button small { overflow:hidden; color:var(--lz-text-muted); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }.ppt-origin-picker button.active { border-color:var(--lz-brand); color:var(--lz-brand-strong); background:var(--lz-brand-soft); }.ppt-origin-picker button.active svg { color:var(--lz-brand); }.ppt-origin-note { display:flex; align-items:flex-start; gap:7px; margin:0; padding:9px 10px; border:1px solid #e0e7ff; border-radius:8px; color:#4f46e5; background:#f8faff; font-size:10px; line-height:1.5; }.ppt-origin-note[data-mode="import"] { border-color:#e2e8f0; color:#475569; background:#f8fafc; }
.dialog-actions { display:flex; justify-content:flex-end; gap:8px; padding-top:4px; }.dialog-actions button { min-height:34px; padding:0 13px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; color:var(--lz-text-secondary); font-size:11px; font-weight:700; cursor:pointer; }.dialog-actions button.primary { border-color:#4f46e5; background:#4f46e5; color:#fff; }.dialog-actions button:disabled { opacity:.45; cursor:not-allowed; }
.preview-surface { min-height:420px; display:grid; place-items:center; }.preview-surface img { max-width:100%; max-height:75vh; }.preview-surface iframe { width:100%; min-height:72vh; border:0; }.office-note { display:flex; flex-direction:column; align-items:center; gap:8px; color:var(--lz-text-muted); text-align:center; }.office-note strong { color:var(--lz-text-strong); }.office-note button { padding:7px 10px; border:1px solid var(--lz-border); border-radius:7px; background:#fff; }
.sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); }.spin { animation:spin 1s linear infinite; }@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:1080px) { .file-layout { grid-template-columns:220px minmax(420px,1fr) 250px; }.list-search { display:none; }.file-table__head,.file-row { grid-template-columns:minmax(190px,1.5fr) 98px 72px 78px; }.file-table__head span:nth-child(4),.file-row>span:nth-child(4) { display:none; } }
@media (max-width:760px) { .file-layout { grid-template-columns:1fr; grid-template-rows:160px minmax(0,1fr) auto; }.file-tree-pane { display:grid; grid-template-rows:42px minmax(0,1fr); overflow:hidden; border-right:0; border-bottom:1px solid var(--lz-border); }.pane-heading { min-height:42px; padding:0 10px; }.folder-navigation { overflow:auto; padding:5px 7px 10px; }.file-tree-pane footer { display:none; }.file-inspector { max-height:42vh; border-left:0; border-top:1px solid var(--lz-border); }.file-inspector .relationship-card { display:none; }.inspector-actions { grid-template-columns:1fr auto auto; }.list-toolbar { min-height:46px; padding:0 10px; }.list-toolbar nav button { max-width:100px; }.folder-title { min-height:52px; padding:7px 11px; }.folder-title h2 { font-size:15px; }.file-table { padding:0 6px 12px; }.file-table__head,.file-row { grid-template-columns:minmax(180px,1fr) 82px; }.file-table__head span:nth-child(2),.file-row>span:nth-child(2),.file-table__head span:nth-child(3),.file-row>span:nth-child(3),.file-table__head span:nth-child(4),.file-row>span:nth-child(4) { display:none; }.form-grid { grid-template-columns:1fr; } }
</style>
