<template>
  <section class="personal-assistant" :aria-label="c('assistant')">
    <header><strong>{{ c('discussing') }}</strong><span>{{ context.section_title }}</span></header>
    <div ref="thread" class="assistant-thread" tabindex="0" aria-live="polite" @scroll="handleMessageScroll">
      <div ref="threadContent">
      <p v-if="!historyLoading && !conversation?.messages.length" class="assistant-intro">{{ c('aiIntro') }}</p>
      <p v-if="historyLoading" class="assistant-empty" role="status">{{ c('aiLoading') }}</p>
      <article v-for="message in conversation?.messages || []" :key="message.message_id" :class="['assistant-message', message.role]">
        <small>{{ message.context_ref.section_title }}<template v-if="message.context_ref.block_title && message.context_ref.block_title !== message.context_ref.section_title"> · {{ message.context_ref.block_title }}</template></small>
        <blockquote v-if="message.role === 'user' && message.context_ref.quote">{{ message.context_ref.quote }}</blockquote>
        <MarkdownRenderer :content="message.content" :enable-code-run="false" />
        <p v-if="['pending','running'].includes(message.status)" role="status">{{ c('aiWaiting') }}</p>
        <template v-else-if="['failed','paused','error'].includes(message.status)"><p>{{ c('aiInterrupted') }}</p><button :disabled="busy || active || !historyReady" @click="resume(message)">{{ c('aiContinue') }}</button></template>
      </article>
      </div>
    </div>
    <form class="assistant-compose" @submit.prevent="send()">
      <button v-if="!followingLatest && conversation?.messages.length" type="button" class="latest-reply" @click="scrollToBottom">{{ t('courseWorkspace.aiTeacher.latestReply') }}</button>
      <div v-if="context.quote" class="assistant-quote"><div class="assistant-quote-header"><strong>{{ c('selectedQuote') }}</strong><button type="button" @click="emit('clearQuote')">{{ c('clearQuote') }}</button></div><p>{{ context.quote }}</p></div>
      <p v-if="error" role="alert">{{ error }}<button type="button" @click="load">{{ c('retry') }}</button></p>
      <div class="assistant-prompts"><button v-for="key in prompts" :key="key" type="button" :disabled="busy || active || !historyReady || !context.section_id" @click="send(promptText(key))">{{ promptText(key) }}</button></div>
      <textarea v-model="input" rows="2" maxlength="6000" :aria-label="c('aiInput')" :placeholder="c('aiPlaceholder')" @keydown.ctrl.enter.prevent="send()" />
      <footer><span>{{ active ? c('running') : historyReady && conversation?.messages.length ? c('aiSaved') : '' }}</span><button type="submit" :disabled="busy || active || !historyReady || !input.trim() || !context.section_id">{{ busy ? c('busy') : c('aiSend') }}</button></footer>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { studyApi, StudyApiError, type AssistantContext, type AssistantConversation, type AssistantMessage } from '../api/study'
import { activeLocale, t } from '../shared/i18n'
import { studyCopy as c } from '../shared/study-copy'
import { useFollowingScroll } from '../composables/useFollowingScroll'
const props = defineProps<{ ownerId: string; materialId: string; revisionId: string; context: AssistantContext }>()
const emit = defineEmits<{ clearQuote: []; sessionExpired: [error: StudyApiError] }>()
const prompts = ['aiExplain','aiExample','aiDiagram'] as const
const promptText = (key: typeof prompts[number]) => c(key === 'aiExplain' && props.context.quote ? 'aiExplainQuote' : key)
const conversation = ref<AssistantConversation | null>(null), input = ref(''), error = ref(''), busy = ref(false), thread = ref<HTMLElement | null>(null)
const historyLoading = ref(false), historyReady = ref(false)
const threadContent = ref<HTMLElement | null>(null)
const { followingLatest, handleMessageScroll, scrollToBottom } = useFollowingScroll(thread,
  () => [conversation.value?.messages.length, conversation.value?.messages.at(-1)?.content], () => true, threadContent)
