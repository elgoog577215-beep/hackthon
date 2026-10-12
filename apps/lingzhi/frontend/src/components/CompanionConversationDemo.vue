<template>
  <section class="demo-chat" :aria-label="t('companionWorkspace.title')" data-companion-obstacle>
    <CompanionPanelHeader :floating="floating" :history="historyOpen" live-pet @new="newConversation" @history="historyOpen = !historyOpen" @mode="emit('mode')" @close="emit('close')" />
    <div v-if="context" class="chat-context"><BookOpen :size="16" /><span>{{ t('companionWorkspace.current') }} · <b>{{ context.name }}</b></span><button :aria-label="t('companionWorkspace.clearContext')" @click="context = null"><X :size="14" /></button></div>
    <div v-if="reference" class="chat-reference"><ClipboardCheck :size="15" /><span>{{ reference }}</span><button :aria-label="t('companionWorkspace.removeReference')" @click="reference = ''"><X :size="13" /></button></div>
    <nav v-if="historyOpen" class="chat-history" :aria-label="t('companionWorkspace.history')"><button v-for="item in conversations" :key="item.id" :class="{ active:item.id === activeId }" @click="activeId = item.id; historyOpen = false"><MessageSquare :size="16" /><span>{{ item.title }}</span></button></nav>
    <div v-else ref="messagesEl" class="chat-messages" aria-live="polite">
      <div v-if="!current.messages.length" class="chat-welcome"><Sparkles :size="27" /><h3>{{ t('companionWorkspace.welcome') }}</h3><p>{{ context?.statement || t('companionWorkspace.chooseContext') }}</p><button @click="current.draft = t('companionWorkspace.exampleQuestion')">{{ t('companionWorkspace.exampleQuestion') }}</button></div>
      <article v-for="message in current.messages" :key="message.id" :class="['chat-message', message.role]">
        <div class="message-body">{{ message.text }}</div>
        <template v-if="message.role === 'assistant' && message.point">
          <button class="chat-source" @click="emit('lecture', message.point)"><BookOpen :size="17" /><span>{{ t('companionWorkspace.source') }} · {{ message.point.name }}</span><ChevronRight :size="16" /></button>
          <div class="chat-actions"><button :disabled="saved.has(message.id)" @click="saveNote(message)"><NotebookPen :size="15" />{{ saved.has(message.id) ? t('companionWorkspace.saved') : t('companionWorkspace.save') }}</button><button @click="emit('practice', message.point)"><ClipboardCheck :size="15" />{{ t('companionWorkspace.practice') }}</button></div>
        </template>
      </article>
    </div>
    <form class="chat-composer" @submit.prevent="send"><label class="sr-only" for="demo-chat-input">{{ t('companionWorkspace.placeholder') }}</label><div><textarea id="demo-chat-input" v-model="current.draft" rows="2" :placeholder="t('companionWorkspace.placeholder')" @keydown.enter.exact.prevent="send" /><button class="chat-send" :disabled="!current.draft.trim()" :aria-label="t('companionWorkspace.send')"><Send :size="19" /></button></div><small><Info :size="13" />{{ t('companionWorkspace.demoChatNotice') }}</small></form>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { BookOpen, ChevronRight, ClipboardCheck, Info, MessageSquare, NotebookPen, Send, Sparkles, X } from 'lucide-vue-next'
