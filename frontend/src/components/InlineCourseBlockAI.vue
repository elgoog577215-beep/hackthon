<template>
  <div
    ref="root"
    class="inline-course-block-ai"
    :class="{ 'has-result': resultVisible }"
    :data-block-id="block.block_id"
    @keydown.esc="closeMenu(true)"
  >
    <button
      ref="handleButton"
      type="button"
      class="block-ai-handle"
      :class="{ active }"
      :title="t('courseWorkspace.inlineAi.open', '打开此内容块的 AI 助手')"
      :aria-label="t('courseWorkspace.inlineAi.open', '打开此内容块的 AI 助手')"
      :aria-expanded="active"
      @click="toggleMenu"
    >
      <Sparkles :size="16" />
    </button>

    <div
      ref="menu"
      class="block-ai-menu"
      :class="{ 'is-active': active }"
      role="menu"
      :aria-label="t('courseWorkspace.inlineAi.menu', '内容块 AI 操作')"
      @keydown="handleMenuKeydown"
    >
      <button
        v-for="action in actions"
        :key="action.key"
        type="button"
        role="menuitem"
        :disabled="aiStore.loading"
        @click="chooseAction(action.key)"
      >
        <component :is="action.icon" :size="15" />
        <span>{{ action.label }}</span>
      </button>
    </div>

    <section v-if="resultVisible" ref="resultRegion" class="inline-ai-result" aria-live="polite" :aria-busy="isCurrentMessageLoading">
      <header class="inline-ai-result__header">
        <span class="inline-ai-result__mark"><Sparkles :size="15" /></span>
        <div>
          <small>
            {{ t('courseWorkspace.inlineAi.temporary', '临时个人内容') }}
            <span aria-hidden="true"> · </span>
            {{ t('courseWorkspace.inlineAi.source', '来源：') }}{{ sourceLabel }}
          </small>
          <strong>{{ resultTitle }}</strong>
        </div>
      </header>

      <div v-if="isCurrentMessageLoading && !assistantMessage?.content" class="inline-ai-result__loading">
        <span></span><span></span><span></span>
        <small>{{ t('courseWorkspace.inlineAi.thinking', '正在结合当前内容块思考') }}</small>
      </div>
      <MarkdownRenderer
        v-else-if="assistantMessage?.content"
        class="inline-ai-result__content"
        :class="{ failed: assistantMessage.status === 'failed' }"
        :content="assistantMessage.content"
      />
      <p v-else-if="activeAction === 'ask' && !composerOpen" class="inline-ai-result__empty">
        {{ t('courseWorkspace.inlineAi.askHint', '围绕这一个内容块提出你的问题。') }}
      </p>

      <div v-if="canCollectFeedback" class="inline-ai-feedback" :aria-busy="feedbackState === 'saving'">
        <span>{{ t('courseWorkspace.inlineAi.feedbackPrompt', '这次回答解决你的问题了吗？') }}</span>
        <div>
          <button
            type="button"
            :class="{ active: answerFeedback === 'resolved' }"
            :disabled="feedbackState === 'saving' || feedbackState === 'saved'"
            @click="submitFeedback('resolved')"
          >
            <CheckCircle2 :size="14" />
            {{ t('courseWorkspace.inlineAi.feedbackResolved', '已解决') }}
          </button>
          <button
            type="button"
            :class="{ active: answerFeedback === 'unclear' }"
            :disabled="feedbackState === 'saving' || feedbackState === 'saved'"
            @click="submitFeedback('unclear')"
          >
            <CircleHelp :size="14" />
            {{ t('courseWorkspace.inlineAi.feedbackUnclear', '还不清楚') }}
          </button>
        </div>
      </div>
      <p v-if="feedbackState === 'failed'" class="inline-ai-result__feedback-error">
        {{ t('courseWorkspace.inlineAi.feedbackFailed', '反馈暂时未记录，请重试。') }}
      </p>

      <form v-if="composerOpen" class="inline-ai-composer" @submit.prevent="submitFollowUp">
        <textarea
          ref="composer"
          v-model="question"
          rows="2"
          :placeholder="t('courseWorkspace.inlineAi.placeholder', '继续问这个内容块…')"
          :aria-label="t('courseWorkspace.inlineAi.placeholder', '继续问这个内容块…')"
          :disabled="aiStore.loading"
          @keydown.enter.exact.prevent="submitFollowUp"
          @keydown.esc.stop.prevent="cancelComposer"
        ></textarea>
        <button
          type="button"
          class="cancel-composer-action"
          :title="t('courseWorkspace.inlineAi.cancelQuestion', '取消本次追问')"
          :aria-label="t('courseWorkspace.inlineAi.cancelQuestion', '取消本次追问')"
          @click="cancelComposer"
        >
          <X :size="15" />
        </button>
        <button
          type="submit"
          :disabled="!question.trim() || aiStore.loading"
          :title="t('courseWorkspace.inlineAi.send', '发送问题')"
          :aria-label="t('courseWorkspace.inlineAi.send', '发送问题')"
        >
          <SendHorizontal :size="16" />
        </button>
      </form>

      <footer v-if="assistantMessage && !composerOpen" class="inline-ai-result__actions">
        <button v-if="assistantMessage.content" type="button" :disabled="isCurrentMessageLoading" @click="openFollowUp">
          <MessageCircleMore :size="14" />
          {{ t('courseWorkspace.inlineAi.followUp', '继续追问') }}
        </button>
        <button v-if="assistantMessage.content" type="button" :disabled="saveState === 'saving' || saveState === 'saved' || assistantMessage.status !== 'complete'" @click="saveAsPersonalContent">
          <LoaderCircle v-if="saveState === 'saving'" class="spin" :size="14" />
          <Check v-else-if="saveState === 'saved'" :size="14" />
          <BookmarkPlus v-else :size="14" />
          {{ saveLabel }}
        </button>
        <button type="button" class="remove-action" :class="{ 'is-stop': isCurrentMessageLoading }" @click="removeResult">
          <CircleStop v-if="isCurrentMessageLoading" :size="14" />
          <Trash2 v-else :size="14" />
          {{ removeLabel }}
        </button>
      </footer>
      <p v-if="saveState === 'failed'" class="inline-ai-result__save-error">
        {{ t('courseWorkspace.inlineAi.saveFailed', '暂时无法保留，请稍后重试。') }}
      </p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  AlignLeft,
  BookmarkPlus,
  Check,
  CheckCircle2,
  CircleHelp,
  CircleStop,
  Lightbulb,
  LoaderCircle,
  MessageCircleMore,
  MessageSquareText,
  SendHorizontal,
  Sparkles,
  Trash2,
  X,
} from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useAITeacherStore, type AIAnswerFeedback, type AIMessage } from '../stores/aiTeacher'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import type { ContentBlock, Node as CourseNode } from '../stores/types'
import { t } from '../shared/i18n'