const active = computed(() => conversation.value?.messages.some(m => ['pending','running'].includes(m.status)) || false)
const key = `lingzhi-study-ai:${props.ownerId}:${props.materialId}:${props.revisionId}`
let disposed = false, timer: ReturnType<typeof setTimeout> | undefined, requestId = crypto.randomUUID(), fingerprint = '', observation = 0
try { const draft = JSON.parse(sessionStorage.getItem(key) || '{}'); input.value = draft.input || ''; requestId = draft.requestId || requestId; fingerprint = draft.fingerprint || '' } catch { /* Saved replies remain server-owned. */ }
function keepDraft() { try { sessionStorage.setItem(key, JSON.stringify({ input: input.value, requestId, fingerprint })) } catch { /* Browser storage must not prevent asking or editing. */ } }
watch(input, keepDraft)
watch(() => props.context.quote, quote => { if (quote && !input.value.trim()) input.value = c('aiSelectedPrompt') })
function fail(cause: unknown) { if (disposed) return; error.value = cause instanceof Error ? cause.message : c('requestFailure'); if (cause instanceof StudyApiError && cause.status === 401) emit('sessionExpired', cause) }
async function load() {
  clearTimeout(timer)
  const current = ++observation
  if (!historyReady.value) historyLoading.value = true
  try { const result = await studyApi.assistant(props.materialId); if (disposed || current !== observation) return; conversation.value = result; historyReady.value = true; error.value = ''; if (active.value) timer = setTimeout(() => { void load() }, 1500) }
  catch (cause) { if (!disposed && current === observation) { historyReady.value = false; fail(cause) } }
  finally { if (!disposed && current === observation) historyLoading.value = false }
}
async function send(prompt?: string) {
  if (busy.value || active.value || !historyReady.value || !props.context.section_id) return
  const text = (prompt || input.value).trim(); if (!text) return
  if (prompt) input.value = prompt
  const body = { revision_id: props.revisionId, section_id: props.context.section_id, block_id: props.context.block_id, quote: props.context.quote, text, language: activeLocale.value }
  const next = JSON.stringify(body); if (fingerprint && fingerprint !== next) requestId = crypto.randomUUID(); fingerprint = next; keepDraft()
  busy.value = true; error.value = ''; observation++; clearTimeout(timer); scrollToBottom()
  try { const result = await studyApi.ask(props.materialId, { ...body, request_id: requestId }); if (disposed) return; conversation.value = result; if (input.value.trim() === text) input.value = ''; requestId = crypto.randomUUID(); fingerprint = ''; keepDraft(); await load() }
  catch (cause) { fail(cause) }
  finally { if (!disposed) busy.value = false }
}
async function resume(message: AssistantMessage) { if (busy.value || active.value || !message.task_ref) return; busy.value = true; try { await studyApi.continueAnswer(props.materialId, message.task_ref.task_id); if (!disposed) await load() } catch (cause) { fail(cause) } finally { if (!disposed) busy.value = false } }
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); keepDraft() })
</script>

<style scoped>
.personal-assistant { display:flex; flex-direction:column; flex:1; min-height:0; font:15px/1.7 var(--study-ui-font, var(--handout-sans)); color:var(--lz-text); }
.personal-assistant header { margin:18px 20px 0; padding:12px 14px; background:#f8fafc; border-radius:8px; }
.personal-assistant header strong { display:block; font-size:15px; font-weight:500; color:var(--lz-text-muted); }
.personal-assistant header span { display:block; color:var(--lz-text-secondary); margin-top:4px; }
.assistant-thread { flex:1; min-height:100px; overflow:auto; padding:20px; }
.assistant-thread:focus-visible { outline:2px solid #8b6cc3; outline-offset:-2px; }
.assistant-empty { color:#8b95a4; }
.assistant-intro { margin:0; line-height:1.9; }
.assistant-message { margin:0 0 24px; overflow-wrap:anywhere; }
.assistant-message.user { background:#eef2ff; padding:12px 14px; border-radius:10px; }
.assistant-message small { display:block; font-size:15px; color:#9298a8; margin-bottom:7px; }
.assistant-message blockquote { margin:0 0 12px; padding-left:10px; border-left:3px solid #b8a8dc; color:#788197; }
.assistant-compose { padding:16px 18px; border-top:1px solid #ededf2; background:white; }
.assistant-compose textarea { box-sizing:border-box; width:100%; min-height:76px; max-height:160px; font:15px/1.7 var(--study-ui-font, var(--handout-sans)); padding:12px; border:1px solid #dbe2ee; border-radius:10px; background:#fff; resize:vertical; }
.personal-assistant button { font:15px/1.5 var(--study-ui-font, var(--handout-sans)); border:1px solid #dbe2ee; border-radius:8px; background:white; color:var(--lz-text-secondary); padding:7px 10px; cursor:pointer; }
.personal-assistant button:disabled { opacity:.5; cursor:default; }
.personal-assistant button:focus-visible, .assistant-compose textarea:focus-visible { outline:3px solid #9280df; outline-offset:2px; }
.assistant-prompts { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }
.assistant-compose footer { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:9px; }
.assistant-compose footer span { color:#8595a0; }
.assistant-compose footer button { background:var(--lz-action-primary-bg); color:var(--lz-action-primary-text); padding:9px 20px; border-color:var(--lz-action-primary-border); }
.assistant-quote { margin-bottom:12px; background:#eef2ff; padding:12px; border-radius:9px; }
.assistant-quote p { margin:4px 0 0; max-height:52px; overflow:auto; color:#7a8396; }
.assistant-quote-header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.assistant-compose [role=alert] { color:#ab4b60; }
</style>
