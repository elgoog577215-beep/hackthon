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
        <button type="button" :aria-label="sortMode === 'time' ? t('courseWorkspace.records.sortByChapter', '按章节排序') : t('courseWorkspace.records.sortByTime', '按时间排序')" :title="sortMode === 'time' ? t('courseWorkspace.records.sortByChapter', '按章节排序') : t('courseWorkspace.records.sortByTime', '按时间排序')" :aria-pressed="sortMode === 'chapter'" @click="toggleSortMode">
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
            <span v-if="quickNoteSaved" class="quick-note-saved" role="status">{{ copy('已保存到笔记本', 'Saved to notebook') }}</span>
            <template v-else>{{ t('quickNote.currentNode', '记录到当前章节') }}: <MathText :content="courseStore.currentNode.node_name" /></template>
          </small>
          <small v-else>{{ t('quickNote.noNode', '请先选择一个课程章节') }}</small>
        </span>
        <Plus :size="17" />
      </button>

      <form
        v-else
        id="quick-note-composer"
        class="quick-note-composer"
        :aria-busy="quickNoteSaving"
        @submit.prevent="saveQuickNote"
      >
        <div class="quick-note-heading">
          <NotebookPen :size="17" />
          <div>
            <strong>{{ t('quickNote.title', '随手记') }}</strong>
            <small>{{ t('quickNote.currentNode', '记录到当前章节') }}: <MathText :content="courseStore.currentNode?.node_name" /></small>
          </div>
          <button type="button" :disabled="quickNoteSaving" :aria-label="t('quickNote.cancel', '取消')" :title="t('quickNote.cancel', '取消')" @click="cancelQuickNote">
            <X :size="15" />
          </button>
        </div>
        <textarea
          v-model="quickNoteContent"
          ref="quickNoteInput"
          :disabled="quickNoteSaving"
          :aria-label="t('quickNote.title', '随手记')"
          maxlength="2000"
          :placeholder="t('quickNote.placeholder', '记下一个想法、疑问或待复习点…')"
          @keydown.ctrl.enter.prevent="saveQuickNote"
          @keydown.meta.enter.prevent="saveQuickNote"
          @input="quickNoteError = ''"
        ></textarea>
        <p v-if="quickNoteError" class="quick-note-error" role="alert">{{ quickNoteError }}</p>
        <footer>
          <small>{{ t('quickNote.shortcut', 'Ctrl / ⌘ + Enter 保存') }}</small>
          <button type="submit" :disabled="quickNoteSaving || !quickNoteContent.trim()" :aria-busy="quickNoteSaving">
            <LoaderCircle v-if="quickNoteSaving" :size="14" class="quick-note-spin" />
            <Save v-else :size="14" />
            {{ quickNoteSaving ? copy('正在保存…', 'Saving…') : t('quickNote.save', '保存笔记') }}
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
      <section v-for="group in recordGroups" :key="group.id" class="record-group">
        <h4 v-if="sortMode === 'chapter'" class="record-group-heading">
          <MathText :content="group.nodeName || t('courseWorkspace.records.unknownNode', '未知章节')" />
          <span>{{ group.records.length }}</span>
        </h4>
        <article v-for="record in group.records" :key="record.id" class="record-row" :data-record-id="record.id">
          <button class="record-main" @click="emit('viewDetail', record)">
            <span class="record-type" :data-type="recordType(record)">{{ typeLabel(recordType(record)) }}</span>
            <strong><MathText :content="record.summary || record.quote || record.content || typeLabel(recordType(record))" /></strong>
            <MathText v-if="record.content && record.content !== record.summary && record.content !== record.quote" tag="p" class="record-excerpt" :content="record.content" />
            <MathText v-if="record.quote && record.quote !== record.summary && record.quote !== record.content" tag="p" class="record-quote" :content="record.quote" />
            <small><MathText :content="recordNodeName(record) || t('courseWorkspace.records.unknownNode', '课程位置')" /> · {{ formatTime(record.createdAt) }}</small>
          </button>
          <div class="record-actions">
            <span v-if="statusLabel(record)" class="record-status" :data-tone="statusTone(record)">{{ statusLabel(record) }}</span>
            <button v-if="record.nodeId" :aria-label="t('courseWorkspace.records.locate', '定位原文')" :title="t('courseWorkspace.records.locate', '定位原文')" @click="emit('locate', record)">
              <LocateFixed :size="15" />
            </button>
            <button
              v-if="statusAction(record)"
              type="button"
              :disabled="Boolean(statusSavingFor)"
              :aria-busy="statusSavingFor === record.id"
              @click="updateStatus(record, statusAction(record)!.target)"
            >
              <LoaderCircle v-if="statusSavingFor === record.id" :size="13" class="quick-note-spin" />
              {{ statusSavingFor === record.id ? copy('正在更新…', 'Updating…') : statusSaveFailedFor === record.id ? copy('重试', 'Retry') : statusAction(record)!.label }}
            </button>
          </div>
          <p v-if="statusSaveFailedFor === record.id" class="record-action-error" role="alert">{{ copy('状态没有保存，请重试。', 'Status could not be saved. Please try again.') }}</p>
          <div class="record-metadata">
            <label class="record-priority">
              <span>{{ copy('优先级', 'Priority') }}</span>
              <select :aria-label="`${copy('优先级', 'Priority')}：${record.summary || record.content || typeLabel(recordType(record))}`" :value="record.priority || 'medium'" :disabled="Boolean(prioritySavingFor)" :aria-busy="prioritySavingFor === record.id" @change="updatePriority(record, $event)">
                <option value="low">{{ copy('低', 'Low') }}</option>
                <option value="medium">{{ copy('中', 'Medium') }}</option>
                <option value="high">{{ copy('高', 'High') }}</option>
              </select>
            </label>
            <span v-if="prioritySavingFor === record.id" class="record-save-feedback" role="status">{{ copy('正在保存优先级…', 'Saving priority…') }}</span>
            <span v-if="prioritySaveFailedFor === record.id" class="record-priority-error" role="alert">{{ copy('优先级保存失败，请重试。', 'Could not save priority. Please try again.') }}</span>
            <span v-if="tagSavedFor === record.id" class="record-save-feedback" role="status">{{ copy('标签已保存', 'Tags saved') }}</span>
            <div class="record-tags">
              <span v-for="tag in record.tags || []" :key="tag" class="record-tag">{{ tag }}</span>
              <button type="button" class="record-tags-edit" :disabled="tagSaving" :aria-expanded="editingTagsFor === record.id" @click="beginTagEdit(record)">
                {{ editingTagsFor === record.id ? copy('正在编辑', 'Editing tags') : copy('编辑标签', 'Edit tags') }}
              </button>
            </div>
            <form v-if="editingTagsFor === record.id" class="record-tag-form" :aria-busy="tagSaving" @submit.prevent="saveTags(record)">
              <input ref="tagInput" v-model="tagDraft" :aria-label="copy('标签，使用逗号分隔', 'Tags, separated by commas')" :placeholder="copy('输入标签，用逗号分隔', 'Enter tags separated by commas')" maxlength="240" :disabled="tagSaving" />
              <span v-if="tagSaveFailed" class="record-tag-error" role="alert">{{ copy('保存失败，请重试。', 'Could not save. Please try again.') }}</span>
              <button type="submit" :disabled="tagSaving"><LoaderCircle v-if="tagSaving" :size="13" class="quick-note-spin" />{{ tagSaving ? copy('保存中…', 'Saving…') : copy('保存', 'Save') }}</button>
              <button type="button" :disabled="tagSaving" @click="cancelTagEdit">{{ copy('取消', 'Cancel') }}</button>
            </form>
          </div>
        </article>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import dayjs from 'dayjs'
