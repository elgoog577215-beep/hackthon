<template>
  <main class="course-library teacher-space">
    <header class="library-header">
      <div>
        <p>教师课程空间</p>
        <h1>课程文件库</h1>
        <span>按课程、学年和目录保存原始资料。</span>
      </div>
      <div class="library-actions">
        <button class="secondary-button" type="button" @click="router.push('/courses')">返回课程库</button>
      </div>
    </header>

    <section v-if="!selected" class="workspace-create">
      <div class="workspace-create__copy"><strong>新建课程文件库</strong><span>空白开始，或按学校课程材料目录创建。</span></div>
      <form @submit.prevent="createPackage">
        <input v-model.trim="form.course_name" required placeholder="课程名称，如：数据结构" />
        <input v-model.trim="form.academic_year" required placeholder="学年，如：2025–2026" />
        <select v-model="form.term"><option>春季</option><option>秋季</option><option>夏季</option></select>
        <select v-model="form.template"><option value="blank">空白文件库</option><option value="school_course_materials">学校材料模板</option></select>
        <button class="primary-button" :disabled="busy">创建文件库</button>
      </form>
    </section>

    <section class="knowledge-space">
      <aside class="knowledge-sidebar">
        <div class="sidebar-heading"><strong>我的课程</strong><button type="button" @click="selected = null">新建</button></div>
        <button v-for="item in packages" :key="item.package_id" class="package-item" :class="{ active: item.package_id === selected?.package_id }" type="button" @click="openPackage(item.package_id)">
          <strong>{{ item.course_name }}</strong><span>{{ item.academic_year }} · {{ item.term }} · {{ item.asset_count }} 份资料</span>
        </button>
        <p v-if="!packages.length" class="sidebar-empty">还没有课程文件库。</p>

        <template v-if="selected">
          <div class="sidebar-divider" />
          <div class="sidebar-heading"><strong>文件目录</strong></div>
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

      <section v-if="selected" class="folder-workbench">
        <div class="folder-workbench__topline">
          <nav class="workspace-breadcrumb" aria-label="文件路径">
            <button type="button" @click="openFolder('')"><Home :size="14" />课程资料</button>
            <template v-for="crumb in breadcrumbs" :key="crumb.path">
              <ChevronRight :size="14" /><button type="button" @click="openFolder(crumb.path)">{{ crumb.label }}</button>
            </template>
          </nav>
          <button class="text-button" type="button" @click="downloadPackage"><Download :size="14" />下载整课 ZIP</button>
        </div>

        <div class="folder-workbench__heading">
          <div><p>{{ selected.academic_year }} · {{ selected.term }}</p><h2>{{ currentFolderLabel }}</h2><span>{{ currentPath ? '正在查看此目录下的资料。' : '课程根目录。可建立目录或直接导入资料。' }}</span></div>
          <div class="folder-actions">
            <button class="secondary-button" type="button" @click="addFolder"><FolderPlus :size="15" />新建文件夹</button>
            <button class="primary-button" type="button" :disabled="busy" @click="fileInput?.click()"><Upload :size="15" />上传到此处</button>
          </div>
        </div>

        <input ref="folderInput" class="sr-only" type="file" multiple webkitdirectory @change="pickFolder" />
        <input ref="fileInput" class="sr-only" type="file" multiple @change="pickFiles" />
        <div class="context-import" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="dropFiles">
          <FolderUp :size="18" /><span>把文件或文件夹拖到这里，导入到「{{ currentFolderLabel }}」</span>
          <button class="text-button" type="button" :disabled="busy" @click="folderInput?.click()">选择整个文件夹</button>
        </div>

        <div class="folder-list" :class="{ 'folder-list--empty': !currentChildren.length }">
          <template v-if="currentChildren.length">
            <div class="folder-list__columns"><span>名称</span><span>类型</span><span>大小</span><span>操作</span></div>
            <div v-for="node in currentChildren" :key="node.id" class="folder-row" :class="`folder-row--${node.kind}`" @dblclick="node.kind === 'folder' ? openNode(node) : previewNode(node)">
              <button class="folder-row__name" type="button" @click="openNode(node)">
                <Folder v-if="node.kind === 'folder'" :size="18" /><FileText v-else :size="17" />
                <span>{{ node.label }}</span>
              </button>
              <span>{{ node.kind === 'folder' ? '文件夹' : node.asset?.extension?.replace('.', '').toUpperCase() }}</span>
              <span>{{ node.asset ? size(node.asset.size_bytes) : '—' }}</span>
              <div class="row-actions">
                <button v-if="node.asset" class="row-action" type="button" @click.stop="downloadAsset(node.asset)"><Download :size="14" />下载</button>
                <button v-if="node.kind === 'folder' || node.asset" class="row-action row-action--danger" type="button" @click.stop="deleteNode(node)"><Trash2 :size="14" />删除</button>
              </div>
            </div>
          </template>
          <div v-else class="folder-empty"><FolderOpen :size="28" /><strong>这个目录还是空的</strong><span>可把电脑里的文件或文件夹拖进来，也可以先新建下一层目录。</span></div>
        </div>
        <p v-if="status" class="runtime-note">{{ status }}</p>
      </section>
    </section>
    <el-dialog v-model="previewOpen" :title="previewAsset?.filename || '文件预览'" :width="previewDialogWidth" top="4vh" class="file-preview-dialog" destroy-on-close @closed="closePreview">
      <div class="preview-surface" :class="`preview-surface--${previewKind}`">
        <img v-if="previewKind === 'image'" class="file-preview-image" :src="previewUrl" :alt="previewAsset?.filename" />
        <iframe v-else-if="previewKind === 'browser'" class="file-preview-frame" :src="previewUrl" :title="previewAsset?.filename" />
        <div v-else class="office-preview-note"><FileText :size="30" /><strong>此 Office 文件已安全保存</strong><span>Word、Excel 和 PPT 可直接下载后用本机 Office 打开；PDF、图片和文本支持页内双击预览。</span><button class="text-button" type="button" @click="previewAsset && downloadAsset(previewAsset)"><Download :size="14" />下载原件</button></div>
      </div>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChevronRight, Download, FileText, Folder, FolderOpen, FolderPlus, FolderUp, Home, Trash2, Upload } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
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

