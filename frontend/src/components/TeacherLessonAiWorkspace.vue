<template>
  <aside class="lesson-ai-workspace" :aria-label="tr('title')">
    <header class="lesson-ai-header">
      <div class="lesson-ai-title">
        <Sparkles :size="16" />
        <strong>{{ tr('title') }}</strong>
        <span :data-phase="phase"><i />{{ phaseLabel }}</span>
      </div>
      <button type="button" :title="tr('close')" :aria-label="tr('close')" @click="emit('close')">
        <X :size="17" />
      </button>
    </header>

    <div class="lesson-ai-scope" :title="scopeTitle" :aria-label="tr('context')">
      <BookOpenText :size="14" />
      <strong>{{ scopeTitle }}</strong>
      <span aria-hidden="true">·</span>
      <span>{{ scopeDetail }}</span>
      <small>{{ tr('sourceCount').replace('{count}', String(referenceCount)) }}</small>
    </div>

    <main ref="messageViewport" class="lesson-ai-messages" aria-live="polite">
      <article
        v-for="message in messages"
        :key="message.id"
        :class="['lesson-ai-message', `is-${message.role}`, `is-${message.kind}`]"
      >
        <div v-if="message.role === 'user'" class="lesson-ai-user-bubble">{{ message.text }}</div>
        <template v-else-if="message.kind === 'candidate'">
          <section class="lesson-ai-review">
            <header>
              <FileDiff :size="15" />
              <strong>{{ tr('candidateReady') }}</strong>
              <span>{{ tr('changeCount').replace('{count}', String(candidateFields.length)) }}</span>
            </header>
            <p>{{ candidateFieldSummary || message.text }}</p>
            <footer v-if="candidatePending && message.id === latestCandidateMessageId">
              <button type="button" :disabled="busy" @click="emit('focus-candidate')">
                <LocateFixed :size="14" />{{ tr('locate') }}
              </button>
              <button type="button" :disabled="busy" @click="emit('reject')">{{ tr('reject') }}</button>
              <button class="primary" type="button" :disabled="busy" @click="emit('accept')">
                <Check :size="14" />{{ tr('accept') }}
              </button>
            </footer>
          </section>
        </template>
        <div v-else :class="['lesson-ai-assistant-line', `is-${message.kind}`]">
          <CheckCircle2 v-if="message.kind === 'receipt'" :size="14" />
          <CircleAlert v-else-if="message.kind === 'error'" :size="14" />
          <Sparkles v-else :size="13" />
          <p>{{ message.text }}</p>
          <button
            v-if="message.kind === 'error' && canRetry && message.id === latestErrorMessageId"
            type="button"
            :disabled="busy"
            @click="emit('retry')"
          >{{ tr('retry') }}</button>
        </div>
      </article>

      <section v-if="showQuickPrompts" class="lesson-ai-quick-start" :aria-label="tr('quickPrompts')">
        <button v-for="prompt in quickPrompts" :key="prompt" type="button" :disabled="busy" @click="submit(prompt)">
          {{ prompt }}
        </button>
      </section>

      <div v-if="phase === 'clarifying' && clarificationOptions.length" class="lesson-ai-clarification">
        <button
          v-for="option in clarificationOptions"
          :key="option"
          type="button"
          @click="emit('clarify', option)"
        >{{ option }}</button>
      </div>

      <div v-if="busy" class="lesson-ai-working-state" aria-busy="true">
        <LoaderCircle :size="14" class="spin" />
        <span>{{ workingLabel }}</span>
      </div>
    </main>

    <footer class="lesson-ai-composer-shell">
      <form class="lesson-ai-composer" @submit.prevent="submit(draft)">
        <textarea
          ref="composer"
          v-model="draft"
          rows="1"
          maxlength="800"
          :placeholder="placeholder || tr('placeholder')"
          :aria-label="placeholder || tr('placeholder')"
          :disabled="busy"
          @keydown.enter.exact.prevent="submit(draft)"
        />
        <button type="submit" :disabled="busy || !draft.trim()" :title="tr('send')" :aria-label="tr('send')">
          <LoaderCircle v-if="busy" :size="15" class="spin" />
          <SendHorizontal v-else :size="15" />
        </button>
      </form>
      <small v-if="candidatePending">{{ tr('followUpHint') }}</small>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  BookOpenText,
  Check,
  CheckCircle2,
  CircleAlert,
  FileDiff,
  LoaderCircle,
  LocateFixed,
  SendHorizontal,
  Sparkles,
  X,
} from 'lucide-vue-next'
import type {
  TeacherProductionAiDomain,
  TeacherProductionAiMessage,
  TeacherProductionAiPhase,
} from '../composables/useTeacherProductionAiCollaboration'
import { t } from '../shared/i18n'

export type { TeacherProductionAiMessage } from '../composables/useTeacherProductionAiCollaboration'