import { ArrowDownUp, Download, LoaderCircle, LocateFixed, Notebook, NotebookPen, Plus, Save, X } from 'lucide-vue-next'
import { useNoteStore } from '../stores/notes'
import { useCourseStore } from '../stores/course'
import { activeLocale, t } from '../shared/i18n'
import { createUuid } from '../utils/client-id'
import MathText from './MathText.vue'
import type { Note } from '../stores/types'

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
const editingTagsFor = ref('')
const tagDraft = ref('')
const tagSaveFailed = ref(false)
const tagSaving = ref(false)
const tagInput = ref<HTMLInputElement | HTMLInputElement[] | null>(null)
const tagSavedFor = ref('')
let tagSavedTimer: ReturnType<typeof setTimeout> | undefined
const prioritySaveFailedFor = ref('')
const prioritySavingFor = ref('')
const statusSavingFor = ref('')
const statusSaveFailedFor = ref('')
const copy = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh

async function openQuickNote() {
  quickNoteSaved.value = false
  quickNoteError.value = ''
  quickNoteOpen.value = true
  await nextTick()
  quickNoteInput.value?.focus()
}
const quickNoteContent = ref('')
const quickNoteSaving = ref(false)
const quickNoteError = ref('')
const quickNoteSaved = ref(false)
let quickNoteSavedTimer: ReturnType<typeof setTimeout> | undefined

