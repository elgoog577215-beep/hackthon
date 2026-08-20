import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import http, { learnerIdentityHeaders, withApiBase } from '../utils/http'
import { useLearningProgressStore } from './learningProgress'
import logger from '../utils/logger'

export interface AIContextRef {
  course_id: string
  course_version_id?: string
  node_id?: string
  node_name?: string
  objective_id?: string
  objective_revision_id?: string
  content_anchor?: Record<string, unknown>
}

export interface AIActionProposal {
  proposal_id: string
  action_type: string
  target_ref: Record<string, any>
  payload_preview: Record<string, any>
  reason: string
  expected_effect: string
  confirmation_mode: string
  runtime_revision_id: string
  status: string
  undo_capability?: string
}

export type AIReceiptResultCode =
  | 'note_created'
  | 'issue_created'
  | 'review_task_created'
  | 'bookmark_created'
  | 'runtime_action_opened'
  | 'record_archived'
  | 'proposal_expired'
  | 'runtime_changed'
  | 'undo_target_changed'
  | 'proposal_rejected'
  | 'action_failed'
  | 'undo_not_supported'
  | 'undo_target_missing'

export interface AIActionReceipt {
  receipt_id: string
  proposal_id: string
  status: 'succeeded' | 'failed' | 'stale'
  /** Machine-readable outcome; the localized copy is derived from this, not from `summary`. */
  result_code?: AIReceiptResultCode
  schema_version?: string
  action_type: string
  affected_refs: Array<Record<string, any>>
  summary: string
  failure_reason?: string
  undo_capability: string
  runtime_revision_after?: string
  undo_of_receipt_id?: string
}

export type AIModelFailureCode =
  | 'model_not_configured'
  | 'model_auth_failed'
  | 'model_quota_exhausted'
  | 'model_request_too_large'
  | 'model_rate_limited'
  | 'model_timeout'
  | 'model_response_truncated'
  | 'model_unavailable'
  | 'cancelled'

export interface AIMessage {
  message_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  status?: 'streaming' | 'complete' | 'failed'
  /** Which classified model failure produced a `failed` turn. */
  failure_code?: AIModelFailureCode
  /** Whether retrying the same question could plausibly succeed. */
  failure_retryable?: boolean
  context_ref?: AIContextRef
  task_ref?: Record<string, any>
  sources?: Array<Record<string, any>>
  retrieval_status?: 'started' | 'completed' | 'failed_fallback_local'
  retrieval_receipt?: Record<string, any> | null
  proposal_id?: string
  receipt_id?: string
  proposal?: AIActionProposal | null
  receipt?: AIActionReceipt | null
  created_at?: string
}

export interface AIConversation {
  conversation_id: string
  course_id: string
  course_version_id?: string
  title: string
  revision: number
  retrieval_enabled?: boolean
  messages: AIMessage[]
  created_at: string
  updated_at: string
}

export interface SendAIMessagePayload {
  courseId: string
  perspective?: 'learner' | 'teacher'
  courseVersionId?: string
  nodeId?: string
  nodeName?: string
  question: string
  selection?: string
  entrypoint?: 'global' | 'selection' | 'practice' | 'continuity' | 'record' | 'block'
  contextRef?: AIContextRef
  taskRef?: Record<string, any>
  onAssistantMessage?: (message: AIMessage) => void
  onQuestionRecorded?: () => void | Promise<void>
}

export type AIAnswerFeedback = 'resolved' | 'unclear'

/**
 * Natural pauses at which a proactive suggestion may be offered. Deliberately
 * excludes reading — the owner's decision (2026-08-12) is that the AI never
 * interrupts mid-paragraph.
 */
export type SuggestionMoment = 'section_completed' | 'practice_submitted' | 'course_entered'

