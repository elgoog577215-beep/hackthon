<template>
  <section id="reading-notes-panel" class="reading-notes" role="tabpanel" aria-labelledby="reading-notes-tab">
    <header class="reading-notes-tools">
      <button type="button" class="follow-toggle" :aria-pressed="following" @click="toggleFollowing">
        <Link2 :size="15" /><span>{{ following ? t('readingNotes.following', '随正文滚动') : t('readingNotes.resume', '恢复跟随正文') }}</span>
      </button>
      <button type="button" class="quick-note-button" :disabled="!courseStore.currentNode" @click="emit('create', $event)"><Plus :size="15" />{{ t('quickNote.title', '随手记') }}</button>
    </header>
    <div class="reading-notes-location"><MathText :content="courseStore.currentNode?.node_name || t('readingNotes.selectSection', '选择一讲开始阅读')" /></div>
    <details v-if="looseNotes.length" class="loose-notes">
      <summary>{{ t('readingNotes.sectionNotes', '本讲其他笔记') }} <span>{{ looseNotes.length }}</span></summary>
      <button v-for="note in looseNotes" :key="note.id" type="button" @click="openNote(note, $event)">
        <MathText :content="note.content || note.quote || t('inlineRecords.empty', '这条记录还没有正文')" />
        <small>{{ note.quote ? t('readingNotes.unlocated', '原文待定位') : t('readingNotes.sectionOnly', '记录在本讲') }}</small>
      </button>
    </details>
    <div ref="viewport" class="reading-notes-viewport" tabindex="0" @wheel.passive="following = false" @keydown="onScrollKey">
      <div v-if="!positioned.length" class="reading-notes-empty">
        <NotebookPen :size="26" />
        <p>{{ t('readingNotes.empty', '读到哪里，笔记就跟到哪里') }}</p>
        <span>{{ t('readingNotes.emptyHint', '选中正文记笔记，或用随手记记录想法。') }}</span>
        <button type="button" @click="emit('notebook')">{{ t('readingNotes.allNotes', '查看全部笔记') }}</button>
      </div>
      <div v-else class="reading-notes-canvas" :style="{ height: `${canvasHeight}px` }">
        <article v-for="item in positioned" :key="item.note.id" class="reading-note-strip" :class="{ 'is-current': item.note.id === currentNoteId }" :data-note-id="item.note.id" :data-color="item.note.sourceType === 'ai' ? 'violet' : item.note.color" :style="{ top: `${item.top}px` }">
          <button type="button" class="reading-note-main" @click="openNote(item.note, $event)">
            <span class="reading-note-quote"><MathText :content="item.note.quote" /></span>
            <span class="reading-note-copy"><MathText :content="item.note.content || item.note.summary || t('inlineRecords.empty', '这条记录还没有正文')" /></span>
          </button>
          <footer>
            <span>{{ item.note.syncState === 'local_only' ? t('inlineRecords.localOnly', '仅保存在本机') : item.note.sourceType === 'ai' ? t('readingNotes.aiNote', 'AI 笔记') : t('readingNotes.myNote', '我的笔记') }}</span>
            <button type="button" :title="t('courseWorkspace.records.locate', '定位原文')" :aria-label="t('courseWorkspace.records.locate', '定位原文')" @click="emit('locate', item.note)"><LocateFixed :size="14" /></button>
          </footer>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Link2, LocateFixed, NotebookPen, Plus } from 'lucide-vue-next'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import type { Note } from '../stores/types'
import { t } from '../shared/i18n'
import MathText from './MathText.vue'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  open: [payload: { note: Note; x: number; y: number }]
  locate: [note: Note]
  create: [event: MouseEvent]
  notebook: []
}>()
const courseStore = useCourseStore()
const noteStore = useNoteStore()
const viewport = ref<HTMLElement | null>(null)
const following = ref(true)
const positioned = ref<Array<{ note: Note; top: number }>>([])
const canvasHeight = ref(0)
const currentNoteId = ref('')
const notes = computed(() => noteStore.notes.filter(note => (!note.recordType || note.recordType === 'note') && note.sourceType !== 'format' && note.sourceType !== 'wrong'))
const looseNotes = computed(() => {
  const located = new Set(positioned.value.map(item => item.note.id))
  return notes.value.filter(note => note.nodeId === courseStore.currentNode?.node_id && !located.has(note.id))
})
let root: HTMLElement | null = null
let observer: MutationObserver | undefined
let resizeObserver: ResizeObserver | undefined
let frame: number | null = null

