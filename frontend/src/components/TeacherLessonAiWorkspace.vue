<template>
  <aside class="lesson-ai-workspace" :data-phase="phase" :aria-label="tr('title')">
    <header v-if="!embedded" class="lesson-ai-header">
      <div class="lesson-ai-title">
        <span class="lesson-ai-brand"><Sparkles :size="16" /></span>
        <div>
          <strong>{{ tr('title') }}</strong>
          <span :data-phase="phase"><i />{{ phaseLabel }}</span>
        </div>
      </div>
      <button type="button" :title="tr('close')" :aria-label="tr('close')" @click="emit('close')">
        <X :size="17" />
      </button>
    </header>

    <section class="lesson-ai-scope" :title="`${scopeTitle} · ${scopeDetail}`" :aria-label="tr('context')">
      <div>
        <component :is="scopeIcon" :size="15" />
        <span>
          <label v-if="scopeOptions.length > 1" class="lesson-ai-scope-select">
            <select
              :value="scopeValue"
              :aria-label="tr('context')"
              :disabled="busy || candidatePending"
              @change="changeScope"
            >
              <option v-for="option in scopeOptions" :key="option.id" :value="option.id">{{ option.label }}</option>
            </select>
            <ChevronDown :size="13" aria-hidden="true" />
          </label>
          <strong v-else>{{ scopeDetail }}</strong>
          <small>{{ scopeTitle }}</small>
        </span>
      </div>
      <button
        type="button"
        class="lesson-ai-sources"
        :class="{ active: sourcesOpen }"
        :aria-expanded="sourcesOpen"
        :title="sourceTitle"
        @click="emit('open-sources')"
      ><Paperclip :size="13" />{{ tr('sourceCount').replace('{count}', String(referenceCount)) }}</button>
    </section>

    <section v-if="selectionText" class="lesson-ai-selection" aria-live="polite">
      <div>
        <strong>{{ tr('selectionContext') }}</strong>
        <p>“{{ selectionText }}”</p>
      </div>
      <button type="button" :aria-label="tr('clearSelection')" :title="tr('clearSelection')" @click="emit('clear-selection')">
        <X :size="14" />
      </button>
    </section>

    <main ref="messageViewport" class="lesson-ai-messages" aria-live="polite">
      <section v-if="showStarter" class="lesson-ai-starter">
        <div class="lesson-ai-quick-heading">
          <strong>{{ tr('quickPrompts') }}</strong>
        </div>
        <div class="lesson-ai-quick-grid">
          <button
            v-for="action in quickActions"
            :key="action.id"
            type="button"
            :disabled="busy"
            :title="action.prompt"
            @click="submit(action.prompt)"
          >
            <component :is="quickActionIcon(action.icon)" :size="15" />
            <span>{{ action.label }}</span>
            <ChevronRight :size="13" />
          </button>
        </div>
      </section>

      <template v-for="message in messages" :key="message.id">
        <article
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
              <div class="lesson-ai-review-fields">
                <span v-for="field in candidateFields" :key="field">{{ field }}</span>
                <span v-if="!candidateFields.length">{{ candidateFieldSummary || message.text }}</span>
              </div>
              <div v-if="candidateImpacts.length" class="lesson-ai-review-impact">
                <GitBranch :size="13" />
                <span v-for="impact in candidateImpacts" :key="impact">{{ impact }}</span>
              </div>
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
          <template v-else-if="message.kind === 'course_plan'">
            <section class="lesson-ai-course-plan">
              <header>
                <GitBranch :size="15" />
                <strong>{{ tr('coursePlanReady') }}</strong>
                <span>{{ message.planStatus === 'needs_clarification' ? tr('coursePlanNeedsDetail') : tr('coursePlanReview') }}</span>
              </header>
              <p>{{ message.text }}</p>
              <div v-if="message.impacts?.length" class="lesson-ai-review-impact">
                <span v-for="impact in message.impacts" :key="impact">{{ impact }}</span>
              </div>
              <footer>
                <button class="primary" type="button" :disabled="busy" @click="emit('open-course-plan', message.planId || '')">
                  <GitBranch :size="14" />{{ tr('openCoursePlan') }}
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
      </template>

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
      <div v-if="showCompactActions" class="lesson-ai-quick-strip" :aria-label="tr('quickPrompts')">
        <button v-for="action in recommendedQuickActions" :key="action.id" type="button" :disabled="busy" @click="submit(action.prompt)">
          <component :is="quickActionIcon(action.icon)" :size="13" />{{ action.label }}
        </button>
      </div>
      <form class="lesson-ai-composer" @submit.prevent="submit(draft)">
        <textarea
          ref="composer"
          v-model="draft"
          rows="2"
          maxlength="800"
          :placeholder="composerPlaceholder"
          :aria-label="composerPlaceholder"
          :disabled="busy"
          @keydown.enter.exact.prevent="submit(draft)"
        />
        <button type="submit" :disabled="busy || !draft.trim()" :title="tr('send')" :aria-label="tr('send')">
          <LoaderCircle v-if="busy" :size="15" class="spin" />
          <SendHorizontal v-else :size="15" />
        </button>
      </form>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, type Component } from 'vue'