onBeforeUnmount(() => {
  if (tagSavedTimer) clearTimeout(tagSavedTimer)
  if (quickNoteSavedTimer) clearTimeout(quickNoteSavedTimer)
})

const officialRecords = computed(() => noteStore.notes.filter(item => item.sourceType !== 'format' && item.sourceType !== 'wrong'))
const recordType = (record: Note) => (record.recordType || 'note') as Exclude<RecordTab, 'all'>
const count = (type: Exclude<RecordTab, 'all'>) => officialRecords.value.filter(item => recordType(item) === type).length
const tabs = computed(() => [
  { key: 'all' as const, label: t('courseWorkspace.records.tabs.all', '全部'), count: officialRecords.value.length },
  { key: 'note' as const, label: t('notebook.categories.note', '笔记'), count: count('note') },
  { key: 'issue' as const, label: t('notebook.categories.issue', '问题'), count: count('issue') },
  { key: 'review_task' as const, label: t('notebook.categories.review', '复习'), count: count('review_task') },
  { key: 'bookmark' as const, label: t('notebook.categories.bookmark', '书签'), count: count('bookmark') },
])
const chapterOrder = computed(() => {
  const linearNodes = courseStore.getLinearNodes(courseStore.courseTree)
  const orderedNodes = linearNodes.length ? linearNodes : courseStore.nodes
  return new Map(orderedNodes.map((node, index) => [node.node_id, index]))
})
const filteredRecords = computed(() => {
  const query = search.value.trim().toLowerCase()
  const values = officialRecords.value.filter(item => {
    if (activeTab.value !== 'all' && recordType(item) !== activeTab.value) return false
    if (!query) return true
    return [item.summary, item.content, item.quote, recordNodeName(item), ...(item.tags || [])]
      .some(value => String(value || '').toLowerCase().includes(query))
  })
  return [...values].sort((left, right) => {
    if (sortMode.value === 'chapter') {
      const order = (chapterOrder.value.get(left.nodeId) ?? Number.MAX_SAFE_INTEGER) - (chapterOrder.value.get(right.nodeId) ?? Number.MAX_SAFE_INTEGER)
      return order || recordNodeName(left).localeCompare(recordNodeName(right), 'zh-CN') || Number(right.createdAt || 0) - Number(left.createdAt || 0)
    }
    return Number(right.createdAt || 0) - Number(left.createdAt || 0)
  })
})
const recordGroups = computed(() => {
  if (sortMode.value === 'time') return [{ id: 'recent', nodeName: '', records: filteredRecords.value }]
  const groups = new Map<string, Note[]>()
  filteredRecords.value.forEach(record => {
    const key = record.nodeId || ''
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(record)
  })
  return Array.from(groups.entries()).map(([id, records]) => ({ id: id || 'unknown', nodeName: recordNodeName(records[0]!), records }))
})