import CompanionPanelHeader from './CompanionPanelHeader.vue'
import type { KnowledgeProfileNode } from '../types/knowledge-profile'
import { t } from '../shared/i18n'
type Message = { id:number; role:'user'|'assistant'; text:string; point:KnowledgeProfileNode|null }
type Conversation = { id:number; title:string; draft:string; messages:Message[] }
const props = defineProps<{ point:KnowledgeProfileNode|null; floating:boolean }>()
const emit = defineEmits<{ (e:'mode'):void; (e:'close'):void; (e:'lecture',point:KnowledgeProfileNode):void; (e:'practice',point:KnowledgeProfileNode):void; (e:'note',text:string,point:KnowledgeProfileNode):void }>()
let sequence = 1
const context = ref<KnowledgeProfileNode|null>(null)
const reference = ref('')
const historyOpen = ref(false)
const messagesEl = ref<HTMLElement|null>(null)
const saved = ref(new Set<number>())
const conversations = ref<Conversation[]>([{ id:1, title:t('companionWorkspace.initialConversation'), draft:'', messages:[] }])
const activeId = ref(1)
const current = computed(() => conversations.value.find(item => item.id === activeId.value)!)
watch(() => props.point, point => { context.value = point; reference.value = '' }, { immediate:true })
function newConversation() { const id = ++sequence; conversations.value.unshift({ id, title:t('companionWorkspace.new'), draft:'', messages:[] }); activeId.value = id; historyOpen.value = false }
async function send() {
  const text = current.value.draft.trim()
  if (!text) return
  const point = context.value
  const answer = point?.knowledge_id === 'demo-k7' ? t('companionWorkspace.boundaryAnswer') : t('companionWorkspace.genericAnswer').replace('{statement}', point?.statement || t('companionWorkspace.chooseContext'))
  if (!current.value.messages.length) current.value.title = text.slice(0,28)
  current.value.messages.push({ id:++sequence,role:'user',text,point }, { id:++sequence,role:'assistant',text:answer,point })
  current.value.draft = ''
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = current.value.messages.length <= 2 ? 0 : messagesEl.value.scrollHeight
}
function saveNote(message:Message) { if (!message.point) return; saved.value.add(message.id); emit('note',message.text,message.point) }
function discuss(point:KnowledgeProfileNode, evidence:KnowledgeProfileNode['evidence'][number]) { context.value = point; reference.value = `${t('companionWorkspace.checkReference')} · ${t(`knowledgeProfile.outcomes.${evidence.outcome}`)}` }
defineExpose({ discuss })
</script>
<style scoped>
.demo-chat { display:flex; flex-direction:column; height:100%; min-height:0; color:#3d3159; background:#fff; border-radius:18px; overflow:hidden; }.chat-context { margin:16px 16px 0; padding:12px; background:#f3effd; border-radius:9px; display:flex; gap:8px; align-items:flex-start; font-size:13px; line-height:1.6; }.chat-context b { color:#7550ba; font-weight:500; }.chat-context svg { flex:none; margin-top:2px; }.chat-context button,.chat-reference button { border:0; background:none; color:#8977a5; margin-left:auto; cursor:pointer; }
.chat-reference { margin:10px 16px 0; display:flex; gap:6px; font-size:12px; color:#8366ab; align-items:center; }.chat-messages { flex:1; min-height:0; overflow:auto; padding:24px 20px; }.chat-message { margin-bottom:22px; font-size:15px; line-height:1.85; white-space:pre-wrap; }.chat-message.user { display:flex; justify-content:flex-end; }.user .message-body { max-width:94%; padding:10px 15px; border-radius:15px 15px 4px 15px; background:#efe9fb; }.assistant .message-body { padding:14px; border:1px solid #ece7f5; border-radius:14px; }.chat-source { width:100%; display:flex; align-items:center; gap:7px; margin-top:10px; text-align:left; border:0; border-radius:9px; padding:10px; background:#f6f2ff; color:#815caf; font-size:12px; cursor:pointer; }.chat-source span { flex:1; }.chat-source svg { flex:none; }.chat-actions { display:flex; gap:8px; margin-top:10px; }.chat-actions button,.chat-welcome button { display:flex; align-items:center; gap:6px; padding:8px 10px; border:1px solid #e4dcf0; background:#fff; color:#7557a3; border-radius:8px; cursor:pointer; font-size:13px; }.chat-actions button:disabled { color:#668d7e; cursor:default; }
.chat-composer { padding:14px 16px 16px; flex:none; }.chat-composer>div { display:flex; align-items:flex-end; gap:8px; padding:12px; border:1px solid #ddd4ed; border-radius:14px; }.chat-composer textarea { width:100%; resize:none; min-height:48px; border:0; outline:none; background:transparent; font:inherit; font-size:14px; line-height:1.6; color:#453457; }.chat-send { display:grid; place-items:center; width:38px; height:38px; flex:none; border:0; background:#7a53cf; color:#fff; border-radius:50%; cursor:pointer; }.chat-send:disabled { opacity:.4; cursor:default; }.chat-composer small { display:flex; align-items:flex-start; gap:5px; margin-top:10px; font-size:11px; color:#9986a9; line-height:1.5; }.chat-composer small svg { flex:none; margin-top:2px; }.chat-history { flex:1; overflow:auto; padding:18px; }.chat-history button { width:100%; padding:13px; display:flex; gap:10px; text-align:left; border:1px solid #eee7f8; border-radius:10px; margin-bottom:8px; background:#fff; color:#6e5b84; cursor:pointer; }.chat-history button.active { background:#f3eefa; }.chat-welcome { color:#8b70a9; padding:18px 0; }.chat-welcome h3 { font-size:21px; color:#48325f; margin:12px 0; }.chat-welcome p { font-size:15px; line-height:1.8; margin:0 0 20px; }button:focus-visible { outline:2px solid #835dc6; outline-offset:3px; }.sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); }
</style>