import {
  AlignLeft,
  ArrowDownUp,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleHelp,
  ClipboardList,
  Combine,
  FileDiff,
  FileText,
  Focus,
  Lightbulb,
  ListChecks,
  ListTree,
  GitBranch,
  LoaderCircle,
  LocateFixed,
  MessagesSquare,
  MoveRight,
  Paperclip,
  Presentation,
  Route,
  ScanSearch,
  SendHorizontal,
  Split,
  Sparkles,
  Target,
  TimerReset,
  WandSparkles,
  X,
} from 'lucide-vue-next'
import type {
  TeacherProductionAiDomain,
  TeacherProductionAiMessage,
  TeacherProductionAiPhase,
} from '../composables/useTeacherProductionAiCollaboration'
import { t } from '../shared/i18n'

export type { TeacherProductionAiMessage } from '../composables/useTeacherProductionAiCollaboration'

export type TeacherAiQuickActionIcon =
  | 'diagnose'
  | 'sequence'
  | 'path'
  | 'merge'
  | 'target'
  | 'split'
  | 'interaction'
  | 'check'
  | 'timing'
  | 'focus'
  | 'example'
  | 'voice'
  | 'compress'
  | 'question'
  | 'transition'

export interface TeacherAiQuickAction {
  id: string
  label: string
  prompt: string
  icon: TeacherAiQuickActionIcon
}

export interface TeacherAiScopeOption {
  id: string
  label: string
}

const props = withDefaults(defineProps<{
  domain?: TeacherProductionAiDomain
  scopeTitle: string
  scopeDetail: string
  scopeOptions?: TeacherAiScopeOption[]
  scopeValue?: string
  referenceCount?: number
  referenceLabels?: string[]
  sourcesOpen?: boolean
  messages: TeacherProductionAiMessage[]
  phase?: TeacherProductionAiPhase
  busy?: boolean
  candidatePending?: boolean
  candidateFields?: string[]
  candidateImpacts?: string[]
  clarificationOptions?: string[]
  quickActions?: TeacherAiQuickAction[]
  placeholder?: string
  canRetry?: boolean
  embedded?: boolean
  selectionText?: string
}>(), {
  domain: 'lesson',
  referenceCount: 0,
  referenceLabels: () => [],
  scopeOptions: () => [],
  scopeValue: '',
  sourcesOpen: false,
  phase: 'ready',
  busy: false,
  candidatePending: false,
  candidateFields: () => [],
  candidateImpacts: () => [],
  clarificationOptions: () => [],
  quickActions: () => [],
  placeholder: '',
  canRetry: false,
  embedded: false,
  selectionText: '',
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'change-scope', value: string): void
  (event: 'open-sources'): void
  (event: 'send', value: string): void
  (event: 'clarify', value: string): void
  (event: 'retry'): void
  (event: 'accept'): void
  (event: 'reject'): void
  (event: 'focus-candidate'): void
  (event: 'clear-selection'): void
  (event: 'open-course-plan', planId: string): void
}>()

