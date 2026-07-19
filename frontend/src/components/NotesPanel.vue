<template>
  <section class="records-panel" :class="{ 'is-empty': !filteredRecords.length }">
    <header class="records-header">
      <div class="records-title">
        <span class="records-title__icon"><Notebook :size="20" /></span>
        <div>
          <h3>{{ t('notebook.title', '笔记本') }}</h3>
          <p>{{ t('notebook.count', '共 {count} 条内容').replace('{count}', String(filteredRecords.length)) }}</p>
        </div>
      </div>
      <div class="records-tools">
        <input v-model="search" :placeholder="t('notebook.search', '搜索笔记本...')" />
        <button :title="sortMode === 'time' ? t('courseWorkspace.records.sortByTime', '按时间排序') : t('courseWorkspace.records.sortByChapter', '按章节排序')" @click="toggleSortMode">
          <ArrowDownUp :size="16" />
        </button>
        <button v-if="activeTab === 'all' || activeTab === 'note'" :title="t('courseWorkspace.records.exportNotes', '导出笔记')" @click="exportNotes">
          <Download :size="16" />
        </button>
        <button :title="t('common.close', '关闭')" @click="emit('close')"><X :size="17" /></button>
      </div>
    </header>

    <section class="quick-note">
      <button
        v-if="!quickNoteOpen"
        class="quick-note-trigger"
        type="button"
        :disabled="!courseStore.currentNode"
        :aria-expanded="false"
        aria-controls="quick-note-composer"
        @click="quickNoteOpen = true"
      >
        <NotebookPen :size="17" />
        <span>
          <strong>{{ t('quickNote.title', '随手记') }}</strong>
          <small v-if="courseStore.currentNode">
            {{ t('quickNote.currentNode', '记录到当前章节') }}: {{ courseStore.currentNode.node_name }}
          </small>
          <small v-else>{{ t('quickNote.noNode', '请先选择一个课程章节') }}</small>
        </span>
        <Plus :size="17" />
      </button>

      <form
        v-else
        id="quick-note-composer"
        class="quick-note-composer"
        @submit.prevent="saveQuickNote"
      >
        <div class="quick-note-heading">
          <NotebookPen :size="17" />
          <div>
            <strong>{{ t('quickNote.title', '随手记') }}</strong>
            <small>{{ t('quickNote.currentNode', '记录到当前章节') }}: {{ courseStore.currentNode?.node_name }}</small>
          </div>
          <button type="button" :title="t('quickNote.cancel', '取消')" @click="cancelQuickNote">
            <X :size="15" />
          </button>
        </div>
        <textarea
          v-model="quickNoteContent"
          autofocus
          maxlength="2000"
          :placeholder="t('quickNote.placeholder', '记下一个想法、疑问或待复习点…')"
          @keydown.ctrl.enter.prevent="saveQuickNote"
          @keydown.meta.enter.prevent="saveQuickNote"
        ></textarea>
        <footer>
          <small>{{ t('quickNote.shortcut', 'Ctrl / ⌘ + Enter 保存') }}</small>
          <button type="submit" :disabled="quickNoteSaving || !quickNoteContent.trim()">
            <LoaderCircle v-if="quickNoteSaving" :size="14" class="quick-note-spin" />
            <Save v-else :size="14" />
            {{ t('quickNote.save', '保存笔记') }}
          </button>
        </footer>
      </form>
    </section>

    <nav class="record-tabs" :aria-label="t('notebook.types', '笔记本分类')">
      <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
        {{ tab.label }} <span>{{ tab.count }}</span>
      </button>
    </nav>

    <div class="records-list">
      <div v-if="!filteredRecords.length" class="records-empty">
        <NotebookPen :size="28" />
        <span>{{ t('notebook.empty', '笔记本还是空的') }}</span>
      </div>
      <article v-for="record in filteredRecords" :key="record.id" class="record-row">
        <button class="record-main" @click="emit('viewDetail', record)">
          <span class="record-type" :data-type="recordType(record)">{{ typeLabel(recordType(record)) }}</span>
          <strong>{{ record.summary || record.quote || record.content || typeLabel(recordType(record)) }}</strong>
          <p v-if="record.quote && record.quote !== record.summary">{{ record.quote }}</p>
          <small>{{ recordNodeName(record) || t('courseWorkspace.records.unknownNode', '课程位置') }} · {{ formatTime(record.createdAt) }}</small>
        </button>
        <div class="record-actions">
          <span class="record-status">{{ statusLabel(record.status || '') }}</span>
          <button v-if="record.nodeId" :title="t('courseWorkspace.records.locate', '定位原文')" @click="emit('locate', record)">
            <LocateFixed :size="15" />
          </button>
          <button v-if="recordType(record) === 'issue' && record.status !== 'resolved'" @click="updateStatus(record, 'resolved')">
            {{ t('courseWorkspace.records.resolve', '标记解决') }}
          </button>
          <button v-else-if="recordType(record) === 'issue' && record.status === 'resolved'" @click="updateStatus(record, 'reopened')">
            {{ t('courseWorkspace.records.reopen', '重新打开') }}
          </button>
          <button v-if="recordType(record) === 'review_task' && record.status !== 'completed'" @click="updateStatus(record, 'completed')">
            {{ t('courseWorkspace.records.completeReview', '完成复习') }}
          </button>
          <button v-else-if="recordType(record) === 'review_task' && record.status === 'completed'" @click="updateStatus(record, 'pending')">
            {{ t('courseWorkspace.records.reviewAgain', '再次复习') }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import dayjs from 'dayjs'
import { ArrowDownUp, Download, LoaderCircle, LocateFixed, Notebook, NotebookPen, Plus, Save, X } from 'lucide-vue-next'
import { useNoteStore } from '../stores/notes'
import { useCourseStore } from '../stores/course'
import { t } from '../shared/i18n'

type RecordTab = 'all' | 'note' | 'issue' | 'review_task' | 'bookmark'
const emit = defineEmits<{
  (event: 'locate', record: any): void
  (event: 'viewDetail', record: any): void
  (event: 'close'): void
}>()
const noteStore = useNoteStore()
const courseStore = useCourseStore()
const activeTab = ref<RecordTab>('all')
const search = ref('')
const sortMode = ref<'time' | 'chapter'>('time')
const quickNoteOpen = ref(false)
const quickNoteContent = ref('')
const quickNoteSaving = ref(false)

const officialRecords = computed(() => noteStore.notes.filter(item => item.sourceType !== 'format' && item.sourceType !== 'wrong'))
const recordType = (record: any) => (record.recordType || 'note') as Exclude<RecordTab, 'all'>
const count = (type: Exclude<RecordTab, 'all'>) => officialRecords.value.filter(item => recordType(item) === type).length
const tabs = computed(() => [
  { key: 'all' as const, label: t('courseWorkspace.records.tabs.all', '全部'), count: officialRecords.value.length },
  { key: 'note' as const, label: t('courseWorkspace.records.note', '笔记'), count: count('note') },
  { key: 'issue' as const, label: t('courseWorkspace.records.issue', '问题'), count: count('issue') },
  { key: 'review_task' as const, label: t('courseWorkspace.records.review', '复习'), count: count('review_task') },
  { key: 'bookmark' as const, label: t('courseWorkspace.records.bookmark', '书签'), count: count('bookmark') },
])
const filteredRecords = computed(() => {
  const query = search.value.trim().toLowerCase()
  const values = officialRecords.value.filter(item => {
    if (activeTab.value !== 'all' && recordType(item) !== activeTab.value) return false
    if (!query) return true
    return [item.summary, item.content, item.quote, recordNodeName(item), ...(item.tags || [])]
      .some(value => String(value || '').toLowerCase().includes(query))
  })
  return [...values].sort((left, right) => {
    if (sortMode.value === 'chapter') return recordNodeName(left).localeCompare(recordNodeName(right), 'zh-CN')
    return Number(right.createdAt || 0) - Number(left.createdAt || 0)
  })
})

function toggleSortMode() {
  sortMode.value = sortMode.value === 'time' ? 'chapter' : 'time'
}

function typeLabel(type: Exclude<RecordTab, 'all'>) {
  return t(`courseWorkspace.records.${type === 'review_task' ? 'review' : type}`, type)
}

function statusLabel(status: string) {
  return status ? t(`courseWorkspace.records.status.${status}`, status) : ''
}

async function updateStatus(record: any, status: string) {
  await noteStore.updateRecordStatus(record.id, status)
}

function cancelQuickNote() {
  quickNoteOpen.value = false
  quickNoteContent.value = ''
}

async function saveQuickNote() {
  const node = courseStore.currentNode
  const content = quickNoteContent.value.trim()
  if (!node || !content || quickNoteSaving.value) return
  quickNoteSaving.value = true
  try {
    const saved = await noteStore.createNote({
      id: `quick-note-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`,
      nodeId: node.node_id,
      highlightId: '',
      quote: '',
      title: content.split(/\r?\n/).find(line => line.trim())?.trim().slice(0, 80) || t('quickNote.title', '随手记'),
      content,
      color: 'amber',
      createdAt: Date.now(),
      sourceType: 'user',
      recordType: 'note',
      status: 'active',
      origin: 'user_quick_note',
      priority: 'medium',
      metadata: { record_subtype: 'quick_note' },
    })
    if (!saved) return
    activeTab.value = 'note'
    cancelQuickNote()
  } finally {
    quickNoteSaving.value = false
  }
}

function formatTime(timestamp: number) {
  return dayjs(timestamp).format('YYYY-MM-DD HH:mm')
}

function recordNodeName(record: any) {
  return String(courseStore.nodes.find(node => node.node_id === record.nodeId)?.node_name || '')
}

function exportNotes() {
  const notes = filteredRecords.value.filter(item => recordType(item) === 'note')
  const markdown = notes.map(item => `## ${item.summary || recordNodeName(item) || '笔记'}\n\n${item.quote ? `> ${item.quote}\n\n` : ''}${item.content || ''}`).join('\n\n---\n\n')
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'learning-notes.md'
  anchor.click()
  URL.revokeObjectURL(url)
}

function setTab(tab: RecordTab) {
  activeTab.value = tab
}

defineExpose({ setTab })
</script>

<style scoped>
.records-panel { width:100%; height:min(620px,calc(100dvh - 72px)); display:flex; flex-direction:column; min-height:420px; overflow:hidden; color:#172033; background:#fff; }
.records-panel.is-empty { height:min(430px,calc(100dvh - 72px)); }
.records-header { min-height:72px; flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:14px 18px 14px 20px; border-bottom:1px solid #eef0f6; }
.records-title { min-width:0; display:flex; gap:11px; align-items:center; }
.records-title__icon { width:40px; height:40px; flex:0 0 auto; display:grid; place-items:center; border-radius:12px; color:#fff; background:linear-gradient(135deg,#818cf8,#8b5cf6 55%,#a855f7); box-shadow:0 7px 18px rgba(124,58,237,.2); }
.records-title h3,.records-title p { margin:0; letter-spacing:0; }
.records-title h3 { color:#312e81; font-size:18px; font-weight:800; }
.records-title p { margin-top:2px; color:#64748b; font-size:11px; }
.records-tools { min-width:0; display:flex; gap:7px; align-items:center; }
.records-tools input { width:178px; height:34px; padding:0 12px; border:1px solid #e2e8f0; border-radius:999px; outline:none; color:#334155; background:#fbfcff; font-size:12px; transition:border-color .16s ease,box-shadow .16s ease,background .16s ease; }
.records-tools input:focus { border-color:#c4b5fd; background:#fff; box-shadow:0 0 0 3px rgba(139,92,246,.1); }
.records-tools button,.record-actions button { min-width:34px; height:34px; display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:0 9px; border:1px solid #e2e8f0; border-radius:10px; color:#64748b; background:#fff; cursor:pointer; transition:color .16s ease,border-color .16s ease,background .16s ease,transform .16s ease; }
.records-tools button:hover,.record-actions button:hover { color:#7c3aed; border-color:#ddd6fe; background:#f5f3ff; }
.quick-note { flex:0 0 auto; padding:12px 20px 4px; background:#fff; }
.quick-note-trigger { width:100%; min-height:44px; display:grid; grid-template-columns:20px minmax(0,1fr) 18px; align-items:center; gap:10px; padding:8px 12px; border:1px solid #e9d5ff; border-radius:12px; color:#6d28d9; background:linear-gradient(135deg,#faf5ff,#f5f3ff 55%,#eef2ff); text-align:left; cursor:pointer; box-shadow:0 4px 12px rgba(124,58,237,.06); }
.quick-note-trigger:hover:not(:disabled) { border-color:#c4b5fd; background:linear-gradient(135deg,#f5f3ff,#ede9fe); transform:translateY(-1px); }
.quick-note-trigger:focus-visible,.quick-note-composer textarea:focus-visible,.quick-note-composer button:focus-visible { outline:3px solid rgba(139,92,246,.2); outline-offset:2px; }
.quick-note-trigger:disabled { color:#94a3b8; border-color:#e2e8f0; background:#f8fafc; box-shadow:none; cursor:not-allowed; }
.quick-note-trigger>span { min-width:0; display:flex; align-items:baseline; gap:8px; }
.quick-note-trigger strong { flex:0 0 auto; font-size:12px; }
.quick-note-trigger small { min-width:0; overflow:hidden; color:#7c7197; text-overflow:ellipsis; white-space:nowrap; }
.quick-note-composer { display:grid; gap:10px; padding:13px; border:1px solid #ddd6fe; border-radius:14px; background:linear-gradient(180deg,#fdfcff,#faf8ff); box-shadow:0 8px 22px rgba(124,58,237,.09); }
.quick-note-heading { display:grid; grid-template-columns:18px minmax(0,1fr) 28px; align-items:center; gap:9px; color:#7c3aed; }
.quick-note-heading>div { min-width:0; display:flex; align-items:baseline; gap:8px; }
.quick-note-heading strong { flex:0 0 auto; font-size:12px; }
.quick-note-heading small { min-width:0; overflow:hidden; color:#7c7197; text-overflow:ellipsis; white-space:nowrap; }
.quick-note-heading button { width:28px; height:28px; display:grid; place-items:center; padding:0; border:0; border-radius:8px; color:#64748b; background:transparent; cursor:pointer; }
.quick-note-heading button:hover { color:#7c3aed; background:#ede9fe; }
.quick-note-composer textarea { width:100%; min-height:82px; resize:vertical; padding:10px 11px; border:1px solid #e2e8f0; border-radius:10px; color:#1e293b; background:#fff; font:inherit; font-size:12px; line-height:1.65; outline:none; box-sizing:border-box; }
.quick-note-composer textarea:focus { border-color:#c4b5fd; box-shadow:0 0 0 3px rgba(139,92,246,.08); }
.quick-note-composer footer { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.quick-note-composer footer small { color:#94a3b8; }
.quick-note-composer footer button { min-height:32px; display:inline-flex; align-items:center; gap:6px; padding:0 12px; border:0; border-radius:9px; color:#fff; background:linear-gradient(135deg,#6366f1,#8b5cf6); box-shadow:0 5px 12px rgba(99,102,241,.2); font-size:11px; font-weight:700; cursor:pointer; }
.quick-note-composer footer button:disabled { opacity:.5; box-shadow:none; cursor:not-allowed; }
.quick-note-spin { animation:quick-note-spin .8s linear infinite; }
.record-tabs { flex:0 0 auto; display:flex; gap:7px; padding:11px 20px 12px; overflow-x:auto; border-bottom:1px solid #eef0f6; }
.record-tabs button { flex:0 0 auto; padding:6px 10px; border:1px solid transparent; border-radius:999px; color:#64748b; background:transparent; font-size:11px; font-weight:600; cursor:pointer; }
.record-tabs button:hover { color:#6d28d9; background:#faf5ff; }
.record-tabs button.active { color:#7c3aed; border-color:#ddd6fe; background:#f5f3ff; font-weight:750; box-shadow:0 2px 8px rgba(124,58,237,.07); }
.record-tabs span { margin-left:2px; color:inherit; font:10px ui-monospace,monospace; }
.records-list { flex:1; min-height:0; overflow:auto; display:flex; flex-direction:column; gap:10px; padding:14px 20px 22px; background:linear-gradient(180deg,#fff,#fdfdff); }
.records-empty { flex:1; min-height:210px; display:flex; flex-direction:column; gap:10px; align-items:center; justify-content:center; color:#94a3b8; }
.records-empty svg { color:#a78bfa; }
.records-empty span { color:#64748b; font-size:12px; }
.record-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; padding:14px; border:1px solid #eceff5; border-radius:13px; background:#fff; box-shadow:0 3px 10px rgba(15,23,42,.035); transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease; }
.record-row:hover { border-color:#ddd6fe; box-shadow:0 7px 18px rgba(79,70,229,.08); transform:translateY(-1px); }
.record-main { min-width:0; text-align:left; border:0; background:transparent; padding:0; cursor:pointer; }
.record-main strong { display:block; margin:7px 0 4px; color:#1e293b; font-size:13px; line-height:1.55; }
.record-main p { margin:0 0 6px; overflow:hidden; color:#64748b; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.record-main small { color:#94a3b8; font-size:10px; }
.record-type { display:inline-flex; padding:3px 7px; border-radius:999px; color:#6d28d9; background:#f5f3ff; font-size:10px; font-weight:700; }
.record-type[data-type="issue"] { color:#be123c; background:#fff1f2; }
.record-type[data-type="review_task"] { color:#a16207; background:#fffbeb; }
.record-type[data-type="bookmark"] { color:#047857; background:#ecfdf5; }
.record-actions { display:flex; gap:6px; align-items:center; }
.record-status { color:#64748b; font-size:10px; white-space:nowrap; }
@keyframes quick-note-spin { to { transform:rotate(360deg); } }
@media (max-width:720px) {
  .records-panel { height:calc(100dvh - 20px); min-height:0; }
  .records-panel.is-empty { height:calc(100dvh - 20px); }
  .records-header { min-height:64px; align-items:center; padding:11px 12px 11px 14px; }
  .records-title__icon { width:36px; height:36px; border-radius:10px; }
  .records-title h3 { font-size:16px; }
  .records-tools input { display:none; }
  .records-tools button { min-width:32px; width:32px; height:32px; padding:0; }
  .quick-note { padding:10px 14px 3px; }
  .quick-note-trigger>span,.quick-note-heading>div { align-items:flex-start; flex-direction:column; gap:1px; }
  .quick-note-composer footer small { display:none; }
  .record-tabs { gap:4px; padding:10px; }
  .record-tabs button { padding:6px 8px; font-size:10px; }
  .records-list { padding:12px 14px 18px; }
  .record-row { grid-template-columns:1fr; }
  .record-actions { justify-content:flex-end; flex-wrap:wrap; }
}
</style>
