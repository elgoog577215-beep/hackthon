<template>
  <section class="personal-assistant" :aria-label="c('assistant')">
    <header class="assistant-context"><strong>{{ c('discussing') }}</strong><span :title="context.section_title">{{ context.section_title }}</span></header>
    <div class="assistant-conversation">
    <div ref="thread" class="assistant-thread" tabindex="0" aria-live="polite" @scroll="handleMessageScroll">
      <div ref="threadContent">
      <p v-if="historyLoading" class="assistant-empty" role="status">{{ c('aiLoading') }}</p>
      <article v-for="message in conversation?.messages || []" :key="message.message_id" :class="['assistant-message', message.role]">
        <small>{{ message.context_ref.section_title }}<template v-if="message.context_ref.block_title && message.context_ref.block_title !== message.context_ref.section_title"> · {{ message.context_ref.block_title }}</template></small>
        <blockquote v-if="message.role === 'user' && message.context_ref.quote">{{ message.context_ref.quote }}</blockquote>
        <MarkdownRenderer :content="message.content" :enable-code-run="false" />
        <p v-if="['pending','running'].includes(message.status)" role="status">{{ c('aiWaiting') }}</p>
        <template v-else-if="['failed','paused','error'].includes(message.status)"><p>{{ c('aiInterrupted') }}</p><ElButton :disabled="busy || active || !historyReady" @click="resume(message)">{{ c('aiContinue') }}</ElButton></template>
      </article>
      </div>
    </div>
      <button v-if="!followingLatest && conversation?.messages.length" type="button" class="latest-reply" @click="scrollToBottom"><ArrowDown :size="14" aria-hidden="true" />{{ t('courseWorkspace.aiTeacher.latestReply') }}</button>
    </div>
    <form class="assistant-compose" @submit.prevent="send()">
      <div v-if="context.quote" class="assistant-quote"><div class="assistant-quote-header"><strong>{{ c('selectedQuote') }}</strong><ElButton native-type="button" @click="emit('clearQuote')">{{ c('clearQuote') }}</ElButton></div><p>{{ context.quote }}</p></div>
      <p v-if="error" role="alert">{{ error }}<ElButton native-type="button" @click="load">{{ c('retry') }}</ElButton></p>
      <div class="assistant-prompts"><button v-for="key in prompts" :key="key" type="button" :disabled="busy || active || !historyReady || !context.section_id" @click="send(promptText(key))">{{ promptText(key) }}</button></div>
      <div class="assistant-input-shell">
      <ElInput v-model="input" type="textarea" :autosize="{ minRows: 1, maxRows: 5 }" resize="none" maxlength="6000" :aria-label="c('aiInput')" :placeholder="c('aiPlaceholder')" @keydown.ctrl.enter.prevent="send()" />
      <footer><button class="assistant-send" type="submit" :aria-label="busy ? c('busy') : c('aiSend')" :title="c('aiSend')" :disabled="busy || active || !historyReady || !input.trim() || !context.section_id"><ArrowUp :size="19" aria-hidden="true" /></button></footer>
      </div>
      <p v-if="active || (historyReady && conversation?.messages.length)" class="assistant-save-state" role="status">{{ active ? c('running') : c('aiSaved') }}</p>
    </form>
  </section>
</template>

<script setup lang="ts">
import { createUuid } from '../utils/client-id'
import { ElButton, ElInput } from 'element-plus'
import { ArrowDown, ArrowUp } from 'lucide-vue-next'
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
let disposed = false, timer: ReturnType<typeof setTimeout> | undefined, requestId = createUuid(), fingerprint = '', observation = 0
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
  const next = JSON.stringify(body); if (fingerprint && fingerprint !== next) requestId = createUuid(); fingerprint = next; keepDraft()
  busy.value = true; error.value = ''; observation++; clearTimeout(timer); scrollToBottom()
  try { const result = await studyApi.ask(props.materialId, { ...body, request_id: requestId }); if (disposed) return; conversation.value = result; if (input.value.trim() === text) input.value = ''; requestId = createUuid(); fingerprint = ''; keepDraft(); await load() }
  catch (cause) { fail(cause) }
  finally { if (!disposed) busy.value = false }
}
async function resume(message: AssistantMessage) { if (busy.value || active.value || !message.task_ref) return; busy.value = true; try { await studyApi.continueAnswer(props.materialId, message.task_ref.task_id); if (!disposed) await load() } catch (cause) { fail(cause) } finally { if (!disposed) busy.value = false } }
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); keepDraft() })
</script>

