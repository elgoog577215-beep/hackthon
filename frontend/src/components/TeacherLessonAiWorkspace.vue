<template>
  <aside class="lesson-ai-workspace" :aria-label="tr('title')">
    <header class="lesson-ai-header">
      <div class="lesson-ai-identity">
        <span><Sparkles :size="17" /></span>
        <div>
          <strong>{{ tr('title') }}</strong>
          <small>{{ tr('mode') }}</small>
        </div>
      </div>
      <button type="button" :title="tr('close')" :aria-label="tr('close')" @click="emit('close')">
        <X :size="18" />
      </button>
    </header>

    <section class="lesson-ai-context" :aria-label="tr('context')">
      <div class="lesson-ai-context__title">
        <BookOpenText :size="15" />
        <strong>{{ courseTitle }}</strong>
      </div>
      <dl>
        <div>
          <dt>{{ tr('lesson') }}</dt>
          <dd>{{ lessonTitle }}</dd>
        </div>
        <div>
          <dt>{{ tr('section') }}</dt>
          <dd>{{ sectionTitle || tr('wholeLesson') }}</dd>
        </div>
        <div>
          <dt>{{ tr('sources') }}</dt>
          <dd>{{ tr('sourceCount').replace('{count}', String(referenceCount)) }}</dd>
        </div>
      </dl>
    </section>

    <main ref="messageViewport" class="lesson-ai-messages" aria-live="polite">
      <article
        v-for="message in messages"
        :key="message.id"
        :class="['lesson-ai-message', `is-${message.role}`, `is-${message.kind}`]"
      >
        <div v-if="message.role === 'user'" class="lesson-ai-user-bubble">{{ message.text }}</div>
        <template v-else>
          <span class="lesson-ai-avatar"><Sparkles :size="13" /></span>
          <div class="lesson-ai-assistant-copy">
            <p v-if="message.kind !== 'candidate'">{{ message.text }}</p>
            <section v-else class="lesson-ai-candidate-card">
              <header>
                <span><FileDiff :size="15" /></span>
                <div>
                  <strong>{{ tr('candidateReady') }}</strong>
                  <small>{{ tr('candidatePending') }}</small>
                </div>
              </header>
              <p>{{ message.text }}</p>
              <div class="lesson-ai-candidate-target">
                <LocateFixed :size="14" />
                <span>{{ tr('candidateOnCanvas') }}</span>
              </div>
              <footer v-if="candidatePending && message.id === latestCandidateMessageId">
                <button type="button" :disabled="busy" @click="emit('focus-candidate')">
                  <ScanSearch :size="14" />{{ tr('locate') }}
                </button>
                <button type="button" :disabled="busy" @click="emit('reject')">
                  {{ tr('reject') }}
                </button>
                <button class="primary" type="button" :disabled="busy" @click="emit('accept')">
                  <Check :size="14" />{{ tr('accept') }}
                </button>
              </footer>
            </section>
          </div>
        </template>
      </article>

      <article v-if="busy" class="lesson-ai-message is-assistant is-loading" aria-busy="true">
        <span class="lesson-ai-avatar"><LoaderCircle :size="13" class="spin" /></span>
        <div class="lesson-ai-working-state">
          <strong>{{ tr('working') }}</strong>
          <span>{{ tr('workingDetail') }}</span>
        </div>
      </article>
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
          rows="3"
          :placeholder="tr('placeholder')"
          :aria-label="tr('placeholder')"
          :disabled="busy"
          @keydown.enter.exact.prevent="submit(draft)"
        />
        <button type="submit" :disabled="busy || !draft.trim()" :title="tr('send')" :aria-label="tr('send')">
          <LoaderCircle v-if="busy" :size="16" class="spin" />
          <SendHorizontal v-else :size="16" />
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
  FileDiff,
  LoaderCircle,
  LocateFixed,
  ScanSearch,
  SendHorizontal,
  Sparkles,
  X,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'

export interface TeacherLessonAiMessage {
  id: string
  role: 'assistant' | 'user'
  kind: 'text' | 'candidate' | 'receipt' | 'error'
  text: string
}

const props = withDefaults(defineProps<{
  courseTitle: string
  lessonTitle: string
  sectionTitle?: string
  referenceCount?: number
  messages: TeacherLessonAiMessage[]
  busy?: boolean
  candidatePending?: boolean
}>(), {
  sectionTitle: '',
  referenceCount: 0,
  busy: false,
  candidatePending: false,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'send', value: string): void
  (event: 'accept'): void
  (event: 'reject'): void
  (event: 'focus-candidate'): void
}>()

