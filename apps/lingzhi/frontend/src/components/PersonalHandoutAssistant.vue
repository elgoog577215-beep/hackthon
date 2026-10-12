<template>
  <section class="personal-assistant" :aria-label="c('assistant')">
    <header><strong>{{ c('assistant') }}</strong><p>{{ c('aiIntro') }}</p><span>{{ context.section_title }}</span></header>
    <div ref="thread" class="assistant-thread" aria-live="polite">
      <p v-if="!conversation?.messages.length" class="assistant-empty">{{ c('aiIntro') }}</p>
      <article v-for="message in conversation?.messages || []" :key="message.message_id" :class="['assistant-message', message.role]">
        <small>{{ message.context_ref.block_title || message.context_ref.section_title }}</small>
        <blockquote v-if="message.role === 'user' && message.context_ref.quote">{{ message.context_ref.quote }}</blockquote>
        <MarkdownRenderer :content="message.content" :enable-code-run="false" />
        <p v-if="['pending','running'].includes(message.status)" role="status">{{ c('aiWaiting') }}</p>
        <template v-else-if="['failed','paused','error'].includes(message.status)"><p>{{ c('aiInterrupted') }}</p><button :disabled="busy || active" @click="resume(message)">{{ c('aiContinue') }}</button></template>
      </article>
    </div>
    <form class="assistant-compose" @submit.prevent="send()">
      <div v-if="context.quote" class="assistant-quote"><strong>{{ c('selectedQuote') }}</strong><p>{{ context.quote }}</p><button type="button" @click="emit('clearQuote')">{{ c('clearQuote') }}</button></div>
      <p v-if="error" role="alert">{{ error }}<button type="button" @click="load">{{ c('retry') }}</button></p>
      <div class="assistant-prompts"><button v-for="key in prompts" :key="key" type="button" :disabled="busy || active || !context.section_id" @click="send(c(key))">{{ c(key) }}</button></div>
      <textarea v-model="input" rows="3" maxlength="6000" :aria-label="c('aiInput')" :placeholder="c('aiPlaceholder')" @keydown.ctrl.enter.prevent="send()" />
      <footer><span>{{ active ? c('running') : conversation?.messages.length ? c('aiSaved') : '' }}</span><button type="submit" :disabled="busy || active || !input.trim() || !context.section_id">{{ busy ? c('busy') : c('aiSend') }}</button></footer>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { studyApi, StudyApiError, type AssistantContext, type AssistantConversation, type AssistantMessage } from '../api/study'
