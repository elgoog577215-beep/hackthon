<template>
  <section class="study-dialogue" :class="{'is-compact':compact}" :aria-label="t('studyDialogue.title')">
    <details v-if="!compact" class="study-source">
      <summary>{{t('studyDialogue.source')}} · {{workspace.node_name}}</summary>
      <blockquote><MarkdownRenderer :content="workspace.quote || t('studyDialogue.quickNote')" :enable-code-run="false" /></blockquote>
    </details>
    <span v-if="historical" class="study-error">{{ t('studyDialogue.historical') }}</span>
    <span v-if="preview" class="study-preview">{{ t('studyDialogue.preview') }}</span>
    <div v-if="!compact && view!=='conversation'" class="study-tool-heading">
      <button type="button" data-study-back @click="backToChat">← {{t('studyDialogue.backToChat')}}</button><strong>{{t(view==='draft'?'studyDialogue.noteDraft':'studyDialogue.understanding')}}</strong>
    </div>
    <div ref="messageList" class="study-body" tabindex="0" @scroll="handleMessageScroll">
      <div v-if="compact || view === 'conversation'" ref="messageContent">
        <p v-if="!conversation.messages.length" class="study-hint">{{ t('studyDialogue.welcome') }}</p>
        <article v-for="message in displayedMessages" :key="message.message_id" class="study-message" :class="message.role">
          <small v-if="!compact">{{ t(message.role === 'user' ? 'studyDialogue.you' : 'companionWorkspace.title') }}</small>
          <p v-if="message.status === 'failed'" class="study-error">{{ modelFailureLabel(message.failure_code) }}</p>
          <MarkdownRenderer :content="compact ? shortReply(message.content) : message.content" />
        </article>
        <p v-if="compact && busy" class="study-hint" role="status">{{t('studyDialogue.working')}}</p>
        <p v-if="compact && longReply" class="study-hint">{{t('readingCompanion.longReply')}}</p>
        <details v-if="!compact && workspace.nearby.length" class="study-nearby">
          <summary>{{ t('studyDialogue.nearby') }}</summary>
          <button v-for="note in workspace.nearby" :key="note.record_id" type="button" @click="emit('openRecord', note.record_id)"><span>{{ note.quote }}</span>{{ note.content }}</button>
        </details>
      </div>
      <template v-else-if="view === 'draft'">
        <label class="study-editor">{{ t('studyDialogue.currentDraft') }}<textarea v-model="draft" :disabled="historical" :placeholder="t('studyDialogue.writeHint')" rows="8" /></label>
        <p class="study-hint">{{ t('studyDialogue.autoDraftHint') }}</p>
        <p class="study-hint">{{ t('studyDialogue.saveHint') }}</p>
        <div class="study-actions"><button type="button" class="primary" :disabled="!canAct || !draft.trim()" @click="run('save')">{{ t('studyDialogue.save') }}</button></div>
        <details v-if="workspace.versions.length"><summary>{{ t('studyDialogue.versions') }} · {{ workspace.versions.length }}</summary>
          <article v-for="version in [...workspace.versions].reverse()" :key="version.revision" class="study-version"><small>v{{ version.revision }}</small><p>{{ version.content }}</p><button type="button" :disabled="!canAct" @click="run('restore', { version:version.revision })">{{ t('studyDialogue.restore') }}</button></article>
        </details>
      </template>
      <template v-else>
        <p class="study-hint">{{ t('studyDialogue.checkHint') }}</p>
        <p v-if="!workspace.knowledge.length || preview">{{ t('studyDialogue.noKnowledge') }}</p>
        <template v-else>
          <label>{{ t('studyDialogue.knowledge') }}<select v-model="knowledgeId"><option v-for="point in workspace.knowledge" :key="point.knowledge_id" :value="point.knowledge_id">{{ point.name }}</option></select></label>
          <p class="study-question">{{ selectedPoint?.question }}</p>
          <label class="study-editor">{{ t('studyDialogue.yourExplanation') }}<textarea v-model="answer" :disabled="!canAct" rows="5" /></label>
          <p>{{ t(workspace.solution_seen ? 'studyDialogue.solutionSeen' : workspace.assisted ? 'studyDialogue.assisted' : 'studyDialogue.independent') }}</p>
          <button type="button" class="primary" :disabled="!canAct || !answer.trim() || !selectedPoint?.question" @click="run('check', { text:answer, knowledge_id:knowledgeId })">{{ t('studyDialogue.submitCheck') }}</button>
        </template>
        <article v-for="(check, index) in [...workspace.checks].reverse()" :key="index" class="study-check">
          <strong>{{ t(check.passed === null || check.confidence < .72 ? 'studyDialogue.inconclusive' : check.passed ? 'studyDialogue.passed' : 'studyDialogue.notPassed') }}</strong><p>{{ check.feedback }}</p>
          <small>{{ t(check.solution_seen ? 'studyDialogue.solutionSeen' : check.support_level ? 'studyDialogue.assisted' : 'studyDialogue.independent') }}</small>
        </article>
      </template>
    </div>
    <p v-if="error" class="study-error" role="alert">{{ error }} <button v-if="conflict" type="button" :disabled="busy" @click="reload">{{ t('studyDialogue.reload') }}</button></p>
    <p v-if="notice && !compact" class="study-notice" role="status">{{ notice }}</p>
    <div v-if="compact && !busy && displayedMessages.length" class="inline-reply-actions">
      <button v-if="!compactComposer" type="button" @click="compactComposer=true">{{t('courseWorkspace.inlineAi.followUp')}}</button>
      <button v-if="longReply" type="button" data-testid="companion-expand" @click="emit('expand')">{{t('readingCompanion.expand')}}</button>
    </div>
    <form v-if="compact ? compactComposer || input.trim() || (!displayedMessages.length && !busy) : view === 'conversation'" class="study-composer" @submit.prevent="run('discuss', { text:input })">
      <button v-if="!compact && !followingLatest && conversation.messages.length" type="button" class="latest-reply" @click="scrollToBottom">{{ t('courseWorkspace.aiTeacher.latestReply') }}</button>
      <textarea v-model="input" :disabled="historical" :rows="compact ? 1 : 2" maxlength="12000" :aria-label="t('studyDialogue.message')" :placeholder="t('studyDialogue.message')" />
      <div>
        <details v-if="!compact" ref="moreTools" class="study-more" @keydown.esc.stop.prevent="closeTools(true)" @focusout="leaveTools">
          <summary>{{t('studyDialogue.more')}}</summary>
          <div class="study-more-options">
            <button type="button" data-study-tool="draft" @click="openTool('draft')">{{t('studyDialogue.noteDraft')}}</button>
            <button type="button" data-study-tool="understanding" @click="openTool('understanding')">{{t('studyDialogue.understanding')}}</button>
            <button v-for="action in ['explain','contrast','step'] as const" :key="action" type="button" :data-teaching-action="action" :disabled="!canAct" @click="closeTools();run('discuss',{text:t(`companionTeaching.${action}`),teaching_action:action})">{{t(`companionTeaching.${action}`)}}</button>
            <button type="button" data-teaching-action="verify" :disabled="!canAct || !selectedPoint || preview" @click="closeTools();independentCheck()">{{t('companionTeaching.verify')}}</button>
          </div>
        </details>
        <button type="submit" class="primary" :disabled="!canAct || !input.trim()">{{ t(busy ? 'studyDialogue.working' : 'studyDialogue.send') }}</button>
      </div>
    </form>
    <p v-else-if="busy" class="study-notice" role="status">{{ t('studyDialogue.working') }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { AIConversation } from '../stores/aiTeacher'
import { useAITeacherStore } from '../stores/aiTeacher'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import { useLearnerModelStore } from '../stores/learnerModel'
import { getLearnerIdentity } from '../utils/http'
import { isTeacherPreviewCourse } from '../utils/teacher-preview'
import { createUuid } from '../utils/client-id'
import { t } from '../shared/i18n'
import { modelFailureLabel } from '../utils/ai-teacher-failures'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useFollowingScroll } from '../composables/useFollowingScroll'
import http from '../utils/http'

