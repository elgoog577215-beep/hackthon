/**
 * 对话状态 store
 *
 * 把「每个会话的消息 / 流式生成状态 / 当前选中的会话」从 ChatView 组件搬到这里，
 * 让流式请求的生命周期与组件挂载解耦：
 *   - 用户离开 /chat 到别的路由时，ChatView 会被卸载，但 store 里仍在累积流式增量。
 *   - 用户在侧边栏切换到其它会话时，不再覆盖进行中的那条会话的本地 messages。
 * 回到对应会话时，组件从 store 读到最新的累积内容即可继续展示。
 */

import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'

import { sessionChatStream } from '../api/chat'

function classifyErrorMessage(err: Error): string {
  const msg = (err.message || '').toLowerCase()
  if (/connection\s*(error|refused)|econnrefused|connect\s+timeout/i.test(msg)) {
    return '模型服务暂时不可用，请稍后再试。如持续出现，请联系管理员检查服务状态。'
  }
  if (/rate.?limit|too many requests|429/i.test(msg)) {
    return '当前使用人数较多，模型正在排队处理中，请稍等片刻后重试。'
  }
  if (/timeout|timed?\s*out|deadline/i.test(msg)) {
    return '模型响应超时，可能是当前负载较高。请缩短输入内容或稍后重试。'
  }
  if (/请先登录|not authenticated|401/i.test(msg)) {
    return '登录已过期，请刷新页面重新登录。'
  }
  if (/500|internal server error/i.test(msg)) {
    return '服务器内部错误，请稍后重试。如反复出现请联系管理员。'
  }
  return `抱歉，服务出现了问题：${err.message || '未知错误'}。请稍后重试。`
}

export interface ChatAttachmentMeta {
  name: string
  /** 字节数；历史消息从后端加载时可能没有 size 信息 */
  size?: number
}

export interface ChatMessage {
  id: string
  role: 'assistant' | 'user'
  content: string
  /** 用户消息的结构化附件信息；仅当条消息由本会话发送时才有，历史消息走 content 里的 `[文件名]` 回退 */
  attachments?: ChatAttachmentMeta[]
}

/** 尚未分配 sessionId 的新会话在 store 中临时使用的 key */
export const NEW_CHAT_KEY = '__new__'

interface SessionState {
  messages: ChatMessage[]
  /** 该会话当前是否有进行中的流式请求 */
  streaming: boolean
  /** 是否还在等待第一块增量到达（用于「…」打字指示） */
  typing: boolean
  /** SSE loading / thinking 下发的进度说明，首段正文到达前展示 */
  progressStatus: string
  /** 复杂任务的全局规划文本（plan 事件累积），在 typing 阶段展示 */
  plan: string
  /** 正在被流式写入的助手消息 id；onChunk/onDone/onError 通过它定位消息 */
  assistantMsgId: string | null
  /** 已累积的流式文本（用于出错时回填、也便于外部观察） */
  streamed: string
}

function emptySession(): SessionState {
  return {
    messages: [],
    streaming: false,
    typing: false,
    progressStatus: '',
    plan: '',
    assistantMsgId: null,
    streamed: '',
  }
}

