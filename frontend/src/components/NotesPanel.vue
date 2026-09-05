<template>
  <section class="records-panel" :class="{ 'is-empty': !filteredRecords.length, 'is-sidebar': props.mode === 'sidebar' }">
    <header class="records-header">
      <div class="records-title">
        <span class="records-title__icon"><Notebook :size="20" /></span>
        <div>
          <h3>{{ t('notebook.title', '笔记本') }}</h3>
          <p>{{ t('notebook.count', '共 {count} 条内容').replace('{count}', String(filteredRecords.length)) }}</p>
        </div>
      </div>
      <button class="records-close" type="button" :title="t('common.close', '关闭')" :aria-label="t('common.close', '关闭')" @click="emit('close')"><X :size="18" /></button>
      <div class="records-tools">
        <input v-model="search" type="search" :aria-label="t('notebook.search', '搜索笔记本...')" :placeholder="t('notebook.search', '搜索笔记本...')" />
        <button :aria-label="sortMode === 'time' ? t('courseWorkspace.records.sortByTime', '按时间排序') : t('courseWorkspace.records.sortByChapter', '按章节排序')" :title="sortMode === 'time' ? t('courseWorkspace.records.sortByTime', '按时间排序') : t('courseWorkspace.records.sortByChapter', '按章节排序')" @click="toggleSortMode">
          <ArrowDownUp :size="16" />
        </button>
        <button v-if="activeTab === 'all' || activeTab === 'note'" :aria-label="t('courseWorkspace.records.exportNotes', '导出笔记')" :title="t('courseWorkspace.records.exportNotes', '导出笔记')" @click="exportNotes">
          <Download :size="16" />
        </button>
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
        @click="openQuickNote"
      >
        <NotebookPen :size="17" />
        <span>
          <strong>{{ t('quickNote.title', '随手记') }}</strong>
          <small v-if="courseStore.currentNode">
            {{ t('quickNote.currentNode', '记录到当前章节') }}: <MathText :content="courseStore.currentNode.node_name" />
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
            <small>{{ t('quickNote.currentNode', '记录到当前章节') }}: <MathText :content="courseStore.currentNode?.node_name" /></small>
          </div>
          <button type="button" :aria-label="t('quickNote.cancel', '取消')" :title="t('quickNote.cancel', '取消')" @click="cancelQuickNote">
            <X :size="15" />
          </button>
        </div>
        <textarea
          v-model="quickNoteContent"
          ref="quickNoteInput"
          :aria-label="t('quickNote.title', '随手记')"
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
      <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" :aria-pressed="activeTab === tab.key" @click="activeTab = tab.key">
        {{ tab.label }} <span>{{ tab.count }}</span>
      </button>
    </nav>

    <div class="records-list">
      <div v-if="!filteredRecords.length" class="records-empty">
        <NotebookPen :size="28" />
        <span>{{ search.trim() ? t('notebook.noResults', '没有找到相关内容') : activeTab !== 'all' ? t('notebook.emptyCategory', '这个分类还没有记录') : t('notebook.empty', '笔记本还是空的') }}</span>
        <button v-if="search.trim()" type="button" @click="search = ''">{{ t('notebook.clearSearch', '清除搜索') }}</button>
      </div>
      <article v-for="record in filteredRecords" :key="record.id" class="record-row">
        <button class="record-main" @click="emit('viewDetail', record)">
          <span class="record-type" :data-type="recordType(record)">{{ typeLabel(recordType(record)) }}</span>
          <strong><MathText :content="record.summary || record.quote || record.content || typeLabel(recordType(record))" /></strong>
          <MathText v-if="record.quote && record.quote !== record.summary" tag="p" :content="record.quote" />
          <small><MathText :content="recordNodeName(record) || t('courseWorkspace.records.unknownNode', '课程位置')" /> · {{ formatTime(record.createdAt) }}</small>
        </button>
        <div class="record-actions">
          <span class="record-status">{{ statusLabel(record.status || '') }}</span>
          <button v-if="record.nodeId" :aria-label="t('courseWorkspace.records.locate', '定位原文')" :title="t('courseWorkspace.records.locate', '定位原文')" @click="emit('locate', record)">
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
import { computed, nextTick, ref } from 'vue'
import dayjs from 'dayjs'
import { ArrowDownUp, Download, LoaderCircle, LocateFixed, Notebook, NotebookPen, Plus, Save, X } from 'lucide-vue-next'
import { useNoteStore } from '../stores/notes'
import { useCourseStore } from '../stores/course'
import { t } from '../shared/i18n'
import { createUuid } from '../utils/client-id'
import MathText from './MathText.vue'