const props = defineProps<{ conversation:AIConversation;compact?:boolean }>()
const emit = defineEmits<{ expand:[];openRecord:[id:string]; practice:[target:{nodeId:string;taskRevisionId:string}] }>()
const ai = useAITeacherStore(), course = useCourseStore(), notes = useNoteStore()
const workspace = computed(() => props.conversation.study_workspace!)
const displayedMessages=computed(()=>props.compact ? props.conversation.messages.filter(m=>m.role==='assistant').slice(-1) : props.conversation.messages)
const longReply=computed(()=>props.compact && (displayedMessages.value.at(-1)?.content.length||0)>700)
function shortReply(text:string){if(text.length<=700)return text;const paragraph=text.split(/\n\s*\n/)[0]||'';return paragraph.length<=500&&!paragraph.includes('```')?paragraph:''}
const preview = computed(() => isTeacherPreviewCourse(props.conversation.course_id))
const historical = computed(() => workspace.value.course_version_id !== (course.currentCourseVersionId || ''))
const tabs = ['conversation','draft','understanding'] as const
const view = ref<typeof tabs[number]>('conversation')
const moreTools=ref<HTMLDetailsElement|null>(null)
function closeTools(focus=false){if(moreTools.value){moreTools.value.open=false;if(focus)moreTools.value.querySelector('summary')?.focus()}}
async function openTool(tool:'draft'|'understanding'){closeTools();view.value=tool;await nextTick();messageList.value?.querySelector<HTMLElement>('textarea,select,button')?.focus({preventScroll:true})}
function leaveTools(event:FocusEvent){if(!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node|null))closeTools()}
async function backToChat(){view.value='conversation';await nextTick();moreTools.value?.querySelector('summary')?.focus({preventScroll:true})}
const draft = ref(workspace.value.draft), input = ref(''), answer = ref('')
const knowledgeId = ref(workspace.value.knowledge[0]?.knowledge_id || '')
const selectedPoint = computed(() => workspace.value.knowledge.find(point=>point.knowledge_id===knowledgeId.value))
const busy = ref(false), error = ref(''), notice = ref(''), conflict = ref(false)
const compactComposer=ref(false)
async function independentCheck(){if(!canAct.value||!selectedPoint.value||preview.value)return;const target=props.conversation;busy.value=true;error.value='';try{const {data}=await http.post(`/api/courses/${encodeURIComponent(target.course_id)}/learning-records/companion/check-target`,{conversation_id:target.conversation_id,knowledge_id:selectedPoint.value.knowledge_id,knowledge_revision:selectedPoint.value.revision_id});if(disposed||course.currentCourseId!==target.course_id)return;if(data.status==='available')emit('practice',{nodeId:data.node_id,taskRevisionId:data.task_revision_id});else notice.value=t('companionTeaching.awaiting')}catch{if(!disposed)error.value=t('companionTeaching.unavailable')}finally{if(!disposed)busy.value=false}}
const canAct = computed(() => !busy.value && !historical.value && !conflict.value)
const messageList = ref<HTMLElement | null>(null)
const messageContent = ref<HTMLElement | null>(null)
const { followingLatest, handleMessageScroll, scrollToBottom } = useFollowingScroll(messageList,
  () => [view.value, props.conversation.messages.length, props.conversation.messages.at(-1)?.content],
  () => view.value === 'conversation', messageContent)
