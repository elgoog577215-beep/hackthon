<template>
  <section class="personal-notes" :class="{ 'is-editing': !!editor }" :aria-label="c('note')">
    <div v-if="!editor" class="reading-aid-controls">
      <div class="notes-heading"><strong>{{ c('notesNotebook') }}</strong><ElButton plain @click="create({})"><Plus :size="15" />{{ c('notesNew') }}</ElButton></div>
      <template v-if="!editor">
      <div class="reading-aid-scope" role="group" :aria-label="c('referenceScope')"><button v-for="s in ['current', 'all'] as const" :key="s" :aria-pressed="scope === s" @click="scope = s">{{ c(s === 'current' ? 'referenceCurrent' : 'referenceAllCourse') }}</button></div>
      <input v-model="query" type="search" :placeholder="c('notesSearch')" :aria-label="c('notesSearch')" />
      <div class="notes-filters"><select v-model="filter" :aria-label="c('notesFilter')"><option value="all">{{ c('referenceAll') }}</option><option value="important">{{ c('notesImportant') }}</option><option value="open">{{ c('notesOpen') }}</option><option value="answered">{{ c('notesAnswered') }}</option></select><select v-model="sourceType" :aria-label="c('notesSourceType')"><option value="">{{ c('notesAllTypes') }}</option><option v-for="type in sourceTypes" :key="type" :value="type">{{ typeLabel(type) }}</option></select></div>
      </template>
    </div>
    <div ref="results" class="reading-aid-results">
      <p v-if="!draftStorageAvailable" role="alert">{{ c('notesDraftUnavailable') }}</p>
      <div v-if="editor" ref="editorRoot" class="note-editor">
        <header><ElButton text :disabled="saving" @click="closeEditor"><ArrowLeft :size="16" aria-hidden="true" />{{ c('notesBack') }}</ElButton><button class="note-important" :aria-pressed="editor.important" @click="editor.important = !editor.important"><Star :size="16" :fill="editor.important ? 'currentColor' : 'none'" />{{ c('notesImportant') }}</button></header>
        <p class="note-location"><MathText :content="editor.section_title || c('notesCourseWide')" /><template v-if="editor.block_title"> · <MathText :content="editor.block_title" /></template></p>
        <blockquote v-if="editor.quote"><small>{{ c('notesSource') }}</small><MathText :content="editor.quote" /></blockquote>
        <p v-if="editor.location_status !== 'current'" class="notes-status">{{ locationLabel(editor.location_status) }}</p>
        <label class="note-input-label"><span class="note-input-caption">{{ c('notesMyText') }}</span><ElInput v-model="editor.content" type="textarea" :rows="10" :maxlength="20000" resize="none" :aria-label="c('notesMyText')" :placeholder="c('notesTextPlaceholder')" /></label>
        <div class="notes-options"><label for="note-question-state">{{ c('notesQuestionState') }}</label><select id="note-question-state" v-model="editor.question_state" :aria-label="c('notesQuestionState')"><option value="none">{{ c('notesNoQuestion') }}</option><option value="open">{{ c('notesOpen') }}</option><option value="answered">{{ c('notesAnswered') }}</option></select></div>
        <div v-if="suggestions[editor.id]" class="notes-suggestion"><p>{{ c(suggestions[editor.id]!.noteVersion === editor.version ? 'notesSuggestionHint' : 'notesSuggestionOutdated') }}</p><details><summary>{{ c('notesViewSuggestion') }}</summary><MarkdownRenderer :content="suggestions[editor.id]!.content" :enable-code-run="false" /></details><ElButton plain :disabled="suggestions[editor.id]!.noteVersion !== editor.version" @click="applySuggestion(true)">{{ c('notesUseSuggestion') }}</ElButton></div>
        <div v-if="conflict" class="notes-conflict" role="alert"><p>{{ c('notesConflict') }}</p><details><summary>{{ c('notesSavedVersion') }}</summary><MarkdownRenderer :content="conflict.content" :enable-code-run="false" /></details><ElButton plain @click="adoptServerVersion">{{ c('notesUseSaved') }}</ElButton><ElButton plain @click="keepMyDraft">{{ c('notesKeepMine') }}</ElButton></div>
        <p v-if="error" role="alert">{{ error }}<ElButton v-if="editor.id" text @click="compareLatest">{{ c('notesCompare') }}</ElButton></p>
        <p class="notes-status note-save-status" role="status">{{ saving ? c('busy') : dirty ? c('noteUnsaved') : editor.id ? c('noteSaved') : '' }}</p>
        <footer><ElButton type="primary" data-action="save" :disabled="saving || !canSave || !dirty || !!conflict" @click="save()"><Save :size="16" aria-hidden="true" />{{ saving ? c('busy') : c('saveNote') }}</ElButton><ElButton :disabled="saving || !canSave || !!conflict || !editor.section_id || editor.location_status !== 'current'" data-action="discuss" @click="discuss"><MessageCircle :size="16" aria-hidden="true" />{{ c('notesDiscuss') }}</ElButton></footer>
      </div>
      <p v-if="error && !editor" role="alert">{{ error }}</p>
      <p v-if="!visible.length && !editor" class="notes-empty">{{ c(query || filter !== 'all' || sourceType ? 'referenceNoMatches' : 'notesEmpty') }}</p>
      <article v-for="note in editor ? [] : visible" :key="note.id" class="personal-note-card" :class="{ selected: editor?.id === note.id }" :data-note-id="note.id">
        <header><small><MathText :content="note.section_title || c('notesCourseWide')" /><span v-if="note.content_type" class="note-type">{{ typeLabel(note.content_type) }}</span></small><button :aria-label="c(note.important ? 'notesUnmark' : 'notesImportant')" :aria-pressed="note.important" :disabled="saving" @click="toggleImportant(note)"><Star :size="16" :fill="note.important ? 'currentColor' : 'none'" /></button></header>
        <div class="note-card-preview"><blockquote v-if="note.quote"><MathText :content="note.quote" /></blockquote><MarkdownRenderer v-if="note.content" :content="note.content" :enable-code-run="false" /><span v-else>{{ c('notesMarked') }}</span></div>
        <p v-if="note.location_status !== 'current'" class="notes-status">{{ locationLabel(note.location_status) }}</p>
        <footer><span v-if="note.question_state !== 'none' || note.source_type === 'ai'" class="note-state" :class="{ 'is-question': note.question_state === 'open' }">{{ c(note.question_state === 'open' ? 'notesOpen' : note.question_state === 'answered' ? 'notesAnswered' : note.source_type === 'ai' ? 'notesAIOrigin' : 'notesMyRecord') }}</span><button v-if="note.location_status === 'current' && (note.block_id || note.section_id)" @click="emit('locate', note)"><ArrowUpRight :size="14" aria-hidden="true" />{{ c('referenceJump') }}</button><button class="note-card-open" @click="open(note)"><Pencil :size="14" aria-hidden="true" />{{ c('notesEdit') }}</button></footer>
        <div v-if="deleting === note.id" class="note-delete-confirm"><span>{{ c('notesDeleteConfirm') }}</span><ElButton plain :disabled="saving" @click="remove(note)">{{ c('notesDelete') }}</ElButton><ElButton plain @click="deleting = ''">{{ c('notesCancel') }}</ElButton></div>
        <button v-else class="note-delete" :aria-label="c('notesDelete')" @click="deleting = note.id"><Trash2 :size="13" /></button>
      </article>
      <details v-if="!editor" class="notes-legacy"><summary>{{ c('notesCourseWide') }}</summary><slot name="legacy" /></details>
    </div>
  </section>