type InlineAIAction = 'explain' | 'example' | 'simplify' | 'ask'
type SaveState = 'idle' | 'saving' | 'saved' | 'failed'
type FeedbackState = 'idle' | 'saving' | 'saved' | 'failed'

const props = withDefaults(defineProps<{
  node: CourseNode
  block: ContentBlock
  active?: boolean
}>(), { active: false })
const emit = defineEmits<{
  activate: [blockId: string]
}>()

const aiStore = useAITeacherStore()
const courseStore = useCourseStore()
const noteStore = useNoteStore()
const root = ref<HTMLElement | null>(null)
const handleButton = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const resultRegion = ref<HTMLElement | null>(null)
const activeAction = ref<InlineAIAction | null>(null)
const assistantMessage = ref<AIMessage | null>(null)
const resultVisible = ref(false)
const composerOpen = ref(false)
const composer = ref<HTMLTextAreaElement | null>(null)
const question = ref('')
const saveState = ref<SaveState>('idle')
const answerFeedback = ref<AIAnswerFeedback | null>(null)
const feedbackState = ref<FeedbackState>('idle')

const actions = computed(() => [
  { key: 'explain' as const, icon: MessageSquareText, label: t('courseWorkspace.inlineAi.explain', '解释') },
  { key: 'example' as const, icon: Lightbulb, label: t('courseWorkspace.inlineAi.example', '举例') },
  { key: 'simplify' as const, icon: AlignLeft, label: t('courseWorkspace.inlineAi.simplify', '简化') },
  { key: 'ask' as const, icon: CircleHelp, label: t('courseWorkspace.inlineAi.ask', '提问') },
])
const actionLabel = computed(() => actions.value.find(item => item.key === activeAction.value)?.label || t('courseWorkspace.inlineAi.ask', '提问'))
const resultTitle = computed(() => `${t('courseWorkspace.inlineAi.aiPrefix', 'AI')} · ${actionLabel.value}`)
const isCurrentMessageLoading = computed(() => assistantMessage.value?.status === 'streaming')
const saveLabel = computed(() => {
  if (saveState.value === 'saving') return t('courseWorkspace.inlineAi.saving', '正在保留')
  if (saveState.value === 'saved') return t('courseWorkspace.inlineAi.saved', '已保留到个人内容')
  return t('courseWorkspace.inlineAi.save', '保留为个人内容')
})
const removeLabel = computed(() => isCurrentMessageLoading.value
  ? t('courseWorkspace.inlineAi.stop', '停止生成')
  : t('courseWorkspace.inlineAi.remove', '移除'))