const router = useRouter()
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
const form = ref({ course_name: '', academic_year: '2025–2026', term: '春季', template: 'school_course_materials' })

const treeData = computed<TreeNode[]>(() => {
  const root: TreeNode = { id: 'root', label: '课程资料', path: '', kind: 'root', children: [] }
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
const currentFolderLabel = computed(() => breadcrumbs.value.at(-1)?.label || '课程资料')
const size = (value: number) => value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`

async function refresh() { try { packages.value = (await http.get('/api/teacher-course-spaces')).data } catch { status.value = '课程空间服务暂不可用；请确认后端已启动后重试。' } }
async function openPackage(id: string) { selected.value = (await http.get(`/api/teacher-course-spaces/${id}`)).data; currentPath.value = '' }
async function createPackage() { busy.value = true; try { const data = (await http.post('/api/teacher-course-spaces', form.value)).data; await refresh(); await openPackage(data.package_id); form.value.course_name = '' } finally { busy.value = false } }
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
  } catch { ElMessage.error('文件预览读取失败，请重试。') }
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
  } catch { status.value = '无法读取这个文件夹，请改用“选择整个文件夹”重试。' }
}
async function submitFiles(uploads: UploadCandidate[], folders: string[]) {
  if (!selected.value || (!uploads.length && !folders.length)) return
  busy.value = true; status.value = `正在导入 ${uploads.length} 份资料和 ${folders.length} 个目录…`
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
    status.value = rejected ? `已导入，${rejected} 份资料需要检查。` : '已完成导入，文件已保存到当前目录。'
    await refresh()
  } catch (error: any) { status.value = error?.response?.data?.detail || '导入失败，请检查文件类型、大小和目录名称后重试。' } finally { busy.value = false }
}
async function addFolder() {
  if (!selected.value) return
  try {
    const response = await ElMessageBox.prompt('将在当前目录创建文件夹', '新建文件夹', { confirmButtonText: '创建', cancelButtonText: '取消', inputPlaceholder: '如：第 1 讲', inputPattern: /\S+/, inputErrorMessage: '请输入文件夹名称' })
    const name = String((response as any).value || '').trim()
    const path = currentPath.value ? `${currentPath.value}/${name}` : name
    await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/folders`, { name: path })
    await openPackage(selected.value.package_id)
    currentPath.value = path
    ElMessage.success('文件夹已创建。')
  } catch (error: any) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.response?.data?.detail || '新建文件夹失败') }
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
    ? `确定删除文件夹“${node.label}”吗？${contained ? `其中 ${contained} 个文件也会从服务器永久删除。` : '这个文件夹会从服务器永久删除。'}`
    : `确定删除文件“${node.label}”吗？文件会从服务器永久删除。`
  try {
    await ElMessageBox.confirm(message, isFolder ? '删除文件夹' : '删除文件', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger', closeOnClickModal: false,
    })
    if (isFolder) await http.delete(`/api/teacher-course-spaces/${selected.value.package_id}/folders`, { params: { path: node.path } })
    else if (node.asset) await http.delete(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${node.asset.asset_id}`)
    if (node.asset && previewAsset.value?.asset_id === node.asset.asset_id) { previewOpen.value = false; closePreview() }
    await reloadSelectedPackage()
    ElMessage.success(isFolder ? '文件夹及其内容已删除。' : '文件已删除。')
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.response?.data?.detail || '删除失败，请重试。')
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
  const url = URL.createObjectURL(response.data); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${selected.value.course_name}-课程资料包.zip`; anchor.click(); URL.revokeObjectURL(url)
}
onMounted(refresh)
</script>

