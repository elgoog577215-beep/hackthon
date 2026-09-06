/**
 * 智能对话 / 会话 API
 */

import { get, del, postStream } from './request'

const SESSION_PREFIX = '/session'

// ---------- 类型（与后端一致） ----------

export enum MessageRoleEnum {
  Assistant = 'assistant',
  User = 'user',
}

export enum MessageTypeEnum {
  Card = 'card',
  Text = 'text',
}

export enum CardSceneEnum {
  VideoAnalysis = 'video_analysis',
}

export interface CardResponse {
  id: string
  content: string
  scene: CardSceneEnum
  [k: string]: any
}

/** 会话历史单条（与后端 SessionHistoryMessage 一致，适配 ChatView） */
export interface SessionHistoryMessage {
  content: string
  role: string
  session_id: string
  type: string
  [k: string]: any
}

/** 会话摘要（与后端 SessionSummary 一致；列表接口返回） */
export interface SessionSummary {
  id: string
  title: string
  create_time: string
  update_time: string
  [k: string]: any
}

/** 会话详情（与后端 SessionDetail 一致；详情接口可返回 messages） */
export interface SessionDetail {
  id: string
  title: string
  create_time: string
  update_time: string
  messages?: SessionHistoryMessage[]
  [k: string]: any
}

/** @deprecated 流式 SSE 解析仍用；历史列表请用 SessionHistoryMessage */
export interface SessionMessage {
  role: string
  type: MessageTypeEnum
  content: string | CardResponse
  session_id?: string | null
  [k: string]: any
}

export interface ApiResponse<T> {
  data?: T | null
  success?: boolean
  error?: string | null
  [k: string]: any
}


/**
 * 聊天请求（与后端 ChatRequest 一致）
 * POST /chat，Header: Authorization: Bearer &lt;token&gt;
 */
export interface ChatRequest {
  query: string
  session_id?: string | null
  file_paths?: string[] | null
  extra_params?: Record<string, any> | null
  [k: string]: any
}

/** 附件文件 */
export interface ChatAttachment {
  id: string
  name: string
  size: number
  path?: string
  status: 'pending' | 'uploading' | 'done' | 'error'
  error?: string
}

// ---------- 接口 ----------

/**
 * 查询会话列表
 * GET /session/
 */
export async function listSessions(): Promise<SessionSummary[]> {
  const response = await get<ApiResponse<SessionSummary[]>>(`${SESSION_PREFIX}/list`)
  if (!response.success || !response.data) {
    throw new Error(response.error || '获取会话列表失败')
  }
  return response.data ?? []
}

/**
 * 按 id 查询会话详情（可含 messages）
 * GET /session?id=xxx
 * Header: Authorization: Bearer &lt;token&gt;
 */
export async function getSession(id: string): Promise<SessionDetail> {
  const response = await get<ApiResponse<SessionDetail>>(`${SESSION_PREFIX}`, { id })
  if (!response.success || !response.data) {
    throw new Error(response.error || '获取会话详情失败')
  }
  return response.data
}

/**
 * 删除会话
 * DELETE /session/delete?id=xxx
 */
export async function deleteSession(id: string): Promise<void> {
  const response = await del<ApiResponse<null>>(`${SESSION_PREFIX}/delete`, { id })
  if (!response.success) {
    throw new Error(response.error || '删除会话失败')
  }
}

/**
 * 解析 SSE 行，提取 event 和 data
 * 格式示例:
 *   event: start
 *   data: {"session_id": "xxx"}
 *
 *   event: message
 *   data: {"content": "xxx"}
 */
function parseSSELine(line: string): { event?: string; data?: string } {
  const out: { event?: string; data?: string } = {}
  if (line.startsWith('event:')) {
    out.event = line.slice(6).trim()
  } else if (line.startsWith('data:')) {
    out.data = line.slice(5).trim()
  }
  return out
}