const fallbackMessages: Record<string, string> = {
  title: '教师智能体',
  mode: 'AI 协作编辑',
  close: '退出 AI 协作编辑',
  context: '当前编辑范围',
  lesson: '当前讲次',
  section: '当前小节',
  wholeLesson: '整讲教案',
  sources: '资料范围',
  sourceCount: '{count} 份当前资料',
  candidateReady: '修改候选已生成',
  candidatePending: '等待教师确认',
  candidateOnCanvas: '候选已经呈现在左侧画布，高亮内容尚未写入正式教案。',
  locate: '定位候选',
  reject: '放弃',
  accept: '采用候选',
  working: '正在生成结构化候选',
  workingDetail: '完成后会直接呈现在左侧教案画布。',
  quickPrompts: '常用修改要求',
  placeholder: '说明你希望怎样修改当前教案…',
  send: '发送',
  composerHint: 'Enter 发送，Shift + Enter 换行',
  followUpHint: '可以继续补充要求；新候选会综合本轮对话重新生成。',
  quickObjective: '让教学目标更可观察',
  quickActivity: '增加课堂互动与检查',
  quickPacing: '压缩讲授时间，突出关键活动',
}

function tr(key: string): string {
  return t(`courseWorkbench.aiCollaboration.${key}`, fallbackMessages[key] || key)
}

const draft = ref('')
const composer = ref<HTMLTextAreaElement | null>(null)
const messageViewport = ref<HTMLElement | null>(null)
const quickPrompts = computed(() => [tr('quickObjective'), tr('quickActivity'), tr('quickPacing')])
const showQuickPrompts = computed(() => !props.messages.some(message => message.role === 'user'))
const latestCandidateMessageId = computed(() => [...props.messages].reverse().find(message => message.kind === 'candidate')?.id || '')

function submit(value: string) {
  const instruction = value.trim()
  if (!instruction || props.busy) return
  draft.value = ''
  emit('send', instruction)
}

watch(
  () => [props.messages.length, props.busy],
  () => nextTick(() => {
    if (messageViewport.value) messageViewport.value.scrollTop = messageViewport.value.scrollHeight
  }),
)

watch(() => props.lessonTitle, () => nextTick(() => composer.value?.focus()))
</script>