</template>

<script setup lang="ts">
import "../styles/study-tool-controls.css"
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElButton, ElInput } from 'element-plus'
import { Plus, Star, Trash2, Save, MessageCircle, ArrowLeft, Pencil, ArrowUpRight } from 'lucide-vue-next'
import MathText from './MathText.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { studyApi, StudyApiError, type StudyNote, type StudyNoteInput, type StudySection, type NoteDraftSuggestion } from '../api/study'
import { studyCopy as c } from '../shared/study-copy'
import { activeLocale } from '../shared/i18n'
import { handoutPresentation } from '../utils/handout-content'
import { createUuid } from '../utils/client-id'
const props = defineProps<{ ownerId: string; materialId: string; revisionId: string; notes: StudyNote[]; sections: StudySection[]; currentSection: string }>()
const emit = defineEmits<{ saved: [note: StudyNote]; removed: [id: string]; locate: [note: StudyNote]; discuss: [payload: { note: StudyNote; draft: string }]; sessionExpired: [error: StudyApiError] }>()
type Editor = StudyNote & { request_id: string; pending_ai_message_id?: string }
type NoteContext = { section_id?: string; block_id?: string; quote?: string; anchor_prefix?: string; anchor_suffix?: string; content?: string; question_state?: StudyNote['question_state']; source_message_id?: string }
const scope = ref<'current' | 'all'>('current'), query = ref(''), filter = ref('all'), sourceType = ref('')
const editor = ref<Editor | null>(null), results = ref<HTMLElement | null>(null), conflict = ref<StudyNote | null>(null)
const editorRoot = ref<HTMLElement | null>(null)
let editorGeneration = 0, disposed = false
const saving = ref(false), error = ref(''), saved = ref(false), deleting = ref(''), draftStorageAvailable = ref(true)
const suggestions = ref<Record<string, NoteDraftSuggestion>>({})
const key = `lingzhi-personal-notes:${props.ownerId}:${props.materialId}:${props.revisionId}`
function persist() { if (!editor.value) return; try { sessionStorage.setItem(`${key}:${editor.value.id || 'new'}`, JSON.stringify(editor.value)); sessionStorage.setItem(key, editor.value.id || 'new') } catch { draftStorageAvailable.value = false } }
function cached(id: string): Editor | null { try { const value = JSON.parse(sessionStorage.getItem(`${key}:${id}`) || 'null'); return value && typeof value.content === 'string' && value.revision_id === props.revisionId ? value : null } catch { return null } }
watch(editor, () => { saved.value = false; persist() }, { deep: true })
function typeLabel(type: string) { return handoutPresentation(type, activeLocale.value).label }
function locationLabel(state: StudyNote['location_status']) { return c(state === 'historical' ? 'notesHistorical' : state === 'missing' ? 'notesMissingSource' : 'notesChangedSource') }
const sourceTypes = computed(() => [...new Set(props.notes.map(n => n.content_type).filter(Boolean))])
const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  const positions = new Map(props.sections.flatMap((s, i) => s.blocks.map((b, j) => [b.block_id, i * 100000 + j] as const)))
  return props.notes.filter(n => (scope.value === 'all' || n.revision_id === props.revisionId && (!n.section_id || n.section_id === (props.currentSection || props.sections[0]?.id)))
    && (filter.value === 'all' || (filter.value === 'important' ? n.important : n.question_state === filter.value))
    && (!sourceType.value || n.content_type === sourceType.value)
    && (!needle || [n.quote, n.content, n.section_title, n.block_title].join(' ').toLocaleLowerCase().includes(needle)))
    .sort((a, b) => (positions.get(a.block_id) ?? Number.MAX_SAFE_INTEGER) - (positions.get(b.block_id) ?? Number.MAX_SAFE_INTEGER) || a.created_at.localeCompare(b.created_at))
})
const baseline = ref<StudyNote | null>(null)
const dirty = computed(() => {
  const draft = editor.value, original = baseline.value
  return !!draft && (!draft.id || !original || draft.content !== original.content || draft.important !== original.important || draft.question_state !== original.question_state || !!draft.pending_ai_message_id)
})
const canSave = computed(() => !!editor.value && (!!editor.value.content.trim() || !!editor.value.quote.trim() && !!editor.value.block_id))
function top() { void nextTick(() => { if (results.value) results.value.scrollTop = 0; editorRoot.value?.querySelector('textarea')?.focus({ preventScroll: true }) }) }
function create(context: NoteContext = {}, kind: StudyNote['kind'] = 'note') {
  editorGeneration++
  baseline.value = null
  persist(); submittedFingerprint = ''; conflict.value = null; error.value = ''; saved.value = false
  const sid = context.section_id ?? props.currentSection ?? '', section = props.sections.find(s => s.id === sid), block = section?.blocks.find(b => b.block_id === context.block_id)
  editor.value = { id: '', request_id: createUuid(), revision_id: props.revisionId, section_id: section?.id || '', section_title: section?.title || '', block_id: block?.block_id || '', block_title: block?.title || '', content_type: block?.content_type || '', quote: context.quote || '', anchor_prefix: context.anchor_prefix || '', anchor_suffix: context.anchor_suffix || '', content: context.content || '', kind, question_state: context.question_state || 'none', important: kind === 'mark', version: 0, source_type: context.source_message_id ? 'ai' : 'self', source_message_id: context.source_message_id, created_at: '', updated_at: '', source_sha256: '', location_status: 'current' }
  top()
}
function open(note: StudyNote) {
  editorGeneration++
  persist(); error.value = ''; saved.value = false
  baseline.value = { ...note }
  const draft = cached(note.id)
  editor.value = draft || { ...note, request_id: createUuid() }
  editor.value.location_status = note.location_status
  conflict.value = draft && draft.version !== note.version ? note : null
  top()
}
function closeEditor() { editorGeneration++; persist(); editor.value = null; conflict.value = null; error.value = ''; try { sessionStorage.removeItem(key) } catch { /* Optional browser state. */ } }
function fail(cause: unknown) { error.value = cause instanceof Error ? cause.message : c('requestFailure'); if (cause instanceof StudyApiError && cause.status === 401) emit('sessionExpired', cause) }
let submittedFingerprint = ''
async function save(): Promise<StudyNote | undefined> {
  if (!editor.value || saving.value || !canSave.value || conflict.value) return
  const draft = { ...editor.value }
  const generation = editorGeneration
  draft.kind = draft.content.trim() ? 'note' : 'mark'
  saving.value = true; error.value = ''
  try {
    let note: StudyNote
    if (draft.id) note = await studyApi.updateNote(props.materialId, draft.id, { expected_version: draft.version, content: draft.content, kind: draft.kind, question_state: draft.question_state, important: draft.important, ...(draft.pending_ai_message_id ? { source_message_id: draft.pending_ai_message_id } : {}) })
    else {
      const body: StudyNoteInput = { request_id: draft.request_id, revision_id: draft.revision_id, section_id: draft.section_id, block_id: draft.block_id, quote: draft.quote, anchor_prefix: draft.anchor_prefix, anchor_suffix: draft.anchor_suffix, content: draft.content, kind: draft.kind, question_state: draft.question_state, important: draft.important, ...(draft.source_message_id ? { source_message_id: draft.source_message_id } : {}) }
      const fingerprint = JSON.stringify({ ...body, request_id: '' })
      if (submittedFingerprint && submittedFingerprint !== fingerprint) { draft.request_id = createUuid(); body.request_id = draft.request_id; editor.value.request_id = draft.request_id }
      submittedFingerprint = fingerprint
      note = await studyApi.createNote(props.materialId, body)
    }
    if (disposed) return
    emit('saved', note)
    if (generation === editorGeneration && editor.value && editor.value.id === draft.id) {
      baseline.value = { ...note }
      const unchanged = editor.value.content === draft.content && editor.value.question_state === draft.question_state && editor.value.important === draft.important
      editor.value = unchanged ? { ...note, request_id: createUuid() } : { ...editor.value, id: note.id, version: note.version }
      await nextTick(); saved.value = unchanged
      persist()
    }
    if (!draft.id && generation === editorGeneration) { try { sessionStorage.removeItem(`${key}:new`) } catch { /* Optional cache. */ } }
    return note
  } catch (cause) { if (!disposed && generation === editorGeneration) { fail(cause); if (cause instanceof StudyApiError && cause.status === 409 && draft.id) await compareLatest() } }
  finally { if (!disposed) saving.value = false }
}
async function compareLatest() {
  if (!editor.value?.id) return
  const id = editor.value.id, revision = editor.value.revision_id, generation = editorGeneration
  try { const result = await studyApi.listNotes(props.materialId, revision); if (disposed || generation !== editorGeneration) return; const latest = result.entries.find(n => n.id === id); if (latest) { emit('saved', latest); conflict.value = latest; } }
  catch (cause) { if (!disposed && generation === editorGeneration) fail(cause) }
}
function adoptServerVersion() { if (conflict.value) { baseline.value = { ...conflict.value }; editor.value = { ...conflict.value, request_id: createUuid() }; conflict.value = null; error.value = '' } }
function keepMyDraft() { if (editor.value && conflict.value) { baseline.value = { ...conflict.value }; editor.value.version = conflict.value.version; editor.value.location_status = conflict.value.location_status; editor.value.pending_ai_message_id = undefined; conflict.value = null; error.value = '' } }
async function discuss() {
  if (!editor.value || saving.value || !canSave.value || conflict.value) return
  const generation = editorGeneration, draft = editor.value
  const current = props.notes.find(note => note.id === draft.id)
  // Reopening a discussion is not an edit. Keep its saved version so earlier
  // suggestions can still be matched to the same unchanged note.
  const unchanged = current && current.version === draft.version && current.location_status === 'current'
    && draft.location_status === 'current' && !draft.pending_ai_message_id
    && current.content === draft.content && current.kind === draft.kind
    && current.question_state === draft.question_state && current.important === draft.important
  const note = unchanged ? current : await save()
  if (!disposed && generation === editorGeneration && note) emit('discuss', { note, draft: editor.value?.content ?? note.content })
}
async function toggleImportant(note: StudyNote) {
  if (saving.value) return; saving.value = true
  try { const result = await studyApi.updateNote(props.materialId, note.id, { expected_version: note.version, important: !note.important }); if (disposed) return; emit('saved', result); if (editor.value?.id === note.id && editor.value.version === note.version) { editor.value.version = result.version; editor.value.important = result.important } }
  catch (cause) { if (!disposed) fail(cause) } finally { if (!disposed) saving.value = false }
}
async function remove(note: StudyNote) {
  saving.value = true
  try { await studyApi.deleteNote(props.materialId, note.id, note.version); if (disposed) return; emit('removed', note.id); deleting.value = ''; if (editor.value?.id === note.id) closeEditor(); try { sessionStorage.removeItem(`${key}:${note.id}`) } catch { /* Optional cache. */ } }
  catch (cause) { if (!disposed) fail(cause) } finally { if (!disposed) saving.value = false }
}
function receiveSuggestion(value: NoteDraftSuggestion) {
  if (editor.value?.id === value.noteId && editor.value.content === value.content) return
  suggestions.value[value.noteId] = value
  if (editor.value?.id === value.noteId && editor.value.version === value.noteVersion && editor.value.content === value.basedOnDraft) applySuggestion(false)
}
function applySuggestion(explicit: boolean) {
  if (!editor.value) return
  const value = suggestions.value[editor.value.id]
  if (!value || editor.value.version !== value.noteVersion) return
  if (!explicit && editor.value.content !== value.basedOnDraft) return
  editor.value.content = value.content; editor.value.pending_ai_message_id = value.messageId; editor.value.source_type = 'ai'
  delete suggestions.value[editor.value.id]
}
try { const active = sessionStorage.getItem(key); if (active) { const draft = cached(active); if (draft) { editor.value = draft; const current = props.notes.find(n => n.id === draft.id); if (current) { baseline.value = { ...current }; editor.value.location_status = current.location_status; if (current.version !== draft.version) conflict.value = current } } } } catch { /* Drafts are optional, official notes remain available. */ }
watch(() => props.notes, notes => { const current = notes.find(n => n.id === editor.value?.id); if (!current || !editor.value) return; editor.value.location_status = current.location_status; if (current.version !== editor.value.version) conflict.value = current }, { deep: true })
onBeforeUnmount(() => { persist(); disposed = true; editorGeneration++ })
function currentDraft(noteId: string) { return editor.value?.id === noteId ? editor.value.content : cached(noteId)?.content }
defineExpose({ create, open, receiveSuggestion, save, currentDraft })
</script>