/** 从 SSE data JSON 中取文本增量（兼容 message / chunk 等） */
function extractDeltaFromDataPayload(parsed: unknown): string {
  if (parsed == null) return ''
  if (typeof parsed === 'string') return parsed
  if (typeof parsed !== 'object') return ''
  const o = parsed as Record<string, unknown>
  if (typeof o.content === 'string') return o.content
  if (o.content != null && typeof o.content === 'object' && 'content' in (o.content as object)) {
    return String((o.content as { content?: unknown }).content ?? '')
  }
  return ''
}

/** 从 loading / thinking 等事件的 data 里取出可展示的说明文案 */
function extractStatusTextFromPayload(parsed: unknown): string {
  if (parsed == null) return ''
  if (typeof parsed === 'string') return parsed.trim()
  if (typeof parsed !== 'object') return ''
  const o = parsed as Record<string, unknown>
  const str = (v: unknown) => (typeof v === 'string' ? v.trim() : '')
  for (const k of ['message', 'status', 'label', 'text', 'detail', 'description', 'title']) {
    const t = str(o[k])
    if (t) return t
  }
  if (typeof o.content === 'string' && o.content.trim()) return o.content.trim()
  const c = o.content
  if (c && typeof c === 'object' && 'content' in (c as object)) {
    const inner = str((c as { content?: unknown }).content)
    if (inner) return inner
  }
  const step = o.step
  const total = o.total
  if (typeof step === 'number') {
    return typeof total === 'number' && total > 0
      ? `处理进度 ${step}/${total}`
      : `步骤 ${step}`
  }
  return ''
}

export interface SessionChatStreamCallbacks {
  onChunk: (delta: string) => void
  onSessionId?: (sessionId: string) => void
  /** SSE plan：全局规划文本（复杂任务第一轮输出） */
  onPlan?: (text: string) => void
  /** SSE loading：进度说明，用于缓解等待焦虑（文案来自后端 data，可为空） */
  onLoading?: (text: string) => void
  /** SSE thinking：推理/思考片段（可为空，由上层决定默认文案） */
  onThinking?: (text: string) => void
  onDone: (full: string) => void
  onError: (err: Error) => void
}

/** 前端入参：允许传可选字段，内部会补齐后端必填结构 */
export interface SessionChatStreamParams {
  query: string
  session_id?: string | null
  file_paths?: string[]
  extra_params?: Record<string, any>
}

/**
 * 发送消息，流式获取回复
 * POST /chat（SSE）
 *
 * 事件类型（与接口说明一致）：start / loading / thinking / message / card / error
 * 兼容后端仍可能下发的 chunk、step 等内部类型（chunk 视为正文增量；step 忽略）
 */
