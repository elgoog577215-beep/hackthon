<template>
  <main class="course-library teacher-space">
    <header class="library-header">
      <div class="library-header__copy">
        <p>{{ t('teacherCourseSpace.eyebrow', '教师课程空间') }}</p>
        <h1>{{ t('teacherCourseSpace.title', '课程文件库') }}</h1>
        <span>{{ t('teacherCourseSpace.subtitle', '按课程、学年和目录保存原始资料。') }}</span>
      </div>
    </header>

    <section
      class="knowledge-space"
      :class="{
        'knowledge-space--first-run': !packages.length && !selected,
        'knowledge-space--creating': !selected,
      }"
    >
      <aside v-if="packages.length" class="knowledge-sidebar">
        <div class="sidebar-heading">
          <strong>{{ t('teacherCourseSpace.myCourses', '我的课程') }}</strong>
          <button type="button" @click="selected = null">{{ t('teacherCourseSpace.new', '新建') }}</button>
        </div>
        <button v-for="item in packages" :key="item.package_id" class="package-item" :class="{ active: item.package_id === selected?.package_id }" type="button" @click="openPackage(item.package_id)">
          <strong>{{ item.course_name }}</strong>
          <span>{{ t('teacherCourseSpace.courseMeta', '{year} / {term} / {count} 份资料')
            .replace('{year}', item.academic_year)
            .replace('{term}', termLabel(item.term))
            .replace('{count}', String(item.asset_count)) }}</span>
        </button>

        <template v-if="selected">
          <div class="sidebar-divider" />
          <div class="sidebar-heading"><strong>{{ t('teacherCourseSpace.fileDirectory', '文件目录') }}</strong></div>
          <el-tree
            class="folder-tree"
            :data="treeData"
            node-key="id"
            :current-node-key="currentPath || 'root'"
            :expand-on-click-node="false"
            :default-expand-all="true"
            :highlight-current="true"
            @node-click="handleTreeClick"
          >
            <template #default="{ data }">
              <span class="tree-node" :class="`tree-node--${data.kind}`">
                <FolderOpen v-if="data.kind === 'root' || data.kind === 'folder'" :size="15" />
                <FileText v-else :size="14" />
                <span>{{ data.label }}</span>
              </span>
            </template>
          </el-tree>
        </template>
      </aside>

      <section v-if="!selected" class="workspace-create">
        <div class="workspace-create__copy">
          <strong>{{ t('teacherCourseSpace.createTitle', '新建课程文件库') }}</strong>
          <span>{{ t('teacherCourseSpace.createHelp', '空白开始，或按学校课程材料目录创建。') }}</span>
        </div>
        <form @submit.prevent="createPackage">
          <label class="create-field create-field--course">
            <span>{{ t('teacherCourseSpace.courseName', '课程名称') }}</span>
            <input
              v-model.trim="form.course_name"
              required
              :placeholder="t('teacherCourseSpace.courseNamePlaceholder', '如：数据结构')"
            />
          </label>
          <label class="create-field">
            <span>{{ t('teacherCourseSpace.academicYear', '学年') }}</span>
            <input
              v-model.trim="form.academic_year"
              required
              inputmode="numeric"
              :placeholder="t('teacherCourseSpace.academicYearPlaceholder', '如：2025-2026')"
            />
          </label>
          <label class="create-field create-field--term">
            <span>{{ t('teacherCourseSpace.term', '学期') }}</span>
            <select v-model="form.term">
              <option value="春季">{{ t('teacherCourseSpace.terms.spring', '春季') }}</option>
              <option value="秋季">{{ t('teacherCourseSpace.terms.autumn', '秋季') }}</option>
              <option value="夏季">{{ t('teacherCourseSpace.terms.summer', '夏季') }}</option>
            </select>
          </label>
          <fieldset class="create-template">
            <legend>{{ t('teacherCourseSpace.startMode', '创建方式') }}</legend>
            <button
              type="button"
              :aria-pressed="form.template === 'blank'"
              @click="form.template = 'blank'"
            >
              <FilePlus2 :size="16" />
              <span><strong>{{ t('teacherCourseSpace.templates.blank', '空白文件库') }}</strong></span>
            </button>
            <button
              type="button"
              :aria-pressed="form.template === 'school_course_materials'"
              @click="form.template = 'school_course_materials'"
            >
              <Folders :size="16" />
              <span><strong>{{ t('teacherCourseSpace.templates.school', '学校材料模板') }}</strong></span>
            </button>
          </fieldset>
          <button class="primary-button create-submit" :disabled="busy">
            <LoaderCircle v-if="busy" :size="15" class="spin" />
            <Plus v-else :size="15" />
            {{ busy ? t('teacherCourseSpace.creating', '正在创建') : t('teacherCourseSpace.createAction', '创建文件库') }}
          </button>
        </form>
        <p v-if="status" class="runtime-note" role="status">{{ status }}</p>
      </section>

      <section v-if="selected" class="folder-workbench">
        <div class="folder-workbench__topline">
          <nav class="workspace-breadcrumb" :aria-label="t('teacherCourseSpace.filePath', '文件路径')">
            <button type="button" @click="openFolder('')"><Home :size="14" />{{ t('teacherCourseSpace.courseMaterials', '课程资料') }}</button>
            <template v-for="crumb in breadcrumbs" :key="crumb.path">
              <ChevronRight :size="14" /><button type="button" @click="openFolder(crumb.path)">{{ crumb.label }}</button>
            </template>
          </nav>
          <button class="text-button" type="button" @click="downloadPackage"><Download :size="14" />{{ t('teacherCourseSpace.downloadCourseZip', '下载整课 ZIP') }}</button>
        </div>

        <div class="folder-workbench__heading">
          <div>
            <p>{{ selected.academic_year }} / {{ termLabel(selected.term) }}</p>
            <h2>{{ currentFolderLabel }}</h2>
            <span>{{ currentPath
              ? t('teacherCourseSpace.currentFolderHelp', '正在查看此目录下的资料。')
              : t('teacherCourseSpace.rootFolderHelp', '课程根目录。可建立目录或直接导入资料。') }}</span>
          </div>
          <div class="folder-actions">
            <button class="secondary-button" type="button" @click="addFolder"><FolderPlus :size="15" />{{ t('teacherCourseSpace.newFolder', '新建文件夹') }}</button>
            <button class="primary-button" type="button" :disabled="busy" @click="fileInput?.click()"><Upload :size="15" />{{ t('teacherCourseSpace.uploadHere', '上传到此处') }}</button>
          </div>
        </div>

        <input ref="folderInput" class="sr-only" type="file" multiple webkitdirectory @change="pickFolder" />
        <input ref="fileInput" class="sr-only" type="file" multiple @change="pickFiles" />
        <div class="context-import" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="dropFiles">
          <FolderUp :size="18" />
          <span>{{ t('teacherCourseSpace.dropHelp', '把文件或文件夹拖到这里，导入到“{folder}”').replace('{folder}', currentFolderLabel) }}</span>
          <button class="text-button" type="button" :disabled="busy" @click="folderInput?.click()">{{ t('teacherCourseSpace.chooseFolder', '选择整个文件夹') }}</button>
        </div>

        <div class="folder-list" :class="{ 'folder-list--empty': !currentChildren.length }">
          <template v-if="currentChildren.length">
            <div class="folder-list__columns">
              <span>{{ t('teacherCourseSpace.columns.name', '名称') }}</span>
              <span>{{ t('teacherCourseSpace.columns.type', '类型') }}</span>
              <span>{{ t('teacherCourseSpace.columns.size', '大小') }}</span>
              <span>{{ t('teacherCourseSpace.columns.actions', '操作') }}</span>
            </div>
            <div v-for="node in currentChildren" :key="node.id" class="folder-row" :class="`folder-row--${node.kind}`" @dblclick="node.kind === 'folder' ? openNode(node) : previewNode(node)">
              <button class="folder-row__name" type="button" @click="openNode(node)">
                <Folder v-if="node.kind === 'folder'" :size="18" /><FileText v-else :size="17" />
                <span>{{ node.label }}</span>
              </button>
              <span>{{ node.kind === 'folder' ? t('teacherCourseSpace.folder', '文件夹') : node.asset?.extension?.replace('.', '').toUpperCase() }}</span>
              <span>{{ node.asset ? size(node.asset.size_bytes) : '-' }}</span>
              <div class="row-actions">
                <button v-if="node.asset" class="row-action" type="button" @click.stop="downloadAsset(node.asset)"><Download :size="14" />{{ t('teacherCourseSpace.download', '下载') }}</button>
                <button v-if="node.kind === 'folder' || node.asset" class="row-action row-action--danger" type="button" @click.stop="deleteNode(node)"><Trash2 :size="14" />{{ t('teacherCourseSpace.delete', '删除') }}</button>
              </div>
            </div>
          </template>
          <div v-else class="folder-empty">
            <FolderOpen :size="28" />
            <strong>{{ t('teacherCourseSpace.folderEmpty', '这个目录还是空的') }}</strong>
            <span>{{ t('teacherCourseSpace.folderEmptyHelp', '可把电脑里的文件或文件夹拖进来，也可以先新建下一层目录。') }}</span>
          </div>
        </div>
        <p v-if="status" class="runtime-note" role="status">{{ status }}</p>
      </section>
    </section>
    <el-dialog v-model="previewOpen" :title="previewAsset?.filename || t('teacherCourseSpace.preview', '文件预览')" :width="previewDialogWidth" top="4vh" class="file-preview-dialog" destroy-on-close @closed="closePreview">
      <div class="preview-surface" :class="`preview-surface--${previewKind}`">
        <img v-if="previewKind === 'image'" class="file-preview-image" :src="previewUrl" :alt="previewAsset?.filename" />
        <iframe v-else-if="previewKind === 'browser'" class="file-preview-frame" :src="previewUrl" :title="previewAsset?.filename" />
        <div v-else class="office-preview-note">
          <FileText :size="30" />
          <strong>{{ t('teacherCourseSpace.officeSaved', '此 Office 文件已安全保存') }}</strong>
          <span>{{ t('teacherCourseSpace.officeSavedHelp', 'Word、Excel 和 PPT 可下载后用本机 Office 打开；PDF、图片和文本支持页内预览。') }}</span>
          <button class="text-button" type="button" @click="previewAsset && downloadAsset(previewAsset)"><Download :size="14" />{{ t('teacherCourseSpace.downloadOriginal', '下载原件') }}</button>
        </div>
      </div>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChevronRight, Download, FilePlus2, FileText, Folder, FolderOpen, FolderPlus,
  FolderUp, Folders, Home, LoaderCircle, Plus, Trash2, Upload,
} from 'lucide-vue-next'
import { activeLocale, t } from '@/shared/i18n'
import http from '@/utils/http'