// Use the rendered quote anchor, so font changes, formulas and virtualized
// sections share exactly the same position as the reader's text.
async function refresh() {
  if (!props.visible || !viewport.value) return
  await nextTick()
  if (!root || !viewport.value) return
  const rootRect = root.getBoundingClientRect()
  const rows = notes.value.flatMap(note => {
    if (!note.highlightId) return []
    const anchor = document.getElementById(note.highlightId)
      || root!.querySelector<HTMLElement>(`[id^="${CSS.escape(note.highlightId)}-"]`)
    if (!anchor || !root!.contains(anchor)) return []
    return [{ note, top: anchor.getBoundingClientRect().top - rootRect.top + root!.scrollTop }]
  }).sort((a, b) => a.top - b.top || a.note.createdAt - b.note.createdAt)
  const readingY = root.scrollTop + 100
  currentNoteId.value = [...rows].reverse().find(item => item.top <= readingY)?.note.id || rows[0]?.note.id || ''
  let bottom = 0
  positioned.value = rows.map(item => {
    const top = Math.max(0, item.top, bottom)
    bottom = top + 104
    return { ...item, top }
  })
  canvasHeight.value = Math.max(root.scrollHeight, bottom + 16)
  await nextTick()
  if (following.value && viewport.value) {
    viewport.value.scrollTop = Math.max(0, root.scrollTop + viewport.value.getBoundingClientRect().top - rootRect.top)
  }
}
function scheduleRefresh() {
  if (frame !== null) return
  frame = requestAnimationFrame(() => { frame = null; void refresh() })
}
function toggleFollowing() { following.value = !following.value; scheduleRefresh() }
function onScrollKey(event: KeyboardEvent) {
  if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End'].includes(event.key)) following.value = false
}
function openNote(note: Note, event: MouseEvent) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  emit('open', { note, x: rect.left + rect.width / 2, y: rect.top + 20 })
}
watch(() => [props.visible, courseStore.currentNode?.node_id, notes.value.map(note => `${note.id}:${note.quote}:${note.content}:${note.syncState}`).join('|')], scheduleRefresh)
watch(() => courseStore.currentCourseId, () => { following.value = true; positioned.value = []; currentNoteId.value = ''; scheduleRefresh() })
onMounted(() => {
  root = document.getElementById('content-scroll-container')
  root?.addEventListener('scroll', scheduleRefresh, { passive: true })
  root?.addEventListener('load', scheduleRefresh, true)
  window.addEventListener('resize', scheduleRefresh)
  if (root) {
    observer = new MutationObserver(scheduleRefresh)
    observer.observe(root, { childList: true, subtree: true, characterData: true })
  }
  if (typeof ResizeObserver !== 'undefined' && viewport.value) {
    resizeObserver = new ResizeObserver(scheduleRefresh)
    resizeObserver.observe(viewport.value)
    if (root) resizeObserver.observe(root)
  }
  scheduleRefresh()
})
onBeforeUnmount(() => {
  root?.removeEventListener('scroll', scheduleRefresh)
  root?.removeEventListener('load', scheduleRefresh, true)
  window.removeEventListener('resize', scheduleRefresh)
  observer?.disconnect()
  resizeObserver?.disconnect()
  if (frame !== null) cancelAnimationFrame(frame)
})
</script>