export async function sessionChatStream(
  params: SessionChatStreamParams,
  callbacks: SessionChatStreamCallbacks
): Promise<void> {
  const { onChunk, onSessionId, onPlan, onLoading, onThinking, onDone, onError } = callbacks
  try {
    const body: ChatRequest = {
      query: params.query,
    }
    if (params.session_id != null && params.session_id !== '') {
      body.session_id = params.session_id
    }
    if (params.file_paths != null && params.file_paths.length > 0) {
      body.file_paths = params.file_paths
    }
    if (params.extra_params != null) {
      body.extra_params = params.extra_params
    }
    const response = await postStream('/ai/chat', body)
    if (!response.ok) {
      const text = await response.text()
      let message = `HTTP ${response.status}`
      try {
        const data = JSON.parse(text)
        if (data?.error) message = data.error
        else if (data?.detail) message = typeof data.detail === 'string' ? data.detail : String(data.detail)
      } catch {
        if (text) message = text.slice(0, 300)
      }
      if (response.status === 401 || /not authenticated/i.test(message)) message = '请先登录'
      onError(new Error(message))
      return
    }
    const stream = response.body
    if (!stream) {
      onDone('')
      return
    }
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let full = ''
    let buffer = ''
    const seenSessionIds = new Set<string>()
    let currentEvent: string | null = null
    let currentData: string | null = null

    const applyEnvelope = (eventName: string | null, rawData: string) => {
      if (!rawData) return
      let parsed: unknown
      try {
        parsed = JSON.parse(rawData)
      } catch {
        if (eventName === 'error') {
          throw new Error(rawData || '流式响应错误')
        }
        return
      }

      // 兼容：data 为完整对象 { type: "chunk" | "message" | "start" | ... }
      if (
        parsed &&
        typeof parsed === 'object' &&
        'type' in (parsed as object) &&
        typeof (parsed as { type?: unknown }).type === 'string'
      ) {
        const t = (parsed as { type: string }).type
        const obj = parsed as Record<string, unknown>

        if (t === 'start') {
          const sid = (obj.session_id ?? obj.sessionId) as string | undefined
          if (sid && onSessionId && !seenSessionIds.has(sid)) {
            seenSessionIds.add(sid)
            onSessionId(sid)
          }
          return
        }
        if (t === 'message' || t === 'chunk') {
          const delta = extractDeltaFromDataPayload(parsed)
          if (delta !== '') {
            full += delta
            onChunk(delta)
          }
          return
        }
        if (t === 'plan') {
          const delta = extractDeltaFromDataPayload(parsed)
          if (delta !== '') {
            onPlan?.(delta)
          }
          return
        }
        if (t === 'loading') {
          onLoading?.(extractStatusTextFromPayload(parsed))
          return
        }
        if (t === 'thinking') {
          onThinking?.(extractStatusTextFromPayload(parsed))
          return
        }
        if (t === 'card' || t === 'step') {
          return
        }
        if (t === 'error') {
          const msg =
            typeof obj.message === 'string'
              ? obj.message
              : typeof obj.error === 'string'
                ? obj.error
                : '服务暂时不可用，请稍后重试'
          throw new Error(msg)
        }
        return
      }

      // 标准：依赖 SSE event 名
      const ev = (eventName || '').toLowerCase()
      if (ev === 'start') {
        const o = parsed as Record<string, unknown>
        const sid = (o.session_id ?? o.sessionId) as string | undefined
        if (sid && onSessionId && !seenSessionIds.has(sid)) {
          seenSessionIds.add(sid)
          onSessionId(sid)
        }
        return
      }
      if (ev === 'message' || ev === 'chunk') {
        const delta = extractDeltaFromDataPayload(parsed)
        if (delta !== '') {
          full += delta
          onChunk(delta)
        }
        return
      }
      if (ev === 'plan') {
        const delta = extractDeltaFromDataPayload(parsed)
        if (delta !== '') {
          onPlan?.(delta)
        }
        return
      }
      if (ev === 'loading') {
        onLoading?.(extractStatusTextFromPayload(parsed))
        return
      }
      if (ev === 'thinking') {
        onThinking?.(extractStatusTextFromPayload(parsed))
        return
      }
      if (ev === 'card') {
        return
      }
      if (ev === 'error') {
        const o = parsed as Record<string, unknown>
        const msg =
          typeof o.message === 'string'
            ? o.message
            : typeof o.error === 'string'
              ? o.error
              : typeof o.detail === 'string'
                ? o.detail
                : rawData
        throw new Error(msg || '流式响应错误')
      }
    }

    const processSseMessage = () => {
      if (currentData == null) return
      try {
        applyEnvelope(currentEvent, currentData)
      } catch (e) {
        throw e instanceof Error ? e : new Error(String(e))
      } finally {
        currentEvent = null
        currentData = null
      }
    }

    const processChunk = (text: string) => {
      buffer += text
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (line.trim() === '') {
          processSseMessage()
        } else {
          const { event, data } = parseSSELine(line)
          if (event !== undefined) {
            currentEvent = event
          } else if (data !== undefined) {
            currentData = data
          }
        }
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      processChunk(decoder.decode(value, { stream: true }))
    }
    processChunk('\n')
    // 处理最后可能未发送的消息
    processSseMessage()
    onDone(full)
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}

export { uploadAttachment, uploadAttachment as uploadChatFile } from './attachment'
