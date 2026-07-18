<template>
  <div :class="panelClasses" class="ai-teacher-panel glass-panel-elevated">
    <button
      v-if="isOverlayMode"
      type="button"
      class="ai-teacher-backdrop"
      :aria-label="t('courseWorkspace.aiTeacher.close', '关闭 AI 老师')"
      @click="emit('close')"
    />

    <section class="ai-teacher-surface" :aria-label="t('courseWorkspace.aiTeacher.title', 'AI 老师')">
      <header class="ai-teacher-header">
        <div class="ai-teacher-heading">
          <span class="ai-teacher-icon"><Sparkles :size="16" /></span>
          <div class="ai-teacher-heading-copy">
            <strong>{{ t('courseWorkspace.aiTeacher.title', 'AI 老师') }}</strong>
          </div>
        </div>
        <div class="ai-teacher-header-actions">
          <button
            v-if="!props.blockTarget"
            type="button"
            class="icon-button"
            :title="t('courseWorkspace.aiTeacher.newConversation', '新建对话')"
            @click="createConversation"
          >
            <Plus :size="17" />
          </button>
          <button
            type="button"
            class="icon-button"
            :title="t('courseWorkspace.aiTeacher.close', '关闭 AI 老师')"
            @click="emit('close')"
          >
            <X :size="18" />
          </button>
        </div>
      </header>

      <div v-if="!props.blockTarget" class="conversation-shell" :class="{ open: conversationOpen }">
        <button
          type="button"
          class="conversation-toggle"
          :aria-expanded="conversationOpen"
          :title="t('courseWorkspace.aiTeacher.manageConversations', '管理对话')"
          @click="conversationOpen = !conversationOpen"
        >
          <History :size="15" />
          <span>
            <small>{{ t('courseWorkspace.aiTeacher.conversation', '当前对话') }}</small>
            <strong>{{ currentConversationTitle }}</strong>
          </span>
          <ChevronDown :size="15" />
        </button>

        <Transition name="conversation-reveal">
          <div v-if="conversationOpen" class="conversation-drawer">
            <label class="conversation-select-wrap">
              <span class="sr-only">{{ t('courseWorkspace.aiTeacher.conversation', '对话') }}</span>
              <select v-model="selectedConversationId" class="conversation-select" @change="switchConversation">
                <option
                  v-for="conversation in aiStore.conversations"
                  :key="conversation.conversation_id"
                  :value="conversation.conversation_id"
                >
                  {{ conversation.title }}
                </option>
              </select>
              <ChevronDown :size="14" />
            </label>
            <button
              type="button"
              class="icon-button danger"
              :disabled="!aiStore.currentConversationId"
              :title="t('courseWorkspace.aiTeacher.deleteConversation', '删除当前对话')"
              @click="deleteConversation"
            >
              <Trash2 :size="15" />
            </button>
          </div>
        </Transition>
      </div>

      <div class="context-panel">
        <div class="context-line">
          <BookOpenText :size="14" />
          <span>{{ t('courseWorkspace.aiTeacher.context', '当前上下文') }}</span>
          <strong>{{ contextLabel }}</strong>
          <small
            v-if="modelEvidenceLabel"
            class="context-evidence"
            :title="t('courseWorkspace.aiTeacher.evidenceReady', '已加载学习证据')"
          >{{ modelEvidenceLabel }}</small>
        </div>
        <div v-if="props.blockTarget" class="block-target-line">
          <WandSparkles :size="14" />
          <span>{{ t('courseWorkspace.blockRegeneration.target', '改进正文块') }}</span>
          <strong>{{ blockTargetTitle }}</strong>
        </div>
        <div v-if="quoteVisible" class="context-quote">
          <Quote :size="14" />
          <p>{{ props.quoteText }}</p>
          <button
            type="button"
            :title="t('courseWorkspace.aiTeacher.clearQuote', '取消引用')"
            @click="quoteVisible = false"
          >
            <X :size="13" />
          </button>
        </div>
      </div>

      <CourseEvolutionPanel
        v-if="!props.blockTarget && courseStore.currentCourseId"
        :course-id="courseStore.currentCourseId"
        :section-id="currentNode?.node_id"
      />

      <section
        v-if="!props.blockTarget && changeProposalsStore.pendingProposals.length"
        class="change-proposals-panel"
        aria-live="polite"
      >
        <header class="change-proposals-heading">
          <span><FileDiff :size="14" /></span>
          <strong>{{ t('courseWorkspace.changeProposals.title', '基础课程修改') }}</strong>
        </header>

        <article
          v-for="proposal in changeProposalsStore.pendingProposals"
          :key="proposal.proposal_id"
          :class="['change-proposal-card', { 'is-in-view': proposalTargetsCurrentNode(proposal) }]"
        >
          <div class="change-proposal-meta">
            <span :class="['scope-badge', `scope-${proposal.scope}`]">{{ scopeLabel(proposal.scope) }}</span>
            <span v-if="sourceLabel(proposal.source)" :class="['source-badge', `source-${proposal.source}`]">
              {{ sourceLabel(proposal.source) }}
            </span>
            <span v-if="proposalTargetsCurrentNode(proposal)" class="in-view-badge">
              {{ t('courseWorkspace.changeProposals.currentNode', '涉及当前节点') }}
            </span>
          </div>

          <ul class="change-proposal-items">
            <li
              v-for="item in proposal.items.filter(candidate => candidate.status === 'pending')"
              :key="item.item_id"
              class="change-proposal-item"
            >
              <div class="change-item-diff">
                <template v-if="isAwaitingGeneration(item)">
                  <p class="diff-awaiting-generation">
                    <LoaderCircle :size="13" />
                    {{ t('courseWorkspace.changeProposals.awaitingGeneration', '该条目正在等待重新生成，请稍后刷新或联系管理员。') }}
                  </p>
                </template>
                <template v-else-if="!item.before">
                  <span class="diff-label diff-added">{{ t('courseWorkspace.changeProposals.added', '新增') }}</span>
                  <MarkdownRenderer class="diff-after" :content="proposalItemContent(item.after)" />
                </template>
                <template v-else>
                  <div class="diff-before">
                    <span class="diff-label diff-removed">{{ t('courseWorkspace.changeProposals.before', '原文') }}</span>
                    <MarkdownRenderer :content="proposalItemContent(item.before)" />
                  </div>
                  <div class="diff-after-wrap">
                    <span class="diff-label diff-added">{{ t('courseWorkspace.changeProposals.after', '修改为') }}</span>
                    <MarkdownRenderer class="diff-after" :content="proposalItemContent(item.after)" />
                  </div>
                </template>
              </div>
              <p v-if="item.reason" class="change-item-reason">{{ item.reason }}</p>

              <p v-if="isKgNodeItem(item)" class="change-item-unsupported-note">
                {{ t('courseWorkspace.changeProposals.kgNodeReviewOnly', '该建议涉及知识库节点：接受后仅会在知识库目录上记录一条待人工复核的备注，不会自动改写知识节点的正式定义。') }}
              </p>

              <div class="change-item-actions">
                <button
                  v-if="canApplyProposalItem(item)"
                  type="button"
                  class="primary-command"
                  :disabled="changeProposalsStore.isItemActing(item.item_id) || isAwaitingGeneration(item)"
                  :title="isAwaitingGeneration(item)
                    ? t('courseWorkspace.changeProposals.awaitingGeneration', '该条目正在等待重新生成，请稍后刷新或联系管理员。')
                    : undefined"
                  @click="handleApplyItem(proposal.proposal_id, item.item_id)"
                >
                  <LoaderCircle v-if="changeProposalsStore.isItemActing(item.item_id)" class="spin" :size="13" />
                  <Check v-else :size="13" />
                  {{ t('courseWorkspace.changeProposals.accept', '接受') }}
                </button>
                <button
                  type="button"
                  class="secondary-command"
                  :disabled="changeProposalsStore.isItemActing(item.item_id)"
                  @click="promptRejectItem(proposal.proposal_id, item.item_id)"
                >
                  <X :size="13" />
                  {{ t('courseWorkspace.changeProposals.reject', '拒绝') }}
                </button>
                <button
                  type="button"
                  class="secondary-command"
                  :disabled="changeProposalsStore.isItemActing(item.item_id)"
                  @click="promptRegenerateItem(proposal.proposal_id, item.item_id)"
                >
                  <RotateCcw :size="13" />
                  {{ t('courseWorkspace.changeProposals.regenerate', '重新生成') }}
                </button>
              </div>

              <Transition name="conversation-reveal">
                <div v-if="itemPromptOpen === `${proposal.proposal_id}:${item.item_id}`" class="change-item-prompt">
                  <textarea
                    v-model="itemPromptText"
                    rows="2"
                    :placeholder="itemPromptMode === 'reject'
                      ? t('courseWorkspace.changeProposals.rejectReasonPlaceholder', '（可选）说明拒绝理由')
                      : t('courseWorkspace.changeProposals.regenerateInstructionPlaceholder', '（可选）补充生成说明')"
                  />
                  <div class="change-item-prompt-actions">
                    <button type="button" class="primary-command" @click="confirmItemPrompt(proposal.proposal_id, item.item_id)">
                      {{ t('courseWorkspace.changeProposals.confirm', '确认') }}
                    </button>
                    <button type="button" class="secondary-command" @click="cancelItemPrompt">
                      {{ t('courseWorkspace.changeProposals.cancel', '取消') }}
                    </button>
                  </div>
                </div>
              </Transition>
            </li>
          </ul>
        </article>
      </section>

      <section
        v-if="!props.blockTarget && changeProposalsStore.lastRepresentationSync"
        class="representation-sync-receipt"
        :data-status="changeProposalsStore.lastRepresentationSync.status"
        aria-live="polite"
      >
        <CheckCircle2 v-if="changeProposalsStore.lastRepresentationSync.status === 'synchronized'" :size="15" />
        <AlertCircle v-else :size="15" />
        <div>
          <strong>{{ changeProposalsStore.lastRepresentationSync.status === 'synchronized'
            ? t('courseWorkspace.changeProposals.synced', '基础课程及教学资源已同步')
            : t('courseWorkspace.changeProposals.syncFallback', '基础课程已更新，旧教学资源暂时保留') }}</strong>
          <small>{{ changeProposalsStore.lastRepresentationSync.status === 'synchronized'
            ? t('courseWorkspace.changeProposals.syncedUnits', '已精准重建 {count} 个受影响单元').replace('{count}', String(representationSyncUnitCount))
            : t('courseWorkspace.changeProposals.syncFallbackDetail', '重建未通过检查，旧版本已标记为待同步，没有被覆盖') }}</small>
        </div>
      </section>

      <section v-if="props.blockTarget" class="personalization-workspace" aria-live="polite">
        <header class="personalization-heading">
          <div>
            <span><WandSparkles :size="14" /></span>
            <div>
              <small>{{ t('courseWorkspace.personalization.eyebrow', '个性化正文优化') }}</small>
              <strong>{{ blockTargetTitle }}</strong>
            </div>
          </div>
          <button type="button" class="icon-button" :title="t('courseWorkspace.personalization.returnToChat', '返回对话')" @click="clearBlockTarget">
            <X :size="16" />
          </button>
        </header>

        <div class="personalization-directions" role="radiogroup" :aria-label="t('courseWorkspace.personalization.direction', '优化方向')">
          <button
            v-for="direction in personalizationDirections"
            :key="direction.value"
            type="button"
            class="personalization-direction-chip"
            :class="{ active: personalizationDirection === direction.value }"
            role="radio"
            :aria-checked="personalizationDirection === direction.value"
            :disabled="personalizationBusy || Boolean(personalizationProposal)"
            @click="personalizationDirection = direction.value"
          >
            <component :is="direction.icon" :size="14" />
            {{ direction.label }}
          </button>
        </div>

        <label class="personalization-feedback-wrap">
          <span>{{ t('courseWorkspace.personalization.feedback', '你的反馈') }}</span>
          <textarea
            v-model="personalizationFeedback"
            class="personalization-feedback"
            rows="4"
            :disabled="personalizationBusy || Boolean(personalizationProposal)"
            :placeholder="personalizationFeedbackPlaceholder"
          />
        </label>

        <div v-if="!personalizationProposal" class="personalization-original-preview">
          <small>{{ t('courseWorkspace.personalization.currentContent', '当前正文') }}</small>
          <MarkdownRenderer :content="blockOriginalContent" />
        </div>

        <button
          v-if="!personalizationProposal"
          type="button"
          class="primary-command personalization-generate"
          :disabled="!canGeneratePersonalization"
          @click="generatePersonalizationProposal"
        >
          <LoaderCircle v-if="personalizationGenerationLoading" class="spin" :size="14" />
          <WandSparkles v-else :size="14" />
          {{ t('courseWorkspace.personalization.generate', '生成优化对比') }}
        </button>

        <div v-if="personalizationError" class="personalization-error">
          <AlertCircle :size="16" />
          <span>{{ personalizationError }}</span>
        </div>

        <template v-if="personalizationProposal">
          <div class="personalization-proposal-summary">
            <FileDiff :size="15" />
            <span>{{ t('courseWorkspace.personalization.reviewCount', '请核对 {count} 个受影响课程块').replace('{count}', String(personalizationProposal.items.length)) }}</span>
          </div>

          <div class="personalization-diff-list">
            <article
              v-for="(item, index) in personalizationProposal.items"
              :key="item.item_id"
              class="personalization-diff-card"
              :class="{ selected: selectedPersonalizationItemIds.has(item.item_id) }"
            >
              <header>
                <label>
                  <input
                    class="personalization-item-check"
                    type="checkbox"
                    :checked="selectedPersonalizationItemIds.has(item.item_id)"
                    :disabled="personalizationBusy || Boolean(personalizationResult)"
                    @change="togglePersonalizationItem(item.item_id, $event)"
                  />
                  <span>{{ personalizationItemTitle(item, index) }}</span>
                </label>
                <small>{{ item.block_id }}</small>
              </header>
              <div class="personalization-diff-columns">
                <div class="personalization-before">
                  <span>{{ t('courseWorkspace.personalization.before', '优化前') }}</span>
                  <MarkdownRenderer :content="proposalItemContent(item.before)" />
                </div>
                <div class="personalization-after">
                  <span>{{ t('courseWorkspace.personalization.after', '优化后') }}</span>
                  <MarkdownRenderer :content="proposalItemContent(item.after)" />
                </div>
              </div>
              <p v-if="item.reason">{{ item.reason }}</p>
            </article>
          </div>

          <button
            v-if="!personalizationResult"
            type="button"
            class="primary-command personalization-apply"
            :disabled="selectedPersonalizationItemIds.size === 0 || personalizationBusy"
            @click="applySelectedPersonalization"
          >
            <LoaderCircle v-if="personalizationApplying" class="spin" :size="14" />
            <Check v-else :size="14" />
            {{ t('courseWorkspace.personalization.applySelected', '应用所选优化') }}
          </button>
        </template>

        <div v-if="personalizationResult" class="personalization-apply-receipt">
          <CheckCircle2 :size="18" />
          <div>
            <strong>{{ t('courseWorkspace.personalization.applied', '所选优化已写入课程真源') }}</strong>
            <span>{{ t('courseWorkspace.personalization.affectedBlocks', '影响课程块') }}：{{ personalizationAffectedBlockIds.join('、') }}</span>
            <span>{{ personalizationRepresentationSummary }}</span>
          </div>
        </div>
      </section>

      <main v-else ref="messageList" class="ai-teacher-messages" aria-live="polite">
        <div v-if="aiStore.loadingConversations" class="panel-state">
          <LoaderCircle class="spin" :size="20" />
          <span>{{ t('courseWorkspace.aiTeacher.loadingConversation', '正在恢复对话') }}</span>
        </div>

        <div v-else-if="!aiStore.messages.length" class="ai-teacher-empty">
          <span class="empty-mark"><MessageSquareText :size="22" /></span>
          <strong>{{ t('courseWorkspace.aiTeacher.emptyTitle', '从当前学习现场开始提问') }}</strong>
          <p>{{ t('courseWorkspace.aiTeacher.emptyBody', '从没弄懂的概念、题目或课程内容开始。') }}</p>
        </div>

        <article
          v-for="message in aiStore.messages"
          :key="message.message_id"
          :class="['ai-message', `is-${message.role}`]"
        >
          <div v-if="message.role === 'user'" class="user-message-bubble">{{ message.content }}</div>

          <template v-else>
            <span class="assistant-avatar"><Sparkles :size="13" /></span>
            <div class="assistant-message-column">
              <div :class="['assistant-answer', { failed: message.status === 'failed' }]">
                <MarkdownRenderer v-if="message.content" :content="message.content" />
                <div v-else class="thinking-line">
                  <span class="sr-only">{{ t('courseWorkspace.aiTeacher.thinking', '正在思考') }}</span>
                  <i /><i /><i />
                </div>
              </div>

              <div v-if="message.sources?.length" class="message-sources">
                <span>{{ t('courseWorkspace.aiTeacher.basedOn', '依据') }}</span>
                <button
                  v-for="source in message.sources"
                  :key="source.source_id"
                  type="button"
                  :title="source.source_id"
                >
                  {{ source.title || t('courseWorkspace.aiTeacher.courseSource', '课程内容') }}
                </button>
              </div>

              <div v-if="message.proposal && message.proposal.status === 'presented'" class="action-proposal">
                <span class="action-proposal__icon"><Sparkles :size="14" /></span>
                <div>
                  <strong>{{ message.proposal.expected_effect }}</strong>
                  <p>{{ message.proposal.reason }}</p>
                  <div class="proposal-actions">
                    <button type="button" class="primary-command" @click="aiStore.confirmProposal(message)">
                      <Check :size="14" />
                      {{ t('courseWorkspace.aiTeacher.confirm', '确认') }}
                    </button>
                    <button type="button" class="secondary-command" @click="aiStore.rejectProposal(message)">
                      {{ t('courseWorkspace.aiTeacher.notNow', '暂时不要') }}
                    </button>
                  </div>
                </div>
              </div>

              <div v-if="message.receipt" :class="['action-receipt', `is-${message.receipt.status}`]">
                <CheckCircle2 v-if="message.receipt.status === 'succeeded'" :size="16" />
                <AlertCircle v-else :size="16" />
                <span>{{ message.receipt.summary }}</span>
                <button
                  v-if="message.receipt.status === 'succeeded' && message.receipt.undo_capability === 'archive_record'"
                  type="button"
                  @click="aiStore.undoReceipt(message)"
                >
                  <RotateCcw :size="13" />
                  {{ t('courseWorkspace.aiTeacher.undo', '撤销') }}
                </button>
              </div>

              <div
                v-if="message.status === 'complete' && message.content && !message.receipt && !message.proposal"
                class="message-commands"
              >
                <button type="button" @click="saveAnswerAsNote(message)">
                  <BookmarkPlus :size="13" />
                  {{ t('courseWorkspace.aiTeacher.saveAsNote', '保存为笔记') }}
                </button>
              </div>
            </div>
          </template>
        </article>
      </main>

      <footer v-if="!props.blockTarget" class="ai-teacher-composer">
        <div v-if="!props.blockTarget && !aiStore.messages.length && !aiStore.loadingConversations" class="quick-actions">
          <button v-for="item in quickPrompts" :key="item.prompt" type="button" @click="sendPrompt(item.prompt)">
            <component :is="item.icon" :size="14" />
            {{ item.label }}
          </button>
        </div>

        <div v-if="aiStore.loading" class="composer-status">
          <LoaderCircle class="spin" :size="13" />
          <span>{{ t('courseWorkspace.aiTeacher.generating', '正在生成回答') }}</span>
        </div>

        <div v-if="!isOnline" class="offline-notice">
          <WifiOff :size="14" />
          {{ t('courseWorkspace.aiTeacher.offline', '当前离线，可以查看缓存对话，但不能执行新动作。') }}
        </div>

        <div class="composer-box">
          <textarea
            ref="inputElement"
            v-model="input"
            :placeholder="composerPlaceholder"
            :disabled="composerDisabled"
            rows="2"
            @input="resizeComposer"
            @keydown="handleKeydown"
          />
          <button
            type="button"
            class="send-button"
            :class="{ 'is-stop': aiStore.loading }"
            :disabled="composerButtonDisabled"
            :title="composerButtonTitle"
            @click="handleComposerAction"
          >
            <Square v-if="aiStore.loading" :size="14" />
            <Send v-else :size="17" />
          </button>
        </div>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  AlertCircle,
  BookOpenText,
  BookmarkPlus,
  Check,
  CheckCircle2,
  ChevronDown,
  FileDiff,
  History,
  Lightbulb,
  LoaderCircle,
  MessageSquareText,
  Plus,
  Quote,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Trash2,
  WandSparkles,
  WifiOff,
  X,
} from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import CourseEvolutionPanel from './CourseEvolutionPanel.vue'
import { useAITeacherStore, type AIMessage } from '../stores/aiTeacher'
import { useCourseStore } from '../stores/course'
import { useLearningProgressStore } from '../stores/learningProgress'
import { useNoteStore } from '../stores/notes'
import { useChangeProposalsStore } from '../stores/changeProposals'
import { t } from '../shared/i18n'
import type { CourseBlockEditTarget } from '../stores/types'
import type {
  ApplySelectedChangeProposalResult,
  ChangeProposal,
  ChangeProposalAfterPayload,
  ChangeProposalBlockPayload,
  ChangeProposalContent,
  ChangeProposalItem,
  ChangeProposalScope,
  ChangeProposalSource,
  PersonalizationDirection,
} from '../types/changeProposal'
import logger from '../utils/logger'