type RecordTab = 'all' | 'note' | 'issue' | 'review_task' | 'bookmark'
const emit = defineEmits<{
  (event: 'locate', record: any): void
  (event: 'viewDetail', record: any): void
  (event: 'close'): void
}>()
const props = withDefaults(defineProps<{ mode?: 'dialog' | 'sidebar' }>(), { mode: 'dialog' })
const noteStore = useNoteStore()
const courseStore = useCourseStore()
const activeTab = ref<RecordTab>('all')
const search = ref('')
const sortMode = ref<'time' | 'chapter'>('time')
const quickNoteOpen = ref(false)
const quickNoteInput = ref<HTMLTextAreaElement | null>(null)

async function openQuickNote() {
  quickNoteOpen.value = true
  await nextTick()
  quickNoteInput.value?.focus()
}
const quickNoteContent = ref('')
const quickNoteSaving = ref(false)

const officialRecords = computed(() => noteStore.notes.filter(item => item.sourceType !== 'format' && item.sourceType !== 'wrong'))
const recordType = (record: any) => (record.recordType || 'note') as Exclude<RecordTab, 'all'>
const count = (type: Exclude<RecordTab, 'all'>) => officialRecords.value.filter(item => recordType(item) === type).length
const tabs = computed(() => [
  { key: 'all' as const, label: t('courseWorkspace.records.tabs.all', '全部'), count: officialRecords.value.length },
  { key: 'note' as const, label: t('notebook.categories.note', '笔记'), count: count('note') },
  { key: 'issue' as const, label: t('notebook.categories.issue', '问题'), count: count('issue') },
  { key: 'review_task' as const, label: t('notebook.categories.review', '复习'), count: count('review_task') },
  { key: 'bookmark' as const, label: t('notebook.categories.bookmark', '书签'), count: count('bookmark') },
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
  return t(`notebook.categories.${type === 'review_task' ? 'review' : type}`, type)
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
      id: `quick-note-${createUuid()}`,
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
.records-panel { width:100%; height:min(680px,calc(100dvh - 72px)); display:flex; flex-direction:column; min-height:420px; overflow:hidden; color:var(--lz-text); background:var(--bg-secondary); font-size:var(--text-sm); }
.records-panel.is-empty { height:min(480px,calc(100dvh - 72px)); }
.records-header { flex:0 0 auto; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:12px; padding:16px 20px; border-bottom:1px solid var(--lz-border); }
.records-title { min-width:0; display:flex; gap:10px; align-items:center; }
.records-title__icon { width:32px; height:32px; flex:0 0 auto; display:grid; place-items:center; border-radius:var(--radius-sm); color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.records-title h3,.records-title p { margin:0; }
.records-title h3 { color:var(--lz-text-strong); font-size:var(--text-base); font-weight:650; }
.records-title p { margin-top:2px; color:var(--lz-text-secondary); font-size:var(--text-xs); }
.records-tools { grid-column:1/-1; min-width:0; display:flex; gap:8px; align-items:center; }
.records-tools input { min-width:0; flex:1; width:100%; height:38px; padding:0 12px; border:1px solid var(--lz-border); border-radius:var(--lz-radius-control); color:var(--lz-text); background:var(--lz-surface-subtle); font-size:var(--text-sm); }
.records-panel input::placeholder,.records-panel textarea::placeholder { color:var(--lz-text-secondary); opacity:1; }
.records-tools button,.records-close,.record-actions button,.records-empty button { flex:0 0 auto; min-width:34px; min-height:34px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:6px 9px; border:1px solid var(--lz-border); border-radius:var(--radius-sm); color:var(--lz-text-secondary); background:var(--bg-secondary); cursor:pointer; font-size:var(--text-xs); }
.records-tools button:hover,.records-close:hover,.record-actions button:hover,.records-empty button:hover { color:var(--lz-brand-strong); border-color:var(--lz-brand); background:var(--lz-brand-soft); }
.records-panel :is(button,input,textarea):focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.records-panel button:active:not(:disabled) { background:var(--lz-brand-soft); }
.quick-note { flex:0 0 auto; padding:16px 20px 4px; }
.quick-note-trigger { width:100%; display:grid; grid-template-columns:20px minmax(0,1fr) 18px; align-items:center; gap:10px; padding:12px; border:1px solid var(--lz-border); border-radius:var(--lz-radius-control); color:var(--lz-brand-strong); background:var(--lz-brand-soft); text-align:left; cursor:pointer; transition:border-color var(--duration-fast); }
.quick-note-trigger:hover:not(:disabled) { border-color:var(--lz-brand); }
.quick-note-trigger:disabled { color:var(--lz-text-secondary); background:var(--lz-surface-subtle); cursor:not-allowed; }
.quick-note-trigger>span,.quick-note-heading>div { min-width:0; display:flex; flex-direction:column; gap:4px; }
.quick-note-trigger strong,.quick-note-heading strong { font-size:var(--text-sm); font-weight:650; }
.quick-note-trigger small,.quick-note-heading small { color:var(--lz-text); font-size:var(--text-xs); line-height:1.5; overflow-wrap:anywhere; }
.quick-note-composer { display:grid; gap:12px; padding:12px; border:1px solid var(--lz-border); border-radius:var(--lz-radius-control); background:var(--lz-surface-subtle); }
.quick-note-heading { display:grid; grid-template-columns:18px minmax(0,1fr) 30px; align-items:start; gap:9px; color:var(--lz-brand-strong); }
.quick-note-heading>svg { margin-top:3px; }
.quick-note-heading button { width:30px; height:30px; display:grid; place-items:center; padding:0; border:1px solid var(--lz-border); border-radius:var(--radius-sm); color:var(--lz-text-secondary); background:var(--bg-secondary); cursor:pointer; }
.quick-note-heading button:hover { color:var(--lz-brand-strong); border-color:var(--lz-brand); }
.quick-note-composer textarea { width:100%; min-height:120px; resize:vertical; padding:10px 12px; border:1px solid var(--lz-border-strong); border-radius:var(--radius-sm); color:var(--lz-text-strong); background:var(--bg-secondary); font-size:var(--text-base); line-height:1.65; box-sizing:border-box; }
.quick-note-composer footer { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; }
.quick-note-composer footer small { color:var(--lz-text-secondary); font-size:var(--text-xs); }
.quick-note-composer footer button { min-height:36px; display:inline-flex; align-items:center; gap:6px; padding:6px 12px; border:1px solid transparent; border-radius:var(--radius-sm); color:var(--text-inverse); background:var(--lz-brand-strong); font-size:var(--text-sm); font-weight:600; cursor:pointer; }
.quick-note-composer footer button:hover:not(:disabled),.quick-note-composer footer button:active:not(:disabled) { background:var(--color-primary-700); }
.quick-note-composer footer button:disabled { opacity:.5; cursor:not-allowed; }
.quick-note-spin { animation:quick-note-spin .8s linear infinite; }
.record-tabs { flex:0 0 auto; display:flex; flex-wrap:wrap; gap:4px; padding:12px 20px; border-bottom:1px solid var(--lz-border); }
.record-tabs button { min-height:34px; display:inline-flex; align-items:center; gap:5px; padding:6px 8px; border:0; border-radius:var(--radius-sm); color:var(--lz-text-secondary); background:transparent; font-size:var(--text-sm); cursor:pointer; }
.record-tabs button:hover { color:var(--lz-brand-strong); background:var(--lz-surface-subtle); }
.record-tabs button.active { color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-weight:600; }
.record-tabs span { font-size:var(--text-xs); font-variant-numeric:tabular-nums; }
.records-list { flex:1; min-height:0; overflow:auto; scrollbar-gutter:stable; display:flex; flex-direction:column; gap:12px; padding:16px 20px 24px; }
.records-empty { flex:1; min-height:180px; display:flex; flex-direction:column; gap:12px; align-items:center; justify-content:center; color:var(--lz-text-secondary); text-align:center; }
.records-empty svg { color:var(--lz-brand); }
.records-empty span { font-size:var(--text-sm); }
.record-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; padding:14px; border:1px solid var(--lz-border); border-radius:var(--lz-radius-control); background:var(--bg-secondary); transition:border-color var(--duration-fast); }
.record-row:hover { border-color:var(--lz-brand); }
.record-main { min-width:0; text-align:left; border:0; border-radius:var(--radius-sm); background:transparent; padding:0; cursor:pointer; overflow-wrap:anywhere; }
.record-main strong { display:block; margin:8px 0 6px; color:var(--lz-text-strong); font-size:var(--text-base); font-weight:600; line-height:1.6; }
.record-main p { margin:0 0 8px; color:var(--lz-text); font-size:var(--text-sm); line-height:1.6; }
.record-main small { display:block; color:var(--lz-text-secondary); font-size:var(--text-xs); line-height:1.6; }
.record-type { display:inline-flex; padding:3px 7px; border-radius:6px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:var(--text-xs); font-weight:600; }
.record-type[data-type="issue"] { color:var(--lz-danger); background:var(--lz-danger-soft); }
.record-type[data-type="review_task"] { color:var(--lz-warning); background:var(--lz-warning-soft); }
.record-type[data-type="bookmark"] { color:var(--lz-success); background:var(--lz-success-soft); }
.record-actions { display:flex; gap:8px; align-items:center; }
.record-status { color:var(--lz-text-secondary); font-size:var(--text-xs); }
.records-panel.is-sidebar { height:100%; min-height:0; }
.records-panel.is-sidebar .records-header { padding:16px; }
.records-panel.is-sidebar .quick-note { padding:14px 16px 4px; }
.records-panel.is-sidebar .record-tabs { padding:12px; }
.records-panel.is-sidebar .records-list { padding:14px 16px 20px; }
.records-panel.is-sidebar .record-row { grid-template-columns:1fr; gap:10px; }
.records-panel.is-sidebar .record-actions { justify-content:flex-end; flex-wrap:wrap; }
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