import { activeLocale } from '../shared/i18n'
import { studyCopy as c } from '../shared/study-copy'
const props = defineProps<{ ownerId: string; materialId: string; revisionId: string; context: AssistantContext }>()
const emit = defineEmits<{ clearQuote: []; sessionExpired: [error: StudyApiError] }>()
const prompts = ['aiExplain','aiExample','aiDiagram'] as const
const conversation = ref<AssistantConversation | null>(null), input = ref(''), error = ref(''), busy = ref(false), thread = ref<HTMLElement | null>(null)
const active = computed(() => conversation.value?.messages.some(m => ['pending','running'].includes(m.status)) || false)
const key = `lingzhi-study-ai:${props.ownerId}:${props.materialId}:${props.revisionId}`
let disposed = false, timer: ReturnType<typeof setTimeout> | undefined, requestId = crypto.randomUUID(), fingerprint = ''
try { const draft = JSON.parse(sessionStorage.getItem(key) || '{}'); input.value = draft.input || ''; requestId = draft.requestId || requestId; fingerprint = draft.fingerprint || '' } catch { /* Saved replies remain server-owned. */ }
function keepDraft() { sessionStorage.setItem(key, JSON.stringify({ input: input.value, requestId, fingerprint })) }
watch(input, keepDraft)
watch(() => props.context.quote, quote => { if (quote && !input.value.trim()) input.value = c('aiSelectedPrompt') })
function fail(cause: unknown) { if (disposed) return; error.value = cause instanceof Error ? cause.message : c('requestFailure'); if (cause instanceof StudyApiError && cause.status === 401) emit('sessionExpired', cause) }
async function load() {
  clearTimeout(timer)
  try { const result = await studyApi.assistant(props.materialId); if (disposed) return; conversation.value = result; error.value = ''; if (active.value) timer = setTimeout(() => { void load() }, 1500) }
  catch (cause) { fail(cause) }
}
async function send(prompt?: string) {
  if (busy.value || active.value || !props.context.section_id) return
  const text = (prompt || input.value).trim(); if (!text) return
  if (prompt) input.value = prompt
  const body = { revision_id: props.revisionId, section_id: props.context.section_id, block_id: props.context.block_id, quote: props.context.quote, text, language: activeLocale.value }
  const next = JSON.stringify(body); if (fingerprint && fingerprint !== next) requestId = crypto.randomUUID(); fingerprint = next; keepDraft()
  busy.value = true; error.value = ''
  try { const result = await studyApi.ask(props.materialId, { ...body, request_id: requestId }); if (disposed) return; conversation.value = result; if (input.value.trim() === text) input.value = ''; requestId = crypto.randomUUID(); fingerprint = ''; keepDraft(); await load(); await nextTick(); if (thread.value) thread.value.scrollTop = thread.value.scrollHeight }
  catch (cause) { fail(cause) }
  finally { if (!disposed) busy.value = false }
}
async function resume(message: AssistantMessage) { if (busy.value || active.value || !message.task_ref) return; busy.value = true; try { await studyApi.continueAnswer(props.materialId, message.task_ref.task_id); if (!disposed) await load() } catch (cause) { fail(cause) } finally { if (!disposed) busy.value = false } }
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); keepDraft() })
</script>

<style scoped>
.personal-assistant{display:flex;flex-direction:column;flex:1;min-height:0;font:15px/1.7 var(--handout-sans);color:#34435d}.personal-assistant header{padding:18px 20px;border-bottom:1px solid #e3e5ef}.personal-assistant header strong{font-size:19px;color:#6350aa}.personal-assistant header p{margin:8px 0;color:#8791a2}.personal-assistant header span{color:#738198}.assistant-thread{flex:1;min-height:130px;overflow:auto;padding:16px}.assistant-empty{color:#8b95a4}.assistant-message{margin:0 0 18px;padding:12px 14px;border:1px solid #e1e5f0;border-radius:12px;background:white;overflow-wrap:anywhere}.assistant-message.user{background:#f1edfb;border-color:#e2dbf4}.assistant-message small{display:block;font-size:15px;color:#8c94a5;margin-bottom:7px}.assistant-message blockquote{margin:0 0 12px;padding-left:10px;border-left:3px solid #b8a8dc;color:#788197}.assistant-compose{padding:15px;border-top:1px solid #dfe5ef;background:#fcfdff}.assistant-compose textarea{box-sizing:border-box;width:100%;font:15px/1.7 var(--handout-sans);padding:11px;border:1px solid #d4dced;border-radius:10px;resize:vertical}.personal-assistant button{font:15px/1.5 var(--handout-sans);border:1px solid #dadfee;border-radius:8px;background:white;color:#6651a7;padding:7px 10px;cursor:pointer}.personal-assistant button:disabled{opacity:.5;cursor:default}.personal-assistant button:focus-visible,.assistant-compose textarea:focus-visible{outline:3px solid #9280df;outline-offset:2px}.assistant-prompts{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}.assistant-compose footer{display:flex;align-items:center;justify-content:space-between;margin-top:9px}.assistant-compose footer span{color:#8595a0}.assistant-compose footer button{background:#6651bd;color:white;padding:9px 22px}.assistant-quote{margin-bottom:12px;background:#f3f0fa;padding:12px;border-radius:9px}.assistant-quote p{max-height:100px;overflow:auto;margin:7px 0;color:#7a8396}.assistant-compose [role=alert]{color:#ab4b60}
</style>