const props = defineProps<{
  visible: boolean
  quoteText: string
  quoteNodeId: string
  quoteAnchor?: Record<string, unknown>
  prefill?: string
  entrypoint?: 'global' | 'selection' | 'practice' | 'continuity' | 'record'
  blockTarget?: CourseBlockEditTarget
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'clearBlockTarget'): void
  (event: 'blockApplied', target: CourseBlockEditTarget): void
}>()
const aiStore = useAITeacherStore()
const courseStore = useCourseStore()
const progressStore = useLearningProgressStore()
const noteStore = useNoteStore()
const changeProposalsStore = useChangeProposalsStore()
const input = ref('')
const quoteVisible = ref(Boolean(props.quoteText))
const conversationOpen = ref(false)
const windowWidth = ref(window.innerWidth)
const isOnline = ref(navigator.onLine)
const messageList = ref<HTMLElement | null>(null)
const inputElement = ref<HTMLTextAreaElement | null>(null)
const selectedConversationId = ref('')
const personalizationDirection = ref<PersonalizationDirection>('simplify')
const personalizationFeedback = ref('')
const personalizationProposal = ref<ChangeProposal | null>(null)
const selectedPersonalizationItemIds = reactive(new Set<string>())
const personalizationResult = ref<ApplySelectedChangeProposalResult | null>(null)
const personalizationError = ref('')
const personalizationGenerationLoading = ref(false)
const personalizationApplying = ref(false)
let personalizationGenerationToken = 0
let personalizationApplyToken = 0