<style scoped>
.personal-assistant { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; font:15px/1.75 var(--study-ui-font, var(--handout-sans)); color:#414a5d; }
.assistant-context { flex:none; margin:0; padding:9px 18px; display:flex; align-items:baseline; gap:8px; background:#fcfcfe; }
.assistant-context strong { flex:none; font-size:12px; font-weight:400; color:#929aab; }
.assistant-context span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#727c90; font-size:13px; }
.assistant-conversation { position:relative; display:flex; flex-direction:column; flex:1; min-height:0; }
.assistant-thread { flex:1; min-height:0; overflow:auto; padding:18px 20px 44px; scrollbar-width:thin; scrollbar-color:#d9dde7 transparent; }
.personal-assistant button:focus-visible,.assistant-thread:focus-visible { outline:2px solid #8b7ab5; outline-offset:-2px; }
.assistant-empty { color:#8b95a4; }
.assistant-message { margin:0 0 28px; min-width:0; overflow-wrap:anywhere; }
.assistant-message.user { margin-left:24px; padding:10px 13px; background:#f0eef8; border-radius:12px 12px 3px 12px; color:#504764; }
.assistant-message small { display:block; font-size:12px; line-height:1.5; color:#7f8798; margin-bottom:8px; }
.assistant-message blockquote { margin:0 0 10px; padding-left:10px; border-left:2px solid #c7bddc; color:#788197; }
.assistant-message :deep(.markdown-renderer) { font-size:15px; line-height:1.8; color:inherit; }
.assistant-message :deep(.markdown-renderer > :first-child) { margin-top:0; }
.assistant-message :deep(.markdown-renderer > :last-child) { margin-bottom:0; }
.assistant-message :deep(p) { margin:.65em 0; }
.assistant-message :deep(h1),.assistant-message :deep(h2),.assistant-message :deep(h3),.assistant-message :deep(h4) { margin:1.2em 0 .5em; font-weight:650; line-height:1.55; color:#303a4e; }
.assistant-message :deep(h1) { font-size:18px; }
.assistant-message :deep(h2) { font-size:17px; }
.assistant-message :deep(h3),.assistant-message :deep(h4) { font-size:15px; }
.assistant-message :deep(hr) { margin:20px 0; border-color:#eceef4; }
.assistant-message :deep(ul),.assistant-message :deep(ol) { margin:.5em 0 .8em; padding-left:1.5em; }
.assistant-message :deep(li) { margin:.25em 0; }
.assistant-message :deep(.code-block-wrapper) { margin:12px 0; border:0; border-radius:8px; box-shadow:none; }
.assistant-message :deep(.markdown-code-tools) { padding:5px 10px 0; gap:7px; }
.assistant-message :deep(.markdown-code-tools span),.assistant-message :deep(.markdown-code-tools .copy-btn) { font-size:12px; }
.assistant-message :deep(.copy-btn) { min-height:26px; padding:3px 6px; border-radius:5px; }
.assistant-message :deep(pre) { margin:0; padding:8px 12px 12px; border-radius:0; font-size:13px; line-height:1.65; }
.personal-assistant .latest-reply { position:absolute; right:18px; bottom:10px; display:flex; align-items:center; gap:5px; min-height:30px; padding:4px 10px; border:1px solid #e6e3ef; border-radius:20px; background:#fff; color:#71658c; box-shadow:0 2px 8px #28354b0b; font:inherit; font-size:12px; font-weight:400; cursor:pointer; }
.assistant-compose { flex:none; padding:8px 16px 10px; background:#fff; border-top:1px solid #f1f2f6; }
.assistant-prompts { display:flex; flex-wrap:wrap; gap:0 12px; margin:0 0 7px; }
.personal-assistant .assistant-prompts button { flex:none; min-height:30px; padding:3px 0; border:0; border-radius:4px; background:transparent; color:#716780; font:inherit; font-size:14px; font-weight:400; line-height:1.5; cursor:pointer; }
.personal-assistant .assistant-prompts button:hover:not(:disabled) { color:#66528e; text-decoration:underline; text-underline-offset:4px; }
.personal-assistant .assistant-prompts button:disabled { color:#adb0bd; cursor:default; }
.assistant-input-shell { display:grid; grid-template-columns:minmax(0,1fr) 34px; align-items:end; gap:8px; padding:8px 8px 8px 12px; border:1px solid #e3e4ec; border-radius:12px; background:#fafafd; transition:border-color .15s; }
.assistant-input-shell:focus-within { border-color:#a99bc5; background:#fff; box-shadow:0 0 0 2px #8c7bc30a; }
.assistant-input-shell :deep(.el-textarea__inner) { padding:5px 0; box-shadow:none; background:transparent; font-size:15px; line-height:1.6; color:#414a5d; }
.assistant-input-shell :deep(.el-textarea__inner::placeholder) { color:#a0a5b2; }
.assistant-compose footer { display:flex; margin:0; }
.personal-assistant .assistant-send { display:grid; place-items:center; width:34px; height:34px; min-height:34px; padding:0; border:0; border-radius:9px; color:#fff; background:#7966aa; cursor:pointer; }
.personal-assistant .assistant-send:hover:not(:disabled) { background:#695598; }
.personal-assistant .assistant-send:disabled { color:#b0adc0; background:#eceaf2; cursor:default; }
.assistant-save-state { min-height:16px; margin:5px 2px 0; color:#8790a1; font-size:12px; line-height:1.5; }
.assistant-quote { margin:0 0 9px; padding:8px 10px; border-left:2px solid #c2b4dc; background:#f7f5fb; border-radius:0 6px 6px 0; }
.assistant-quote p { margin:3px 0 0; max-height:52px; overflow:auto; font-size:13px; color:#7a8396; }
.assistant-quote-header { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:13px; }
.assistant-compose [role=alert] { color:#ab4b60; font-size:13px; }
@media(max-width:760px) {
  .assistant-context { padding:8px 14px; }
  .assistant-thread { padding:14px 16px 48px; }
  .assistant-compose { padding:4px 12px 8px; }
  .personal-assistant .assistant-prompts button { min-height:44px; }
  .assistant-input-shell { grid-template-columns:minmax(0,1fr) 44px; padding:5px 5px 5px 10px; }
  .personal-assistant .assistant-send { width:44px; height:44px; }
  .personal-assistant .latest-reply { min-height:44px; bottom:6px; }
  .assistant-input-shell :deep(.el-textarea__inner) { font-size:16px; }
}
</style>
