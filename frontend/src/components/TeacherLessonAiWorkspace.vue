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

    <div class="lesson-ai-scope" :title="courseTitle" :aria-label="tr('context')">
      <BookOpenText :size="14" />
      <strong>{{ lessonTitle }}</strong>
      <span aria-hidden="true">·</span>
      <span>{{ sectionTitle || tr('wholeLesson') }}</span>
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
      <div v-if="showQuickPrompts" class="lesson-ai-quick-prompts" :aria-label="tr('quickPrompts')">
        <button v-for="prompt in quickPrompts" :key="prompt" type="button" :disabled="busy" @click="submit(prompt)">
          {{ prompt }}
        </button>
      </div>
      <form class="lesson-ai-composer" @submit.prevent="submit(draft)">
        <textarea
          ref="composer"
          v-model="draft"
          rows="2"
          maxlength="800"
          :placeholder="tr('placeholder')"
          :aria-label="tr('placeholder')"
          :disabled="busy"
          @keydown.enter.exact.prevent="submit(draft)"
        />
        <button type="submit" :disabled="busy || !draft.trim()" :title="tr('send')" :aria-label="tr('send')">
          <LoaderCircle v-if="busy" :size="15" class="spin" />
          <SendHorizontal v-else :size="15" />
        </button>
      </form>
      <small>{{ candidatePending ? tr('followUpHint') : tr('composerHint') }}</small>
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
  TeacherLessonAiMessage,
  TeacherLessonAiPhase,
} from '../composables/useTeacherLessonAiCollaboration'
import { t } from '../shared/i18n'

export type { TeacherLessonAiMessage } from '../composables/useTeacherLessonAiCollaboration'

