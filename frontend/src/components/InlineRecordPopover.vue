<template>
  <Teleport to="body">
    <Transition name="inline-record-fade">
      <aside
        v-if="visible && note"
        class="inline-record-popover"
        :class="{ interactive }"
        :style="positionStyle"
        :role="interactive ? 'dialog' : 'status'"
        :aria-modal="interactive ? 'false' : undefined"
        @mousedown.stop
        @mouseenter="emit('hold')"
        @mouseleave="!interactive && emit('close')"
      >
        <header>
          <span><NotebookTabs :size="14" /></span>
          <strong>{{ typeLabel }}</strong>
          <small :data-state="saveState">{{ saveLabel }}</small>
          <button v-if="interactive" type="button" :title="t('common.close', '关闭')" @click="emit('close')"><X :size="14" /></button>
        </header>
        <blockquote v-if="note.quote">{{ note.quote }}</blockquote>
        <textarea
          v-if="interactive && editable"
          ref="editorRef"
          v-model="draft"
          :placeholder="t('inlineRecords.placeholder', '在原文旁写下你的理解')"
          @input="queueSave"
        />
        <div v-else class="inline-record-content">{{ note.content || note.summary || t('inlineRecords.empty', '这条记录还没有正文') }}</div>
        <footer v-if="interactive">
          <button type="button" @click="emit('askAi', note)"><MessageSquareText :size="14" />{{ t('courseWorkspace.records.ask', '问 AI') }}</button>
          <button v-if="saveState === 'local_only'" type="button" @click="emit('retry', note)"><RefreshCw :size="14" />{{ t('inlineRecords.retry', '重试保存') }}</button>
          <button v-if="initialEdit" type="button" @click="emit('undo', note)"><Undo2 :size="14" />{{ t('inlineRecords.undo', '撤销') }}</button>
          <button type="button" class="danger" @click="emit('delete', note)"><Trash2 :size="14" />{{ t('common.delete', '删除') }}</button>
        </footer>
      </aside>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { MessageSquareText, NotebookTabs, RefreshCw, Trash2, Undo2, X } from 'lucide-vue-next'
import type { Note } from '@/stores/types'
import { t } from '@/shared/i18n'

const props = withDefaults(defineProps<{
  visible: boolean
  note: Note | null
  x: number
  y: number
  interactive?: boolean
  saveState?: 'idle' | 'saving' | 'saved' | 'local_only'
  initialEdit?: boolean
}>(), { interactive: false, saveState: 'idle', initialEdit: false })
const emit = defineEmits<{
  close: []
  hold: []
  save: [payload: { note: Note; content: string }]
  retry: [note: Note]
  undo: [note: Note]
  delete: [note: Note]
  askAi: [note: Note]
}>()
const draft = ref('')
const editorRef = ref<HTMLTextAreaElement | null>(null)
let saveTimer: ReturnType<typeof setTimeout> | null = null

const editable = computed(() => props.note?.recordType === 'note' && props.note?.sourceType !== 'ai')
const typeLabel = computed(() => {
  if (props.note?.sourceType === 'ai') return t('courseWorkspace.records.type.aiNote', 'AI 笔记')
  if (props.note?.recordType === 'issue') return t('courseWorkspace.records.type.issue', '问题')
  if (props.note?.recordType === 'review_task') return t('courseWorkspace.records.type.review', '复习')
  if (props.note?.recordType === 'bookmark') return t('courseWorkspace.records.type.bookmark', '书签')
  return t('courseWorkspace.records.type.note', '笔记')
})
const saveLabel = computed(() => ({
  idle: '',
  saving: t('inlineRecords.saving', '正在保存'),
  saved: t('inlineRecords.saved', '已保存'),
  local_only: t('inlineRecords.localOnly', '仅保存在本机'),
}[props.saveState]))
const positionStyle = computed(() => {
  const width = Math.min(340, Math.max(260, window.innerWidth - 24))
  const left = Math.min(Math.max(12, props.x - width / 2), Math.max(12, window.innerWidth - width - 12))
  const above = props.y > window.innerHeight * .54
  return {
    width: `${width}px`,
    left: `${left}px`,
    top: `${Math.min(window.innerHeight - 12, Math.max(12, props.y + (above ? -10 : 10)))}px`,
    transform: above ? 'translateY(-100%)' : 'none',
  }
})

watch(() => [props.visible, props.note?.id], async () => {
  draft.value = props.note?.content || ''
  if (props.visible && props.interactive && props.initialEdit) {
    await nextTick()
    editorRef.value?.focus()
  }
}, { immediate: true })

function queueSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    if (props.note && draft.value.trim()) emit('save', { note: props.note, content: draft.value })
  }, 650)
}

onBeforeUnmount(() => { if (saveTimer) clearTimeout(saveTimer) })
</script>

<style scoped>
.inline-record-popover { position:fixed; z-index:610; overflow:hidden; border:1px solid rgba(203,213,225,.78); border-radius:8px; color:var(--lz-text); background:rgba(255,255,255,.98); box-shadow:0 14px 38px rgba(15,23,42,.18); pointer-events:none; }
.inline-record-popover.interactive { pointer-events:auto; }
.inline-record-popover header { min-height:38px; display:grid; grid-template-columns:24px minmax(0,1fr) auto auto; align-items:center; gap:6px; padding:0 9px; border-bottom:1px solid var(--lz-border); background:rgba(248,250,252,.88); }
.inline-record-popover header > span { width:22px; height:22px; display:grid; place-items:center; border-radius:6px; color:#b45309; background:#fffbeb; }.inline-record-popover header strong { font-size:11px; }.inline-record-popover header small { color:var(--lz-text-muted); font-size:9px; }.inline-record-popover header small[data-state="local_only"] { color:var(--lz-warning); }.inline-record-popover header button { width:25px; height:25px; display:grid; place-items:center; border:0; border-radius:5px; color:var(--lz-text-muted); background:transparent; cursor:pointer; }
.inline-record-popover blockquote { max-height:64px; overflow:hidden; margin:0; padding:9px 11px; border-left:3px solid #fde68a; color:var(--lz-text-muted); background:#fffbeb; font-size:10px; line-height:1.5; }
.inline-record-content { max-height:150px; overflow:auto; padding:11px; color:var(--lz-text); font-size:12px; line-height:1.6; white-space:pre-wrap; }
.inline-record-popover textarea { width:calc(100% - 20px); min-height:96px; margin:10px; padding:9px 10px; resize:vertical; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text); background:#fff; outline:none; font-size:12px; line-height:1.55; }.inline-record-popover textarea:focus { border-color:var(--lz-brand); box-shadow:0 0 0 3px rgba(99,102,241,.08); }
.inline-record-popover footer { display:flex; align-items:center; gap:5px; padding:7px 9px; border-top:1px solid var(--lz-border); }.inline-record-popover footer button { min-height:28px; display:inline-flex; align-items:center; gap:5px; padding:0 7px; border:0; border-radius:5px; color:var(--lz-text-secondary); background:transparent; font-size:10px; cursor:pointer; }.inline-record-popover footer button:hover { background:var(--lz-surface-muted); }.inline-record-popover footer button.danger { margin-left:auto; color:var(--lz-danger); }
.inline-record-fade-enter-active,.inline-record-fade-leave-active { transition:opacity .12s ease,transform .12s ease; }.inline-record-fade-enter-from,.inline-record-fade-leave-to { opacity:0; }
</style>