const fallbackMessages: Record<string, string> = {
  title: 'AI 助手',
  close: '退出 AI 编辑模式',
  context: '当前编辑范围',
  sources: '资料范围',
  sourceCount: '{count} 份资料',
  candidateReady: '修改候选',
  coursePlanReady: '整课修改方案',
  coursePlanReview: '尚未应用',
  coursePlanNeedsDetail: '需要补充',
  openCoursePlan: '查看并确认',
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
  starterTitle: '从哪里开始修改？',
  starterHint: '选择一项常用操作，或直接描述你想要的结果。',
  quickPrompts: '快捷修改',
  quickHint: '点击后生成可审阅候选',
  composerLabel: '描述修改要求',
  placeholder: '告诉我具体想改什么…',
  send: '发送',
  composerHint: 'Enter 发送，Shift + Enter 换行',
  followUpHint: '继续补充会替换当前候选，正式内容保持不变。',
  selectionContext: '已选内容',
  clearSelection: '取消选区',
  selectionPlaceholder: '告诉 AI 如何修改这段内容…',
}

function tr(key: string): string {
  return t(`courseWorkbench.aiCollaboration.${key}`, fallbackMessages[key] || key)
}

const draft = ref('')
const composer = ref<HTMLTextAreaElement | null>(null)
const messageViewport = ref<HTMLElement | null>(null)
const showStarter = computed(() => props.phase === 'ready' && !props.messages.some(message => message.role === 'user'))
const showCompactActions = computed(() => !showStarter.value
  && !props.candidatePending
  && !props.busy
  && ['ready', 'success'].includes(props.phase)
  && props.quickActions.length > 0)
const latestCandidateMessageId = computed(() => [...props.messages].reverse().find(message => message.kind === 'candidate')?.id || '')
const latestErrorMessageId = computed(() => [...props.messages].reverse().find(message => message.kind === 'error')?.id || '')
const recommendedQuickActions = computed(() => props.quickActions.slice(0, 3))
const scopeIcon = computed<Component>(() => {
  if (props.domain === 'outline') return ListTree
  if (props.domain === 'question-bank') return ListChecks
  if (props.domain === 'script') return FileText
  if (props.domain === 'ppt') return Presentation
  return ClipboardList
})
const sourceTitle = computed(() => props.referenceLabels.length
  ? props.referenceLabels.join('\n')
  : tr('sources'))
const candidateFieldSummary = computed(() => props.candidateFields.length
  ? tr('changedFields').replace('{fields}', props.candidateFields.join('、'))
  : tr('noChangedFields'))
const phaseLabel = computed(() => tr(`status${props.phase[0]!.toUpperCase()}${props.phase.slice(1)}`))
const composerPlaceholder = computed(() => props.selectionText
  ? tr('selectionPlaceholder')
  : props.placeholder || tr('placeholder'))
const workingLabel = computed(() => {
  if (props.phase === 'accepting') {
    if (props.domain === 'outline') return '正在应用大纲修订…'
    if (props.domain === 'question-bank') return '正在创建题库任务…'
    if (props.domain === 'script') return '正在形成新的讲稿修订…'
    if (props.domain === 'ppt') return '正在形成新的 PPT 修订…'
    return tr('workingAccepting')
  }
  if (props.phase === 'rejecting') return tr('workingRejecting')
  if (props.domain === 'outline') return '正在生成大纲调整候选…'
  if (props.domain === 'question-bank') return '正在组织题库任务候选…'
  if (props.domain === 'script') return '正在生成讲稿表达候选…'
  if (props.domain === 'ppt') return '正在生成 PPT 页面候选…'
  return tr('workingGenerating')
})

const quickActionIcons: Record<TeacherAiQuickActionIcon, Component> = {
  diagnose: ScanSearch,
  sequence: ArrowDownUp,
  path: Route,
  merge: Combine,
  target: Target,
  split: Split,
  interaction: MessagesSquare,
  check: ListChecks,
  timing: TimerReset,
  focus: Focus,
  example: Lightbulb,
  voice: WandSparkles,
  compress: AlignLeft,
  question: CircleHelp,
  transition: MoveRight,
}

function quickActionIcon(icon: TeacherAiQuickActionIcon): Component {
  return quickActionIcons[icon] || ListTree
}