export interface AISuggestion {
  trigger_id: string
  trigger_type: string
  moment: SuggestionMoment
  node_id: string
  scope_ref: Record<string, any>
  severity: 'high' | 'medium'
  eligible_action: string
  runtime_action: Record<string, any>
  dedupe_key: string
  runtime_revision_id: string
  expires_at?: string
}

export interface SubmitAIAnswerFeedbackPayload {
  nodeId?: string
  nodeName?: string
  action: 'explain' | 'example' | 'simplify' | 'ask'
  contentAnchor?: Record<string, unknown>
}

const cacheKey = (courseId: string) => `ai_teacher_cache_v1:${courseId}`

/**
 * The learning session the interruption budget is counted against. Shared with
 * `learningSession.ts` so "2 per session" means the same session the rest of
 * the learning shell uses. The budget itself lives on the server; this is only
 * the key it is counted under.
 */
function learningSessionId() {
  try {
    const key = 'learning_session_id'
    const current = sessionStorage.getItem(key)
    if (current) return current
    const created = `session-${crypto.randomUUID()}`
    sessionStorage.setItem(key, created)
    return created
  } catch {
    return ''
  }
}

export const useAITeacherStore = defineStore('aiTeacher', () => {
  const courseId = ref('')
  const conversations = ref<AIConversation[]>([])
  const currentConversationId = ref('')
  const loading = ref(false)
  const loadingConversations = ref(false)
  const retrievalUpdating = ref(false)
  const error = ref<string | null>(null)
  const currentContext = ref<Record<string, any> | null>(null)
  const suggestion = ref<AISuggestion | null>(null)
  const abortController = ref<AbortController | null>(null)
  let requestSequence = 0

  const currentConversation = computed(() => (
    conversations.value.find(item => item.conversation_id === currentConversationId.value) || null
  ))
  const messages = computed(() => currentConversation.value?.messages || [])

  function replaceConversation(conversation: AIConversation) {
    const normalized = {
      ...conversation,
      retrieval_enabled: Boolean(conversation.retrieval_enabled),
    }
    const index = conversations.value.findIndex(item => item.conversation_id === conversation.conversation_id)
    if (index >= 0) conversations.value[index] = normalized
    else conversations.value.unshift(normalized)
    persistCache()
  }

  function persistCache() {
    if (!courseId.value) return
    try {
      localStorage.setItem(cacheKey(courseId.value), JSON.stringify({
        conversations: conversations.value,
        currentConversationId: currentConversationId.value,
      }))
    } catch (cacheError) {
      logger.warn('Failed to cache AI teacher conversations', cacheError)
    }
  }

  function loadCache(targetCourseId: string) {
    try {
      const cached = JSON.parse(localStorage.getItem(cacheKey(targetCourseId)) || 'null')
      if (!cached) return
      conversations.value = Array.isArray(cached.conversations)
        ? cached.conversations.map((conversation: AIConversation) => ({
            ...conversation,
            retrieval_enabled: Boolean(conversation.retrieval_enabled),
          }))
        : []
      currentConversationId.value = String(cached.currentConversationId || '')
    } catch (cacheError) {
      logger.warn('Failed to read AI teacher cache', cacheError)
    }
  }

  async function load(targetCourseId: string, _nodeId?: string) {
    if (!targetCourseId) return
    const sequence = ++requestSequence
    courseId.value = targetCourseId
    loadCache(targetCourseId)
    loadingConversations.value = true
    try {
      const response = await http.get('/api/ai-teacher/conversations', { params: { course_id: targetCourseId } })
      if (sequence !== requestSequence) return
      conversations.value = (response.data?.conversations || []).map((conversation: AIConversation) => ({
        ...conversation,
        retrieval_enabled: Boolean(conversation.retrieval_enabled),
      }))
      if (!conversations.value.length) {
        await createConversation()
      } else if (!conversations.value.some(item => item.conversation_id === currentConversationId.value)) {
        currentConversationId.value = conversations.value[0]?.conversation_id || ''
      }
      persistCache()
    } catch (loadError: any) {
      error.value = loadError?.message || 'conversation_load_failed'
    } finally {
      if (sequence === requestSequence) loadingConversations.value = false
    }
  }

  async function createConversation(title = '', retrievalEnabled = false) {
    if (!courseId.value) return null
    const response = await http.post('/api/ai-teacher/conversations', {
      course_id: courseId.value,
      title,
      retrieval_enabled: retrievalEnabled,
    })
    const conversation = response.data as AIConversation
    replaceConversation(conversation)
    currentConversationId.value = conversation.conversation_id
    persistCache()
    return conversation
  }

  async function selectConversation(conversationId: string) {
    currentConversationId.value = conversationId
    persistCache()
    const response = await http.get(`/api/ai-teacher/conversations/${conversationId}`, {
      params: { course_id: courseId.value },
    })
    replaceConversation(response.data)
  }

  async function deleteConversation(conversationId: string) {
    await http.delete(`/api/ai-teacher/conversations/${conversationId}`, {
      params: { course_id: courseId.value },
    })
    conversations.value = conversations.value.filter(item => item.conversation_id !== conversationId)
    if (currentConversationId.value === conversationId) {
      currentConversationId.value = conversations.value[0]?.conversation_id || ''
      if (!currentConversationId.value) await createConversation()
    }
    persistCache()
  }

  async function ensureConversation() {
    if (currentConversation.value) return currentConversation.value
    return createConversation()
  }

  async function updateRetrievalEnabled(enabled: boolean) {
    const conversation = currentConversation.value
    if (!conversation || retrievalUpdating.value) return
    retrievalUpdating.value = true
    error.value = null
    try {
      const response = await http.patch(
        `/api/ai-teacher/conversations/${conversation.conversation_id}/settings`,
        {
          course_id: courseId.value,
          retrieval_enabled: enabled,
          expected_revision: conversation.revision,
        },
      )
      replaceConversation(response.data as AIConversation)
    } catch (updateError: any) {
      if (Number(updateError?.response?.status || 0) === 409) {
        await refreshConversation(conversation.conversation_id)
        error.value = 'conversation_revision_conflict'
        return
      }
      error.value = updateError?.message || 'conversation_settings_update_failed'
      throw updateError
    } finally {
      retrievalUpdating.value = false
    }
  }

  async function sendMessage(payload: SendAIMessagePayload) {
    if (!payload.question.trim() || loading.value) return
    if (courseId.value !== payload.courseId) await load(payload.courseId, payload.nodeId)
    const conversation = await ensureConversation()
    if (!conversation) return
    const localUserId = `local-user-${crypto.randomUUID()}`
    const localAssistantId = `local-ai-${crypto.randomUUID()}`
    conversation.messages.push({
      message_id: localUserId,
      role: 'user',
      content: payload.question,
      status: 'complete',
      context_ref: payload.contextRef,
    })
    const pendingAssistantMessage: AIMessage = {
      message_id: localAssistantId,
      role: 'assistant',
      content: '',
      status: 'streaming',
      context_ref: payload.contextRef,
      sources: [],
      proposal: null,
      receipt: null,
    }
    conversation.messages.push(pendingAssistantMessage)
    // 从响应式会话数组中重新取得代理对象，保证流式状态变化能立即驱动块内 UI 更新。
    const assistantMessage = conversation.messages[conversation.messages.length - 1]!
    payload.onAssistantMessage?.(assistantMessage)
    persistCache()

    loading.value = true
    error.value = null
    abortController.value?.abort()
    const controller = new AbortController()
    abortController.value = controller
    try {
      const response = await fetch(withApiBase('/api/ask_events'), {
        method: 'POST',
        headers: learnerIdentityHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          request_id: localUserId,
          course_id: payload.courseId,
          conversation_id: conversation.conversation_id,
          perspective: payload.perspective || 'learner',
          entrypoint: payload.entrypoint || 'global',
          node_id: payload.nodeId || '',
          node_name: payload.nodeName || '',
          question: payload.question,
          selection: payload.selection || '',
          context_ref: payload.contextRef || {
            course_id: payload.courseId,
            course_version_id: payload.courseVersionId || '',
            node_id: payload.nodeId || '',
            node_name: payload.nodeName || '',
          },
          task_ref: payload.taskRef || {},
        }),
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const reader = response.body?.getReader()
      if (!reader) throw new Error('missing_stream')
      const decoder = new TextDecoder()
      let buffer = ''
      let questionRecordedNotified = false
      const notifyQuestionRecorded = () => {
        if (questionRecordedNotified) return
        questionRecordedNotified = true
        void Promise.resolve(payload.onQuestionRecorded?.()).catch((callbackError) => {
          logger.warn('Failed to refresh course growth after recording AI question', callbackError)
        })
      }
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
        let splitAt = buffer.indexOf('\n\n')
        while (splitAt >= 0) {
          handleEvent(
            buffer.slice(0, splitAt),
            assistantMessage,
            conversation,
            localUserId,
            notifyQuestionRecorded,
          )
          buffer = buffer.slice(splitAt + 2)
          splitAt = buffer.indexOf('\n\n')
        }
      }
      if (buffer.trim()) {
        handleEvent(
          buffer,
          assistantMessage,
          conversation,
          localUserId,
          notifyQuestionRecorded,
        )
      }
      assistantMessage.status = assistantMessage.status === 'failed' ? 'failed' : 'complete'
      await refreshConversation(conversation.conversation_id)
    } catch (sendError: any) {
      if (controller.signal.aborted || sendError?.name === 'AbortError') {
        assistantMessage.status = 'failed'
        assistantMessage.failure_code = 'cancelled'
        assistantMessage.failure_retryable = true
        assistantMessage.content ||= '已停止生成'
      } else {
        // A transport-level failure never reached the classifier, so report the
        // generic retryable code rather than pretending to know the cause.
        assistantMessage.status = 'failed'
        assistantMessage.failure_code = 'model_unavailable'
        assistantMessage.failure_retryable = true
        assistantMessage.content ||= 'AI 老师暂时不可用，课程和正式学习任务仍可继续使用。'
        error.value = sendError?.message || 'assistant_failed'
      }
    } finally {
      if (abortController.value === controller) abortController.value = null
      loading.value = false
      persistCache()
    }
  }

  function handleEvent(
    block: string,
    assistantMessage: AIMessage,
    conversation: AIConversation,
    localUserId: string,
    onQuestionRecorded?: () => void,
  ) {
    let eventName = ''
    const dataLines: string[] = []
    block.split('\n').forEach(line => {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    })
    if (!eventName || !dataLines.length) return
    let data: any
    try {
      data = JSON.parse(dataLines.join('\n'))
    } catch (parseError) {
      logger.warn('Failed to parse AI teacher event', parseError)
      return
    }
    if (eventName === 'context') {
      currentContext.value = data
      assistantMessage.message_id = data.assistant_message_id || assistantMessage.message_id
      const userMessage = conversation.messages.find(item => item.message_id === localUserId)
      if (userMessage && data.user_message_id) userMessage.message_id = data.user_message_id
      if (data.conversation_id) currentConversationId.value = data.conversation_id
      onQuestionRecorded?.()
    } else if (eventName === 'answer') {
      assistantMessage.content += data.chunk || ''
    } else if (eventName === 'final_answer') {
      assistantMessage.content = data.answer || assistantMessage.content
      if (data.message_id) assistantMessage.message_id = data.message_id
    } else if (eventName === 'sources') {
      assistantMessage.sources = data.sources || []
    } else if (eventName === 'retrieval') {
      assistantMessage.retrieval_status = data.status
      if (data.receipt) assistantMessage.retrieval_receipt = data.receipt
    } else if (eventName === 'proposal') {
      assistantMessage.proposal = data
      assistantMessage.proposal_id = data.proposal_id
    } else if (eventName === 'receipt') {
      assistantMessage.receipt = data
      assistantMessage.receipt_id = data.receipt_id
    } else if (eventName === 'error') {
      // The backend classifies the provider failure; keep the code so the UI
      // can say whether retrying is worth it, and keep any partial answer the
      // learner already read rather than replacing it with the error text.
      assistantMessage.status = 'failed'
      assistantMessage.failure_code = data.code || 'model_unavailable'
      assistantMessage.failure_retryable = data.retryable !== false
      assistantMessage.content ||= data.message || 'AI teacher unavailable'
    }
  }

  async function refreshConversation(conversationId: string) {
    const response = await http.get(`/api/ai-teacher/conversations/${conversationId}`, {
      params: { course_id: courseId.value },
    })
    replaceConversation(response.data)
  }

  function cancel() {
    abortController.value?.abort()
  }

  async function proposeForMessage(
    message: AIMessage,
    actionType: 'create_note' | 'create_issue' | 'create_review_task' | 'create_bookmark',
    payload: Record<string, any>,
    targetRef: Record<string, any>,
  ) {
    const response = await http.post('/api/ai-teacher/proposals', {
      course_id: courseId.value,
      conversation_id: currentConversationId.value,
      message_id: message.message_id,
      action_type: actionType,
      target_ref: targetRef,
      payload,
      reason: actionType === 'create_note' ? '用户明确选择保存当前回答。' : '用户明确选择创建学习记录。',
      confirmation_mode: 'user_command',
      origin: 'user_click',
    })
    message.proposal = response.data
    message.proposal_id = response.data.proposal_id
    return response.data as AIActionProposal
  }

  async function confirmProposal(message: AIMessage, proposal?: AIActionProposal) {
    const target = proposal || message.proposal
    if (!target) return null
    const response = await http.post(`/api/ai-teacher/proposals/${target.proposal_id}/confirm`, {
      course_id: courseId.value,
      idempotency_key: `web:${target.proposal_id}`,
    })
    const receipt = response.data as AIActionReceipt
    message.receipt = receipt
    message.receipt_id = receipt.receipt_id
    // A refused confirm (expired, rejected, runtime moved) still returns a
    // receipt. Reflect its real status so the proposal card stops offering
    // "confirm" on an action the server has already declined to run.
    target.status = receipt.status === 'succeeded' ? 'succeeded' : receipt.status
    if (receipt.status === 'succeeded') {
      await useLearningProgressStore().loadRuntime(courseId.value, target.target_ref?.node_id)
    }
    persistCache()
    return receipt
  }

  async function submitAnswerFeedback(
    message: AIMessage,
    feedback: AIAnswerFeedback,
    payload: SubmitAIAnswerFeedbackPayload,
  ) {
    const response = await http.post(
      `/api/ai-teacher/conversations/${currentConversationId.value}/messages/${message.message_id}/feedback`,
      {
        course_id: courseId.value,
        feedback,
        node_id: payload.nodeId || '',
        node_name: payload.nodeName || '',
        action: payload.action,
        content_anchor: payload.contentAnchor || {},
      },
    )
    return response.data as { status: 'recorded'; event_id: string; feedback: AIAnswerFeedback }
  }

  async function rejectProposal(message: AIMessage, reason: 'not_now' | 'irrelevant' | 'already_done' | 'never' = 'not_now') {
    if (!message.proposal) return
    await http.post(`/api/ai-teacher/proposals/${message.proposal.proposal_id}/reject`, {
      course_id: courseId.value,
      reason,
    })
    message.proposal.status = 'rejected'
    persistCache()
  }

  async function undoReceipt(message: AIMessage) {
    if (!message.receipt) return null
    const response = await http.post(`/api/ai-teacher/receipts/${message.receipt.receipt_id}/undo`, {
      course_id: courseId.value,
      idempotency_key: `web:undo:${message.receipt.receipt_id}`,
    })
    const receipt = response.data as AIActionReceipt
    message.receipt = receipt
    message.receipt_id = receipt.receipt_id
    // A refused undo leaves the original record untouched, so only a real
    // archive needs the runtime reloaded.
    if (receipt.status === 'succeeded') {
      await useLearningProgressStore().loadRuntime(courseId.value, message.context_ref?.node_id)
    }
    persistCache()
    return receipt
  }

  /**
   * Ask the server whether a proactive suggestion is justified at this moment.
   *
   * `moment` must be a natural pause — finishing a section, submitting a
   * practice attempt, or entering the course. Reading is deliberately not one:
   * every candidate here is a strong runtime action that keeps until the
   * learner comes up for air, so interrupting a paragraph buys nothing.
   *
   * All three gates (timing, frequency budget, refusal window) are enforced
   * server-side. This function only asks; it never decides.
   */
  async function checkSuggestion(moment: SuggestionMoment, nodeId?: string) {
    if (!courseId.value) return null
    try {
      const response = await http.get('/api/ai-teacher/trigger', {
        params: {
          course_id: courseId.value,
          node_id: nodeId || '',
          moment,
          session_id: learningSessionId(),
        },
      })
      const candidate = (response.data?.candidate || null) as AISuggestion | null
      suggestion.value = candidate
      return candidate
    } catch (suggestionError) {
      // A proactive suggestion is a nicety; never surface its failure.
      logger.warn('Failed to check AI teacher suggestion', suggestionError)
      return null
    }
  }

  /** Spend one unit of the interruption budget once the card is really visible. */
  async function markSuggestionShown(candidate: AISuggestion) {
    if (!candidate?.trigger_id || !courseId.value) return
    try {
      await http.post('/api/ai-teacher/trigger/shown', {
        course_id: courseId.value,
        trigger_id: candidate.trigger_id,
        dedupe_key: candidate.dedupe_key || '',
        node_id: candidate.node_id || '',
        session_id: learningSessionId(),
        moment: candidate.moment || '',
      })
    } catch (shownError) {
      logger.warn('Failed to record AI teacher suggestion delivery', shownError)
    }
  }

  /** Clear the local card. Persistent suppression is the reject endpoint's job. */
  function dismissSuggestion() {
    suggestion.value = null
  }

  /**
   * Tell the server the learner refused this suggestion.
   *
   * Must be persisted, not just cleared locally: the archived action protocol
   * requires a refusal to survive a refresh and follow the learner to another
   * device. `not_now` additionally gets a 24-hour floor server-side.
   */
  async function suppressSuggestion(candidate: AISuggestion, reason: 'not_now' | 'never') {
    if (!candidate?.dedupe_key || !courseId.value) return
    try {
      await http.post('/api/ai-teacher/trigger/suppress', {
        course_id: courseId.value,
        dedupe_key: candidate.dedupe_key,
        runtime_revision_id: candidate.runtime_revision_id || '',
        reason,
      })
    } catch (suppressError) {
      logger.warn('Failed to record AI teacher suggestion refusal', suppressError)
    }
  }

  return {
    courseId,
    conversations,
    currentConversationId,
    currentConversation,
    messages,
    loading,
    loadingConversations,
    retrievalUpdating,
    error,
    currentContext,
    suggestion,
    load,
    createConversation,
    selectConversation,
    deleteConversation,
    updateRetrievalEnabled,
    sendMessage,
    cancel,
    proposeForMessage,
    confirmProposal,
    submitAnswerFeedback,
    rejectProposal,
    undoReceipt,
    checkSuggestion,
    markSuggestionShown,
    dismissSuggestion,
    suppressSuggestion,
  }
})