const isOverlayMode = computed(() => windowWidth.value < 1280)
const panelClasses = computed(() => isOverlayMode.value ? 'is-overlay' : 'is-docked')
const currentNode = computed(() => (
  courseStore.nodes.find(node => node.node_id === (props.quoteNodeId || courseStore.currentNode?.node_id))
  || courseStore.currentNode
))
const contextLabel = computed(() => currentNode.value?.node_name || t('courseWorkspace.aiTeacher.courseContext', '当前课程'))
const modelEvidenceLevel = computed(() => String(
  aiStore.currentContext?.data_sufficiency?.level
  || progressStore.runtime?.learner_model?.data_sufficiency?.level
  || '',
))
const modelEvidenceLabel = computed(() => {
  if (!modelEvidenceLevel.value) return ''
  return t(
    `courseWorkspace.learningOverview.evidenceLevel.${modelEvidenceLevel.value}`,
    ({
      none: '无正式证据',
      limited: '有限证据',
      moderate: '中等证据',
      strong: '强证据',
    } as Record<string, string>)[modelEvidenceLevel.value] || '证据状态未知',
  )
})
const currentConversationTitle = computed(() => (
  aiStore.currentConversation?.title
  || t('courseWorkspace.aiTeacher.newConversation', '新建对话')
))
const blockTargetTitle = computed(() => String(props.blockTarget?.block.payload.title || props.blockTarget?.nodeName || ''))
const blockOriginalContent = computed(() => String(props.blockTarget?.block.payload.markdown || props.blockTarget?.block.payload.text || ''))
const representationSyncUnitCount = computed(() => (
  (changeProposalsStore.lastRepresentationSync?.rebuilt || []).reduce(
    (total: number, item: Record<string, any>) => total + (item.rebuilt_unit_ids?.length || 0),
    0,
  )
))
const personalizationDirections = computed(() => [
  {
    value: 'simplify' as const,
    icon: BookOpenText,
    label: t('courseWorkspace.personalization.directions.simplify', '更通俗易懂'),
  },
  {
    value: 'expand' as const,
    icon: Lightbulb,
    label: t('courseWorkspace.personalization.directions.expand', '讲得更深入'),
  },
  {
    value: 'custom' as const,
    icon: MessageSquareText,
    label: t('courseWorkspace.personalization.directions.custom', '自定义'),
  },
])
const personalizationBusy = computed(() => (
  personalizationGenerationLoading.value || personalizationApplying.value
))
const canGeneratePersonalization = computed(() => Boolean(
  personalizationFeedback.value.trim()
  && courseStore.currentCourseId
  && courseStore.currentDocumentRevision
  && isOnline.value
  && !personalizationBusy.value,
))
const personalizationFeedbackPlaceholder = computed(() => ({
  simplify: t('courseWorkspace.personalization.placeholders.simplify', '告诉我哪里难懂，或希望换成怎样的直观说法'),
  expand: t('courseWorkspace.personalization.placeholders.expand', '告诉我希望补充哪些推导、例子或应用'),
  custom: t('courseWorkspace.personalization.placeholders.custom', '具体描述你希望如何调整本段'),
})[personalizationDirection.value])
const personalizationAffectedBlockIds = computed(() => (
  personalizationResult.value?.receipt.affected_block_ids || []
))
const personalizationRepresentationSummary = computed(() => {
  const sync = personalizationResult.value?.representation_sync
  if (!sync) return ''
  if (sync.status === 'synchronized') {
    return t('courseWorkspace.personalization.representationSynced', '表示同步完成，共重建 {count} 个单元')
      .replace('{count}', String(representationSyncUnitCount.value))
  }
  return t('courseWorkspace.personalization.representationFallback', '表示同步未通过，继续使用上一可用版本')
})
const canSend = computed(() => Boolean(
  input.value.trim()
  && isOnline.value
  && !aiStore.loading,
))
const composerPlaceholder = computed(() => t('courseWorkspace.aiTeacher.placeholder', '询问当前内容或作答过程'))
const composerDisabled = computed(() => !isOnline.value || aiStore.loading)
const composerButtonDisabled = computed(() => !aiStore.loading && !canSend.value)
const composerButtonTitle = computed(() => {
  if (aiStore.loading) return t('courseWorkspace.aiTeacher.stop', '停止')
  return t('courseWorkspace.aiTeacher.send', '发送')
})
const quickPrompts = computed(() => [
  {
    icon: WandSparkles,
    label: t('courseWorkspace.aiTeacher.quickExplain', '解释当前内容'),
    prompt: t('courseWorkspace.aiTeacher.quickExplainPrompt', '请解释当前内容的核心概念。'),
  },
  {
    icon: Lightbulb,
    label: t('courseWorkspace.aiTeacher.quickExample', '举一个例子'),
    prompt: t('courseWorkspace.aiTeacher.quickExamplePrompt', '请用一个具体例子解释当前内容。'),
  },
])