type Asset = { asset_id: string; filename: string; relative_path: string; extension: string; size_bytes: number; category: string }
type Entry = { name: string; path?: string; kind: 'folder' }
type TreeNode = { id: string; label: string; path: string; kind: 'root' | 'folder' | 'file'; children?: TreeNode[]; asset?: Asset }
type UploadCandidate = { file: File; relativePath: string }
type FileSystemEntryLike = {
  isFile: boolean
  isDirectory: boolean
  name: string
  file?: (success: (file: File) => void, failure?: (error: DOMException) => void) => void
  createReader?: () => { readEntries: (success: (entries: FileSystemEntryLike[]) => void, failure?: (error: DOMException) => void) => void }
}

const packages = ref<any[]>([])
const selected = ref<any | null>(null)
const currentPath = ref('')
const busy = ref(false)
const dragging = ref(false)
const status = ref('')
const previewOpen = ref(false)
const previewAsset = ref<Asset | null>(null)
const previewImageSize = ref<{ width: number; height: number } | null>(null)
const folderInput = ref<HTMLInputElement>()
const fileInput = ref<HTMLInputElement>()
const form = ref({ course_name: '', academic_year: '2025-2026', term: '春季', template: 'school_course_materials' })

const termLabel = (term: string) => ({
  春季: t('teacherCourseSpace.terms.spring', '春季'),
  秋季: t('teacherCourseSpace.terms.autumn', '秋季'),
  夏季: t('teacherCourseSpace.terms.summer', '夏季'),
}[term] || term)
const localizedError = (error: any, key: string, fallback: string) => (
  activeLocale.value === 'zh' && error?.response?.data?.detail
    ? String(error.response.data.detail)
    : t(key, fallback)
)

