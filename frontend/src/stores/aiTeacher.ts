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

export interface AIActionReceipt {
  receipt_id: string
  proposal_id: string
  status: string
  action_type: string
  affected_refs: Array<Record<string, any>>
  summary: string
  failure_reason?: string
  undo_capability: string
  runtime_revision_after?: string
}

export interface AIMessage {
  message_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  status?: 'streaming' | 'complete' | 'failed'
  context_ref?: AIContextRef
  task_ref?: Record<string, any>
  sources?: Array<Record<string, any>>
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
  messages: AIMessage[]
  created_at: string
  updated_at: string
}

export interface SendAIMessagePayload {
  courseId: string
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

export interface SubmitAIAnswerFeedbackPayload {
  nodeId?: string
  nodeName?: string
  action: 'explain' | 'example' | 'simplify' | 'ask'
  contentAnchor?: Record<string, unknown>
}

const cacheKey = (courseId: string) => `ai_teacher_cache_v1:${courseId}`

export const useAITeacherStore = defineStore('aiTeacher', () => {
  const courseId = ref('')
  const conversations = ref<AIConversation[]>([])
  const currentConversationId = ref('')
  const loading = ref(false)
  const loadingConversations = ref(false)
  const error = ref<string | null>(null)
  const currentContext = ref<Record<string, any> | null>(null)
  const abortController = ref<AbortController | null>(null)
  let requestSequence = 0

  const currentConversation = computed(() => (
    conversations.value.find(item => item.conversation_id === currentConversationId.value) || null
  ))
  const messages = computed(() => currentConversation.value?.messages || [])

  function replaceConversation(conversation: AIConversation) {
    const index = conversations.value.findIndex(item => item.conversation_id === conversation.conversation_id)
    if (index >= 0) conversations.value[index] = conversation
    else conversations.value.unshift(conversation)
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
      conversations.value = Array.isArray(cached.conversations) ? cached.conversations : []
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
      conversations.value = response.data?.conversations || []
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

  async function createConversation(title = '') {
    if (!courseId.value) return null
    const response = await http.post('/api/ai-teacher/conversations', {
      course_id: courseId.value,
      title,
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
        assistantMessage.content ||= '已停止生成'
      } else {
        assistantMessage.status = 'failed'
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
    } else if (eventName === 'proposal') {
      assistantMessage.proposal = data
      assistantMessage.proposal_id = data.proposal_id
    } else if (eventName === 'receipt') {
      assistantMessage.receipt = data
      assistantMessage.receipt_id = data.receipt_id
    } else if (eventName === 'error') {
      assistantMessage.status = 'failed'
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
    message.receipt = response.data
    message.receipt_id = response.data.receipt_id
    target.status = response.data.status === 'succeeded' ? 'succeeded' : response.data.status
    await useLearningProgressStore().loadRuntime(courseId.value, target.target_ref?.node_id)
    persistCache()
    return response.data as AIActionReceipt
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
    message.receipt = response.data
    await useLearningProgressStore().loadRuntime(courseId.value, message.context_ref?.node_id)
    persistCache()
    return response.data as AIActionReceipt
  }

  return {
    courseId,
    conversations,
    currentConversationId,
    currentConversation,
    messages,
    loading,
    loadingConversations,
    error,
    currentContext,
    load,
    createConversation,
    selectConversation,
    deleteConversation,
    sendMessage,
    cancel,
    proposeForMessage,
    confirmProposal,
    submitAnswerFeedback,
    rejectProposal,
    undoReceipt,
  }
})