const sourceText = computed(() => [props.block.title, props.block.content].filter(Boolean).join('\n\n'))
const sourceLabel = computed(() => props.block.title || props.node.node_name)
const canCollectFeedback = computed(() => Boolean(
  assistantMessage.value?.content
  && assistantMessage.value.status === 'complete'
  && !composerOpen.value,
))

watch(() => props.active, async active => {
  document.removeEventListener('pointerdown', handleOutsidePointerDown)
  if (!active) return
  document.addEventListener('pointerdown', handleOutsidePointerDown)
  await nextTick()
  focusMenuItem(0)
}, { immediate: true })

onBeforeUnmount(() => document.removeEventListener('pointerdown', handleOutsidePointerDown))

function toggleMenu() {
  emit('activate', props.active ? '' : props.block.block_id)
}

function closeMenu(restoreFocus = false) {
  if (props.active) emit('activate', '')
  if (restoreFocus) nextTick(() => handleButton.value?.focus())
}

function handleOutsidePointerDown(event: PointerEvent) {
  if (!props.active || root.value?.contains(event.target as Node)) return
  closeMenu()
}

function menuButtons() {
  return Array.from(menu.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || [])
}

function focusMenuItem(index: number) {
  const buttons = menuButtons()
  if (!buttons.length) return
  buttons[(index + buttons.length) % buttons.length]?.focus()
}

function handleMenuKeydown(event: KeyboardEvent) {
  const buttons = menuButtons()
  const currentIndex = buttons.indexOf(document.activeElement as HTMLButtonElement)
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    focusMenuItem(currentIndex + 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    focusMenuItem(currentIndex - 1)
  } else if (event.key === 'Home') {
    event.preventDefault()
    focusMenuItem(0)
  } else if (event.key === 'End') {
    event.preventDefault()
    focusMenuItem(buttons.length - 1)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeMenu(true)
  }
}

async function chooseAction(action: InlineAIAction) {
  activeAction.value = action
  resultVisible.value = true
  assistantMessage.value = null
  saveState.value = 'idle'
  answerFeedback.value = null
  feedbackState.value = 'idle'
  question.value = ''
  closeMenu()
  if (action === 'ask') {
    composerOpen.value = true
    await focusComposer()
    return
  }
  composerOpen.value = false
  await sendQuestion(actionPrompt(action))
}

function actionPrompt(action: Exclude<InlineAIAction, 'ask'>) {
  return ({
    explain: t('courseWorkspace.inlineAi.explainPrompt', '请只基于当前课程内容块，用更容易理解的方式解释它。'),
    example: t('courseWorkspace.inlineAi.examplePrompt', '请为当前课程内容块给出一个具体、可检验的例子。'),
    simplify: t('courseWorkspace.inlineAi.simplifyPrompt', '请在不改变原意的前提下，用更简洁的方式说明当前课程内容块。'),
  })[action]
}

function contextRef() {
  return {
    course_id: courseStore.currentCourseId,
    course_version_id: courseStore.currentCourseVersionId,
    node_id: props.node.node_id,
    node_name: props.node.node_name,
    objective_id: props.node.objective_id || '',
    objective_revision_id: props.node.objective_revision_id || '',
    content_anchor: {
      block_id: props.block.block_id,
      block_revision_id: props.block.block_revision_id || '',
      block_type: props.block.type,
    },
  }
}

async function sendQuestion(prompt: string) {
  if (!prompt.trim() || !courseStore.currentCourseId || aiStore.loading) return
  saveState.value = 'idle'
  answerFeedback.value = null
  feedbackState.value = 'idle'
  await aiStore.sendMessage({
    courseId: courseStore.currentCourseId,
    courseVersionId: courseStore.currentCourseVersionId,
    nodeId: props.node.node_id,
    nodeName: props.node.node_name,
    question: prompt,
    selection: sourceText.value,
    entrypoint: 'block',
    contextRef: contextRef(),
    onAssistantMessage: message => { assistantMessage.value = message },
  })
}