function contextRef() {
  const runtimeContext = progressStore.runtime?.context || {}
  return {
    course_id: courseStore.currentCourseId,
    course_version_id: courseStore.currentCourseVersionId,
    node_id: currentNode.value?.node_id || '',
    node_name: currentNode.value?.node_name || '',
    objective_id: runtimeContext.objective_id || '',
    objective_revision_id: runtimeContext.objective_revision_id || '',
    content_anchor: props.quoteAnchor,
  }
}

async function initialize() {
  if (!courseStore.currentCourseId) return
  if (props.blockTarget) return
  await aiStore.load(courseStore.currentCourseId, currentNode.value?.node_id)
  selectedConversationId.value = aiStore.currentConversationId
  if (props.prefill) input.value = props.prefill
  await nextTick()
  resizeComposer()
  inputElement.value?.focus()
  scrollToBottom()
}

async function sendPrompt(prompt: string) {
  input.value = prompt
  await send()
}

async function send() {
  const question = input.value.trim()
  if (!question || !courseStore.currentCourseId) return
  input.value = ''
  resetComposerHeight()
  await aiStore.sendMessage({
    courseId: courseStore.currentCourseId,
    courseVersionId: courseStore.currentCourseVersionId,
    nodeId: currentNode.value?.node_id,
    nodeName: currentNode.value?.node_name,
    question,
    selection: quoteVisible.value ? props.quoteText : '',
    entrypoint: props.entrypoint || (quoteVisible.value ? 'selection' : 'global'),
    contextRef: contextRef(),
    taskRef: progressStore.runtime?.active_task || {},
  })
  await progressStore.loadRuntime(
    courseStore.currentCourseId,
    currentNode.value?.node_id,
  ).catch(error => {
    logger.warn('Course evolution refresh deferred after AI question', error)
  })
  scrollToBottom()
}

function handleComposerAction() {
  if (aiStore.loading) {
    aiStore.cancel()
    return
  }
  void send()
}

function resetPersonalization() {
  personalizationGenerationToken += 1
  personalizationApplyToken += 1
  personalizationGenerationLoading.value = false
  personalizationApplying.value = false
  personalizationDirection.value = 'simplify'
  personalizationFeedback.value = props.prefill || ''
  personalizationProposal.value = null
  personalizationResult.value = null
  personalizationError.value = ''
  selectedPersonalizationItemIds.clear()
}

function personalizationErrorText(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  if (detail?.code === 'personalization_generation_in_progress') {
    return t(
      'courseWorkspace.personalization.generationInProgress',
      '同一内容的优化正在生成，请稍后重试',
    )
  }
  if (error?.response?.status === 409) {
    return t(
      'courseWorkspace.personalization.conflict',
      '课程内容已变化，未应用任何优化；请关闭后重新发起',
    )
  }
  return detail?.message
    || fallback
}

interface PersonalizationTargetSnapshot {
  courseId: string
  blockId: string
  expectedDocumentRevision: string
  expectedBlockRevision: string
  direction: PersonalizationDirection
  feedback: string
}

function personalizationTargetSnapshot(
  target: CourseBlockEditTarget,
  expectedDocumentRevision: string,
): PersonalizationTargetSnapshot {
  return {
    courseId: courseStore.currentCourseId,
    blockId: target.block.block_id,
    expectedDocumentRevision,
    expectedBlockRevision: target.block.internal_revision,
    direction: personalizationDirection.value,
    feedback: personalizationFeedback.value.trim(),
  }
}

function isCurrentPersonalizationTarget(snapshot: PersonalizationTargetSnapshot) {
  const target = props.blockTarget
  return Boolean(
    target
    && courseStore.currentCourseId === snapshot.courseId
    && courseStore.currentDocumentRevision === snapshot.expectedDocumentRevision
    && target.block.block_id === snapshot.blockId
    && target.block.internal_revision === snapshot.expectedBlockRevision
    && personalizationDirection.value === snapshot.direction
    && personalizationFeedback.value.trim() === snapshot.feedback,
  )
}

async function generatePersonalizationProposal() {
  const target = props.blockTarget
  const feedback = personalizationFeedback.value.trim()
  if (!target || !feedback || !canGeneratePersonalization.value) return
  const snapshot = personalizationTargetSnapshot(target, courseStore.currentDocumentRevision)
  const requestToken = ++personalizationGenerationToken
  personalizationError.value = ''
  personalizationGenerationLoading.value = true
  try {
    const proposal = await changeProposalsStore.createPersonalizationProposal({
      courseId: snapshot.courseId,
      blockId: snapshot.blockId,
      requestId: crypto.randomUUID(),
      expectedDocumentRevision: snapshot.expectedDocumentRevision,
      expectedBlockRevision: snapshot.expectedBlockRevision,
      direction: snapshot.direction,
      feedback: snapshot.feedback,
    })
    if (requestToken !== personalizationGenerationToken || !isCurrentPersonalizationTarget(snapshot)) return
    personalizationProposal.value = proposal
    selectedPersonalizationItemIds.clear()
    for (const item of proposal.items) {
      if (item.selected !== false) selectedPersonalizationItemIds.add(item.item_id)
    }
  } catch (error: any) {
    if (requestToken !== personalizationGenerationToken || !isCurrentPersonalizationTarget(snapshot)) return
    personalizationError.value = personalizationErrorText(
      error,
      t('courseWorkspace.personalization.generateFailed', '优化对比生成失败，请刷新课程后重试'),
    )
  } finally {
    if (requestToken === personalizationGenerationToken) {
      personalizationGenerationLoading.value = false
    }
  }
}

function togglePersonalizationItem(itemId: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  if (checked) selectedPersonalizationItemIds.add(itemId)
  else selectedPersonalizationItemIds.delete(itemId)
}

function invalidatePersonalizationProposal() {
  personalizationProposal.value = null
  personalizationResult.value = null
  selectedPersonalizationItemIds.clear()
}

function personalizationItemTitle(item: ChangeProposalItem, index: number) {
  const before = item.before
  if (before && typeof before === 'object') {
    const payload = 'payload' in before && before.payload && typeof before.payload === 'object'
      ? before.payload as ChangeProposalBlockPayload
      : before as ChangeProposalBlockPayload
    if (typeof payload.title === 'string' && payload.title.trim()) return payload.title.trim()
  }
  return t('courseWorkspace.personalization.blockFallback', '课程块 {index}')
    .replace('{index}', String(index + 1))
}

async function applySelectedPersonalization() {
  const proposal = personalizationProposal.value
  const target = props.blockTarget
  if (!proposal || !target || !selectedPersonalizationItemIds.size || personalizationBusy.value) return
  const itemIds = proposal.items
    .filter(item => selectedPersonalizationItemIds.has(item.item_id))
    .map(item => item.item_id)
  const expectedRevision = String(
    proposal.generation_meta?.base_document_revision || courseStore.currentDocumentRevision,
  )
  const targetProposalItem = proposal.items.find(item => item.block_id === target.block.block_id)
  if (
    expectedRevision !== courseStore.currentDocumentRevision
    || targetProposalItem?.expected_block_revision !== target.block.internal_revision
  ) {
    invalidatePersonalizationProposal()
    personalizationError.value = personalizationErrorText(
      { response: { status: 409 } },
      t('courseWorkspace.personalization.conflict', '课程内容已变化，未应用任何优化；请关闭后重新发起'),
    )
    return
  }
  const snapshot = personalizationTargetSnapshot(target, expectedRevision)
  const requestToken = ++personalizationApplyToken
  personalizationError.value = ''
  personalizationApplying.value = true
  try {
    const result = await changeProposalsStore.applySelectedItems(
      proposal.proposal_id,
      itemIds,
      expectedRevision,
    )
    const responseCourseId = result.document.course_id
    const shouldWriteCurrentTarget = requestToken === personalizationApplyToken
      && isCurrentPersonalizationTarget(snapshot)
    const shouldRefreshCurrentCourse = Boolean(
      responseCourseId && responseCourseId === courseStore.currentCourseId,
    )
    if (shouldRefreshCurrentCourse) {
      courseStore.applyCourseDocumentEnvelope(result.document)
    }
    if (!shouldWriteCurrentTarget) {
      if (shouldRefreshCurrentCourse) {
        void courseStore.refreshCourseData(responseCourseId).catch(error => {
          logger.warn('Course refresh deferred after personalization apply', error)
        })
      }
      return
    }
    personalizationProposal.value = result.proposal
    personalizationResult.value = result
    emit('blockApplied', target)
    if (shouldRefreshCurrentCourse) {
      void courseStore.refreshCourseData(responseCourseId).catch(error => {
        logger.warn('Course refresh deferred after personalization apply', error)
      })
    }
  } catch (error: any) {
    if (requestToken !== personalizationApplyToken || !isCurrentPersonalizationTarget(snapshot)) return
    personalizationError.value = personalizationErrorText(
      error,
      error?.response?.status === 409
        ? t('courseWorkspace.personalization.conflict', '课程内容已变化，未应用任何优化；请关闭后重新发起')
        : t('courseWorkspace.personalization.applyFailed', '所选优化应用失败，请稍后重试'),
    )
  } finally {
    if (requestToken === personalizationApplyToken) {
      personalizationApplying.value = false
    }
  }
}