const treeData = computed<TreeNode[]>(() => {
  const root: TreeNode = { id: 'root', label: t('teacherCourseSpace.courseMaterials', '课程资料'), path: '', kind: 'root', children: [] }
  const folders = new Map<string, TreeNode>([['', root]])
  const ensureFolder = (path: string) => {
    const parts = path.split('/').filter(Boolean)
    let parent = root
    let accumulated = ''
    for (const part of parts) {
      accumulated = accumulated ? `${accumulated}/${part}` : part
      let node = folders.get(accumulated)
      if (!node) {
        node = { id: `folder:${accumulated}`, label: part, path: accumulated, kind: 'folder', children: [] }
        parent.children?.push(node)
        folders.set(accumulated, node)
      }
      parent = node
    }
    return parent
  }
  const assets = selected.value?.assets || []
  for (const entry of (selected.value?.entries || []) as Entry[]) if (entry.kind === 'folder') ensureFolder(entry.path || entry.name)
  for (const asset of assets as Asset[]) {
    const parts = asset.relative_path.split('/')
    const parent = ensureFolder(parts.slice(0, -1).join('/'))
    parent.children?.push({ id: `asset:${asset.asset_id}`, label: asset.filename, path: asset.relative_path, kind: 'file', asset })
  }
  const sortNodes = (nodes?: TreeNode[]) => {
    nodes?.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN', { numeric: true }) || Number(a.kind !== 'folder') - Number(b.kind !== 'folder'))
    nodes?.forEach(node => sortNodes(node.children))
  }
  sortNodes(root.children)
  return [root]
})