const cacheKey = `study-draft:${getLearnerIdentity()}:${props.conversation.course_id}:${props.conversation.conversation_id}`
let disposed = false
// Local recovery is a draft, never a second saved note or mastery record.
if (!preview.value) {
  try {
    const saved = JSON.parse(localStorage.getItem(cacheKey) || 'null')
    if (saved) {
      if (saved.dirty !== false) {
        if (saved.revision !== workspace.value.revision && saved.draft !== workspace.value.draft) { conflict.value = true; error.value = t('studyDialogue.localConflict') }
        draft.value = saved.draft ?? draft.value
      }
      input.value = saved.input || ''; answer.value = saved.answer || ''
    }
  } catch { /* Retain the server draft if browser storage is unavailable. */ }
}
function cache() {
  if (preview.value) { workspace.value.draft = draft.value; return }
  if (!preview.value) try { localStorage.setItem(cacheKey, JSON.stringify({ draft:draft.value, dirty:draft.value !== workspace.value.draft, input:input.value, answer:answer.value, revision:workspace.value.revision })) } catch { /* Editing remains available. */ }
}
watch([draft,input,answer], cache, { flush:'sync' })
onBeforeUnmount(() => { cache(); disposed = true })

async function previewCommand(action:string, extra:Record<string,unknown>) {
  const ws = workspace.value
  if (action === 'draft') { ws.draft = String(extra.text ?? ''); return }
  if (action === 'save') {
    const note = { id:ws.record_id, nodeId:ws.node_id, quote:ws.quote, anchor:ws.anchor, content:ws.draft, color:'violet', createdAt:Date.now(), highlightId:`hl-${ws.record_id}`, recordType:'note' as const, sourceType:'user' as const, revision:ws.saved_revision + 1, metadata:{ study_conversation_id:props.conversation.conversation_id } }
    const index = notes.notes.findIndex(item=>item.id===ws.record_id)
    if (index >= 0) notes.notes[index] = note
    else notes.addNote(note)
    ws.saved_revision++
    ws.versions.push({ revision:ws.saved_revision, content:ws.draft, assisted:ws.assisted, saved_at:new Date().toISOString() })
  } else if (action === 'restore') { ws.draft = ws.versions.find(v=>v.revision === extra.version)?.content || ws.draft }
  else if (action === 'discuss') return ai.discussStudyPreview(props.conversation.conversation_id, String(extra.text))
}