<style scoped>
.lesson-ai-workspace{height:100%;min-width:0;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;border-left:1px solid #dfe4ec;background:#fff}
.lesson-ai-header{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:0 18px;border-bottom:1px solid #e7ebf2}.lesson-ai-identity{min-width:0;display:flex;align-items:center;gap:10px}.lesson-ai-identity>span,.lesson-ai-avatar{flex:none;display:grid;place-items:center;color:#4f46e5;background:#eef2ff}.lesson-ai-identity>span{width:32px;height:32px;border-radius:10px}.lesson-ai-identity>div{min-width:0;display:grid;gap:1px}.lesson-ai-identity strong{color:#1f2a40;font-size:13px}.lesson-ai-identity small{color:#6b7280;font-size:10px}.lesson-ai-header>button{width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.lesson-ai-header>button:hover{color:#334155;background:#f3f5f8}.lesson-ai-header>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-context{display:grid;gap:11px;padding:15px 18px;border-bottom:1px solid #e7ebf2;background:#fafbfe}.lesson-ai-context__title{min-width:0;display:flex;align-items:center;gap:7px;color:#4f46e5}.lesson-ai-context__title strong{overflow:hidden;color:#334155;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.lesson-ai-context dl{display:grid;gap:7px;margin:0}.lesson-ai-context dl>div{min-width:0;display:grid;grid-template-columns:62px minmax(0,1fr);gap:8px}.lesson-ai-context dt{color:#8a94a5;font-size:10px}.lesson-ai-context dd{margin:0;overflow:hidden;color:#4b5870;font-size:10.5px;font-weight:650;text-overflow:ellipsis;white-space:nowrap}
.lesson-ai-messages{min-height:0;overflow:auto;padding:18px}.lesson-ai-message{display:flex;align-items:flex-start;gap:9px;margin-bottom:16px}.lesson-ai-message.is-user{justify-content:flex-end}.lesson-ai-avatar{width:25px;height:25px;margin-top:1px;border-radius:8px}.lesson-ai-user-bubble{max-width:82%;padding:9px 11px;border-radius:12px 12px 3px 12px;color:#fff;background:#514bdc;font-size:12px;line-height:1.58}.lesson-ai-assistant-copy{min-width:0;max-width:calc(100% - 34px)}.lesson-ai-assistant-copy>p{margin:2px 0 0;color:#475569;font-size:12px;line-height:1.68}.lesson-ai-message.is-receipt .lesson-ai-assistant-copy>p{color:#047857}.lesson-ai-message.is-error .lesson-ai-assistant-copy>p{color:#b91c1c}
.lesson-ai-candidate-card{overflow:hidden;border:1px solid #cfd4f4;border-radius:13px;background:#fbfbff;box-shadow:0 10px 24px rgba(67,56,202,.08)}.lesson-ai-candidate-card>header{display:flex;align-items:center;gap:9px;padding:12px 13px;border-bottom:1px solid #e1e4f7;background:#f4f4ff}.lesson-ai-candidate-card>header>span{width:28px;height:28px;display:grid;place-items:center;border-radius:8px;color:#4338ca;background:#fff}.lesson-ai-candidate-card>header>div{display:grid;gap:1px}.lesson-ai-candidate-card>header strong{color:#2f3170;font-size:12px}.lesson-ai-candidate-card>header small{color:#766fb0;font-size:9.5px}.lesson-ai-candidate-card>p{margin:0;padding:12px 13px 8px;color:#4b5870;font-size:11.5px;line-height:1.6}.lesson-ai-candidate-target{display:flex;align-items:flex-start;gap:7px;margin:0 13px 12px;padding:9px 10px;border-radius:9px;color:#4f46e5;background:#eef2ff}.lesson-ai-candidate-target svg{flex:none;margin-top:1px}.lesson-ai-candidate-target span{font-size:10.5px;line-height:1.5}.lesson-ai-candidate-card>footer{display:flex;align-items:center;justify-content:flex-end;gap:6px;padding:10px 12px;border-top:1px solid #e1e4f7;background:#fff}.lesson-ai-candidate-card button{min-height:32px;display:flex;align-items:center;justify-content:center;gap:5px;padding:0 9px;border:1px solid transparent;border-radius:7px;color:#596579;background:transparent;font-size:10.5px;font-weight:700;cursor:pointer}.lesson-ai-candidate-card button:hover:not(:disabled){background:#f3f5f8}.lesson-ai-candidate-card button.primary{border-color:#514bdc;color:#fff;background:#514bdc;box-shadow:none}.lesson-ai-candidate-card button.primary:hover:not(:disabled){background:#4338ca}.lesson-ai-candidate-card button:disabled{opacity:.5;cursor:not-allowed}.lesson-ai-candidate-card button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-working-state{display:grid;gap:3px;padding-top:1px}.lesson-ai-working-state strong{color:#373b71;font-size:11.5px}.lesson-ai-working-state span{color:#758096;font-size:10.5px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.lesson-ai-composer-shell{display:grid;gap:9px;padding:12px 14px 14px;border-top:1px solid #e4e9f1;background:#fbfcfe}.lesson-ai-quick-prompts{display:flex;gap:6px;overflow:auto;padding-bottom:1px}.lesson-ai-quick-prompts button{flex:none;min-height:30px;padding:0 9px;border:1px solid #d9def0;border-radius:8px;color:#4f4a8d;background:#fff;font-size:10.5px;cursor:pointer}.lesson-ai-quick-prompts button:hover:not(:disabled){border-color:#aeb4ed;background:#f6f5ff}.lesson-ai-composer{position:relative}.lesson-ai-composer textarea{width:100%;min-height:72px;box-sizing:border-box;padding:10px 43px 10px 11px;border:1px solid #cbd4e1;border-radius:11px;outline:0;color:#263147;background:#fff;font:inherit;font-size:12px;line-height:1.55;resize:none}.lesson-ai-composer textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}.lesson-ai-composer>button{position:absolute;right:8px;bottom:8px;width:31px;height:31px;display:grid;place-items:center;padding:0;border:0;border-radius:8px;color:#fff;background:#514bdc;cursor:pointer}.lesson-ai-composer>button:disabled{color:#a3abc0;background:#e6e9f0;cursor:not-allowed}.lesson-ai-composer>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.lesson-ai-composer-shell>small{color:#8791a2;font-size:9.5px;line-height:1.45}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