const props = withDefaults(defineProps<{
  domain?: TeacherProductionAiDomain
  scopeTitle: string
  scopeDetail: string
  referenceCount?: number
  messages: TeacherProductionAiMessage[]
  phase?: TeacherProductionAiPhase
  busy?: boolean
  candidatePending?: boolean
  candidateFields?: string[]
  clarificationOptions?: string[]
  quickPrompts?: string[]
  placeholder?: string
  canRetry?: boolean
}>(), {
  domain: 'lesson',
  referenceCount: 0,
  phase: 'ready',
  busy: false,
  candidatePending: false,
  candidateFields: () => [],
  clarificationOptions: () => [],
  quickPrompts: () => [],
  placeholder: '',
  canRetry: false,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'send', value: string): void
  (event: 'clarify', value: string): void
  (event: 'retry'): void
  (event: 'accept'): void
  (event: 'reject'): void
  (event: 'focus-candidate'): void
}>()

const fallbackMessages: Record<string, string> = {
  title: 'AI 助手',
  close: '退出 AI 编辑模式',
  context: '当前编辑范围',
  sourceCount: '{count} 份资料',
  candidateReady: '修改候选',
  changeCount: '{count} 处修改',
  changedFields: '涉及：{fields}',
  noChangedFields: '候选已显示在左侧，请核对高亮内容。',
  locate: '定位',
  reject: '放弃',
  accept: '采用',
  retry: '重试',
  statusReady: '就绪',
  statusClarifying: '等待补充',
  statusGenerating: '生成中',
  statusReview: '待确认',
  statusAccepting: '正在采用',
  statusRejecting: '正在放弃',
  statusSuccess: '已完成',
  statusError: '需要处理',
  workingGenerating: '正在生成结构化候选…',
  workingAccepting: '正在形成新的教案修订…',
  workingRejecting: '正在放弃当前候选…',
  quickPrompts: '常用修改要求',
  placeholder: '告诉我具体想改什么…',
  send: '发送',
  followUpHint: '继续补充会替换当前候选，正式内容保持不变。',
}

function tr(key: string): string {
  return t(`courseWorkbench.aiCollaboration.${key}`, fallbackMessages[key] || key)
}

const draft = ref('')
const composer = ref<HTMLTextAreaElement | null>(null)
const messageViewport = ref<HTMLElement | null>(null)
const showQuickPrompts = computed(() => props.phase === 'ready' && !props.messages.some(message => message.role === 'user'))
const latestCandidateMessageId = computed(() => [...props.messages].reverse().find(message => message.kind === 'candidate')?.id || '')
const latestErrorMessageId = computed(() => [...props.messages].reverse().find(message => message.kind === 'error')?.id || '')
const candidateFieldSummary = computed(() => props.candidateFields.length
  ? tr('changedFields').replace('{fields}', props.candidateFields.join('、'))
  : tr('noChangedFields'))
const phaseLabel = computed(() => tr(`status${props.phase[0]!.toUpperCase()}${props.phase.slice(1)}`))
const workingLabel = computed(() => {
  if (props.phase === 'accepting') return props.domain === 'outline' ? '正在应用大纲修订…' : props.domain === 'script' ? '正在形成新的讲稿修订…' : tr('workingAccepting')
  if (props.phase === 'rejecting') return tr('workingRejecting')
  return props.domain === 'outline' ? '正在生成大纲调整候选…' : props.domain === 'script' ? '正在生成讲稿表达候选…' : tr('workingGenerating')
})

function submit(value: string) {
  const instruction = value.trim()
  if (!instruction || props.busy) return
  draft.value = ''
  emit('send', instruction)
}

watch(
  () => [props.messages.length, props.busy, props.phase],
  () => nextTick(() => {
    if (messageViewport.value) messageViewport.value.scrollTop = messageViewport.value.scrollHeight
  }),
)

watch(() => [props.domain, props.scopeTitle, props.scopeDetail], () => nextTick(() => composer.value?.focus()))
</script>