function toggleSortMode() {
  sortMode.value = sortMode.value === 'time' ? 'chapter' : 'time'
}

function typeLabel(type: Exclude<RecordTab, 'all'>) {
  const fallback = {
    note: copy('笔记', 'Notes'),
    issue: copy('问题', 'Questions'),
    review_task: copy('复习', 'Review'),
    bookmark: copy('书签', 'Bookmarks'),
  }[type]
  return t(`notebook.categories.${type === 'review_task' ? 'review' : type}`, fallback)
}

const recordStatusCopy: Record<string, [string, string]> = {
  'note:active': ['已记录', 'Saved'],
  'note:archived': ['已归档', 'Archived'],
  'bookmark:active': ['已收藏', 'Saved'],
  'bookmark:archived': ['已归档', 'Archived'],
  'issue:open': ['待处理', 'Open'],
  'issue:explaining': ['处理中', 'In progress'],
  'issue:awaiting_verification': ['待验证', 'Awaiting review'],
  'issue:resolved': ['已解决', 'Resolved'],
  'issue:reopened': ['重新打开', 'Reopened'],
  'issue:archived': ['已归档', 'Archived'],
  'review_task:pending': ['待复习', 'To review'],
  'review_task:due': ['该复习了', 'Due to review'],
  'review_task:completed': ['已完成', 'Completed'],
  'review_task:dismissed': ['已跳过', 'Skipped'],
  'review_task:archived': ['已归档', 'Archived'],
}

function statusLabel(record: Note) {
  const status = String(record.status || '')
  const copyForStatus = recordStatusCopy[`${recordType(record)}:${status}`]
  if (!copyForStatus) return status ? copy('状态已更新', 'Status updated') : ''
  return copy(copyForStatus[0], copyForStatus[1])
}

function statusTone(record: Note) {
  const status = String(record.status || '')
  if (status === 'archived' || status === 'dismissed') return 'muted'
  if (status === 'resolved' || status === 'completed' || (recordType(record) === 'bookmark' && status === 'active')) return 'success'
  if (recordType(record) === 'note' || recordType(record) === 'bookmark') return 'brand'
  return 'warning'
}

function statusAction(record: Note): { target: string; label: string } | null {
  const status = String(record.status || '')
  if (recordType(record) === 'issue') {
    if (status === 'resolved') return { target: 'reopened', label: copy('重新打开', 'Reopen') }
    if (status === 'archived') return { target: 'reopened', label: copy('恢复问题', 'Restore issue') }
    if (['open', 'explaining', 'awaiting_verification', 'reopened'].includes(status)) {
      return { target: 'resolved', label: t('courseWorkspace.records.resolve', '标记解决') }
    }
  }
  if (recordType(record) === 'review_task') {
    if (status === 'pending' || status === 'due') return { target: 'completed', label: t('courseWorkspace.records.completeReview', '完成复习') }
    if (status === 'archived') return { target: 'pending', label: copy('恢复复习', 'Restore review') }
    if (status === 'completed' || status === 'dismissed') return { target: 'pending', label: t('courseWorkspace.records.reviewAgain', '再次复习') }
  }
  return null
}

async function updateStatus(record: Note, status: string) {
  if (statusSavingFor.value) return
  statusSavingFor.value = record.id
  statusSaveFailedFor.value = ''
  try {
    const updated = await noteStore.updateRecordStatus(record.id, status)
    if (!updated) statusSaveFailedFor.value = record.id
  } catch {
    statusSaveFailedFor.value = record.id
  } finally {
    statusSavingFor.value = ''
  }
}