<style scoped>
@import '../styles/reading-aids.css';
.personal-notes { display:flex; flex-direction:column; flex:1; min-width:0; min-height:0; font:15px/1.7 var(--study-ui-font); }.notes-heading,.note-editor header { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:8px; }.notes-heading strong { font-weight:600; }.notes-heading :deep(.el-button>span) { gap:4px; }.notes-filters { display:flex; gap:8px; margin-top:9px; }.notes-filters select,.notes-options select { min-width:0; max-width:100%; padding:6px 8px; font:inherit; font-size:14px; color:#625578; border:1px solid #e2ddec; border-radius:6px; background:white; }.notes-filters select { flex:1; }.notes-empty { color:#82798c; margin:20px 0; }.note-editor { margin:14px 0 22px; padding:0; background:transparent; }.note-location,.notes-status { font-size:13px; color:#81738f; margin:5px 0 10px; }.note-editor blockquote,.personal-note-card blockquote { margin:10px 0; padding:6px 10px; border-left:2px solid #c4b4dc; background:#f7f4fb; color:#726783; font-size:14px; }.note-editor blockquote small { display:block; font-size:12px; color:#9a8aa9; }.note-input-label { display:block; font-size:14px; color:#675978; }.note-input-label :deep(.el-textarea) { margin-top:6px; }.note-input-label :deep(textarea) { font-size:15px; line-height:1.7; }.notes-options { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; margin:10px 0; font-size:14px; }.notes-options label { display:flex; gap:5px; align-items:center; }.notes-options input { accent-color:#7960a0; }.note-editor footer { display:flex; flex-wrap:wrap; gap:8px; }.note-editor footer :deep(.el-button+.el-button) { margin:0; }.personal-note-card { position:relative; padding:13px 13px 9px; margin:14px 0; border-bottom:1px solid #e5dfee; background:#fff; border-radius:6px; }.personal-note-card.selected { box-shadow:inset 3px 0 #a185c2; }.personal-note-card header { display:flex; align-items:flex-start; gap:5px; }.personal-note-card header small { flex:1; min-width:0; color:#8a7c98; font-size:12px; }.personal-note-card button { border:0; background:transparent; color:#72568c; font:inherit; cursor:pointer; text-align:left; }.personal-note-card header button { flex:none; padding:3px; }.note-card-open { width:100%; padding:0; }.note-card-open p { color:#46404e; white-space:pre-wrap; overflow-wrap:anywhere; margin:8px 0; font-size:15px; }.note-card-open>span { font-size:14px; color:#978b9f; }.personal-note-card footer { display:flex; align-items:center; flex-wrap:wrap; gap:10px; font-size:12px; margin-top:10px; padding-right:15px; }.personal-note-card footer .note-state { color:#756387; margin-right:auto; }.personal-note-card footer .is-question { color:#a46b37; }.personal-note-card footer button { padding:2px 0; font-size:13px; }.personal-note-card .note-delete { position:absolute; right:2px; bottom:9px; padding:4px; color:#aaa1b3; }.note-delete-confirm { font-size:13px; color:#9b6372; }.notes-legacy { border-top:1px solid #e0d9ea; margin-top:24px; padding-top:12px; }.notes-legacy :deep(.study-note) { min-height:260px; padding:12px 0; }.notes-legacy summary { cursor:pointer; color:#776585; font-size:14px; }.notes-suggestion,.notes-conflict { margin:10px 0; padding:10px; background:#fbf7ef; font-size:14px; }.notes-suggestion p,.notes-conflict p { margin:0 0 8px; }.personal-notes [role=alert] { color:#a75465; font-size:14px; }.personal-notes button:focus-visible,.personal-notes select:focus-visible,.personal-notes input:focus-visible,.personal-notes summary:focus-visible { outline:2px solid #8b72ac; outline-offset:2px; }
@media (max-width:760px) {
  .personal-notes .reading-aid-controls { padding:12px 14px; }
  .personal-notes .reading-aid-results { padding:0 14px 22px; }
  .notes-heading { margin-bottom:10px; }
  .notes-heading :deep(.el-button), .note-editor :deep(.el-button) { min-height:44px; height:auto; padding:9px 12px; white-space:normal; }
  .notes-heading :deep(.el-button>span),.note-editor :deep(.el-button>span) { white-space:normal; line-height:1.45; }
  .notes-filters select,.notes-options select { min-height:44px; font-size:15px; }
  .note-editor header { align-items:flex-start; }
  .note-editor header strong { padding-top:9px; }
  .note-input-label :deep(textarea) { font-size:16px; min-height:140px; }
  .note-editor footer { display:flex; gap:8px; }
  .notes-options label { min-height:44px; }
  .notes-options input { width:18px; height:18px; }
  .personal-note-card { padding:13px 12px; border-radius:10px; }
  .personal-note-card header { align-items:center; }
  .personal-note-card header button { min-width:44px; min-height:44px; display:grid; place-items:center; }
  .personal-note-card footer { padding-right:38px; gap:6px; }
  .personal-note-card footer button,.personal-note-card .note-delete { min-width:44px; min-height:44px; }
  .personal-note-card .note-delete { right:6px; bottom:12px; display:grid; place-items:center; }
  .personal-note-card header small,.personal-note-card footer span { font-size:13px; }
  .notes-legacy summary { min-height:44px; display:flex; align-items:center; }
  .note-editor blockquote { max-height:160px; overflow:auto; }
  .note-location,.notes-status,.note-delete-confirm { overflow-wrap:anywhere; }
}
.personal-notes :deep(.el-button > span) { gap:6px; }
.personal-notes :deep(.el-button svg) { flex:none; }
.personal-note-card footer button { display:inline-flex; align-items:center; gap:4px; padding:6px 8px; border:1px solid #e2ddec; border-radius:7px; background:#faf9fd; }
@media(max-width:760px) { .notes-heading strong { display:none; } .notes-heading { justify-content:flex-end; margin-bottom:8px; } .notes-heading:has(+ .reading-aid-scope) { margin-bottom:8px; } }
.personal-note-card header small { display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
.note-type,.note-state { display:inline-flex; align-items:center; padding:2px 6px; border-radius:4px; font-size:12px; line-height:18px; background:#f1edf7; color:#705b8b; }
.personal-note-card footer .is-question { background:#fff2e3; color:#94602e; }
.personal-note-card footer button { min-height:var(--study-secondary-height); font-size:var(--study-control-font); line-height:20px; gap:5px; }
.personal-note-card .note-delete { min-height:var(--study-secondary-height); min-width:var(--study-secondary-height); color:#81748e; }
.personal-note-card .note-delete svg { width:16px; height:16px; }
.personal-notes .reading-aid-controls { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:8px; }
.notes-heading { grid-column:2; grid-row:1; margin:0; }
.notes-heading strong { display:none; }
.personal-notes .reading-aid-scope { grid-column:1; grid-row:1; }
.personal-notes .reading-aid-scope button { min-height:36px; font-size:14px; }
.personal-notes .reading-aid-controls>input { grid-column:1 / -1; margin:0; }
.personal-notes .notes-filters { grid-column:1 / -1; margin:0; }
.personal-notes .notes-heading:has(+ .reading-aid-scope) { margin:0; }
.personal-notes.is-editing .reading-aid-results { display:flex; flex-direction:column; padding:0 18px 16px; }
.note-editor { flex:1; display:flex; flex-direction:column; min-height:440px; margin:12px 0 0; }
.note-editor header { margin:0 0 12px; }
.note-editor header :deep(.el-button) { padding-left:0; }
.note-important { display:inline-flex; align-items:center; gap:6px; padding:8px; border:0; background:transparent; color:#625578; font:inherit; cursor:pointer; }
.note-important[aria-pressed=true] { color:#6552bb; }
.note-input-label { display:flex; flex-direction:column; flex:1; min-height:240px; }
.note-input-caption { position:absolute; clip-path:inset(50%); width:1px; height:1px; overflow:hidden; }
.note-input-label :deep(.el-textarea) { flex:1; display:flex; margin:0; }
.note-input-label :deep(textarea) { flex:1; min-height:240px!important; padding:14px; background:#fff; color:#343c50; }
.notes-options { justify-content:flex-start; margin:12px 0 0; }
.notes-options label { color:#637086; }
.note-save-status { margin:10px 0 8px; min-height:22px; }
.note-editor footer { border-top:1px solid #e9ebf2; padding-top:12px; justify-content:flex-end; }
.note-editor footer [data-action=discuss] { order:-1; margin-right:auto; }
.note-editor blockquote { max-height:100px; overflow:auto; }
.note-card-preview { color:#343c50; font-size:15px; overflow-wrap:anywhere; max-height:240px; overflow:auto; }
.note-card-preview :deep(.markdown-body) { font:inherit; }
.note-card-preview :deep(p) { margin:8px 0; }
.note-card-preview :deep(pre) { max-width:100%; overflow:auto; }
.personal-note-card .note-card-open { width:auto; }
@media(max-width:760px) {
  .personal-notes.is-editing .reading-aid-results { padding:0 16px max(16px,env(safe-area-inset-bottom)); }
  .note-editor { min-height:440px; }
  .note-important { min-height:44px; }
  .note-editor footer { position:sticky; bottom:0; background:white; padding-bottom:4px; }
}
</style>