async function submitFeedback(feedback: AIAnswerFeedback) {
  const message = assistantMessage.value
  if (!message || message.status !== 'complete' || !activeAction.value || feedbackState.value === 'saving' || feedbackState.value === 'saved') return
  answerFeedback.value = feedback
  feedbackState.value = 'saving'
  const target = contextRef()
  try {
    await aiStore.submitAnswerFeedback(message, feedback, {
      nodeId: props.node.node_id,
      nodeName: props.node.node_name,
      action: activeAction.value,
      contentAnchor: target.content_anchor,
    })
    feedbackState.value = 'saved'
  } catch {
    feedbackState.value = 'failed'
  }
}

async function submitFollowUp() {
  const prompt = question.value.trim()
  if (!prompt || aiStore.loading) return
  question.value = ''
  composerOpen.value = false
  activeAction.value = activeAction.value || 'ask'
  await sendQuestion(prompt)
}

async function openFollowUp() {
  composerOpen.value = true
  await focusComposer()
}

async function focusComposer() {
  await nextTick()
  composer.value?.focus()
}

async function cancelComposer() {
  question.value = ''
  if (!assistantMessage.value?.content) {
    removeResult()
    return
  }
  composerOpen.value = false
  await nextTick()
  resultRegion.value?.querySelector<HTMLButtonElement>('.inline-ai-result__actions button')?.focus()
}

async function saveAsPersonalContent() {
  const message = assistantMessage.value
  if (!message || message.status !== 'complete' || saveState.value === 'saving' || saveState.value === 'saved') return
  saveState.value = 'saving'
  const target = contextRef()
  try {
    const proposal = await aiStore.proposeForMessage(message, 'create_note', {
      node_id: props.node.node_id,
      title: `${actionLabel.value} · ${props.block.title || props.node.node_name}`.slice(0, 80),
      content: message.content,
      quote: sourceText.value.slice(0, 500),
      anchor: target.content_anchor,
      metadata: {
        ai_conversation_id: aiStore.currentConversationId,
        ai_message_ids: [message.message_id],
        record_subtype: 'assistant_saved_note',
        inline_ai_action: activeAction.value,
      },
    }, target)
    const receipt = await aiStore.confirmProposal(message, proposal)
    if (receipt?.status !== 'succeeded') throw new Error('save_failed')
    await noteStore.loadCourseRecords(courseStore.currentCourseId)
    saveState.value = 'saved'
  } catch {
    saveState.value = 'failed'
  }
}

function removeResult() {
  if (isCurrentMessageLoading.value) aiStore.cancel()
  resultVisible.value = false
  composerOpen.value = false
  assistantMessage.value = null
  activeAction.value = null
  question.value = ''
  saveState.value = 'idle'
  answerFeedback.value = null
  feedbackState.value = 'idle'
  closeMenu()
}
</script>