async function updatePriority(record: Note, event: Event) {
  const value = (event.currentTarget as HTMLSelectElement).value
  if (value !== 'low' && value !== 'medium' && value !== 'high') return
  prioritySaveFailedFor.value = ''
  prioritySavingFor.value = record.id
  try {
    if (!(await noteStore.updateNotePriority(record.id, value))) prioritySaveFailedFor.value = record.id
  } catch {
    prioritySaveFailedFor.value = record.id
  } finally {
    prioritySavingFor.value = ''
  }
}

function beginTagEdit(record: Note) {
  if (editingTagsFor.value === record.id) {
    cancelTagEdit()
    return
  }
  editingTagsFor.value = record.id
  tagDraft.value = (record.tags || []).join(', ')
  tagSaveFailed.value = false
  tagSavedFor.value = ''
  void nextTick(() => {
    const input = Array.isArray(tagInput.value) ? tagInput.value[0] : tagInput.value
    input?.focus()
  })
}

function cancelTagEdit() {
  editingTagsFor.value = ''
  tagDraft.value = ''
  tagSaveFailed.value = false
  tagSaving.value = false
}

async function saveTags(record: Note) {
  if (tagSaving.value) return
  const tags = [...new Set(tagDraft.value.split(/[，,\n]/).map(tag => tag.trim()).filter(Boolean))]
  tagSaving.value = true
  try {
    tagSaveFailed.value = !(await noteStore.updateNoteTags(record.id, tags))
  } catch {
    tagSaveFailed.value = true
  } finally {
    tagSaving.value = false
  }
  if (tagSaveFailed.value) return
  cancelTagEdit()
  tagSavedFor.value = record.id
  if (tagSavedTimer) clearTimeout(tagSavedTimer)
  tagSavedTimer = setTimeout(() => { tagSavedFor.value = '' }, 2200)
}