<style scoped>
.reading-notes { display:flex; flex-direction:column; height:100%; min-height:0; color:var(--lz-text); background:var(--lz-surface-subtle); }
.reading-notes-tools { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:12px 14px 8px; }
.reading-notes-tools button { display:inline-flex; align-items:center; gap:5px; min-height:32px; padding:5px 8px; border:1px solid var(--lz-border); border-radius:7px; background:#fff; color:var(--lz-text-secondary); font-size:13px; cursor:pointer; }
.reading-notes-tools .follow-toggle[aria-pressed="true"] { color:var(--lz-brand-strong); border-color:var(--color-primary-200); background:var(--lz-brand-soft); }
.reading-notes button:hover { border-color:var(--lz-brand); color:var(--lz-brand-strong); }
.reading-notes button:focus-visible,.reading-notes-viewport:focus-visible,.loose-notes summary:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.reading-notes button:disabled { opacity:.5; cursor:not-allowed; }
.reading-notes-location { padding:0 22px 10px; font-size:14px; line-height:1.6; color:var(--lz-text-secondary); overflow-wrap:anywhere; }
.reading-notes-viewport { position:relative; flex:1; min-height:0; overflow:auto; overscroll-behavior:contain; scrollbar-gutter:stable; }
.reading-notes-canvas { position:relative; margin:0 12px; }
.reading-note-strip { --note-accent:#c18a22; position:absolute; left:0; right:0; height:96px; display:flex; flex-direction:column; padding:8px 11px 4px; border:1px solid var(--lz-border); border-left:2px solid var(--note-accent); border-radius:8px; background:#fffefb; box-shadow:0 1px 3px rgba(15,23,42,.025); }
.reading-note-strip[data-color="violet"],.reading-note-strip[data-color="purple"] { --note-accent:#8b76bf; background:#fdfbff; }
.reading-note-strip[data-color="emerald"],.reading-note-strip[data-color="green"] { --note-accent:#5d9c8a; background:#fbfefd; }
.reading-note-strip[data-color="sky"],.reading-note-strip[data-color="blue"] { --note-accent:#6a99bb; background:#fbfdff; }
.reading-note-strip[data-color="rose"],.reading-note-strip[data-color="red"] { --note-accent:#c0808f; background:#fffafb; }
.reading-note-strip.is-current { border-color:var(--note-accent); box-shadow:0 2px 6px rgba(15,23,42,.055); }
.reading-note-main { flex:1; min-height:0; width:100%; padding:0; border:0; background:transparent; text-align:left; color:var(--lz-text); cursor:pointer; }
.reading-note-quote { display:block; margin-bottom:4px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; color:var(--lz-text-secondary); font-size:12px; line-height:1.5; }
.reading-note-copy { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; color:var(--lz-text-strong); font-size:14px; line-height:1.5; overflow-wrap:anywhere; }
.reading-note-strip footer { display:flex; align-items:center; justify-content:space-between; height:23px; flex:none; font-size:11px; color:var(--lz-text-secondary); }
.reading-note-strip footer button { display:grid; place-items:center; width:24px; height:23px; padding:0; border:0; border-radius:4px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.reading-notes-empty { padding:42px 24px; display:flex; flex-direction:column; align-items:center; gap:12px; text-align:center; color:var(--lz-text-secondary); font-size:14px; line-height:1.7; }
.reading-notes-empty > svg { color:var(--lz-brand); }
.reading-notes-empty p { margin:0; color:var(--lz-text-strong); font-size:15px; }
.reading-notes-empty button { margin-top:8px; border:1px solid var(--lz-border); border-radius:7px; padding:6px 12px; color:var(--lz-text); background:#fff; cursor:pointer; }
.loose-notes { flex:none; margin:0 14px 8px; padding:8px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; font-size:13px; max-height:180px; overflow:auto; }
.loose-notes summary { cursor:pointer; color:var(--lz-text-secondary); }
.loose-notes summary span { margin-left:5px; }
.loose-notes > button { display:flex; flex-direction:column; gap:4px; width:100%; padding:8px 0; border:0; border-top:1px solid var(--lz-border); margin-top:8px; text-align:left; color:var(--lz-text); background:transparent; cursor:pointer; }
.loose-notes > button > :first-child { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.loose-notes small { color:var(--lz-text-secondary); }
</style>