function genId() {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export interface SendMessageParams {
  /** 当前选中的会话 id；新会话传 null */
  sessionId: string | null
  query: string
  filePaths?: string[]
  /** 用户消息关联的附件元数据（name/size），用于在 UI 中渲染成附件卡片 */
  attachments?: ChatAttachmentMeta[]
  /** 新会话首条消息时，后端返回真正的 sessionId，会通过此回调通知调用方 */
  onSessionIdReceived?: (newId: string) => void
  onError?: (err: Error) => void
}

export const useChatStore = defineStore('chat', () => {
  /** 按 sessionId 或 NEW_CHAT_KEY 存储每个会话的状态 */
  const sessions = reactive<Record<string, SessionState>>({})
  /** 当前选中的会话 id；null 表示还没有选中具体会话（新会话） */
  const currentSessionId = ref<string | null>(null)

  function ensure(key: string): SessionState {
    if (!sessions[key]) sessions[key] = emptySession()
    return sessions[key]!
  }

  function keyOf(id: string | null): string {
    return id ?? NEW_CHAT_KEY
  }

  /** 组件用来渲染当前会话的响应式消息数组 */
  const currentMessages = computed<ChatMessage[]>(() => {
    return sessions[keyOf(currentSessionId.value)]?.messages ?? []
  })
  /** 当前会话是否正在流式生成（用于 send/attach 按钮禁用） */
  const isCurrentStreaming = computed<boolean>(() => {
    return sessions[keyOf(currentSessionId.value)]?.streaming ?? false
  })
  /** 当前会话是否处于「…」等待首块增量状态 */
  const isCurrentTyping = computed<boolean>(() => {
    return sessions[keyOf(currentSessionId.value)]?.typing ?? false
  })
  /** 流式等待阶段由 loading/thinking 事件更新的说明文案 */
  const currentProgressStatus = computed<string>(() => {
    return sessions[keyOf(currentSessionId.value)]?.progressStatus ?? ''
  })
  /** 复杂任务的全局规划文本，在 typing 阶段展示 */
  const currentPlan = computed<string>(() => {
    return sessions[keyOf(currentSessionId.value)]?.plan ?? ''
  })

  /** 用会话详情接口返回的历史消息替换指定会话的 messages；正在流式生成的会话不覆盖。 */
  function setMessages(id: string | null, msgs: ChatMessage[]) {
    const k = keyOf(id)
    if (sessions[k]?.streaming) return
    ensure(k).messages = msgs
  }

  /** 手动清空某会话的本地状态（例如删除会话） */
  function dropSession(id: string) {
    delete sessions[id]
  }

  /** 清除新会话临时槽（例如用户切走了新会话且没发任何消息） */
  function clearNewChat() {
    delete sessions[NEW_CHAT_KEY]
  }

  /**
   * 发送消息并流式接收回复。流式回调全部写进 store，因此即使 ChatView 在流中被卸载，
   * 增量依旧会累积到对应会话，用户回到该会话时可直接看到当前进度。
   */
  async function sendMessage(params: SendMessageParams): Promise<void> {
    const { sessionId, query, filePaths, attachments, onSessionIdReceived, onError } = params

    /** store 里用来定位该次流的 key；新会话在 onSessionId 回调里会迁移到真实 id */
    let key: string = keyOf(sessionId)
    const s = ensure(key)

    // 入栈用户消息（带结构化附件信息，便于前端渲染卡片）
    s.messages.push({
      id: genId(),
      role: 'user',
      content: query,
      attachments: attachments && attachments.length > 0 ? attachments : undefined,
    })

    const assistantMsgId = genId()
    s.assistantMsgId = assistantMsgId
    s.streamed = ''
    s.progressStatus = ''
    s.streaming = true
    s.typing = true
    let msgAdded = false

    await sessionChatStream(
      {
        query,
        session_id: sessionId ?? undefined,
        file_paths: filePaths && filePaths.length > 0 ? filePaths : undefined,
      },
      {
        onChunk(delta) {
          const current = sessions[key]
          if (!current) return
          current.streamed += delta
          current.progressStatus = ''
          current.plan = '' // 结果开始输出，plan 不再展示
          if (!msgAdded) {
            current.messages.push({
              id: assistantMsgId,
              role: 'assistant',
              content: current.streamed,
            })
            msgAdded = true
            current.typing = false
          } else {
            const idx = current.messages.findIndex((m) => m.id === assistantMsgId)
            if (idx !== -1) current.messages[idx]!.content = current.streamed
          }
        },
        onPlan(text) {
          const current = sessions[key]
          if (!current) return
          current.plan += text
        },
        onLoading(text) {
          const current = sessions[key]
          if (!current || !current.typing) return
          current.progressStatus = text.trim() || '正在处理…'
        },
        onThinking(text) {
          const current = sessions[key]
          if (!current || !current.typing) return
          current.progressStatus = text.trim() || '正在思考…'
        },
        onSessionId(newId) {
          if (key === newId) return
          // 把临时 key 下积累的流式状态迁移到真正的 sessionId
          const existing = sessions[newId]
          if (existing) {
            // 既有历史：把本次的新消息拼到历史末尾，继续往同一条助手消息里写
            existing.messages = [...existing.messages, ...(sessions[key]?.messages ?? [])]
            existing.streaming = true
            existing.typing = sessions[key]?.typing ?? false
            existing.progressStatus = sessions[key]?.progressStatus ?? ''
            existing.assistantMsgId = assistantMsgId
            existing.streamed = sessions[key]?.streamed ?? ''
          } else {
            sessions[newId] = sessions[key]!
          }
          delete sessions[key]
          key = newId
          // 若用户在发送那一刻就停留在新会话视图，则把当前选中切到真实 id；
          // 若他已手动跳到别的会话，保持用户的选择，不强行跳回。
          if (currentSessionId.value === null) {
            currentSessionId.value = newId
          }
          onSessionIdReceived?.(newId)
        },
        onDone(full) {
          const current = sessions[key]
          if (!current) return
          if (!msgAdded) {
            current.messages.push({
              id: assistantMsgId,
              role: 'assistant',
              content: full || '',
            })
          } else {
            const idx = current.messages.findIndex((m) => m.id === assistantMsgId)
            if (idx !== -1) current.messages[idx]!.content = full || current.streamed
          }
          current.progressStatus = ''
          current.plan = ''
          current.typing = false
          current.streaming = false
          current.assistantMsgId = null
        },
        onError(err) {
          const current = sessions[key]
          if (current) {
            const errorMsg = classifyErrorMessage(err)
            if (msgAdded) {
              const idx = current.messages.findIndex((m) => m.id === assistantMsgId)
              if (idx !== -1) current.messages[idx]!.content = current.streamed || errorMsg
            } else {
              current.messages.push({
                id: assistantMsgId,
                role: 'assistant',
                content: errorMsg,
              })
            }
            current.progressStatus = ''
            current.plan = ''
            current.typing = false
            current.streaming = false
            current.assistantMsgId = null
          }
          onError?.(err)
        },
      }
    )
  }

  return {
    sessions,
    currentSessionId,
    currentMessages,
    isCurrentStreaming,
    isCurrentTyping,
    currentProgressStatus,
    currentPlan,
    setMessages,
    dropSession,
    clearNewChat,
    sendMessage,
  }
})