<style scoped>
.lesson-ai-workspace{height:100%;min-width:0;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;background:#fff}
.lesson-ai-header{min-height:46px;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 10px 0 14px;border-bottom:1px solid #e7ebf2}.lesson-ai-title{min-width:0;display:flex;align-items:center;gap:7px;color:#4f46e5}.lesson-ai-title strong{color:#202a3d;font-size:12.5px}.lesson-ai-title>span{display:flex;align-items:center;gap:5px;color:#718096;font-size:9.5px;font-weight:650}.lesson-ai-title>span i{width:5px;height:5px;border-radius:50%;background:#94a3b8}.lesson-ai-title>span[data-phase="generating"] i,.lesson-ai-title>span[data-phase="accepting"] i,.lesson-ai-title>span[data-phase="rejecting"] i{background:#6366f1}.lesson-ai-title>span[data-phase="review"] i{background:#8b5cf6}.lesson-ai-title>span[data-phase="success"] i{background:#16a34a}.lesson-ai-title>span[data-phase="error"] i{background:#dc2626}.lesson-ai-header>button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:7px;color:#64748b;background:transparent;cursor:pointer}.lesson-ai-header>button:hover{color:#334155;background:#f3f5f8}.lesson-ai-header>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-scope{min-width:0;min-height:36px;display:flex;align-items:center;gap:5px;padding:0 14px;border-bottom:1px solid #edf0f5;color:#718096;background:#fbfcfe;font-size:10px}.lesson-ai-scope svg{flex:none;color:#6366f1}.lesson-ai-scope strong,.lesson-ai-scope>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lesson-ai-scope strong{max-width:42%;color:#405068}.lesson-ai-scope>span:last-of-type{flex:1}.lesson-ai-scope small{flex:none;color:#778397;font-size:9.5px}
.lesson-ai-messages{min-height:0;overflow:auto;padding:14px 14px 22px;scrollbar-width:thin;scrollbar-color:transparent transparent}.lesson-ai-messages:hover{scrollbar-color:#cbd3df transparent}.lesson-ai-messages::-webkit-scrollbar{width:5px}.lesson-ai-messages::-webkit-scrollbar-thumb{border-radius:5px;background:transparent}.lesson-ai-messages:hover::-webkit-scrollbar-thumb{background:#cbd3df}.lesson-ai-message{margin:0 0 13px}.lesson-ai-message.is-user{display:flex;justify-content:flex-end}.lesson-ai-user-bubble{max-width:86%;padding:7px 9px;border-radius:10px 10px 3px 10px;color:#fff;background:#514bdc;font-size:11.5px;line-height:1.5;overflow-wrap:anywhere}.lesson-ai-assistant-line{display:grid;grid-template-columns:14px minmax(0,1fr) auto;align-items:start;gap:6px;color:#6366f1}.lesson-ai-assistant-line p{margin:0;color:#435168;font-size:11.5px;line-height:1.58;overflow-wrap:anywhere}.lesson-ai-assistant-line.is-receipt{color:#16925f}.lesson-ai-assistant-line.is-receipt p{color:#29765a}.lesson-ai-assistant-line.is-error{color:#c2414f}.lesson-ai-assistant-line.is-error p{color:#9f3c48}.lesson-ai-assistant-line>button{min-height:25px;padding:0 7px;border:1px solid #e0b5bb;border-radius:6px;color:#9f3c48;background:#fff;font-size:10px;font-weight:700;cursor:pointer}
.lesson-ai-review{border-top:1px solid #dfe2f4;border-bottom:1px solid #dfe2f4;background:#fbfbff}.lesson-ai-review>header{min-height:40px;display:flex;align-items:center;gap:7px;color:#514bdc}.lesson-ai-review>header strong{color:#353567;font-size:12px}.lesson-ai-review>header span{margin-inline-start:auto;color:#7772a8;font-size:10px;font-weight:700}.lesson-ai-review>p{margin:0;padding:0 0 12px;color:#5f6980;font-size:11px;line-height:1.55}.lesson-ai-review>footer{display:flex;align-items:center;justify-content:flex-end;gap:5px;padding:9px 0;border-top:1px solid #ececf6}.lesson-ai-review button{min-height:30px;display:flex;align-items:center;justify-content:center;gap:5px;padding:0 9px;border:1px solid transparent;border-radius:7px;color:#596579;background:transparent;font-size:10.5px;font-weight:700;cursor:pointer}.lesson-ai-review button:hover:not(:disabled){background:#f1f3f7}.lesson-ai-review button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.lesson-ai-review button:disabled{opacity:.5;cursor:not-allowed}.lesson-ai-review button:focus-visible,.lesson-ai-clarification button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-quick-start,.lesson-ai-clarification{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 14px;padding-inline-start:20px}.lesson-ai-quick-start button,.lesson-ai-clarification button{min-height:28px;padding:0 8px;border:1px solid #d9def0;border-radius:7px;color:#4f4a8d;background:#fff;font-size:10px;cursor:pointer}.lesson-ai-quick-start button:hover:not(:disabled),.lesson-ai-clarification button:hover{border-color:#b9bced;background:#f7f7ff}.lesson-ai-working-state{display:flex;align-items:center;gap:7px;color:#65649c;font-size:10.5px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.lesson-ai-composer-shell{display:grid;gap:6px;padding:9px 10px 10px;border-top:1px solid #e4e9f1;background:#fbfcfe}.lesson-ai-composer{position:relative}.lesson-ai-composer textarea{width:100%;height:42px;min-height:42px;max-height:96px;box-sizing:border-box;padding:11px 38px 9px 10px;border:1px solid #cbd4e1;border-radius:9px;outline:0;color:#263147;background:#fff;font:inherit;font-size:11.5px;line-height:1.45;resize:none}.lesson-ai-composer textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.09)}.lesson-ai-composer>button{position:absolute;right:6px;bottom:6px;width:30px;height:30px;display:grid;place-items:center;padding:0;border:0;border-radius:7px;color:#fff;background:#514bdc;cursor:pointer}.lesson-ai-composer>button:disabled{color:#a3abc0;background:#e6e9f0;cursor:not-allowed}.lesson-ai-composer>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.lesson-ai-composer-shell>small{padding:0 2px;color:#778397;font-size:9px;line-height:1.4}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
