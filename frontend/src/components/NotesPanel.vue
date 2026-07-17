<template>
  <section class="records-panel">
    <header class="records-header">
      <div class="records-title">
        <Notebook :size="20" />
        <div>
          <h3>{{ t('courseWorkspace.records.title', '学习记录') }}</h3>
          <p>{{ filteredRecords.length }} {{ t('courseWorkspace.records.items', '条记录') }}</p>
        </div>
      </div>
      <div class="records-tools">
        <input v-model="search" :placeholder="t('courseWorkspace.records.search', '搜索学习记录...')" />
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
            {{ t('quickNote.currentNode', '记录到当前章节') }}：{{ courseStore.currentNode.node_name }}
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
            <small>{{ t('quickNote.currentNode', '记录到当前章节') }}：{{ courseStore.currentNode?.node_name }}</small>
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

    <nav class="record-tabs" :aria-label="t('courseWorkspace.records.types', '记录类型')">
      <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
        {{ tab.label }} <span>{{ tab.count }}</span>
      </button>
    </nav>

    <div class="records-list">
      <div v-if="!filteredRecords.length" class="records-empty">
        <NotebookPen :size="28" />
        <span>{{ t('courseWorkspace.records.empty', '当前没有学习记录') }}</span>
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
  { key: 'all' as const, label: t('courseWorkspace.records.all', '全部'), count: officialRecords.value.length },
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
.records-panel { height:100%; display:flex; flex-direction:column; min-height:0; background:#fff; color:#172033; }
.records-header { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:16px 20px; border-bottom:1px solid #e2e8f0; }.records-title { display:flex; gap:10px; align-items:center; }.records-title h3,.records-title p { margin:0; letter-spacing:0; }.records-title h3 { font-size:17px; }.records-title p { margin-top:2px; color:#64748b; font-size:11px; }.records-tools { display:flex; gap:7px; align-items:center; }.records-tools input { width:180px; height:34px; padding:0 10px; border:1px solid #cbd5e1; border-radius:6px; outline:none; }.records-tools input:focus { border-color:#0f766e; }.records-tools button,.record-actions button { min-width:34px; height:34px; display:inline-flex; align-items:center; justify-content:center; gap:5px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; color:#475569; padding:0 9px; }
.quick-note { padding:10px 20px; border-bottom:1px solid #e2e8f0; background:#f8fafc; }.quick-note-trigger { width:100%; min-height:42px; display:grid; grid-template-columns:18px minmax(0,1fr) 18px; align-items:center; gap:10px; padding:7px 11px; border:1px solid #cbd5e1; border-radius:7px; color:#475569; background:#fff; text-align:left; cursor:pointer; }.quick-note-trigger:hover:not(:disabled) { color:#0f766e; border-color:#99f6e4; background:#f0fdfa; }.quick-note-trigger:focus-visible,.quick-note-composer textarea:focus-visible,.quick-note-composer button:focus-visible { outline:2px solid #14b8a6; outline-offset:2px; }.quick-note-trigger:disabled { color:#94a3b8; background:#f8fafc; cursor:not-allowed; }.quick-note-trigger>span { min-width:0; display:flex; align-items:baseline; gap:8px; }.quick-note-trigger strong { flex:0 0 auto; font-size:12px; }.quick-note-trigger small { min-width:0; overflow:hidden; color:#64748b; text-overflow:ellipsis; white-space:nowrap; }.quick-note-composer { display:grid; gap:9px; padding:11px; border:1px solid #99f6e4; border-radius:7px; background:#fff; box-shadow:0 4px 14px rgba(15,118,110,.08); }.quick-note-heading { display:grid; grid-template-columns:18px minmax(0,1fr) 28px; align-items:center; gap:9px; color:#0f766e; }.quick-note-heading>div { min-width:0; display:flex; align-items:baseline; gap:8px; }.quick-note-heading strong { flex:0 0 auto; font-size:12px; }.quick-note-heading small { min-width:0; overflow:hidden; color:#64748b; text-overflow:ellipsis; white-space:nowrap; }.quick-note-heading button { width:28px; height:28px; display:grid; place-items:center; padding:0; border:0; border-radius:5px; color:#64748b; background:transparent; }.quick-note-composer textarea { width:100%; min-height:76px; resize:vertical; padding:9px 10px; border:1px solid #cbd5e1; border-radius:6px; color:#1e293b; background:#fff; font:inherit; font-size:12px; line-height:1.6; outline:none; box-sizing:border-box; }.quick-note-composer textarea:focus { border-color:#14b8a6; }.quick-note-composer footer { display:flex; align-items:center; justify-content:space-between; gap:10px; }.quick-note-composer footer small { color:#94a3b8; }.quick-note-composer footer button { min-height:32px; display:inline-flex; align-items:center; gap:6px; padding:0 11px; border:1px solid #0f766e; border-radius:6px; color:#fff; background:#0f766e; font-size:11px; font-weight:700; }.quick-note-composer footer button:disabled { opacity:.5; cursor:not-allowed; }.quick-note-spin { animation:quick-note-spin .8s linear infinite; }
.record-tabs { display:flex; gap:4px; padding:9px 20px; border-bottom:1px solid #e2e8f0; overflow-x:auto; }.record-tabs button { flex:0 0 auto; border:0; border-bottom:2px solid transparent; background:transparent; padding:8px 10px; color:#64748b; }.record-tabs button.active { color:#0f766e; border-color:#0f766e; font-weight:700; }.record-tabs span { font:11px ui-monospace,monospace; }
.records-list { flex:1; min-height:0; overflow:auto; padding:0 20px 24px; }.records-empty { min-height:240px; display:flex; flex-direction:column; gap:10px; align-items:center; justify-content:center; color:#64748b; }.record-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:16px; padding:16px 0; border-bottom:1px solid #e2e8f0; }.record-main { min-width:0; text-align:left; border:0; background:transparent; padding:0; }.record-main strong { display:block; margin:8px 0 4px; font-size:14px; line-height:1.5; color:#1e293b; }.record-main p { margin:0 0 6px; color:#64748b; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }.record-main small { color:#94a3b8; }.record-type { display:inline-block; padding:2px 6px; border-radius:4px; background:#eef2ff; color:#4338ca; font-size:11px; }.record-type[data-type="issue"] { background:#fff1f2; color:#be123c; }.record-type[data-type="review_task"] { background:#fffbeb; color:#a16207; }.record-type[data-type="bookmark"] { background:#ecfdf5; color:#047857; }.record-actions { display:flex; gap:6px; align-items:center; }.record-status { color:#64748b; font-size:11px; white-space:nowrap; }
@keyframes quick-note-spin { to { transform:rotate(360deg); } }
@media (max-width:720px) { .records-header { align-items:flex-start; padding:14px; }.records-tools input { display:none; }.quick-note { padding:9px 14px; }.quick-note-trigger>span,.quick-note-heading>div { align-items:flex-start; flex-direction:column; gap:1px; }.quick-note-composer footer small { display:none; }.record-tabs { padding-left:10px; padding-right:10px; }.records-list { padding-left:14px; padding-right:14px; }.record-row { grid-template-columns:1fr; }.record-actions { justify-content:flex-end; flex-wrap:wrap; } }
</style>