async function run(action:string, extra:Record<string,unknown> = {}) {
  if (busy.value || historical.value || conflict.value) return
  busy.value = true; error.value = ''; notice.value = ''; conflict.value = false
  const targetCourse = props.conversation.course_id
  const id = props.conversation.conversation_id
  const submittedDraft = draft.value
  const submittedText = action === 'discuss' ? String(extra.text ?? '') : ''
  if (action === 'discuss') scrollToBottom()
  const command = async (kind:string, data:Record<string,unknown> = {}) => preview.value
    ? previewCommand(kind, data)
    : ai.studyCommand(id, { action:kind, ...data, request_id:createUuid() })
  try {
    if (submittedDraft !== workspace.value.draft) await command('draft', { text:submittedDraft })
    if (disposed || course.currentCourseId !== targetCourse) return
    const response = await command(action, extra)
    if (disposed || course.currentCourseId !== targetCourse) return
    const next = response?.study_workspace || workspace.value
    if (action === 'discuss' || action === 'restore') {
      if (draft.value === submittedDraft) {
        draft.value = next.draft
      } else notice.value = t('studyDialogue.manualDraftKept')
    }
    if (action === 'discuss' && input.value === submittedText) {input.value = '';compactComposer.value=false}
    if (action === 'restore') view.value = 'draft'
    if (action === 'save') {
      if (!preview.value) await notes.loadCourseRecords(targetCourse)
      notice.value = t(draft.value === submittedDraft ? 'studyDialogue.saved' : 'studyDialogue.savedEarlierDraft')
      if (!preview.value && !input.value && !answer.value && draft.value === submittedDraft) localStorage.removeItem(cacheKey)
      else cache()
    }
    if (action === 'check') await useLearnerModelStore().load(targetCourse)
  } catch (failure:any) {
    conflict.value = failure?.response?.status === 409 || Boolean(failure?.contextChanged)
    error.value = conflict.value ? t('studyDialogue.conflict') : failure?.failureCode ? modelFailureLabel(failure.failureCode) : t('studyDialogue.failed')
  } finally { busy.value = false }
}
defineExpose({ startDiscussion: (text:string) => run('discuss', { text }) })
async function reload() {
  if (busy.value) return
  const targetCourse = props.conversation.course_id, id = props.conversation.conversation_id
  busy.value = true
  try { await ai.selectConversation(id); if (disposed || course.currentCourseId !== targetCourse) return; if (!historical.value && !preview.value) await ai.studyCommand(id, { action:'refresh', request_id:createUuid() }); if (disposed || course.currentCourseId !== targetCourse) return; conflict.value = false; error.value = ''; notice.value = t('studyDialogue.reloaded') }
  catch { if (!disposed && course.currentCourseId === targetCourse) error.value = t('studyDialogue.failed') }
  finally { if (!disposed) busy.value = false }
}
</script>