function findFolder(node: TreeNode, path: string): TreeNode | undefined {
  if (node.path === path && (node.kind === 'root' || node.kind === 'folder')) return node
  for (const child of node.children || []) { const found = findFolder(child, path); if (found) return found }
}
const currentChildren = computed(() => {
  const root = treeData.value[0]
  return root ? findFolder(root, currentPath.value)?.children || [] : []
})
const breadcrumbs = computed(() => {
  let path = ''
  return currentPath.value.split('/').filter(Boolean).map(label => ({ label, path: path = path ? `${path}/${label}` : label }))
})
const currentFolderLabel = computed(() => breadcrumbs.value.at(-1)?.label || t('teacherCourseSpace.courseMaterials', '课程资料'))
const size = (value: number) => value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`

async function refresh() {
  try { packages.value = (await http.get('/api/teacher-course-spaces')).data }
  catch { status.value = t('teacherCourseSpace.errors.serviceUnavailable', '课程空间服务暂不可用，请确认后端已启动后重试。') }
}
async function openPackage(id: string) { selected.value = (await http.get(`/api/teacher-course-spaces/${id}`)).data; currentPath.value = '' }
async function createPackage() {
  busy.value = true
  status.value = ''
  try {
    const data = (await http.post('/api/teacher-course-spaces', form.value)).data
    await refresh()
    await openPackage(data.package_id)
    form.value.course_name = ''
  } catch (error: any) {
    status.value = localizedError(error, 'teacherCourseSpace.errors.createFailed', '创建文件库失败，请检查课程名称和学年后重试。')
  } finally { busy.value = false }
}
function openFolder(path: string) { currentPath.value = path }
function handleTreeClick(node: TreeNode) { if (node.kind === 'root' || node.kind === 'folder') openFolder(node.path) }
function openNode(node: TreeNode) { if (node.kind === 'folder') openFolder(node.path) }
async function previewNode(node: TreeNode) {
  if (!node.asset || !selected.value) return
  try {
    const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${node.asset.asset_id}/preview`, { responseType: 'blob' })
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(response.data)
    previewAsset.value = node.asset
    previewImageSize.value = previewKind.value === 'image' ? await imageSize(previewUrl.value) : null
    previewOpen.value = true
  } catch { ElMessage.error(t('teacherCourseSpace.errors.previewFailed', '文件预览读取失败，请重试。')) }
}
function directoryPaths(paths: string[]) {
  const folders = new Set<string>()
  paths.forEach(path => {
    const parts = path.split('/').filter(Boolean)
    for (let index = 1; index < parts.length; index += 1) folders.add(parts.slice(0, index).join('/'))
  })
  return [...folders]
}
function pickFolder(event: Event) {
  const input = event.target as HTMLInputElement
  const uploads = Array.from(input.files || []).map(file => ({ file, relativePath: file.webkitRelativePath || file.name }))
  submitFiles(uploads, directoryPaths(uploads.map(item => item.relativePath)))
  input.value = ''
}
function pickFiles(event: Event) {
  const input = event.target as HTMLInputElement
  submitFiles(Array.from(input.files || []).map(file => ({ file, relativePath: file.name })), [])
  input.value = ''
}
function readEntryFile(entry: FileSystemEntryLike) {
  return new Promise<File>((resolve, reject) => entry.file?.(resolve, reject))
}
function readDirectoryEntries(entry: FileSystemEntryLike) {
  return new Promise<FileSystemEntryLike[]>((resolve, reject) => {
    const reader = entry.createReader?.()
    if (!reader) { resolve([]); return }
    const entries: FileSystemEntryLike[] = []
    const readBatch = () => reader.readEntries(batch => {
      if (!batch.length) { resolve(entries); return }
      entries.push(...batch); readBatch()
    }, reject)
    readBatch()
  })
}
async function walkDroppedEntry(entry: FileSystemEntryLike, parentPath: string, uploads: UploadCandidate[], folders: string[]) {
  const path = parentPath ? `${parentPath}/${entry.name}` : entry.name
  if (entry.isFile) {
    uploads.push({ file: await readEntryFile(entry), relativePath: path })
    return
  }
  if (entry.isDirectory) {
    folders.push(path)
    const children = await readDirectoryEntries(entry)
    for (const child of children) await walkDroppedEntry(child, path, uploads, folders)
  }
}
async function dropFiles(event: DragEvent) {
  dragging.value = false
  const transfer = event.dataTransfer
  if (!transfer) return
  try {
    const uploads: UploadCandidate[] = []
    const folders: string[] = []
    const entries = Array.from(transfer.items || []).map(item => (item as DataTransferItem & { webkitGetAsEntry?: () => FileSystemEntryLike | null }).webkitGetAsEntry?.()).filter(Boolean) as FileSystemEntryLike[]
    if (entries.length) {
      for (const entry of entries) await walkDroppedEntry(entry, '', uploads, folders)
    } else {
      uploads.push(...Array.from(transfer.files || []).map(file => ({ file, relativePath: file.name })))
    }
    await submitFiles(uploads, folders)
  } catch { status.value = t('teacherCourseSpace.errors.folderReadFailed', '无法读取这个文件夹，请改用“选择整个文件夹”重试。') }
}
async function submitFiles(uploads: UploadCandidate[], folders: string[]) {
  if (!selected.value || (!uploads.length && !folders.length)) return
  busy.value = true
  status.value = t('teacherCourseSpace.importing', '正在导入 {files} 份资料和 {folders} 个目录...')
    .replace('{files}', String(uploads.length))
    .replace('{folders}', String(folders.length))
  try {
    const data = new FormData()
    uploads.forEach(item => {
      data.append('files', item.file)
      data.append('relative_paths', currentPath.value ? `${currentPath.value}/${item.relativePath}` : item.relativePath)
    })
    folders.forEach(path => data.append('folder_paths', currentPath.value ? `${currentPath.value}/${path}` : path))
    const result = (await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/imports`, data)).data
    selected.value = result.package
    const rejected = result.outcomes.filter((item: any) => item.outcome === 'rejected').length
    status.value = rejected
      ? t('teacherCourseSpace.importNeedsReview', '已导入，{count} 份资料需要检查。').replace('{count}', String(rejected))
      : t('teacherCourseSpace.importComplete', '已完成导入，文件已保存到当前目录。')
    await refresh()
  } catch (error: any) {
    status.value = localizedError(error, 'teacherCourseSpace.errors.importFailed', '导入失败，请检查文件类型、大小和目录名称后重试。')
  } finally { busy.value = false }
}
async function addFolder() {
  if (!selected.value) return
  try {
    const response = await ElMessageBox.prompt(
      t('teacherCourseSpace.folderPromptHelp', '将在当前目录创建文件夹'),
      t('teacherCourseSpace.newFolder', '新建文件夹'),
      {
        confirmButtonText: t('teacherCourseSpace.create', '创建'),
        cancelButtonText: t('common.cancel', '取消'),
        inputPlaceholder: t('teacherCourseSpace.folderPlaceholder', '如：第 1 讲'),
        inputPattern: /\S+/,
        inputErrorMessage: t('teacherCourseSpace.folderRequired', '请输入文件夹名称'),
      },
    )
    const name = String((response as any).value || '').trim()
    const path = currentPath.value ? `${currentPath.value}/${name}` : name
    await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/folders`, { name: path })
    await openPackage(selected.value.package_id)
    currentPath.value = path
    ElMessage.success(t('teacherCourseSpace.folderCreated', '文件夹已创建。'))
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(localizedError(error, 'teacherCourseSpace.errors.createFolderFailed', '新建文件夹失败。'))
    }
  }
}
function nestedAssetCount(node: TreeNode): number {
  return (node.children || []).reduce((total, child) => total + (child.asset ? 1 : nestedAssetCount(child)), 0)
}
async function reloadSelectedPackage() {
  if (!selected.value) return
  selected.value = (await http.get(`/api/teacher-course-spaces/${selected.value.package_id}`)).data
  await refresh()
}
async function deleteNode(node: TreeNode) {
  if (!selected.value || (node.kind !== 'folder' && !node.asset)) return
  const isFolder = node.kind === 'folder'
  const contained = isFolder ? nestedAssetCount(node) : 0
  const message = isFolder
    ? (contained
        ? t('teacherCourseSpace.deleteFolderWithFiles', '确定删除文件夹“{name}”吗？其中 {count} 个文件也会从服务器永久删除。')
          .replace('{name}', node.label).replace('{count}', String(contained))
        : t('teacherCourseSpace.deleteFolderConfirm', '确定删除文件夹“{name}”吗？这个文件夹会从服务器永久删除。').replace('{name}', node.label))
    : t('teacherCourseSpace.deleteFileConfirm', '确定删除文件“{name}”吗？文件会从服务器永久删除。').replace('{name}', node.label)
  try {
    await ElMessageBox.confirm(message, isFolder ? t('teacherCourseSpace.deleteFolder', '删除文件夹') : t('teacherCourseSpace.deleteFile', '删除文件'), {
      confirmButtonText: t('teacherCourseSpace.delete', '删除'), cancelButtonText: t('common.cancel', '取消'), type: 'warning', confirmButtonClass: 'el-button--danger', closeOnClickModal: false,
    })
    if (isFolder) await http.delete(`/api/teacher-course-spaces/${selected.value.package_id}/folders`, { params: { path: node.path } })
    else if (node.asset) await http.delete(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${node.asset.asset_id}`)
    if (node.asset && previewAsset.value?.asset_id === node.asset.asset_id) { previewOpen.value = false; closePreview() }
    await reloadSelectedPackage()
    ElMessage.success(isFolder
      ? t('teacherCourseSpace.folderDeleted', '文件夹及其内容已删除。')
      : t('teacherCourseSpace.fileDeleted', '文件已删除。'))
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(localizedError(error, 'teacherCourseSpace.errors.deleteFailed', '删除失败，请重试。'))
    }
  }
}
const previewUrl = ref('')
const previewKind = computed(() => {
  const extension = previewAsset.value?.extension.toLowerCase() || ''
  if (['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'].includes(extension)) return 'image'
  if (['.pdf', '.md', '.markdown', '.txt', '.csv', '.json', '.py', '.js', '.ts', '.html', '.css'].includes(extension)) return 'browser'
  return 'office'
})
const previewDialogWidth = computed(() => {
  const viewport = typeof window === 'undefined' ? 1200 : window.innerWidth
  const available = Math.max(320, viewport - 48)
  if (previewKind.value === 'image' && previewImageSize.value) return `${Math.min(available, Math.max(360, previewImageSize.value.width + 40))}px`
  if (previewAsset.value?.extension.toLowerCase() === '.pdf') return `${Math.min(available, 1200)}px`
  return `${Math.min(available, 920)}px`
})
function imageSize(url: string) {
  return new Promise<{ width: number; height: number }>(resolve => {
    const image = new Image()
    image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight })
    image.onerror = () => resolve({ width: 800, height: 600 })
    image.src = url
  })
}
function closePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''; previewAsset.value = null; previewImageSize.value = null
}
async function downloadAsset(asset: Asset) {
  if (!selected.value) return
  const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${asset.asset_id}/download`, { responseType: 'blob' })
  const url = URL.createObjectURL(response.data); const anchor = document.createElement('a'); anchor.href = url; anchor.download = asset.filename; anchor.click(); URL.revokeObjectURL(url)
}
async function downloadPackage() {
  if (!selected.value) return
  const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/export`, { responseType: 'blob' })
  const url = URL.createObjectURL(response.data); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${selected.value.course_name}-${t('teacherCourseSpace.archiveName', '课程资料包')}.zip`; anchor.click(); URL.revokeObjectURL(url)
}
onMounted(refresh)
</script>

<style scoped>
.teacher-space,
.teacher-space * {
  box-sizing: border-box;
}
.course-library {
  width: 100%;
  height: 100%;
  overflow: auto;
  padding: 24px clamp(18px, 4vw, 54px) 38px;
  border: 1px solid rgba(255,255,255,.82);
  border-radius: var(--lz-radius-surface);
  background: rgba(255,255,255,.76);
  box-shadow: var(--lz-shadow-panel);
}
.library-header {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}
.library-header__copy {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: baseline;
  gap: 0 12px;
}
.library-header p,
.folder-workbench__heading p {
  margin: 0;
  color: var(--lz-brand);
  font-size: 12px;
  font-weight: 700;
}
.library-header h1 {
  margin: 0;
  color: #312e81;
  font-size: clamp(23px, 2.4vw, 28px);
  line-height: 1.2;
}
.library-header__copy > span,
.folder-workbench__heading span {
  display: block;
  margin-top: 5px;
  color: var(--lz-text-secondary);
  font-size: 12px;
}
.library-header__copy p,
.library-header__copy h1 { grid-row: 1; }
.library-header__copy > span { grid-column: 2; }
.library-actions,
.folder-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.primary-button,
.secondary-button {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 14px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: transform .16s ease, border-color .16s ease, background .16s ease, box-shadow .16s ease;
}
.primary-button {
  border: 1px solid transparent;
  color: #fff;
  background: linear-gradient(135deg, #6366f1, #7c3aed);
  box-shadow: 0 7px 16px rgba(99,102,241,.18);
}
.secondary-button {
  border: 1px solid rgba(203,213,225,.78);
  color: var(--lz-text-secondary);
  background: rgba(255,255,255,.78);
}
.primary-button:not(:disabled):active,
.secondary-button:not(:disabled):active,
.create-template button:active {
  transform: scale(.985);
}
.primary-button:focus-visible,
.secondary-button:focus-visible,
.text-button:focus-visible,
.create-template button:focus-visible,
.create-field input:focus-visible,
.create-field select:focus-visible {
  outline: 3px solid rgba(99,102,241,.16);
  outline-offset: 2px;
}
.primary-button:disabled,
.secondary-button:disabled {
  opacity: .55;
  cursor: not-allowed;
  box-shadow: none;
}
.text-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  color: var(--lz-brand-strong);
  background: transparent;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.knowledge-space {
  max-width: 1280px;
  min-height: 560px;
  margin: 18px auto 0;
  display: grid;
  grid-template-columns: 252px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid var(--lz-border);
  border-radius: 15px;
  background: rgba(255,255,255,.82);
}
.knowledge-space--creating {
  min-height: 0;
}
.knowledge-space--first-run {
  max-width: 1100px;
  grid-template-columns: minmax(0, 1fr);
}
.workspace-create {
  min-width: 0;
  padding: 22px 26px 24px;
}
.workspace-create__copy {
  display: grid;
  gap: 5px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--lz-border);
}
.workspace-create__copy strong {
  color: var(--lz-text-strong);
  font-size: 16px;
}
.workspace-create__copy span {
  color: var(--lz-text-muted);
  font-size: 12px;
}
.workspace-create form {
  display: grid;
  grid-template-columns: minmax(220px, 1.5fr) minmax(150px, .8fr) 156px;
  gap: 15px 14px;
  padding-top: 16px;
}
.create-field {
  min-width: 0;
  display: grid;
  gap: 7px;
}
.create-field > span,
.create-template legend {
  color: var(--lz-text-secondary);
  font-size: 11px;
  font-weight: 700;
}
.create-field input,
.create-field select {
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--lz-border);
  border-radius: 9px;
  color: var(--lz-text-strong);
  background: #fff;
  padding: 0 11px;
  font-size: 13px;
  outline: none;
}
.create-field input::placeholder {
  color: #64748b;
}
.create-field input:focus,
.create-field select:focus {
  border-color: rgba(99,102,241,.62);
}
.create-template {
  min-width: 0;
  grid-column: 1 / 3;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  border: 0;
}
.create-template legend {
  width: 100%;
  margin-bottom: 1px;
}
.create-template button {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid var(--lz-border);
  border-radius: 9px;
  color: var(--lz-text-secondary);
  background: #fff;
  cursor: pointer;
  transition: transform .16s ease, border-color .16s ease, background .16s ease;
}
.create-template button svg {
  color: var(--lz-brand-strong);
}
.create-template button strong {
  font-size: 12px;
}
.create-template button[aria-pressed="true"] {
  border-color: rgba(99,102,241,.44);
  color: var(--lz-text-strong);
  background: var(--lz-brand-soft);
}
.create-submit {
  grid-column: 3;
  align-self: end;
  min-width: 156px;
  white-space: nowrap;
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.knowledge-sidebar {
  min-width: 0;
  padding: 14px 10px;
  border-right: 1px solid var(--lz-border);
  background: rgba(248,250,252,.76);
}
.sidebar-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px 8px;
  color: var(--lz-text);
  font-size: 12px;
}
.sidebar-heading button {
  border: 0;
  color: var(--lz-brand-strong);
  background: transparent;
  font-weight: 700;
  cursor: pointer;
}
.package-item {
  width: 100%;
  display: grid;
  gap: 4px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 9px;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.package-item:hover { background: rgba(255,255,255,.78); }
.package-item.active {
  border-color: rgba(199,210,254,.78);
  background: var(--lz-brand-soft);
}
.package-item strong,
.package-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.package-item strong { color: var(--lz-text-strong); font-size: 12px; }
.package-item span { color: var(--lz-text-muted); font-size: 10px; }
.sidebar-divider {
  height: 1px;
  margin: 14px 7px;
  background: var(--lz-border);
}
.folder-tree {
  --el-tree-node-hover-bg-color: var(--lz-surface-muted);
  --el-tree-text-color: var(--lz-text-secondary);
  background: transparent;
  font-size: 12px;
}
.tree-node {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
}
.tree-node svg { flex: 0 0 auto; color: var(--lz-brand-strong); }
.tree-node span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.folder-workbench { min-width: 0; padding: 20px 24px; }
.folder-workbench__topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.workspace-breadcrumb {
  min-width: 0;
  display: flex;
  align-items: center;
  overflow: auto;
  color: var(--lz-text-muted);
}
.workspace-breadcrumb button {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  color: var(--lz-text-secondary);
  background: transparent;
  font-size: 12px;
  cursor: pointer;
}
.workspace-breadcrumb button:last-child { color: var(--lz-text-strong); font-weight: 700; }
.folder-workbench__heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin: 22px 0;
}
.folder-workbench__heading h2 { margin: 0; color: var(--lz-text-strong); font-size: 22px; }
.context-import {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 12px;
  border: 1px dashed rgba(99,102,241,.34);
  border-radius: 10px;
  color: var(--lz-text-secondary);
  background: rgba(238,242,255,.4);
  font-size: 12px;
}
.context-import svg { color: var(--lz-brand-strong); }
.context-import .text-button { margin-left: auto; }
.context-import.dragging { border-color: var(--lz-brand); background: var(--lz-brand-soft); }
.folder-list { margin-top: 14px; border-top: 1px solid var(--lz-border); }
.folder-list__columns,
.folder-row {
  display: grid;
  grid-template-columns: minmax(0,1fr) 110px 82px 116px;
  align-items: center;
  gap: 12px;
}
.folder-list__columns { padding: 9px 12px; color: var(--lz-text-muted); font-size: 10px; }
.folder-row {
  min-height: 50px;
  padding: 0 12px;
  border-top: 1px solid var(--lz-border);
  color: var(--lz-text-secondary);
  font-size: 11px;
}
.folder-row:hover { background: var(--lz-surface-muted); }
.folder-row__name {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 9px;
  border: 0;
  color: var(--lz-text);
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.folder-row__name svg { flex: 0 0 auto; color: var(--lz-brand-strong); }
.folder-row__name span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.folder-empty {
  min-height: 260px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--lz-text-muted);
  text-align: center;
}
.folder-empty svg { color: var(--lz-brand-strong); }
.folder-empty strong { color: var(--lz-text); font-size: 13px; }
.folder-empty span { max-width: 420px; font-size: 11px; }
.runtime-note { margin: 12px 0 0; color: #8a4b12; font-size: 12px; }
.row-actions {
  justify-self: end;
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.row-action {
  min-width: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 5px 0;
  border: 0;
  color: var(--lz-brand-strong);
  background: transparent;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
}
.row-action svg { flex: 0 0 auto; }
.row-action--danger { color: #b91c1c; }
.preview-surface { width: 100%; display: grid; place-items: center; overflow: hidden; }
.file-preview-image { display: block; width: auto; height: auto; max-width: 100%; max-height: calc(92vh - 126px); object-fit: contain; }
.file-preview-frame { display: block; width: 100%; height: calc(92vh - 116px); min-height: 560px; border: 0; background: var(--lz-surface-muted); }
.office-preview-note { min-height: 300px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--lz-text-muted); text-align: center; }
.office-preview-note strong { color: var(--lz-text-strong); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
:deep(.file-preview-dialog) { max-width: calc(100vw - 32px); margin-bottom: 4vh; border-radius: 14px; overflow: hidden; }
:deep(.file-preview-dialog .el-dialog__header) { padding: 18px 22px 14px; margin: 0; border-bottom: 1px solid var(--lz-border); }
:deep(.file-preview-dialog .el-dialog__title) { display: block; overflow: hidden; color: var(--lz-text-strong); font-size: 17px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
:deep(.file-preview-dialog .el-dialog__body) { padding: 18px 20px 20px; }
@media (max-width: 760px) {
  .course-library { padding: 22px 20px 40px; border: 0; border-radius: 0; box-shadow: none; }
  .library-header__copy { display: block; }
  .library-header,
  .folder-workbench__heading { align-items: flex-start; flex-direction: column; }
  .knowledge-space,
  .knowledge-space--first-run { grid-template-columns: minmax(0, 1fr); }
  .knowledge-sidebar { border-right: 0; border-bottom: 1px solid var(--lz-border); }
  .workspace-create { padding: 22px 22px 24px; }
  .workspace-create form { grid-template-columns: minmax(0, 1fr); }
  .create-field,
  .create-template,
  .create-submit { grid-column: 1; }
  .create-template { display: grid; grid-template-columns: 1fr 1fr; }
  .create-template legend { grid-column: 1 / -1; }
  .create-template button { width: 100%; justify-content: center; padding: 0 9px; }
  .create-submit { width: 100%; }
  .folder-workbench { padding: 18px; }
  .folder-list__columns { display: none; }
  .folder-row { grid-template-columns: minmax(0,1fr) auto; }
  .folder-row > span { display: none; }
  .context-import { align-items: flex-start; flex-wrap: wrap; }
  .context-import .text-button { margin-left: 27px; }
  .file-preview-frame { height: calc(96vh - 108px); min-height: 420px; }
  :deep(.file-preview-dialog) { max-width: calc(100vw - 16px); }
  :deep(.file-preview-dialog .el-dialog__body) { padding: 10px; }
}
@media (max-width: 420px) {
  .course-library { padding-inline: 16px; }
  .library-header h1 { font-size: 27px; }
  .knowledge-space { margin-top: 24px; }
  .workspace-create { padding: 20px 18px 22px; }
  .create-template { grid-template-columns: minmax(0,1fr); }
  .create-template legend { grid-column: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .primary-button,
  .secondary-button,
  .create-template button { transition: none; }
  .spin { animation: none; }
}
</style>