<style scoped>
.inline-course-block-ai { position:static; min-width:0; }
.inline-course-block-ai.has-result { margin-top:18px; }
.block-ai-handle { position:absolute; top:-3px; left:-46px; z-index:4; width:32px; height:32px; display:grid; place-items:center; border:1px solid rgba(199,210,254,.78); border-radius:10px; color:#7c83a5; background:rgba(255,255,255,.94); box-shadow:0 5px 14px rgba(79,70,229,.08); opacity:.38; cursor:pointer; transition:opacity .16s ease,transform .16s ease,color .16s ease,border-color .16s ease,background .16s ease,box-shadow .16s ease; }
.block-ai-handle:hover,.block-ai-handle:focus-visible,.block-ai-handle.active,:global(.course-content-block:hover .block-ai-handle) { opacity:1; transform:translateY(-1px); border-color:#a5b4fc; color:var(--lz-brand-strong); background:#f5f3ff; box-shadow:0 7px 18px rgba(79,70,229,.13); outline:none; }
.block-ai-menu { --block-ai-hover-corridor:8px; position:absolute; top:34px; left:-46px; z-index:9; width:min(164px,calc(100vw - 24px)); overflow:hidden; padding:3px; border:1px solid rgba(226,232,240,.82); border-radius:10px; background:rgba(255,255,255,.96); box-shadow:0 7px 18px rgba(15,23,42,.07),0 1px 2px rgba(15,23,42,.035); opacity:0; visibility:hidden; pointer-events:none; transform:translateY(-2px); transform-origin:top left; transition:opacity .12s ease,transform .12s ease,visibility 0s linear .12s; }
.block-ai-menu.is-active { opacity:1; visibility:visible; pointer-events:auto; transform:none; transition-delay:0s; }
.block-ai-menu button { width:100%; min-height:30px; display:grid; grid-template-columns:16px minmax(0,1fr); align-items:center; gap:5px; padding:0 6px; border:0; border-radius:7px; color:#64748b; background:transparent; text-align:left; font-size:10px; font-weight:550; cursor:pointer; transition:color .12s ease,background .12s ease; }
.block-ai-menu button span { min-width:0; overflow:hidden; line-height:1.25; text-overflow:ellipsis; white-space:nowrap; }
.block-ai-menu button:hover:not(:disabled),.block-ai-menu button:focus-visible { color:var(--lz-brand-strong); background:rgba(238,242,255,.72); outline:none; }
.block-ai-menu button:disabled { opacity:.5; cursor:not-allowed; }
.inline-ai-result { min-width:0; padding:14px 16px 12px; border-left:3px solid var(--lz-brand); border-radius:0 10px 10px 0; color:var(--lz-text); background:linear-gradient(110deg,#f4f5ff 0%,#fafaff 68%,#fff 100%); box-shadow:inset 0 0 0 1px rgba(199,210,254,.82),0 8px 22px rgba(79,70,229,.05); }
.inline-ai-result__header { display:flex; align-items:center; gap:9px; margin-bottom:10px; }
.inline-ai-result__mark { width:29px; height:29px; flex:0 0 auto; display:grid; place-items:center; border-radius:9px; color:var(--lz-brand-strong); background:#fff; box-shadow:0 3px 10px rgba(79,70,229,.08); }
.inline-ai-result__header > div { min-width:0; }
.inline-ai-result__header small { display:block; margin-bottom:1px; color:var(--lz-text-muted); font-size:9px; line-height:1.2; }
.inline-ai-result__header strong { display:block; overflow:hidden; color:var(--lz-text-strong); font-size:12px; line-height:1.4; text-overflow:ellipsis; white-space:nowrap; }
.inline-ai-result__content { min-width:0; color:var(--lz-text); font-size:13px; line-height:1.72; overflow-wrap:anywhere; }
.inline-ai-result__content.failed { color:var(--lz-danger); }
.inline-ai-feedback { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:12px; padding:9px 0 1px; border-top:1px solid rgba(199,210,254,.62); }
.inline-ai-feedback > span { color:var(--lz-text-secondary); font-size:10px; font-weight:650; }
.inline-ai-feedback > div { display:flex; align-items:center; gap:5px; }
.inline-ai-feedback button { min-height:28px; display:inline-flex; align-items:center; gap:5px; padding:0 8px; border:1px solid rgba(199,210,254,.76); border-radius:8px; color:var(--lz-text-secondary); background:rgba(255,255,255,.82); font-size:10px; cursor:pointer; }
.inline-ai-feedback button:hover:not(:disabled),.inline-ai-feedback button.active { border-color:#a5b4fc; color:var(--lz-brand-strong); background:#fff; }
.inline-ai-feedback button:disabled { cursor:default; opacity:.62; }
.inline-ai-feedback button.active:disabled { opacity:1; }
.inline-ai-result__loading { display:grid; gap:8px; padding:5px 0 6px; }
.inline-ai-result__loading span { display:block; width:100%; height:8px; border-radius:999px; background:linear-gradient(90deg,#dbe3ff,#f5f3ff,#dbe3ff); background-size:180% 100%; animation:ai-shimmer 1.3s linear infinite; }
.inline-ai-result__loading span:nth-child(1) { width:44%; }
.inline-ai-result__loading span:nth-child(2) { width:78%; }
.inline-ai-result__loading span:nth-child(3) { width:58%; }
.inline-ai-result__loading small { margin-top:2px; color:var(--lz-text-secondary); font-size:10px; font-weight:600; }
.inline-ai-result__empty { margin:0; color:var(--lz-text-muted); font-size:11px; }
.inline-ai-composer { min-width:0; display:grid; grid-template-columns:minmax(0,1fr) 30px 34px; align-items:end; gap:6px; margin-top:10px; padding:7px 7px 7px 11px; border:1px solid rgba(165,180,252,.72); border-radius:10px; background:#fff; box-shadow:0 4px 14px rgba(79,70,229,.06); }
.inline-ai-composer textarea { width:100%; min-height:40px; max-height:120px; resize:vertical; border:0; padding:3px 0; color:var(--lz-text); background:transparent; font:inherit; font-size:12px; line-height:1.5; outline:none; }
.inline-ai-composer textarea::placeholder { color:var(--lz-text-muted); }
.inline-ai-composer button { width:34px; height:34px; display:grid; place-items:center; border:0; border-radius:9px; color:#fff; background:var(--lz-brand-strong); cursor:pointer; }
.inline-ai-composer button:disabled { color:#a5b4fc; background:#eef2ff; cursor:not-allowed; }
.inline-ai-composer .cancel-composer-action { width:30px; color:var(--lz-text-muted); background:transparent; }
.inline-ai-composer .cancel-composer-action:hover,.inline-ai-composer .cancel-composer-action:focus-visible { color:var(--lz-text-strong); background:var(--lz-surface-soft); outline:none; }
.inline-ai-result__actions { display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin-top:11px; padding-top:10px; border-top:1px solid rgba(199,210,254,.62); }
.inline-ai-result__actions button { min-height:30px; display:inline-flex; align-items:center; gap:5px; padding:0 8px; border:1px solid rgba(199,210,254,.76); border-radius:8px; color:var(--lz-text-secondary); background:rgba(255,255,255,.84); font-size:10px; cursor:pointer; }
.inline-ai-result__actions button:hover:not(:disabled) { border-color:#a5b4fc; color:var(--lz-brand-strong); background:#fff; }
.inline-ai-result__actions button:disabled { opacity:.54; cursor:not-allowed; }
.inline-ai-result__actions .remove-action { margin-left:auto; border-color:transparent; color:var(--lz-text-muted); background:transparent; }
.inline-ai-result__actions .remove-action:hover { color:var(--lz-danger); background:var(--lz-danger-soft); }
.inline-ai-result__actions .remove-action.is-stop { color:var(--lz-brand-strong); }
.inline-ai-result__actions .remove-action.is-stop:hover { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.inline-ai-result__save-error { margin:8px 0 0; color:var(--lz-danger); font-size:9px; }
.inline-ai-result__feedback-error { margin:7px 0 0; color:var(--lz-danger); font-size:9px; }
.spin { animation:spin .9s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@keyframes ai-shimmer { to { background-position:-180% 0; } }
@media (hover:none) { .block-ai-handle { opacity:.72; } }
@media (min-width:1200px) and (hover:hover) and (pointer:fine) {
  .block-ai-handle,.block-ai-handle:hover,.block-ai-handle.active,:global(.course-content-block:hover .block-ai-handle) { opacity:0; pointer-events:none; transform:none; box-shadow:none; }
  .block-ai-handle:focus-visible { opacity:1; pointer-events:auto; color:var(--lz-brand-strong); border-color:#a5b4fc; background:#f5f3ff; box-shadow:0 7px 18px rgba(79,70,229,.13); }
  .block-ai-menu { top:1px; right:calc(100% + var(--block-ai-hover-corridor)); left:auto; width:104px; overflow:visible; transform-origin:top right; }
  :global(.course-node[data-level="3"] .block-ai-menu),:global(.course-node[data-level="4"] .block-ai-menu),:global(.course-node[data-level="5"] .block-ai-menu) { --block-ai-hover-corridor:var(--inline-ai-menu-offset); }
  :global(.course-content-block:hover .block-ai-menu),:global(.course-content-block:focus-within .block-ai-menu) { opacity:1; visibility:visible; pointer-events:auto; transform:none; transition-delay:0s; }
  .block-ai-menu::after { content:""; position:absolute; top:0; right:calc(-1 * var(--block-ai-hover-corridor)); width:var(--block-ai-hover-corridor); height:100%; }
}
@media (max-width:880px) {
  .block-ai-handle { top:-4px; left:auto; right:0; }
  .block-ai-menu { top:34px; left:auto; right:0; transform-origin:top right; }
  .inline-course-block-ai.has-result { margin-top:14px; }
  .inline-ai-result { padding:12px 12px 11px; }
}
@media (max-width:520px) {
  .inline-ai-feedback { align-items:flex-start; flex-direction:column; gap:7px; }
  .inline-ai-feedback > div { width:100%; }
  .inline-ai-feedback button { flex:1 1 0; justify-content:center; }
  .inline-ai-result__actions { align-items:stretch; }
  .inline-ai-result__actions button { flex:1 1 auto; justify-content:center; }
  .inline-ai-result__actions .remove-action { margin-left:0; flex:0 0 auto; }
}
</style>