<style scoped>
.study-dialogue.is-compact{flex:none;color:#263247;font-size:16px;line-height:1.8}
.is-compact .study-body{flex:none;overflow:visible;padding:16px 18px;max-height:none}
.is-compact .study-message{padding:0;margin:0;background:transparent;border-radius:0}
.is-compact .study-composer{display:flex;align-items:flex-end;gap:10px;padding:10px 16px;background:#fff}
.is-compact .study-composer textarea{flex:1;min-height:44px;max-height:96px;resize:vertical;padding:9px 11px}
.is-compact .study-composer div{flex:none;margin:0}
.is-compact .study-hint{color:#58657a;font-size:15px}
.inline-reply-actions{display:flex;gap:16px;align-items:center;padding:0 18px 12px}
.inline-reply-actions button{border:0;background:transparent;padding:0;color:#5145aa;font-size:14px}
.study-teaching-actions { display:flex;flex-wrap:wrap;gap:6px;padding:8px 14px;border-bottom:1px solid #e9e2f1 }.study-teaching-actions button { font:inherit;font-size:15px;border:1px solid #d7cce8;border-radius:7px;padding:5px 8px;background:#faf7fe;color:#655080;cursor:pointer }.study-teaching-actions button:disabled {opacity:.5;cursor:default}
.study-dialogue { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; color:var(--lz-text,#44384f); background:#fff; font-size:15px; }
.study-source { padding:8px 14px; background:#f7f3fd; flex:none; }
.study-source strong { display:block; font-size:15px; line-height:1.45; }.study-source blockquote { margin:4px 0 0; padding-left:8px; border-left:2px solid #beabd9; max-height:44px; overflow:auto; color:#776587; font-size:13px; line-height:1.6; }
.study-preview { display:block; margin-top:3px; color:#897793; font-size:12px; line-height:1.5; }
.study-tabs { display:flex; gap:6px; padding:8px 12px; border-bottom:1px solid #ece4f5; flex:none; }
button { border:1px solid #e3d8f0; background:#fff; border-radius:8px; padding:7px 10px; color:#705397; cursor:pointer; font-size:15px; }
button:disabled { opacity:.5; cursor:default; }.study-tabs button[aria-pressed=true] { background:#eee6fa; border-color:#beabd9; }.primary { color:var(--lz-action-text); background:var(--lz-action-bg); border-color:var(--lz-action-border); border:1px solid var(--lz-action-border); border-radius:var(--lz-action-radius); box-shadow:var(--lz-action-shadow); }
.study-body { flex:1; min-height:0; overflow:auto; padding:14px 16px; overscroll-behavior:contain; }
.study-message { padding:12px; margin-bottom:12px; border-radius:12px; background:#f7f4fc; overflow-wrap:anywhere; }.study-message.user { background:#f0f3fc; margin-left:20px; }.study-message small { color:#8c769f; }
.study-editor { display:flex; flex-direction:column; gap:8px; font-weight:600; }.study-editor textarea,.study-composer textarea { resize:vertical; width:100%; box-sizing:border-box; min-height:80px; padding:12px; border:1px solid #dfd5ea; border-radius:10px; font:inherit; font-weight:400; line-height:1.65; color:#44384f; background:#fff; }
.study-hint { color:#897793; font-size:13px; line-height:1.7; }.study-actions { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }
.study-proposal,.study-check,.study-version { margin:12px 0; padding:12px; border:1px solid #e5dcee; border-radius:12px; overflow-wrap:anywhere; }.study-version p { white-space:pre-wrap; }
.study-nearby button { display:block; text-align:left; width:100%; margin-top:8px; font-size:13px; }.study-nearby span { display:block; color:#97839e; }
.study-composer { padding:8px 14px; border-top:1px solid #eee7f5; flex:none; }.study-composer div { display:flex; justify-content:space-between; margin-top:6px; }
.study-composer textarea { display:block; min-height:64px; max-height:140px; padding:8px 10px; }
.study-error,.study-notice { padding:8px 16px; margin:0; font-size:13px; color:#98565e; }.study-notice { color:#655088; }
.study-question { padding:12px; background:#f5f1fb; border-radius:10px; }.study-body select { display:block; width:100%; margin:8px 0; padding:8px; border:1px solid #dfd5ea; border-radius:8px; background:#fff; color:inherit; }
.study-source{padding:10px 16px;background:#faf9fd;border-bottom:1px solid #ece8f2}
.study-source summary{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px;color:#645b76}
.study-source blockquote{font-size:15px;color:#4c4658;max-height:180px;line-height:1.7;margin:12px 0 2px}
.study-tool-heading{display:flex;align-items:center;gap:12px;padding:10px 14px;border-bottom:1px solid #ece8f2;flex:none}
.study-tool-heading button{border:0;background:transparent;padding:2px 0;font-size:14px}
.study-tool-heading strong{font-size:15px}
.study-more{position:relative}
.study-more summary{padding:7px 2px;list-style:none;font-size:14px;color:#645b76}
.study-more summary::-webkit-details-marker{display:none}
.study-composer .study-more-options{display:grid;gap:4px;position:absolute;left:0;bottom:calc(100% + 8px);min-width:205px;z-index:5;padding:6px;border:1px solid #ded8ea;border-radius:10px;background:white;box-shadow:0 8px 24px #34224918}
.study-more-options button{border:0;background:white;text-align:left;padding:8px 10px;white-space:nowrap;font-size:15px}
.study-more-options button:hover:not(:disabled){background:#f5f0ff}
.study-more-options button:first-child{border-bottom:1px solid #f0ecf5;border-radius:0}
summary { cursor:pointer; color:#705397; }button:focus-visible,textarea:focus-visible,select:focus-visible,summary:focus-visible { outline:2px solid #8b6cc3; outline-offset:2px; }.study-body:focus-visible{outline:2px solid #8b6cc3;outline-offset:-2px}
</style>