<style scoped>
.course-library{width:100%;height:100%;overflow:auto;padding:30px clamp(18px,4vw,54px) 48px;border:1px solid rgba(255,255,255,.82);border-radius:var(--lz-radius-surface);background:rgba(255,255,255,.76);box-shadow:var(--lz-shadow-panel)}.library-header{max-width:1280px;margin:0 auto;display:flex;align-items:flex-end;justify-content:space-between;gap:24px}.library-header p,.folder-workbench__heading p{margin:0 0 7px;color:var(--lz-brand);font-size:12px;font-weight:700}.library-header h1{margin:0;color:#312e81;font-size:clamp(25px,3vw,32px);line-height:1.2}.library-header>div:first-child>span,.folder-workbench__heading span{display:block;margin-top:8px;color:var(--lz-text-secondary);font-size:13px}.library-actions,.folder-actions{display:flex;gap:8px;flex-wrap:wrap}.primary-button,.secondary-button{min-height:38px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 14px;border-radius:11px;font-size:12px;font-weight:700;cursor:pointer}.primary-button{border:1px solid transparent;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;box-shadow:0 7px 16px rgba(99,102,241,.2)}.secondary-button{border:1px solid rgba(203,213,225,.72);background:rgba(255,255,255,.72);color:var(--lz-text-secondary)}.primary-button:disabled,.secondary-button:disabled{opacity:.55;cursor:not-allowed}.text-button{display:inline-flex;align-items:center;gap:6px;border:0;background:transparent;color:var(--lz-brand-strong);font-size:12px;font-weight:700;cursor:pointer}.workspace-create{max-width:1280px;margin:28px auto;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px 22px;border:1px solid var(--lz-border);border-radius:14px;background:rgba(255,255,255,.78);box-shadow:0 5px 18px rgba(79,70,229,.06)}.workspace-create__copy{display:grid;gap:5px}.workspace-create__copy span,.sidebar-empty{font-size:13px;color:var(--lz-text-muted)}.workspace-create form{display:flex;gap:8px;flex-wrap:wrap}.workspace-create input,.workspace-create select{border:1px solid var(--lz-border);border-radius:8px;background:#fff;padding:9px 10px;color:var(--lz-text-strong)}.knowledge-space{max-width:1280px;min-height:560px;margin:28px auto 0;display:grid;grid-template-columns:252px minmax(0,1fr);border:1px solid var(--lz-border);border-radius:15px;background:rgba(255,255,255,.8);overflow:hidden}.knowledge-sidebar{min-width:0;padding:14px 10px;border-right:1px solid var(--lz-border);background:rgba(248,250,252,.72)}.sidebar-heading{display:flex;align-items:center;justify-content:space-between;padding:0 8px 8px;color:var(--lz-text);font-size:12px}.sidebar-heading button{border:0;background:transparent;color:var(--lz-brand-strong);font-weight:700;cursor:pointer}.package-item{width:100%;border:1px solid transparent;border-radius:9px;background:transparent;padding:10px;text-align:left;display:grid;gap:4px;cursor:pointer}.package-item:hover{background:rgba(255,255,255,.72)}.package-item.active{border-color:rgba(199,210,254,.78);background:var(--lz-brand-soft)}.package-item strong{overflow:hidden;color:var(--lz-text-strong);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.package-item span{overflow:hidden;color:var(--lz-text-muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.sidebar-empty{padding:8px}.sidebar-divider{height:1px;margin:14px 7px;background:var(--lz-border)}.folder-tree{--el-tree-node-hover-bg-color:var(--lz-surface-muted);--el-tree-text-color:var(--lz-text-secondary);background:transparent;font-size:12px}.tree-node{min-width:0;display:inline-flex;align-items:center;gap:6px;overflow:hidden}.tree-node svg{flex:0 0 auto;color:var(--lz-brand-strong)}.tree-node span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.folder-workbench{min-width:0;padding:20px 24px}.folder-workbench__topline{display:flex;align-items:center;justify-content:space-between;gap:16px}.workspace-breadcrumb{display:flex;align-items:center;min-width:0;overflow:auto;color:var(--lz-text-muted)}.workspace-breadcrumb button{display:inline-flex;align-items:center;gap:5px;flex:0 0 auto;border:0;background:transparent;color:var(--lz-text-secondary);font-size:12px;cursor:pointer}.workspace-breadcrumb button:last-child{color:var(--lz-text-strong);font-weight:700}.folder-workbench__heading{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin:22px 0}.folder-workbench__heading h2{margin:0;color:var(--lz-text-strong);font-size:22px}.context-import{display:flex;align-items:center;gap:9px;padding:10px 12px;border:1px dashed rgba(99,102,241,.32);border-radius:10px;color:var(--lz-text-secondary);background:rgba(238,242,255,.38);font-size:12px}.context-import svg{color:var(--lz-brand-strong)}.context-import .text-button{margin-left:auto}.context-import.dragging{border-color:var(--lz-brand);background:var(--lz-brand-soft)}.folder-list{margin-top:14px;border-top:1px solid var(--lz-border)}.folder-list__columns,.folder-row{display:grid;grid-template-columns:minmax(0,1fr) 110px 82px 58px;align-items:center;gap:12px}.folder-list__columns{padding:9px 12px;color:var(--lz-text-muted);font-size:10px}.folder-row{min-height:50px;padding:0 12px;border-top:1px solid var(--lz-border);color:var(--lz-text-secondary);font-size:11px}.folder-row:hover{background:var(--lz-surface-muted)}.folder-row__name{display:flex;align-items:center;min-width:0;gap:9px;border:0;background:transparent;color:var(--lz-text);font:inherit;text-align:left;cursor:pointer}.folder-row__name svg{flex:0 0 auto;color:var(--lz-brand-strong)}.folder-row__name span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.folder-row a{display:inline-flex;align-items:center;gap:4px;color:var(--lz-brand-strong);font-size:11px;font-weight:700;text-decoration:none}.folder-empty{min-height:260px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:var(--lz-text-muted);text-align:center}.folder-empty svg{color:var(--lz-brand-strong)}.folder-empty strong{color:var(--lz-text);font-size:13px}.folder-empty span{font-size:11px}.runtime-note{margin:12px 0 0;color:#9a5c20;font-size:12px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}@media(max-width:760px){.course-library{padding:22px 20px 40px;border:0;border-radius:0;box-shadow:none}.library-header,.workspace-create,.folder-workbench__heading{align-items:flex-start;flex-direction:column}.knowledge-space{grid-template-columns:1fr}.knowledge-sidebar{border-right:0;border-bottom:1px solid var(--lz-border)}.folder-workbench{padding:18px}.folder-list__columns{display:none}.folder-row{grid-template-columns:minmax(0,1fr) 52px}.folder-row>span{display:none}.folder-row a{justify-self:end}.context-import{align-items:flex-start;flex-wrap:wrap}.context-import .text-button{margin-left:27px}}
.row-actions{justify-self:end;display:inline-flex;align-items:center;justify-content:flex-end;gap:8px}.row-action{display:inline-flex;align-items:center;justify-content:center;gap:5px;min-width:48px;padding:5px 0;border:0;background:transparent;color:var(--lz-brand-strong);font-size:11px;font-weight:700;line-height:1;white-space:nowrap;cursor:pointer}.row-action svg{display:block;flex:0 0 auto}.row-action--danger{color:#dc2626}.preview-surface{width:100%;display:grid;place-items:center;overflow:hidden}.file-preview-image{display:block;width:auto;height:auto;max-width:100%;max-height:calc(92vh - 126px);object-fit:contain}.file-preview-frame{display:block;width:100%;height:calc(92vh - 116px);min-height:560px;border:0;background:var(--lz-surface-muted)}.office-preview-note{min-height:300px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--lz-text-muted);text-align:center}.office-preview-note strong{color:var(--lz-text-strong)}:deep(.file-preview-dialog){max-width:calc(100vw - 32px);margin-bottom:4vh;border-radius:14px;overflow:hidden}:deep(.file-preview-dialog .el-dialog__header){padding:18px 22px 14px;margin:0;border-bottom:1px solid var(--lz-border)}:deep(.file-preview-dialog .el-dialog__title){display:block;overflow:hidden;color:var(--lz-text-strong);font-size:17px;font-weight:700;text-overflow:ellipsis;white-space:nowrap}:deep(.file-preview-dialog .el-dialog__body){padding:18px 20px 20px}@media(max-width:760px){.file-preview-frame{height:calc(96vh - 108px);min-height:420px}:deep(.file-preview-dialog){max-width:calc(100vw - 16px)}:deep(.file-preview-dialog .el-dialog__body){padding:10px}}
</style>