// --- 多节点变更提案（change_proposals） ---
const itemPromptOpen = ref<string>('')
const itemPromptMode = ref<'reject' | 'regenerate'>('reject')
const itemPromptText = ref('')

function scopeLabel(scope: ChangeProposalScope) {
  return ({
    block: t('courseWorkspace.changeProposals.scope.block', '当前块'),
    section: t('courseWorkspace.changeProposals.scope.section', '当前小节'),
    sections: t('courseWorkspace.changeProposals.scope.sections', '多个小节'),
    chapters: t('courseWorkspace.changeProposals.scope.chapters', '多个章节'),
    book: t('courseWorkspace.changeProposals.scope.book', '全书'),
  } as Record<ChangeProposalScope, string>)[scope] || scope
}

// kg_node 的接受语义是记录待人工复核备注，不会直接改写正式知识节点。
function isKgNodeItem(item: ChangeProposalItem) {
  return item.target_kind === 'kg_node'
}

function canApplyProposalItem(item: ChangeProposalItem) {
  return ['course_block', 'course_objective', 'kg_node'].includes(
    item.target_kind || 'course_block',
  )
}

// 后端契约：`after === null` 表示该条目的新内容尚未生成完成（例如刚点击过
// "重新生成"，但服务端这次没能立即产出新内容）。不能把它当空字符串渲染成
// 一片空白的"修改为"区块，也不能允许用户点"接受"——那会在服务端 apply_item
// 里必然报错。
function isAwaitingGeneration(item: ChangeProposalItem) {
  return item.after === null || item.after === undefined
}

function isChangeProposalAfterPayload(
  content: ChangeProposalContent,
): content is ChangeProposalAfterPayload {
  return Boolean(
    content
    && typeof content === 'object'
    && 'payload' in content
    && content.payload
    && typeof content.payload === 'object',
  )
}

function proposalItemContent(content: ChangeProposalContent): string {
  if (typeof content === 'string') return content
  if (!content) return ''

  const blockPayload = isChangeProposalAfterPayload(content)
    ? content.payload
    : content as ChangeProposalBlockPayload

  return [
    blockPayload.learning_objective,
    blockPayload.markdown,
    blockPayload.summary,
    blockPayload.title,
  ]
    .find(value => typeof value === 'string' && value.trim())
    ?.trim() || ''
}

function sourceLabel(source: ChangeProposalSource) {
  return ({
    manual: '',
    representation_semantic: t('courseWorkspace.changeProposals.source.representationSemantic', '教学资源语义修改'),
    block_regeneration: t('courseWorkspace.changeProposals.source.blockRegeneration', '正式正文改进'),
    personalization: t('courseWorkspace.changeProposals.source.personalization', '个性化正文优化'),
    evidence: t('courseWorkspace.changeProposals.source.evidence', '旧个人证据提案'),
    kb_link: t('courseWorkspace.changeProposals.source.kbLink', '联动至知识库'),
  } as Record<ChangeProposalSource, string>)[source] || ''
}

function proposalTargetsCurrentNode(proposal: ChangeProposal) {
  const target = props.blockTarget
  const currentBlockId = target?.block.block_id
  const currentNodeId = currentNode.value?.node_id
  return proposal.target_block_ids.some(blockId => (
    blockId === currentBlockId
    || (currentNodeId && proposal.items.some(item => item.block_id === blockId && item.block_id === currentNodeId))
  )) || proposal.items.some(item => item.block_id === currentBlockId)
}

function promptRejectItem(proposalId: string, itemId: string) {
  itemPromptMode.value = 'reject'
  itemPromptText.value = ''
  itemPromptOpen.value = `${proposalId}:${itemId}`
}

function promptRegenerateItem(proposalId: string, itemId: string) {
  itemPromptMode.value = 'regenerate'
  itemPromptText.value = ''
  itemPromptOpen.value = `${proposalId}:${itemId}`
}

function cancelItemPrompt() {
  itemPromptOpen.value = ''
  itemPromptText.value = ''
}

async function confirmItemPrompt(proposalId: string, itemId: string) {
  const text = itemPromptText.value.trim()
  try {
    if (itemPromptMode.value === 'reject') {
      await changeProposalsStore.rejectItem(proposalId, itemId, text || undefined)
    } else {
      await changeProposalsStore.regenerateItem(proposalId, itemId, text || undefined)
    }
  } catch (error) {
    logger.warn('Failed to resolve change proposal item', error)
  } finally {
    cancelItemPrompt()
  }
}

async function handleApplyItem(proposalId: string, itemId: string) {
  try {
    await changeProposalsStore.applyItem(proposalId, itemId)
  } catch (error) {
    logger.warn('Failed to apply change proposal item', error)
  }
}

function clearBlockTarget() {
  resetPersonalization()
  emit('clearBlockTarget')
}

async function saveAnswerAsNote(message: AIMessage) {
  const target = contextRef()
  const proposal = await aiStore.proposeForMessage(message, 'create_note', {
    node_id: target.node_id,
    title: message.content.slice(0, 80),
    content: message.content,
    quote: quoteVisible.value ? props.quoteText : '',
    anchor: props.quoteAnchor,
    metadata: {
      ai_conversation_id: aiStore.currentConversationId,
      ai_message_ids: [message.message_id],
      record_subtype: 'assistant_saved_note',
    },
  }, target)
  await aiStore.confirmProposal(message, proposal)
  await noteStore.loadCourseRecords(courseStore.currentCourseId)
}

async function createConversation() {
  const conversation = await aiStore.createConversation()
  selectedConversationId.value = conversation?.conversation_id || ''
  conversationOpen.value = false
}

async function switchConversation() {
  if (selectedConversationId.value) await aiStore.selectConversation(selectedConversationId.value)
  conversationOpen.value = false
  scrollToBottom()
}

async function deleteConversation() {
  if (!aiStore.currentConversationId) return
  await aiStore.deleteConversation(aiStore.currentConversationId)
  selectedConversationId.value = aiStore.currentConversationId
  conversationOpen.value = false
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}

