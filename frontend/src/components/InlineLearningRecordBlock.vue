<template>
  <aside
    class="inline-learning-record"
    :data-source="note.sourceType || 'user'"
    :data-sync-state="note.syncState || 'saved'"
  >
    <header>
      <span><NotebookTabs :size="14" /></span>
      <strong>{{ recordLabel }}</strong>
      <small v-if="note.syncState === 'local_only'">{{ t('inlineRecords.localOnly', '仅保存在本机') }}</small>
      <button type="button" :title="t('inlineRecords.edit', '编辑学习记录')" :aria-label="t('inlineRecords.edit', '编辑学习记录')" @click="openEditor">
        <PencilLine :size="14" />
      </button>
    </header>
    <p v-if="note.title" class="record-title">{{ note.title }}</p>
    <MarkdownRenderer
      class="record-content"
      :content="note.content || note.summary || t('inlineRecords.empty', '这条记录还没有正文')"
    />
    <blockquote v-if="note.quote">{{ note.quote }}</blockquote>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NotebookTabs, PencilLine } from 'lucide-vue-next'
import type { Note } from '@/stores/types'
import { t } from '@/shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps<{ note: Note }>()
const emit = defineEmits<{ open: [payload: { note: Note; x: number; y: number }] }>()

const recordLabel = computed(() => {
  if (props.note.sourceType === 'ai') return t('inlineRecords.aiSummary', 'AI 问答摘要')
  if (props.note.recordType === 'issue') return t('courseWorkspace.records.type.issue', '问题')
  if (props.note.recordType === 'review_task') return t('courseWorkspace.records.type.review', '复习')
  if (props.note.recordType === 'bookmark') return t('courseWorkspace.records.type.bookmark', '书签')
  return t('inlineRecords.userNote', '我的便签')
})

function openEditor(event: MouseEvent) {
  const rect = (event.currentTarget as HTMLElement).closest('.inline-learning-record')?.getBoundingClientRect()
  emit('open', {
    note: props.note,
    x: rect ? rect.right - 18 : window.innerWidth / 2,
    y: rect ? rect.top + 30 : window.innerHeight / 2,
  })
}
</script>

<style scoped>
.inline-learning-record { --record-accent:#d97706; margin:2px 0 0; padding:12px 14px 12px 16px; border-left:3px solid var(--record-accent); border-radius:0 7px 7px 0; color:var(--lz-text); background:#fffbeb; }
.inline-learning-record[data-source="ai"] { --record-accent:#6366f1; background:#f5f3ff; }
.inline-learning-record[data-sync-state="local_only"] { border-left-style:dashed; }
.inline-learning-record header { display:grid; grid-template-columns:22px minmax(0,1fr) auto 28px; align-items:center; gap:7px; }
.inline-learning-record header > span { width:22px; height:22px; display:grid; place-items:center; color:var(--record-accent); }
.inline-learning-record header strong { color:var(--lz-text-strong); font-size:11px; }
.inline-learning-record header small { color:var(--lz-warning); font-size:9px; }
.inline-learning-record header button { width:28px; height:28px; display:grid; place-items:center; border:0; border-radius:6px; color:var(--lz-text-muted); background:transparent; cursor:pointer; }
.inline-learning-record header button:hover { color:var(--record-accent); background:rgba(255,255,255,.72); }
.record-title { margin:9px 0 0 29px; color:var(--lz-text-strong); font-size:12px; font-weight:700; line-height:1.5; }
.record-content { margin:6px 0 0 29px; color:var(--lz-text-secondary); font-size:12px; line-height:1.65; }
.record-content :deep(p),.record-content :deep(ul),.record-content :deep(ol),.record-content :deep(table) { margin:5px 0; }
.record-content :deep(h1),.record-content :deep(h2),.record-content :deep(h3),.record-content :deep(h4) { margin:8px 0 4px; color:var(--lz-text-strong); font-size:12px; line-height:1.5; }
.record-content :deep(.katex-display) { margin:7px 0; }
.inline-learning-record blockquote { margin:8px 0 0 29px; overflow:hidden; color:var(--lz-text-muted); font-size:10px; line-height:1.55; text-overflow:ellipsis; white-space:nowrap; }
@media (max-width:700px) {
  .inline-learning-record { padding:11px 12px; }
  .record-title,.record-content,.inline-learning-record blockquote { margin-left:0; }
}
</style>