function submit(value: string) {
  const instruction = value.trim()
  if (!instruction || props.busy) return
  draft.value = ''
  emit('send', instruction)
}

function changeScope(event: Event) {
  emit('change-scope', (event.target as HTMLSelectElement).value)
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
.lesson-ai-workspace{height:100%;min-width:0;display:flex;flex-direction:column;overflow:hidden;color:#263147;background:#fff}
.lesson-ai-header{min-height:54px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px 0 16px;border-bottom:1px solid #e8ecf2}.lesson-ai-title{min-width:0;display:flex;align-items:center;gap:9px}.lesson-ai-brand{width:28px;height:28px;display:grid;place-items:center;border-radius:8px;color:#4f46e5;background:#f0f1ff}.lesson-ai-title>div{display:flex;align-items:baseline;gap:8px}.lesson-ai-title strong{color:#202a3d;font-size:13.5px}.lesson-ai-title>div>span{display:flex;align-items:center;gap:5px;color:#718096;font-size:10px;font-weight:650}.lesson-ai-title>div>span i{width:5px;height:5px;border-radius:50%;background:#94a3b8}.lesson-ai-title>div>span[data-phase="generating"] i,.lesson-ai-title>div>span[data-phase="accepting"] i,.lesson-ai-title>div>span[data-phase="rejecting"] i{background:#6366f1}.lesson-ai-title>div>span[data-phase="review"] i{background:#8b5cf6}.lesson-ai-title>div>span[data-phase="success"] i{background:#16a34a}.lesson-ai-title>div>span[data-phase="error"] i{background:#dc2626}.lesson-ai-header>button{width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.lesson-ai-header>button:hover{color:#334155;background:#f3f5f8}.lesson-ai-header>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-scope{min-width:0;min-height:56px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 12px 8px 16px;border-bottom:1px solid #e9edf3;background:#fbfcfe}.lesson-ai-scope>div{min-width:0;display:flex;align-items:center;gap:9px}.lesson-ai-scope>div>svg{flex:none;color:#6366f1}.lesson-ai-scope>div>span{min-width:0;display:grid;gap:1px}.lesson-ai-scope strong,.lesson-ai-scope>div small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lesson-ai-scope strong{color:#344158;font-size:11.5px}.lesson-ai-scope>div small{color:#7b8799;font-size:10px}.lesson-ai-scope-select{position:relative;min-width:0;display:flex;align-items:center}.lesson-ai-scope-select select{min-width:0;max-width:260px;height:24px;padding:0 22px 0 0;border:0;outline:0;color:#344158;background:transparent;font:inherit;font-size:11.5px;font-weight:700;text-overflow:ellipsis;cursor:pointer;appearance:none}.lesson-ai-scope-select>svg{position:absolute;right:2px;color:#8792a3;pointer-events:none}.lesson-ai-scope-select select:hover{color:#4338ca}.lesson-ai-scope-select select:focus-visible{border-radius:4px;box-shadow:0 0 0 2px rgba(91,87,232,.2)}.lesson-ai-scope-select select:disabled{color:#718096;cursor:not-allowed}.lesson-ai-sources{flex:none;min-height:30px;display:flex;align-items:center;gap:5px;padding:0 8px;border:1px solid transparent;border-radius:7px;color:#697589;background:transparent;font:inherit;font-size:9.5px;font-weight:650;cursor:pointer}.lesson-ai-sources:hover,.lesson-ai-sources.active{border-color:#d9dcf7;color:#4338ca;background:#f3f3ff}.lesson-ai-sources:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-selection{display:grid;grid-template-columns:minmax(0,1fr) 28px;align-items:start;gap:8px;padding:10px 12px 10px 16px;border-bottom:1px solid #e7eaf4;background:#f8f8ff}.lesson-ai-selection>div{min-width:0;display:grid;gap:3px}.lesson-ai-selection strong{color:#4f4b92;font-size:10px}.lesson-ai-selection p{display:-webkit-box;overflow:hidden;margin:0;color:#5f697b;font-size:11px;line-height:1.5;-webkit-box-orient:vertical;-webkit-line-clamp:3}.lesson-ai-selection button{width:28px;height:28px;display:grid;place-items:center;padding:0;border:0;border-radius:7px;color:#7b8495;background:transparent;cursor:pointer}.lesson-ai-selection button:hover{color:#4338ca;background:#ececff}.lesson-ai-selection button:focus-visible{outline:2px solid #6366f1;outline-offset:2px}.lesson-ai-messages{flex:1}
.lesson-ai-messages{min-height:0;overflow:auto;padding:18px 16px 28px;scrollbar-width:thin;scrollbar-color:transparent transparent}.lesson-ai-messages:hover{scrollbar-color:#cbd3df transparent}.lesson-ai-messages::-webkit-scrollbar{width:6px}.lesson-ai-messages::-webkit-scrollbar-thumb{border-radius:6px;background:transparent}.lesson-ai-messages:hover::-webkit-scrollbar-thumb{background:#cbd3df}.lesson-ai-message{margin:0 0 15px}.lesson-ai-message.is-user{display:flex;justify-content:flex-end}.lesson-ai-user-bubble{max-width:84%;padding:8px 10px;border-radius:11px 11px 3px 11px;color:#fff;background:#514bdc;font-size:12px;line-height:1.55;overflow-wrap:anywhere}.lesson-ai-assistant-line{display:grid;grid-template-columns:15px minmax(0,1fr) auto;align-items:start;gap:7px;color:#6366f1}.lesson-ai-assistant-line p{margin:0;color:#4c596d;font-size:12px;line-height:1.65;overflow-wrap:anywhere}.lesson-ai-assistant-line.is-receipt{color:#16925f}.lesson-ai-assistant-line.is-receipt p{color:#29765a}.lesson-ai-assistant-line.is-error{color:#c2414f}.lesson-ai-assistant-line.is-error p{color:#9f3c48}.lesson-ai-assistant-line>button{min-height:26px;padding:0 8px;border:1px solid #e0b5bb;border-radius:6px;color:#9f3c48;background:#fff;font-size:10px;font-weight:700;cursor:pointer}
.lesson-ai-starter{display:grid;gap:10px;max-width:560px;margin:0 auto}.lesson-ai-quick-heading{display:flex;align-items:center;min-height:26px}.lesson-ai-quick-heading strong{color:#536176;font-size:10.5px}.lesson-ai-quick-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.lesson-ai-quick-grid button{min-width:0;min-height:42px;display:grid;grid-template-columns:18px minmax(0,1fr) 14px;align-items:center;gap:7px;padding:0 10px;border:1px solid #e1e6ee;border-radius:9px;color:#536176;background:#fff;text-align:left;font:inherit;font-size:10.5px;font-weight:650;cursor:pointer}.lesson-ai-quick-grid button>svg:first-child{color:#625dd7}.lesson-ai-quick-grid button>svg:last-child{color:#a0a9b8}.lesson-ai-quick-grid button:hover:not(:disabled){border-color:#c7c9ef;color:#383379;background:#f8f8ff}.lesson-ai-quick-grid button:hover>svg:last-child{color:#625dd7}.lesson-ai-quick-grid button:disabled{opacity:.48;cursor:not-allowed}.lesson-ai-quick-grid button:focus-visible,.lesson-ai-quick-strip button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-review{border-top:1px solid #dfe2f4;border-bottom:1px solid #dfe2f4;background:#fbfbff}.lesson-ai-review>header{min-height:40px;display:flex;align-items:center;gap:7px;color:#514bdc}.lesson-ai-review>header strong{color:#353567;font-size:12px}.lesson-ai-review>header span{margin-inline-start:auto;color:#7772a8;font-size:10px;font-weight:700}.lesson-ai-review-fields{display:flex;flex-wrap:wrap;gap:5px;padding:0 0 12px}.lesson-ai-review-fields span{min-height:24px;display:inline-flex;align-items:center;padding:0 7px;border-radius:6px;color:#5b5790;background:#f0f0fb;font-size:10px;font-weight:650}.lesson-ai-review-impact{display:flex;flex-wrap:wrap;align-items:center;gap:5px;padding:0 0 10px;color:#8a5b17}.lesson-ai-review-impact span{padding:3px 6px;border-radius:5px;background:#fff7df;font-size:10px;font-weight:700}.lesson-ai-review>footer{display:flex;align-items:center;justify-content:flex-end;gap:5px;padding:9px 0;border-top:1px solid #ececf6}.lesson-ai-review button{min-height:30px;display:flex;align-items:center;justify-content:center;gap:5px;padding:0 9px;border:1px solid transparent;border-radius:7px;color:#596579;background:transparent;font-size:10.5px;font-weight:700;cursor:pointer}.lesson-ai-review button:hover:not(:disabled){background:#f1f3f7}.lesson-ai-review button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.lesson-ai-review button:disabled{opacity:.5;cursor:not-allowed}.lesson-ai-review button:focus-visible,.lesson-ai-clarification button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-course-plan{display:grid;gap:10px;padding:12px;border:1px solid #dddff2;border-radius:10px;background:#fbfbff}.lesson-ai-course-plan>header{display:flex;align-items:center;gap:7px;color:#514bdc}.lesson-ai-course-plan>header strong{color:#353567;font-size:12px}.lesson-ai-course-plan>header span{margin-inline-start:auto;color:#7772a8;font-size:10px;font-weight:700}.lesson-ai-course-plan>p{margin:0;color:#4c596d;font-size:11.5px;line-height:1.65}.lesson-ai-course-plan>.lesson-ai-review-impact{padding:0}.lesson-ai-course-plan>footer{display:flex;justify-content:flex-end;padding-top:8px;border-top:1px solid #ececf6}.lesson-ai-course-plan button{min-height:31px;display:flex;align-items:center;gap:5px;padding:0 10px;border:1px solid #514bdc;border-radius:7px;color:#fff;background:#514bdc;font-size:10.5px;font-weight:700;cursor:pointer}.lesson-ai-course-plan button:disabled{opacity:.5;cursor:not-allowed}.lesson-ai-course-plan button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-clarification{display:flex;flex-wrap:wrap;gap:6px;margin:-3px 0 17px;padding-inline-start:22px}.lesson-ai-clarification button{min-height:29px;padding:0 9px;border:1px solid #d9def0;border-radius:7px;color:#4f4a8d;background:#fff;font-size:10.5px;cursor:pointer}.lesson-ai-clarification button:hover{border-color:#b9bced;background:#f7f7ff}.lesson-ai-working-state{display:flex;align-items:center;gap:7px;color:#65649c;font-size:11px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.lesson-ai-composer-shell{display:grid;gap:7px;padding:10px 12px 12px;border-top:1px solid #e4e9f1;background:#fbfcfe}.lesson-ai-quick-strip{display:flex;gap:6px;overflow:auto;padding-bottom:1px}.lesson-ai-quick-strip button{flex:none;min-height:28px;display:flex;align-items:center;gap:5px;padding:0 8px;border:1px solid #dce1ec;border-radius:7px;color:#55517e;background:#fff;font:inherit;font-size:9.5px;cursor:pointer}.lesson-ai-quick-strip button:hover:not(:disabled){border-color:#c7c9ef;background:#f8f8ff}.lesson-ai-composer{position:relative}.lesson-ai-composer textarea{width:100%;min-height:64px;max-height:132px;box-sizing:border-box;padding:10px 42px 10px 11px;border:1px solid #cbd4e1;border-radius:10px;outline:0;color:#263147;background:#fff;font:inherit;font-size:11.5px;line-height:1.5;resize:none}.lesson-ai-composer textarea::placeholder{color:#6f7c90}.lesson-ai-composer textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.09)}.lesson-ai-composer>button{position:absolute;right:7px;bottom:7px;width:31px;height:31px;display:grid;place-items:center;padding:0;border:0;border-radius:8px;color:#fff;background:#514bdc;cursor:pointer}.lesson-ai-composer>button:disabled{color:#8e98aa;background:#e4e7ee;cursor:not-allowed}.lesson-ai-composer>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.lesson-ai-scope-select{width:100%}.lesson-ai-scope-select select{width:100%}
@media(max-width:430px){.lesson-ai-quick-grid{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