function resizeComposer() {
  const element = inputElement.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 144)}px`
}

function resetComposerHeight() {
  nextTick(() => {
    if (inputElement.value) inputElement.value.style.height = ''
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
  })
}

function handleResize() { windowWidth.value = window.innerWidth }
function handleOnline() { isOnline.value = true }
function handleOffline() { isOnline.value = false }

watch(() => props.quoteText, value => { quoteVisible.value = Boolean(value) })
watch(() => props.prefill, value => {
  if (props.blockTarget) {
    if (personalizationProposal.value || personalizationResult.value) {
      invalidatePersonalizationProposal()
    }
    personalizationFeedback.value = value || ''
  } else if (value) {
    input.value = value
    nextTick(resizeComposer)
  }
})
watch(() => `${props.blockTarget?.block.block_id || ''}:${props.blockTarget?.block.internal_revision || ''}`, () => {
  resetPersonalization()
}, { immediate: true })
watch(() => aiStore.currentConversationId, value => { selectedConversationId.value = value })
watch(() => aiStore.messages.length, scrollToBottom)
watch(() => aiStore.loading, scrollToBottom)
watch(() => courseStore.currentCourseId, () => {
  resetPersonalization()
  void initialize()
})

onMounted(() => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)
  void initialize()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('online', handleOnline)
  window.removeEventListener('offline', handleOffline)
})
</script>

<style scoped>
.ai-teacher-panel { height: 100%; min-width: 0; }
.ai-teacher-panel.is-docked { width: clamp(360px, 28vw, 420px); flex: 0 0 clamp(360px, 28vw, 420px); overflow: hidden; border: 1px solid rgba(255,255,255,.88); border-radius: var(--lz-radius-surface); background: #fff; box-shadow: 0 10px 30px rgba(79,70,229,.08), 0 2px 8px rgba(15,23,42,.04); backdrop-filter: none; -webkit-backdrop-filter: none; }
.ai-teacher-panel.is-overlay { position: fixed; inset: 0; z-index: 90; height: auto; display: flex; justify-content: flex-end; padding-bottom: calc(64px + env(safe-area-inset-bottom, 0px)); backdrop-filter: none; -webkit-backdrop-filter: none; }
.ai-teacher-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: rgba(30,41,59,.32); cursor: default; }
.ai-teacher-surface { position: relative; z-index: 1; width: 100%; height: 100%; min-width: 0; display: flex; flex-direction: column; overflow: hidden; background: #fff; }
.is-overlay .ai-teacher-surface { width: min(100%, 520px); margin-left: auto; border: 1px solid rgba(255,255,255,.9); border-radius: var(--lz-radius-surface); box-shadow: var(--lz-shadow-overlay); }

.ai-teacher-header { min-height: 62px; flex: 0 0 62px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 13px 0 15px; }
.ai-teacher-heading { min-width: 0; display: flex; align-items: center; gap: 10px; }
.ai-teacher-icon { width: 34px; height: 34px; flex: 0 0 auto; display: grid; place-items: center; border: 1px solid rgba(255,255,255,.4); border-radius: 11px; color: #fff; background: linear-gradient(135deg,#6366f1,#8b5cf6); box-shadow: 0 7px 16px rgba(99,102,241,.23), inset 0 1px 0 rgba(255,255,255,.25); }
.ai-teacher-heading-copy { min-width: 0; display: flex; flex-direction: column; }
.ai-teacher-heading-copy strong { color: #312e81; font-size: 14px; line-height: 1.2; }
.ai-teacher-header-actions,.proposal-actions { display: flex; align-items: center; gap: 5px; }
.icon-button { width: 32px; height: 32px; flex: 0 0 auto; display: grid; place-items: center; border: 1px solid transparent; border-radius: 9px; color: var(--lz-text-muted); background: transparent; cursor: pointer; transition: color .16s ease, border-color .16s ease, background .16s ease, transform .16s ease; }
.icon-button:hover:not(:disabled) { transform: translateY(-1px); border-color: #e0e7ff; color: var(--lz-brand-strong); background: #f5f3ff; }
.icon-button.danger:hover:not(:disabled) { border-color: #fecaca; color: var(--lz-danger); background: var(--lz-danger-soft); }
.icon-button:disabled { opacity: .4; cursor: not-allowed; }

.conversation-shell { flex: 0 0 auto; margin: 0 12px 9px; border-radius: 11px; background: rgba(248,250,252,.7); transition: background .16s ease, box-shadow .16s ease; }
.conversation-shell.open { background: #f8fafc; box-shadow: inset 0 0 0 1px rgba(226,232,240,.8); }
.conversation-toggle { width: 100%; min-height: 42px; display: grid; grid-template-columns: 17px minmax(0,1fr) 16px; align-items: center; gap: 9px; padding: 6px 10px; border: 0; border-radius: 11px; color: var(--lz-text-muted); background: transparent; text-align: left; cursor: pointer; }
.conversation-toggle:hover { color: var(--lz-brand-strong); background: rgba(238,242,255,.66); }
.conversation-toggle > span { min-width: 0; display: flex; align-items: baseline; gap: 7px; }
.conversation-toggle small { flex: 0 0 auto; color: inherit; font-size: 9px; }
.conversation-toggle strong { min-width: 0; overflow: hidden; color: var(--lz-text-secondary); font-size: 11px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.conversation-toggle > svg:last-child { transition: transform .18s ease; }
.conversation-shell.open .conversation-toggle > svg:last-child { transform: rotate(180deg); }
.conversation-drawer { display: flex; align-items: center; gap: 6px; padding: 0 7px 8px 10px; }
.conversation-select-wrap { position: relative; min-width: 0; flex: 1; display: flex; align-items: center; }
.conversation-select { width: 100%; height: 34px; appearance: none; border: 1px solid rgba(203,213,225,.8); border-radius: 8px; padding: 0 30px 0 9px; color: var(--lz-text-secondary); background: #fff; font: inherit; font-size: 11px; outline: none; }
.conversation-select:focus { border-color: var(--lz-brand); box-shadow: 0 0 0 3px rgba(99,102,241,.08); }
.conversation-select-wrap svg { position: absolute; right: 9px; color: var(--lz-text-muted); pointer-events: none; }
.conversation-reveal-enter-active,.conversation-reveal-leave-active { transition: opacity .16s ease, transform .16s ease; }
.conversation-reveal-enter-from,.conversation-reveal-leave-to { opacity: 0; transform: translateY(-4px); }

.context-panel { flex: 0 0 auto; margin: 0 12px 10px; padding: 10px 11px; border-left: 3px solid #818cf8; border-radius: 0 10px 10px 0; background: linear-gradient(100deg,rgba(238,242,255,.84),rgba(250,250,255,.62)); }
.context-line { min-width: 0; display: grid; grid-template-columns: 15px auto minmax(0,1fr) auto; align-items: center; gap: 6px; color: var(--lz-brand); }
.context-line span { color: var(--lz-text-muted); font-size: 9px; }
.context-line strong { min-width: 0; overflow: hidden; color: var(--lz-text-secondary); font-size: 10px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.context-evidence { padding: 2px 5px; border-radius: 5px; color: #6d28d9; background: rgba(255,255,255,.76); font-size: 8px; font-weight: 700; white-space: nowrap; }
.context-quote { min-width: 0; display: grid; grid-template-columns: 14px minmax(0,1fr) 25px; align-items: start; gap: 7px; margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(199,210,254,.72); color: var(--lz-brand); }
.context-quote p { max-height: 64px; margin: 0; overflow: auto; color: var(--lz-text-secondary); font-size: 10px; line-height: 1.55; }
.context-quote button { width: 25px; height: 25px; display: grid; place-items: center; border: 0; border-radius: 7px; color: var(--lz-text-muted); background: transparent; cursor: pointer; }
.context-quote button:hover { color: var(--lz-brand-strong); background: rgba(255,255,255,.8); }
.block-target-line { min-width:0; display:grid; grid-template-columns:15px auto minmax(0,1fr); align-items:center; gap:6px; margin-top:8px; padding-top:8px; border-top:1px solid rgba(199,210,254,.72); color:var(--lz-brand); }
.block-target-line span { color:var(--lz-text-muted); font-size:9px; }
.block-target-line strong { min-width:0; overflow:hidden; color:var(--lz-text-secondary); font-size:10px; text-overflow:ellipsis; white-space:nowrap; }

.change-proposals-panel { min-height:0; max-height:44%; overflow-y:auto; margin:0 12px 10px; padding:10px 11px; border:1px solid rgba(199,210,254,.7); border-radius:10px; background:linear-gradient(100deg,rgba(238,242,255,.5),rgba(250,250,255,.4)); }
.representation-sync-receipt { display:grid; grid-template-columns:20px minmax(0,1fr); align-items:center; gap:7px; margin:0 12px 10px; padding:9px 10px; border:1px solid #a7f3d0; border-radius:8px; color:#047857; background:#f0fdf4; }
.representation-sync-receipt[data-status="failed_using_last_available"] { border-color:#fde68a; color:#92400e; background:#fffbeb; }
.representation-sync-receipt > div { min-width:0; display:flex; flex-direction:column; gap:2px; }
.representation-sync-receipt strong { font-size:10px; }
.representation-sync-receipt small { color:#64748b; font-size:8px; line-height:1.45; }
.change-proposals-heading { display:flex; align-items:center; gap:7px; margin-bottom:9px; color:var(--lz-brand-strong); }
.change-proposals-heading span { display:grid; place-items:center; color:var(--lz-brand); }
.change-proposals-heading strong { font-size:11px; }
.change-proposal-card { margin-bottom:10px; padding:9px 10px; border:1px solid var(--lz-border); border-radius:9px; background:#fff; }
.change-proposal-card:last-child { margin-bottom:0; }
.change-proposal-card.is-in-view { border-color:#818cf8; box-shadow:0 0 0 2px rgba(99,102,241,.12); }
.change-proposal-meta { display:flex; flex-wrap:wrap; align-items:center; gap:5px; margin-bottom:8px; }
.scope-badge,.source-badge,.in-view-badge { padding:2px 7px; border-radius:999px; font-size:9px; font-weight:700; white-space:nowrap; }
.scope-badge { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.source-badge { color:#166534; background:var(--lz-success-soft); }
.source-badge.source-kb_link { color:#92400e; background:var(--lz-warning-soft); }
.in-view-badge { color:#3730a3; background:#e0e7ff; }
.change-proposal-items { display:grid; gap:9px; margin:0; padding:0; list-style:none; }
.change-proposal-item { padding:8px 9px; border:1px solid var(--lz-border); border-radius:8px; background:var(--lz-surface-muted); }
.change-item-diff { display:grid; gap:6px; margin-bottom:6px; font-size:11px; line-height:1.6; }
.diff-label { display:inline-block; margin-bottom:2px; padding:1px 5px; border-radius:5px; font-size:8px; font-weight:700; }
.diff-added { color:#166534; background:var(--lz-success-soft); }
.diff-removed { color:#991b1b; background:var(--lz-danger-soft); }
.diff-before p { margin:0; color:#94a3b8; text-decoration:line-through; }
.diff-after-wrap p,.diff-after { margin:0; color:var(--lz-text); }
.diff-awaiting-generation { display:flex; align-items:center; gap:5px; margin:0; padding:6px 8px; border-radius:6px; background:var(--lz-warning-soft, rgba(217,119,6,.12)); color:var(--lz-text-muted); }
.change-item-reason { margin:0 0 8px; color:var(--lz-text-muted); font-size:10px; line-height:1.5; }
.change-item-unsupported-note { margin:0 0 8px; padding:6px 8px; border-radius:6px; background:var(--lz-surface-muted, rgba(148,163,184,.12)); color:var(--lz-text-muted); font-size:10px; line-height:1.5; }
.change-item-actions { display:flex; flex-wrap:wrap; gap:6px; }
.change-item-actions button:disabled { opacity:.55; cursor:not-allowed; }
.change-item-prompt { margin-top:8px; }
.change-item-prompt textarea { width:100%; border:1px solid rgba(203,213,225,.9); border-radius:8px; padding:7px 8px; color:var(--lz-text); background:#fff; font:inherit; font-size:11px; resize:vertical; }
.change-item-prompt-actions { display:flex; gap:6px; margin-top:6px; }

.personalization-workspace { min-height:0; flex:1; overflow-y:auto; padding:8px 14px 20px; background:linear-gradient(180deg,#fff 0%,#fbfcff 100%); }
.personalization-heading { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; }
.personalization-heading > div { min-width:0; display:flex; align-items:center; gap:9px; }
.personalization-heading > div > span { width:30px; height:30px; flex:0 0 auto; display:grid; place-items:center; border-radius:8px; color:var(--lz-brand); background:var(--lz-brand-soft); }
.personalization-heading > div > div { min-width:0; display:flex; flex-direction:column; }
.personalization-heading small,.personalization-original-preview > small { color:var(--lz-text-muted); font-size:9px; }
.personalization-heading strong { overflow:hidden; color:var(--lz-text-strong); font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.personalization-directions { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px; margin-bottom:12px; }
.personalization-direction-chip { min-height:38px; display:flex; align-items:center; justify-content:center; gap:5px; padding:6px; border:1px solid #dbe3f2; border-radius:9px; color:var(--lz-text-secondary); background:#fff; font-size:9px; font-weight:700; cursor:pointer; transition:border-color .16s ease,color .16s ease,background .16s ease,transform .16s ease; }
.personalization-direction-chip:hover:not(:disabled) { transform:translateY(-1px); border-color:#a5b4fc; color:var(--lz-brand-strong); }
.personalization-direction-chip.active { border-color:#818cf8; color:#3730a3; background:#eef2ff; box-shadow:0 0 0 2px rgba(99,102,241,.08); }
.personalization-direction-chip:disabled { opacity:.65; cursor:not-allowed; }
.personalization-feedback-wrap { display:grid; gap:6px; margin-bottom:10px; }
.personalization-feedback-wrap > span { color:var(--lz-text-secondary); font-size:10px; font-weight:750; }
.personalization-feedback { width:100%; min-height:86px; resize:vertical; border:1px solid #dbe3f2; border-radius:10px; padding:9px 10px; color:var(--lz-text); background:#fff; font:inherit; font-size:11px; line-height:1.55; outline:none; }
.personalization-feedback:focus { border-color:#a5b4fc; box-shadow:0 0 0 3px rgba(99,102,241,.08); }
.personalization-feedback:disabled { color:var(--lz-text-muted); background:#f8fafc; }
.personalization-original-preview { margin-bottom:10px; padding:10px 11px; border:1px solid var(--lz-border); border-radius:9px; color:var(--lz-text-secondary); background:var(--lz-surface-muted); font-size:10px; line-height:1.6; }
.personalization-original-preview > small { display:block; margin-bottom:5px; }
.personalization-original-preview :deep(.markdown-renderer > :first-child),.personalization-original-preview :deep(.markdown-renderer > :last-child) { margin-block:0; }
.personalization-generate,.personalization-apply { width:100%; min-height:36px; }
.personalization-generate:disabled,.personalization-apply:disabled { opacity:.5; cursor:not-allowed; }
.personalization-error { display:flex; align-items:flex-start; gap:7px; margin-top:10px; padding:9px 10px; border-left:3px solid var(--lz-danger); border-radius:0 8px 8px 0; color:var(--lz-danger); background:var(--lz-danger-soft); font-size:10px; line-height:1.5; }
.personalization-proposal-summary { display:flex; align-items:center; gap:7px; margin:13px 0 8px; color:var(--lz-brand-strong); font-size:10px; font-weight:750; }
.personalization-diff-list { display:grid; gap:9px; }
.personalization-diff-card { padding:9px; border:1px solid #e2e8f0; border-radius:10px; background:#fff; transition:border-color .16s ease,box-shadow .16s ease; }
.personalization-diff-card.selected { border-color:#a5b4fc; box-shadow:0 0 0 2px rgba(99,102,241,.07); }
.personalization-diff-card > header { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
.personalization-diff-card > header label { min-width:0; display:flex; align-items:center; gap:7px; color:var(--lz-text-strong); font-size:10px; font-weight:750; cursor:pointer; }
.personalization-item-check { width:15px; height:15px; flex:0 0 auto; accent-color:var(--lz-brand); }
.personalization-diff-card > header small { max-width:42%; overflow:hidden; color:var(--lz-text-muted); font-size:8px; text-overflow:ellipsis; white-space:nowrap; }
.personalization-diff-columns { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px; }
.personalization-before,.personalization-after { min-width:0; padding:8px; border-radius:8px; font-size:9.5px; line-height:1.55; overflow-wrap:anywhere; }
.personalization-before { color:#64748b; background:#f8fafc; }
.personalization-after { color:#334155; background:#f0fdf4; }
.personalization-before > span,.personalization-after > span { display:block; margin-bottom:5px; font-size:8px; font-weight:800; }
.personalization-before > span { color:#991b1b; }
.personalization-after > span { color:#166534; }
.personalization-before :deep(.markdown-renderer > :first-child),.personalization-before :deep(.markdown-renderer > :last-child),.personalization-after :deep(.markdown-renderer > :first-child),.personalization-after :deep(.markdown-renderer > :last-child) { margin-block:0; }
.personalization-diff-card > p { margin:7px 1px 0; color:var(--lz-text-muted); font-size:9px; line-height:1.45; }
.personalization-apply { margin-top:11px; }
.personalization-apply-receipt { display:grid; grid-template-columns:20px minmax(0,1fr); align-items:start; gap:8px; margin-top:12px; padding:10px; border-left:3px solid var(--lz-success); border-radius:0 9px 9px 0; color:#166534; background:var(--lz-success-soft); }
.personalization-apply-receipt > div { min-width:0; display:grid; gap:3px; }
.personalization-apply-receipt strong { font-size:10px; }
.personalization-apply-receipt span { color:#47705b; font-size:9px; line-height:1.45; overflow-wrap:anywhere; }

.ai-teacher-messages { min-height: 0; flex: 1; overflow-y: auto; padding: 20px 18px 30px; background: linear-gradient(180deg,#fff 0%,#fbfcff 46%,#fff 100%); scroll-behavior: smooth; }
.panel-state { height: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--lz-text-muted); font-size: 11px; }
.ai-teacher-empty { min-height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; padding: 30px 15px; color: var(--lz-text-muted); text-align: center; }
.empty-mark { width: 44px; height: 44px; display: grid; place-items: center; border: 1px solid #e0e7ff; border-radius: 14px; color: var(--lz-brand); background: linear-gradient(145deg,#fff,#eef2ff); box-shadow: 0 8px 22px rgba(99,102,241,.1); }
.ai-teacher-empty strong { color: var(--lz-text-strong); font-size: 14px; }
.ai-teacher-empty p { max-width: 280px; margin: 0; color: var(--lz-text-muted); font-size: 11px; line-height: 1.6; }
.ai-message { margin-bottom: 24px; }
.ai-message.is-user { display: flex; justify-content: flex-end; }
.ai-message:not(.is-user) { display: grid; grid-template-columns: 28px minmax(0,1fr); align-items: start; gap: 11px; }
.user-message-bubble { max-width: 82%; padding: 10px 13px; border: 1px solid rgba(67,56,202,.12); border-radius: 16px 16px 5px 16px; color: #fff; background: #5547dd; box-shadow: 0 7px 18px rgba(67,56,202,.14), inset 0 1px 0 rgba(255,255,255,.14); font-size: 12px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.assistant-avatar { width: 28px; height: 28px; display: grid; place-items: center; border: 1px solid #e2e8f0; border-radius: 9px; color: #4f46e5; background: #fff; box-shadow: 0 4px 12px rgba(15,23,42,.06); }
.assistant-message-column { min-width: 0; display: grid; gap: 10px; }
.assistant-answer { min-width: 0; padding: 0 3px 2px 0; color: #334155; font-size: 12.5px; line-height: 1.76; overflow-wrap: anywhere; }
.assistant-answer.failed { padding: 9px 10px; border-left: 3px solid var(--lz-danger); border-radius: 0 7px 7px 0; color: var(--lz-danger); background: var(--lz-danger-soft); }
.assistant-answer :deep(.markdown-renderer) { color: inherit; font-size: inherit; line-height: inherit; }
.assistant-answer :deep(.markdown-renderer > :first-child) { margin-top: 0; }
.assistant-answer :deep(.markdown-renderer > :last-child) { margin-bottom: 0; }
.assistant-answer :deep(p) { margin: 0 0 .82em; }
.assistant-answer :deep(.markdown-renderer > p:first-child) { color: #475569; }
.assistant-answer :deep(h1),
.assistant-answer :deep(h2),
.assistant-answer :deep(h3),
.assistant-answer :deep(h4) { position: relative; margin: 1.45em 0 .62em; color: #25235d; font-weight: 760; letter-spacing: -.012em; line-height: 1.38; }
.assistant-answer :deep(h1) { font-size: 19px; }
.assistant-answer :deep(h2) { font-size: 17px; }
.assistant-answer :deep(h3) { padding-left: 11px; font-size: 15px; }
.assistant-answer :deep(h3::before) { position: absolute; top: .22em; bottom: .2em; left: 0; width: 3px; border-radius: 999px; background: #818cf8; content: ''; }
.assistant-answer :deep(h4) { font-size: 13.5px; }
.assistant-answer :deep(hr) { width: 38px; height: 2px; margin: 16px 0 18px; border: 0; border-radius: 999px; background: #c7d2fe; }
.assistant-answer :deep(strong) { color: #1e293b; font-weight: 720; }
.assistant-answer :deep(ul),
.assistant-answer :deep(ol) { margin: .7em 0 1em; padding: 10px 13px 10px 30px; border: 1px solid rgba(226,232,240,.9); border-radius: 10px; background: #fbfcff; }
.assistant-answer :deep(li) { padding-left: 2px; }
.assistant-answer :deep(li + li) { margin-top: .38em; }
.assistant-answer :deep(li::marker) { color: #6366f1; font-weight: 720; }
.assistant-answer :deep(blockquote) { margin: .85em 0 1em; padding: 9px 11px; border-left: 3px solid #a5b4fc; border-radius: 0 9px 9px 0; color: #475569; background: #f8fafc; }
.assistant-answer :deep(blockquote p:last-child) { margin-bottom: 0; }
.assistant-answer :deep(a) { color: #4f46e5; text-decoration-color: #c7d2fe; text-underline-offset: 3px; }
.assistant-answer :deep(code) { padding: .13em .38em; border: 1px solid #e2e8f0; border-radius: 5px; color: #4338ca; background: #f8fafc; font-size: .92em; }
.assistant-answer :deep(pre) { max-width: 100%; margin: .8em 0 1em; overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 10px; padding: 11px 12px; color: #e2e8f0; background: #172033; box-shadow: 0 8px 20px rgba(15,23,42,.08); }
.assistant-answer :deep(pre code) { padding: 0; border: 0; color: inherit; background: transparent; }
.assistant-answer :deep(table) { width: 100%; margin: .8em 0 1em; border-collapse: separate; border-spacing: 0; overflow: hidden; border: 1px solid #e2e8f0; border-radius: 10px; font-size: .94em; }
.assistant-answer :deep(th),
.assistant-answer :deep(td) { padding: 7px 9px; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; }
.assistant-answer :deep(th) { color: #312e81; background: #f8fafc; font-weight: 700; }
.assistant-answer :deep(tr:last-child td) { border-bottom: 0; }
.assistant-answer :deep(th:last-child),
.assistant-answer :deep(td:last-child) { border-right: 0; }
.thinking-line { height: 25px; display: flex; align-items: center; gap: 4px; }
.thinking-line i { width: 5px; height: 5px; border-radius: 50%; background: #a5b4fc; animation: thinking-pulse 1.2s ease-in-out infinite; }
.thinking-line i:nth-child(2) { animation-delay: .16s; }
.thinking-line i:nth-child(3) { animation-delay: .32s; }
.message-sources,.message-commands { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; color: var(--lz-text-muted); font-size: 9px; }
.message-sources > span { margin-right: 1px; }
.message-sources button { max-width: 180px; overflow: hidden; border: 0; border-radius: 5px; padding: 3px 6px; color: var(--lz-text-secondary); background: var(--lz-surface-muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.message-commands button { min-height: 27px; display: inline-flex; align-items: center; gap: 5px; padding: 0 7px; border: 1px solid #e0e7ff; border-radius: 7px; color: var(--lz-brand-strong); background: #fff; font-size: 9px; cursor: pointer; }
.message-commands button:hover { background: #f5f3ff; }

.action-proposal { min-width: 0; display: grid; grid-template-columns: 27px minmax(0,1fr); gap: 9px; padding: 10px; border: 1px solid #c7d2fe; border-radius: 9px; background: linear-gradient(135deg,#eef2ff,#faf5ff); }
.action-proposal__icon { width: 27px; height: 27px; display: grid; place-items: center; border-radius: 8px; color: var(--lz-brand); background: #fff; }
.action-proposal strong { color: #3730a3; font-size: 11px; }
.action-proposal p { margin: 3px 0 9px; color: var(--lz-text-secondary); font-size: 10px; line-height: 1.5; }
.primary-command,.secondary-command { min-height: 29px; display: inline-flex; align-items: center; justify-content: center; gap: 5px; padding: 0 9px; border-radius: 7px; font-size: 10px; font-weight: 700; cursor: pointer; }
.primary-command { border: 1px solid var(--lz-brand-strong); color: #fff; background: var(--lz-brand-strong); }
.secondary-command { border: 1px solid rgba(165,180,252,.8); color: var(--lz-text-secondary); background: rgba(255,255,255,.8); }
.action-receipt { min-width: 0; display: flex; align-items: center; gap: 7px; padding: 8px 9px; border-left: 3px solid var(--lz-success); border-radius: 0 8px 8px 0; color: #166534; background: var(--lz-success-soft); font-size: 10px; }
.action-receipt:not(.is-succeeded) { border-left-color: var(--lz-danger); color: #991b1b; background: var(--lz-danger-soft); }
.action-receipt span { min-width: 0; flex: 1; }
.action-receipt button { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 4px; border: 0; color: inherit; background: transparent; font-size: 9px; font-weight: 700; cursor: pointer; }

.ai-teacher-composer { flex: 0 0 auto; padding: 8px 12px calc(11px + env(safe-area-inset-bottom, 0px)); background: linear-gradient(180deg,rgba(255,255,255,.88),#fff 24%); box-shadow: 0 -10px 24px rgba(79,70,229,.035); }
.quick-actions { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 6px; margin-bottom: 8px; }
.quick-actions button { min-width: 0; min-height: 37px; display: flex; align-items: center; justify-content: center; gap: 5px; padding: 5px 6px; border: 1px solid #e0e7ff; border-radius: 9px; color: var(--lz-text-secondary); background: rgba(255,255,255,.92); font-size: 9px; line-height: 1.25; cursor: pointer; transition: color .16s ease, border-color .16s ease, background .16s ease, transform .16s ease; }
.quick-actions button:hover { transform: translateY(-1px); border-color: #c4b5fd; color: var(--lz-brand-strong); background: #f5f3ff; }
.composer-status,.offline-notice { display: flex; align-items: center; gap: 6px; margin-bottom: 7px; font-size: 9px; }
.composer-status { color: var(--lz-brand); }
.offline-notice { color: var(--lz-warning); }
.composer-box { min-height: 54px; display: grid; grid-template-columns: minmax(0,1fr) 38px; align-items: end; gap: 7px; padding: 6px 6px 6px 11px; border: 1px solid rgba(203,213,225,.9); border-radius: 13px; background: #fff; box-shadow: 0 5px 18px rgba(15,23,42,.06), inset 0 1px 0 rgba(255,255,255,.9); transition: border-color .16s ease, box-shadow .16s ease; }
.composer-box:focus-within { border-color: #a5b4fc; box-shadow: 0 7px 22px rgba(99,102,241,.1), 0 0 0 3px rgba(99,102,241,.08); }
.composer-box textarea { width: 100%; min-height: 40px; max-height: 144px; resize: none; overflow-y: auto; border: 0; padding: 6px 0 4px; color: var(--lz-text); background: transparent; font: inherit; font-size: 12px; line-height: 1.5; outline: none; }
.composer-box textarea::placeholder { color: var(--lz-text-muted); }
.composer-box textarea:disabled { cursor: not-allowed; }
.send-button { width: 38px; height: 38px; display: grid; place-items: center; border: 0; border-radius: 11px; color: #fff; background: linear-gradient(135deg,#6366f1,#8b5cf6); box-shadow: 0 6px 14px rgba(99,102,241,.22); cursor: pointer; transition: transform .16s ease, box-shadow .16s ease, background .16s ease; }
.send-button:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(99,102,241,.28); }
.send-button.is-stop { color: var(--lz-danger); background: var(--lz-danger-soft); box-shadow: none; }
.send-button:disabled { color: #cbd5e1; background: #f1f5f9; box-shadow: none; cursor: not-allowed; }

.spin { animation: spin 1s linear infinite; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes thinking-pulse { 0%,80%,100% { transform: translateY(0); opacity: .38; } 40% { transform: translateY(-4px); opacity: 1; } }

@media (max-width: 1023px) {
  .ai-teacher-panel.is-overlay { padding-bottom: calc(58px + env(safe-area-inset-bottom, 0px)); }
  .is-overlay .ai-teacher-surface { width: 100%; max-width: none; }
}

@media (max-width: 520px) {
  .ai-teacher-header { min-height: 58px; flex-basis: 58px; }
  .conversation-shell,.context-panel { margin-left: 10px; margin-right: 10px; }
  .ai-teacher-messages { padding: 16px 12px 24px; }
  .ai-teacher-composer { padding-left: 10px; padding-right: 10px; }
  .quick-actions { gap: 5px; }
  .quick-actions button { padding-inline: 4px; }
  .ai-message:not(.is-user) { grid-template-columns: 26px minmax(0,1fr); gap: 9px; }
  .assistant-avatar { width: 26px; height: 26px; border-radius: 8px; }
  .assistant-answer { font-size: 12.5px; }
  .assistant-answer :deep(h1) { font-size: 18px; }
  .assistant-answer :deep(h2) { font-size: 16.5px; }
  .assistant-answer :deep(h3) { font-size: 14.5px; }
  .user-message-bubble { max-width: 86%; }
  .action-proposal { grid-template-columns: 24px minmax(0,1fr); padding: 9px; }
  .proposal-actions { align-items: stretch; flex-direction: column; }
  .primary-command,.secondary-command { width: 100%; }
  .action-receipt { align-items: flex-start; flex-wrap: wrap; }
  .personalization-workspace { padding-inline:10px; }
  .personalization-diff-columns { grid-template-columns:1fr; }
}
</style>