const props = withDefaults(defineProps<{
  courseTitle: string
  lessonTitle: string
  sectionTitle?: string
  referenceCount?: number
  messages: TeacherLessonAiMessage[]
  phase?: TeacherLessonAiPhase
  busy?: boolean
  candidatePending?: boolean
  candidateFields?: string[]
  clarificationOptions?: string[]
  canRetry?: boolean
}>(), {
  sectionTitle: '',
  referenceCount: 0,
  phase: 'ready',
  busy: false,
  candidatePending: false,
  candidateFields: () => [],
  clarificationOptions: () => [],
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
  wholeLesson: '整讲教案',
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
  composerHint: 'Enter 发送，Shift + Enter 换行',
  followUpHint: '继续补充会替换当前候选，正式教案仍不会自动修改。',
  quickObjective: '让目标可观察',
  quickActivity: '增加互动与检查',
  quickPacing: '压缩讲授，突出活动',
}

function tr(key: string): string {
  return t(`courseWorkbench.aiCollaboration.${key}`, fallbackMessages[key] || key)
}

const draft = ref('')
const composer = ref<HTMLTextAreaElement | null>(null)
const messageViewport = ref<HTMLElement | null>(null)
const quickPrompts = computed(() => [tr('quickObjective'), tr('quickActivity'), tr('quickPacing')])
const showQuickPrompts = computed(() => props.phase === 'ready' && !props.messages.some(message => message.role === 'user'))
const latestCandidateMessageId = computed(() => [...props.messages].reverse().find(message => message.kind === 'candidate')?.id || '')
const latestErrorMessageId = computed(() => [...props.messages].reverse().find(message => message.kind === 'error')?.id || '')
const candidateFieldSummary = computed(() => props.candidateFields.length
  ? tr('changedFields').replace('{fields}', props.candidateFields.join('、'))
  : tr('noChangedFields'))
const phaseLabel = computed(() => tr(`status${props.phase[0]!.toUpperCase()}${props.phase.slice(1)}`))
const workingLabel = computed(() => (
  props.phase === 'accepting'
    ? tr('workingAccepting')
    : props.phase === 'rejecting'
      ? tr('workingRejecting')
      : tr('workingGenerating')
))

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

watch(() => props.lessonTitle, () => nextTick(() => composer.value?.focus()))
</script>

<style scoped>
.lesson-ai-workspace{height:100%;min-width:0;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;background:#fff}
.lesson-ai-header{min-height:54px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 14px 0 16px;border-bottom:1px solid #e7ebf2}.lesson-ai-title{min-width:0;display:flex;align-items:center;gap:8px;color:#4f46e5}.lesson-ai-title strong{color:#202a3d;font-size:13px}.lesson-ai-title>span{display:flex;align-items:center;gap:5px;color:#7b8798;font-size:10px;font-weight:650}.lesson-ai-title>span i{width:5px;height:5px;border-radius:50%;background:#94a3b8}.lesson-ai-title>span[data-phase="generating"] i,.lesson-ai-title>span[data-phase="accepting"] i,.lesson-ai-title>span[data-phase="rejecting"] i{background:#6366f1}.lesson-ai-title>span[data-phase="review"] i{background:#8b5cf6}.lesson-ai-title>span[data-phase="success"] i{background:#16a34a}.lesson-ai-title>span[data-phase="error"] i{background:#dc2626}.lesson-ai-header>button{width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:7px;color:#64748b;background:transparent;cursor:pointer}.lesson-ai-header>button:hover{color:#334155;background:#f3f5f8}.lesson-ai-header>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-scope{min-width:0;min-height:40px;display:flex;align-items:center;gap:6px;padding:0 16px;border-bottom:1px solid #edf0f5;color:#8290a3;background:#fbfcfe;font-size:10.5px}.lesson-ai-scope svg{flex:none;color:#6366f1}.lesson-ai-scope strong,.lesson-ai-scope>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lesson-ai-scope strong{max-width:34%;color:#48566b}.lesson-ai-scope>span:last-of-type{flex:1}.lesson-ai-scope small{flex:none;color:#8792a3;font-size:10px}
.lesson-ai-messages{min-height:0;overflow:auto;padding:18px 16px 24px;scrollbar-width:thin;scrollbar-color:transparent transparent}.lesson-ai-messages:hover{scrollbar-color:#cbd3df transparent}.lesson-ai-messages::-webkit-scrollbar{width:6px}.lesson-ai-messages::-webkit-scrollbar-thumb{border-radius:6px;background:transparent}.lesson-ai-messages:hover::-webkit-scrollbar-thumb{background:#cbd3df}.lesson-ai-message{margin:0 0 15px}.lesson-ai-message.is-user{display:flex;justify-content:flex-end}.lesson-ai-user-bubble{max-width:84%;padding:8px 10px;border-radius:11px 11px 3px 11px;color:#fff;background:#514bdc;font-size:12px;line-height:1.55;overflow-wrap:anywhere}.lesson-ai-assistant-line{display:grid;grid-template-columns:15px minmax(0,1fr) auto;align-items:start;gap:7px;color:#6366f1}.lesson-ai-assistant-line p{margin:0;color:#4c596d;font-size:12px;line-height:1.65;overflow-wrap:anywhere}.lesson-ai-assistant-line.is-receipt{color:#16925f}.lesson-ai-assistant-line.is-receipt p{color:#29765a}.lesson-ai-assistant-line.is-error{color:#c2414f}.lesson-ai-assistant-line.is-error p{color:#9f3c48}.lesson-ai-assistant-line>button{min-height:26px;padding:0 8px;border:1px solid #e0b5bb;border-radius:6px;color:#9f3c48;background:#fff;font-size:10px;font-weight:700;cursor:pointer}
.lesson-ai-review{border-top:1px solid #dfe2f4;border-bottom:1px solid #dfe2f4;background:#fbfbff}.lesson-ai-review>header{min-height:40px;display:flex;align-items:center;gap:7px;color:#514bdc}.lesson-ai-review>header strong{color:#353567;font-size:12px}.lesson-ai-review>header span{margin-inline-start:auto;color:#7772a8;font-size:10px;font-weight:700}.lesson-ai-review>p{margin:0;padding:0 0 12px;color:#5f6980;font-size:11px;line-height:1.55}.lesson-ai-review>footer{display:flex;align-items:center;justify-content:flex-end;gap:5px;padding:9px 0;border-top:1px solid #ececf6}.lesson-ai-review button{min-height:30px;display:flex;align-items:center;justify-content:center;gap:5px;padding:0 9px;border:1px solid transparent;border-radius:7px;color:#596579;background:transparent;font-size:10.5px;font-weight:700;cursor:pointer}.lesson-ai-review button:hover:not(:disabled){background:#f1f3f7}.lesson-ai-review button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.lesson-ai-review button:disabled{opacity:.5;cursor:not-allowed}.lesson-ai-review button:focus-visible,.lesson-ai-clarification button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-clarification{display:flex;flex-wrap:wrap;gap:6px;margin:-3px 0 17px;padding-inline-start:22px}.lesson-ai-clarification button,.lesson-ai-quick-prompts button{min-height:29px;padding:0 9px;border:1px solid #d9def0;border-radius:7px;color:#4f4a8d;background:#fff;font-size:10.5px;cursor:pointer}.lesson-ai-clarification button:hover,.lesson-ai-quick-prompts button:hover:not(:disabled){border-color:#b9bced;background:#f7f7ff}.lesson-ai-working-state{display:flex;align-items:center;gap:7px;color:#65649c;font-size:11px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.lesson-ai-composer-shell{display:grid;gap:8px;padding:10px 12px 12px;border-top:1px solid #e4e9f1;background:#fbfcfe}.lesson-ai-quick-prompts{display:flex;gap:6px;overflow:auto;padding-bottom:1px}.lesson-ai-quick-prompts button{flex:none}.lesson-ai-composer{position:relative}.lesson-ai-composer textarea{width:100%;min-height:58px;box-sizing:border-box;padding:9px 40px 9px 10px;border:1px solid #cbd4e1;border-radius:10px;outline:0;color:#263147;background:#fff;font:inherit;font-size:12px;line-height:1.5;resize:none}.lesson-ai-composer textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.09)}.lesson-ai-composer>button{position:absolute;right:7px;bottom:7px;width:29px;height:29px;display:grid;place-items:center;padding:0;border:0;border-radius:7px;color:#fff;background:#514bdc;cursor:pointer}.lesson-ai-composer>button:disabled{color:#a3abc0;background:#e6e9f0;cursor:not-allowed}.lesson-ai-composer>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.lesson-ai-composer-shell>small{color:#8791a2;font-size:9.5px;line-height:1.4}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