function cancelQuickNote() {
  quickNoteOpen.value = false
  quickNoteContent.value = ''
  quickNoteError.value = ''
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
    if (!saved) {
      quickNoteError.value = copy('保存失败，内容还在这里，可以重试。', 'Could not save. Your note is still here; you can retry.')
      return
    }
    activeTab.value = 'note'
    cancelQuickNote()
    quickNoteSaved.value = true
    if (quickNoteSavedTimer) clearTimeout(quickNoteSavedTimer)
    quickNoteSavedTimer = setTimeout(() => { quickNoteSaved.value = false }, 2600)
  } catch {
    quickNoteError.value = copy('保存失败，内容还在这里，可以重试。', 'Could not save. Your note is still here; you can retry.')
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
.records-header { flex:0 0 auto; display:grid; grid-template-columns:minmax(0,auto) minmax(0,1fr) auto; align-items:center; gap:12px; padding:14px 20px; border-bottom:1px solid var(--lz-border); }
.records-title { min-width:0; display:flex; gap:10px; align-items:center; }
.records-header .records-title { grid-column:1; grid-row:1; }
.records-header .records-tools { grid-column:2; grid-row:1; }
.records-header .records-close { grid-column:3; grid-row:1; }
.records-title__icon { width:32px; height:32px; flex:0 0 auto; display:grid; place-items:center; border-radius:var(--radius-sm); color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.records-title h3,.records-title p { margin:0; }
.records-title h3 { color:var(--lz-text-strong); font-size:var(--text-base); font-weight:650; }
.records-title p { margin-top:2px; color:var(--lz-text-secondary); font-size:var(--text-xs); }
.records-tools { min-width:0; display:flex; gap:8px; align-items:center; }
.records-tools input { min-width:0; flex:1; width:100%; height:38px; padding:0 12px; border:1px solid var(--lz-border); border-radius:var(--lz-radius-control); color:var(--lz-text); background:var(--lz-surface-subtle); font-size:var(--text-sm); }
.records-panel input::placeholder,.records-panel textarea::placeholder { color:var(--lz-text-secondary); opacity:1; }
.records-tools button,.records-close,.record-actions button,.records-empty button { flex:0 0 auto; min-width:34px; min-height:34px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:6px 9px; border:1px solid var(--lz-border); border-radius:var(--radius-sm); color:var(--lz-text-secondary); background:var(--bg-secondary); cursor:pointer; font-size:var(--text-xs); }
.records-tools button:hover,.records-close:hover,.record-actions button:hover,.records-empty button:hover { color:var(--lz-brand-strong); border-color:var(--lz-brand); background:var(--lz-brand-soft); }
.records-panel button:active:not(:disabled) { background:var(--lz-brand-soft); }
.records-panel :is(button,input,textarea,select):focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.quick-note { flex:0 0 auto; padding:10px 20px 2px; }
.quick-note-trigger { width:100%; display:grid; grid-template-columns:20px minmax(0,1fr) 18px; align-items:center; gap:10px; padding:9px 12px; border:1px solid var(--lz-border); border-radius:var(--lz-radius-control); color:var(--lz-brand-strong); background:var(--lz-brand-soft); text-align:left; cursor:pointer; transition:border-color var(--duration-fast); }
.quick-note-trigger:hover:not(:disabled) { border-color:var(--lz-brand); background:color-mix(in srgb,var(--lz-brand-soft) 72%,var(--bg-secondary)); }
.quick-note-trigger:disabled { color:var(--lz-text-secondary); background:var(--lz-surface-subtle); cursor:not-allowed; }
.quick-note-trigger>span,.quick-note-heading>div { min-width:0; display:flex; flex-direction:column; gap:4px; }
.quick-note-trigger strong,.quick-note-heading strong { font-size:var(--text-sm); font-weight:650; }
.quick-note-trigger small,.quick-note-heading small { color:var(--lz-text); font-size:var(--text-xs); line-height:1.5; overflow-wrap:anywhere; }
.quick-note-saved { color:var(--lz-success); font-weight:600; }
.quick-note-composer { display:grid; gap:12px; padding:12px; border:1px solid var(--lz-border); border-radius:var(--lz-radius-control); background:var(--lz-surface-subtle); }
.quick-note-heading { display:grid; grid-template-columns:18px minmax(0,1fr) 30px; align-items:start; gap:9px; color:var(--lz-brand-strong); }
.quick-note-heading>svg { margin-top:3px; }
.quick-note-heading button { width:30px; height:30px; display:grid; place-items:center; padding:0; border:1px solid var(--lz-border); border-radius:var(--radius-sm); color:var(--lz-text-secondary); background:var(--bg-secondary); cursor:pointer; }
.quick-note-heading button:hover { color:var(--lz-brand-strong); border-color:var(--lz-brand); }
.quick-note-composer textarea { width:100%; min-height:120px; resize:vertical; padding:10px 12px; border:1px solid var(--lz-border-strong); border-radius:var(--radius-sm); color:var(--lz-text-strong); background:var(--bg-secondary); font-size:var(--text-base); line-height:1.65; box-sizing:border-box; }
.quick-note-error { margin:0; color:var(--lz-danger); font-size:var(--text-xs); line-height:1.5; }
.quick-note-composer footer { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; }
.quick-note-composer footer small { color:var(--lz-text-secondary); font-size:var(--text-xs); }
.quick-note-composer footer button { min-height:36px; display:inline-flex; align-items:center; gap:6px; padding:6px 12px; border:1px solid var(--lz-action-border); border-radius:var(--lz-action-radius); color:var(--lz-action-text); background:var(--lz-action-bg); font-size:var(--text-sm); font-weight:600; cursor:pointer; box-shadow:var(--lz-action-shadow); }
.quick-note-composer footer button:hover:not(:disabled),.quick-note-composer footer button:active:not(:disabled) { background:var(--lz-action-bg); }
.quick-note-composer footer button:disabled { opacity:.5; cursor:not-allowed; }
.quick-note-spin { animation:quick-note-spin .8s linear infinite; }
.record-tabs { flex:0 0 auto; display:flex; flex-wrap:wrap; gap:4px; padding:12px 20px; border-bottom:1px solid var(--lz-border); }
.record-tabs button { min-height:34px; display:inline-flex; align-items:center; gap:5px; padding:6px 8px; border:0; border-radius:var(--radius-sm); color:var(--lz-text-secondary); background:transparent; font-size:var(--text-sm); cursor:pointer; }
.record-tabs button:hover { color:var(--lz-brand-strong); background:var(--lz-surface-subtle); }
.record-tabs button.active { color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-weight:600; }
.record-tabs span { font-size:var(--text-xs); font-variant-numeric:tabular-nums; }
.records-list { flex:1; min-height:0; overflow:auto; scrollbar-gutter:stable; display:flex; flex-direction:column; gap:12px; padding:16px 20px 24px; }
.record-group { display:flex; flex-direction:column; gap:12px; }
.record-group-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:8px 0 0; color:var(--lz-text-secondary); font-size:var(--text-xs); font-weight:600; }
.record-group-heading span { color:var(--lz-text-secondary); font-size:11px; font-variant-numeric:tabular-nums; }
.records-empty { flex:1; min-height:180px; display:flex; flex-direction:column; gap:12px; align-items:center; justify-content:center; color:var(--lz-text-secondary); text-align:center; }
.records-empty svg { color:var(--lz-brand); }
.records-empty span { font-size:var(--text-sm); }
.record-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:10px 14px; padding:12px 13px; border:1px solid var(--lz-border); border-radius:var(--lz-radius-control); background:var(--bg-secondary); transition:border-color var(--duration-fast); }
.record-row:hover { border-color:var(--lz-brand); }
.record-main { min-width:0; text-align:left; border:0; border-radius:var(--radius-sm); background:transparent; padding:0; cursor:pointer; overflow-wrap:anywhere; }
.record-main strong { display:block; margin:5px 0 4px; color:var(--lz-text-strong); font-size:var(--text-base); font-weight:600; line-height:1.5; }
.record-main p { margin:0 0 5px; color:var(--lz-text); font-size:var(--text-sm); line-height:1.5; }
.record-main .record-excerpt { display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
.record-main .record-quote { display:-webkit-box; overflow:hidden; color:var(--lz-text-secondary); font-size:var(--text-xs); font-style:italic; -webkit-box-orient:vertical; -webkit-line-clamp:1; }
.record-main small { display:block; color:var(--lz-text-secondary); font-size:var(--text-xs); line-height:1.45; }
.record-type { display:inline-flex; padding:3px 7px; border-radius:6px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:var(--text-xs); font-weight:600; }
.record-type[data-type="issue"] { color:var(--lz-danger); background:var(--lz-danger-soft); }
.record-type[data-type="review_task"] { color:var(--lz-warning); background:var(--lz-warning-soft); }
.record-type[data-type="bookmark"] { color:var(--lz-success); background:var(--lz-success-soft); }
.record-actions { display:flex; gap:8px; align-items:center; }
.record-metadata { grid-column:1/-1; min-width:0; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px 14px; padding-top:8px; border-top:1px solid var(--lz-border); }
.record-priority { display:flex; align-items:center; gap:7px; color:var(--lz-text-secondary); font-size:var(--text-xs); }
.record-priority select { min-height:28px; padding:3px 24px 3px 8px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text); background:var(--bg-secondary); font-size:var(--text-xs); }
.record-priority-error { color:var(--lz-danger); font-size:var(--text-xs); }
.record-tags { min-width:0; display:flex; align-items:center; flex-wrap:wrap; gap:5px; }
.record-tag { max-width:18ch; overflow:hidden; padding:3px 7px; border-radius:5px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.record-tags-edit { min-height:28px !important; padding:4px 8px !important; border-style:dashed !important; font-size:11px !important; }
.record-tag-form { grid-column:1/-1; display:flex; flex-wrap:wrap; gap:7px; }
.record-tag-form input { flex:1 1 180px; min-width:0; min-height:34px; padding:6px 9px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text); background:var(--bg-secondary); font-size:var(--text-sm); }
.record-tag-form button { min-height:34px; padding:6px 10px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:var(--bg-secondary); cursor:pointer; font-size:var(--text-xs); }
.record-tag-form button[type="submit"] { color:var(--lz-action-text); border-color:var(--lz-action-border); background:var(--lz-action-bg); font-weight:600; }
.record-tag-error { flex:1 1 100%; color:var(--lz-danger); font-size:var(--text-xs); }
.record-status { display:inline-flex; align-items:center; min-height:25px; padding:3px 8px; border-radius:999px; color:var(--lz-text-secondary); background:var(--lz-surface-subtle); font-size:var(--text-xs); font-weight:600; white-space:nowrap; }
.record-status[data-tone="brand"] { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.record-status[data-tone="success"] { color:var(--lz-success); background:var(--lz-success-soft); }
.record-status[data-tone="warning"] { color:var(--lz-warning); background:var(--lz-warning-soft); }
.record-status[data-tone="muted"] { color:var(--lz-text-secondary); background:var(--lz-surface-subtle); }
.record-actions button:disabled,.record-tag-form button:disabled,.record-tag-form input:disabled,.record-priority select:disabled { opacity:.62; cursor:wait; }
.record-action-error { grid-column:1/-1; margin:0; color:var(--lz-danger); font-size:var(--text-xs); line-height:1.5; text-align:right; }
.record-save-feedback { color:var(--lz-success); font-size:var(--text-xs); }
.record-tag-form button:disabled { opacity:.62; cursor:wait; }
.records-panel.is-sidebar { height:100%; min-height:0; }
.records-panel.is-sidebar .records-header { grid-template-columns:minmax(0,1fr) auto; padding:16px; }
.records-panel.is-sidebar .records-header .records-title { grid-column:1; grid-row:1; }
.records-panel.is-sidebar .records-header .records-tools { grid-column:1/-1; grid-row:2; }
.records-panel.is-sidebar .records-header .records-close { grid-column:2; grid-row:1; }
.records-panel.is-sidebar .quick-note { padding:14px 16px 4px; }
.records-panel.is-sidebar .record-tabs { padding:12px; }
.records-panel.is-sidebar .records-list { padding:14px 16px 20px; }
.records-panel.is-sidebar .record-row { grid-template-columns:1fr; gap:10px; }
.records-panel.is-sidebar .record-actions { justify-content:flex-end; flex-wrap:wrap; }
@keyframes quick-note-spin { to { transform:rotate(360deg); } }
@media (max-width:720px) {
  .records-panel { height:calc(100dvh - 20px); min-height:0; }
  .records-panel.is-empty { height:calc(100dvh - 20px); }
  .records-header { min-height:64px; grid-template-columns:minmax(0,1fr) auto; align-items:center; padding:11px 12px 11px 14px; }
  .records-header .records-title { grid-column:1; grid-row:1; }
  .records-header .records-tools { grid-column:1/-1; grid-row:2; }
  .records-header .records-close { grid-column:2; grid-row:1; }
  .records-title__icon { width:36px; height:36px; border-radius:10px; }
  .records-title h3 { font-size:16px; }
  .records-tools input { display:block; height:36px; }
  .records-tools button { min-width:32px; width:32px; height:32px; padding:0; }
  .quick-note { padding:10px 14px 3px; }
  .quick-note-trigger>span,.quick-note-heading>div { align-items:flex-start; flex-direction:column; gap:1px; }
  .quick-note-composer footer small { display:none; }
  .record-tabs { gap:4px; padding:10px; }
  .record-tabs button { padding:6px 8px; font-size:10px; }
  .records-list { padding:12px 14px 18px; }
  .record-row { grid-template-columns:1fr; }
  .record-actions { justify-content:flex-end; flex-wrap:wrap; }
  .record-metadata { align-items:flex-start; flex-direction:column; }
}
</style>
