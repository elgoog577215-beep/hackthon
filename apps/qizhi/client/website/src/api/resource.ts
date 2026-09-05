/**
 * 资源相关 API
 */

import { buildApiFullUrl, get, post, getBlob, postStream, postFormData } from './request'
import {
  OperationEnum,
  ResourceTypeEnum,
  type ApiResponse,
  type ResourceResponse,
  type ResourceListParams,
  type ResourceOperationParams,
  type ResourceGenerateParams,
  type OutlineGenerateParams,
  type ResourceBindingRequest,
} from './types'
import type { DownloadFormat } from './types'

const API_PREFIX = '/resource'

/** 根据资源类型获取 AI 生成接口路径（大纲/教案/题库已迁移到 /ai 前缀） */
function getGeneratePath(resourceType: ResourceTypeEnum): string {
  switch (resourceType) {
    case ResourceTypeEnum.Outline:
      return '/ai/outline'
    case ResourceTypeEnum.TeachingPlan:
      return '/ai/teaching_plan'
    case ResourceTypeEnum.QuestionBank:
      return '/ai/question_bank'
    case ResourceTypeEnum.Ppt:
      return '/ai/ppt'
    default:
      return `${API_PREFIX}/generate`
  }
}

/** 判断上传回参是否为存储路径而非资源主键 id */
export function isLikelyResourceFilePath(value: string): boolean {
  const v = value.trim()
  if (!v) return false
  return /[\\/]/.test(v) || /^uploads[/\\]/i.test(v)
}

/** 从 uploads/resources/{id}.ext 形式路径提取资源 id（文件名去扩展名） */
export function extractResourceIdFromUploadPath(path: string): string {
  const normalized = path.replace(/\\/g, '/').trim()
  const base = normalized.split('/').filter(Boolean).pop() ?? normalized
  return base.replace(/\.[^.]+$/, '')
}

/** 从路径中取文件名（用于 uploads/ 与 /static/ 等不同前缀的路径比对） */
function resourcePathBasename(path: string): string {
  const normalized = path.replace(/\\/g, '/').trim()
  return normalized.split('/').filter(Boolean).pop() ?? normalized
}

/** 判断两条存储路径是否指向同一上传文件 */
function resourcePathsReferToSameFile(a: string, b: string): boolean {
  const na = a.replace(/\\/g, '/').trim()
  const nb = b.replace(/\\/g, '/').trim()
  if (!na || !nb) return false
  if (na === nb) return true
  if (na.endsWith(`/${nb}`) || nb.endsWith(`/${na}`)) return true
  return resourcePathBasename(na) === resourcePathBasename(nb)
}

/** 从上传接口 data 中解析资源主键 id（兼容 id 字符串、{ id }；存储路径不是资源 id） */
export function parseResourceIdFromUploadPayload(data: unknown): string {
  if (data == null || data === '') return ''
  if (typeof data === 'string') {
    const s = data.trim()
    if (!s) return ''
    // 上传回参为 uploads/... 或 /static/... 时，文件名并非数据库资源主键
    if (isLikelyResourceFilePath(s)) return ''
    return s
  }
  if (typeof data === 'number' && Number.isFinite(data)) return String(data)
  if (typeof data === 'object') {
    const record = data as Record<string, unknown>
    const candidate = record.id ?? record.resource_id ?? record.resourceId
    if (candidate != null && candidate !== '') {
      const s = String(candidate).trim()
      if (isLikelyResourceFilePath(s)) return ''
      return s
    }
  }
  return ''
}

/**
 * 若上传接口已直接创建资源（回参为资源主键 id 且可查到），返回该 id；否则返回 null
 */
async function tryResolveExistingResourceId(data: unknown): Promise<string | null> {
  const raw = typeof data === 'string' ? data.trim() : ''
  if (!raw) return null

  // 上传接口通常只返回存储路径，勿将路径中的文件名当作资源 id 去 query
  if (isLikelyResourceFilePath(raw)) {
    return findResourceIdByStoredPath(raw)
  }

  const primary = parseResourceIdFromUploadPayload(data)
  if (!primary) return null
  try {
    const detail = await queryResource(primary)
    if (detail?.id) return detail.id
  } catch {
    // 回参不是有效资源 id
  }
  return null
}

/** 上传回参为文件路径时，通过 operation create + path 创建只读资源记录 */
async function createResourceFromUploadedFilePath(
  filePath: string,
  file: File,
  opts?: { resourceType?: ResourceTypeEnum; relatedUserId?: string },
): Promise<string> {
  const path = filePath.trim()
  if (!path) {
    throw new Error('上传资源失败：未返回文件路径')
  }
  const name = (file.name || '未命名文件').trim() || '未命名文件'
  const resourceId = await operateResource({
    operation: OperationEnum.CREATE,
    name,
    path,
    editable: false,
    resource_type: opts?.resourceType ?? ResourceTypeEnum.Outline,
    related_user_id: opts?.relatedUserId,
  })
  let id = parseResourceIdFromUploadPayload(resourceId) || String(resourceId ?? '').trim()
  if (!id || isLikelyResourceFilePath(id)) {
    id = (await findResourceIdByStoredPath(path)) ?? ''
  }
  if (!id) {
    throw new Error('创建资源失败，未返回资源 id')
  }
  return id
}

async function findResourceIdByStoredPath(storedPath: string): Promise<string | null> {
  const normalized = storedPath.replace(/\\/g, '/').trim()
  let list: ResourceResponse[] = []
  try {
    list = await listResources({})
  } catch {
    return null
  }
  for (const item of list.slice(0, 80)) {
    try {
      const detail = await queryResource(item.id)
      const p = getResourceFilePath(detail).replace(/\\/g, '/')
      if (!p) continue
      if (resourcePathsReferToSameFile(p, normalized)) {
        return detail.id
      }
    } catch {
      continue
    }
  }
  return null
}

/**
 * 获取只读上传文档的正文（Markdown）。
 * query 有 content 则直接返回；否则通过 operation copy 触发服务端 convert_file_to_markdown。
 */
export async function resolveReadonlyResourceMarkdown(resourceId: string): Promise<string> {
  const detail = await queryResource(resourceId)
  const existing = (detail.content ?? '').trim()
  if (existing) return existing

  const filePath = getResourceFilePath(detail)
  if (!filePath) return ''

  const tempId = await operateResource({
    operation: OperationEnum.COPY,
    id: resourceId,
    name: `__outline_extract_${Date.now()}`,
  })
  if (!tempId) {
    throw new Error('无法解析参考文档内容')
  }

  try {
    const copied = await queryResource(tempId)
    return (copied.content ?? '').trim()
  } finally {
    try {
      await operateResource({ operation: OperationEnum.DELETE, id: tempId })
    } catch (e) {
      console.warn('[resource] 删除临时文档提取副本失败', e)
    }
  }
}

/** 资源详情中的只读文件路径（后端 path，兼容 file_path） */
export function getResourceFilePath(
  data: ResourceResponse | Record<string, unknown> | null | undefined
): string {
  if (!data || typeof data !== 'object') return ''
  const d = data as Record<string, unknown>
  return String(d.path ?? d.file_path ?? '').trim()
}

/**
 * 查询单个资源（Query Resource 接口）
 * GET /resource?id=xxx
 * @param id 资源 ID（string，与后端 Request.id 一致）
 * @returns 返回 data：id, name, resource_type, file_path, file_format, file_size, create_time, update_time
 */
export async function queryResource(id: string | number): Promise<ResourceResponse> {
  const response = await get<ApiResponse<ResourceResponse>>(
    `${API_PREFIX}`,
    { id: String(id) }
  )

  if (!response.success) {
    throw new Error(response.error || '查询资源失败')
  }
  if (!response.data) {
    throw new Error('资源不存在或无权访问，请重新上传或选择其他文档')
  }

  const data = response.data
  return data
}

/**
 * 列出资源
 * @param params 查询参数
 */
export async function listResources(
  params: ResourceListParams = {}
): Promise<ResourceResponse[]> {
  const response = await get<ApiResponse<ResourceResponse[]>>(
    `${API_PREFIX}/list`,
    params
  )

  if (!response.success) {
    throw new Error(response.error || '获取资源列表失败')
  }

  return response.data ?? []
}

/**
 * 资源操作（/resource/operation）
 * POST 请求体：operation（必填）, id?, name?, content?, path?, file?, editable?, related_course_id?, related_unit_id?, resource_type?
 * @param params 操作参数
 * @returns 成功时返回 data 字符串（如新建资源的 id 或提示信息）
 */
export async function operateResource(
  params: ResourceOperationParams
): Promise<string> {
  const body: Record<string, unknown> = {
    operation: params.operation,
  }
  if (params.id != null) body.id = params.id
  if (params.name != null) body.name = params.name
  if (params.content != null) body.content = params.content
  if (params.path != null) body.path = params.path
  if (params.file != null) body.file = params.file
  // CREATE 必须带 editable；未传时默认可编辑（避免后端 BizException: editable 不能为空）
  if (params.operation === OperationEnum.CREATE) {
    body.editable = params.editable ?? true
  } else if (params.editable != null) {
    body.editable = params.editable
  }
  if (params.related_user_id != null) body.related_user_id = params.related_user_id
  if (params.related_course_id != null) body.related_course_id = params.related_course_id
  if (params.related_unit_id != null) body.related_unit_id = params.related_unit_id
  if (params.parent_resource_id != null) body.parent_resource_id = params.parent_resource_id
  if (params.resource_type != null) body.resource_type = params.resource_type

  const response = await post<ApiResponse<string>>(
    `${API_PREFIX}/operation`,
    body
  )

  if (!response.success) {
    throw new Error(response.error || '操作资源失败')
  }

  return response.data ?? ''
}

/**
 * 绑定或取绑资源（POST /resource/binding）
 * 请求体：
 * - id（必填，string）
 * - related_course_id?: null | string
 * - related_unit_id?: null | string
 * - unbind?: boolean（为 true 时执行解绑）
 * @param params 资源绑定参数
 */
export async function bindResource(params: ResourceBindingRequest): Promise<void> {
  const { id, ...rest } = params
  const body: Record<string, unknown> = { ...rest, id: String(id) }
  const response = await post<ApiResponse<null>>(
    `${API_PREFIX}/binding`,
    body
  )
  if (!response.success) {
    throw new Error(response.error || '资源绑定失败')
  }
}

/**
 * 生成资源（根据类型路由到 /ai/outline、/ai/teaching_plan、/ai/question_bank）
 * @param params 生成参数：operation、resource_type 必填；source_resource_id、previous_content、outline_form、prompt 可选
 * @returns 成功时返回 data.result 字符串（生成结果内容或 URL 等）
 */
export async function generateResource(
  params: ResourceGenerateParams
): Promise<{ result: string }> {
  const response = await post<ApiResponse<{ result: string }>>(
    getGeneratePath(params.resource_type),
    params
  )
  if (!response.success) {
    throw new Error(response.error || '生成资源失败')
  }
  const data = response.data as { result?: string; response?: string } | undefined
  return { result: data?.result ?? data?.response ?? '' }
}

export interface GenerateResourceStreamCallbacks {
  onChunk: (delta: string) => void
  onDone: (full: string) => void
  onError: (err: Error) => void
  /** 4 步流水线阶段进度（analyze / generate / verify / refine）；后端以 loading 事件下发 */
  onStage?: (stage: string, message: string) => void
}

/**
 * SSE 文本增量原样传递，保留换行符。
 * 此前会去掉「仅 \\n」的 chunk 或单块末尾的 \\n，导致 Markdown 段落/标题无法换行（大纲若观感正常多因分块差异；教案/题目表现更明显）。
 */
function normalizeStreamDelta(delta: string): string {
  if (typeof delta !== 'string' || delta === '') return delta
  return delta
}

/** 还原 content 中的转义：\\n -> 换行等（与后端转义一致） */
function unescapeContent(raw: string): string {
  return raw
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\r/g, '\r')
    .replace(/\\'/g, "'")
    .replace(/\\\\/g, '\\')
}

/** LangChain / OpenAI 等可能返回 string 或 content block 数组，统一为可拼接文本 */
function normalizeMessageContentToString(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'number' || typeof raw === 'boolean') return String(raw)
  if (Array.isArray(raw)) {
    const parts: string[] = []
    for (const block of raw) {
      if (typeof block === 'string') parts.push(block)
      else if (block && typeof block === 'object') {
        const b = block as Record<string, unknown>
        if (typeof b.text === 'string') parts.push(b.text)
        else if (typeof b.content === 'string') parts.push(b.content)
      }
    }
    return parts.join('')
  }
  if (typeof raw === 'object') {
    const o = raw as Record<string, unknown>
    if (typeof o.text === 'string') return o.text
  }
  return ''
}

/**
 * 从 SSE 一帧的 data JSON 中取正文增量（与 /chat 解析策略对齐，兼容 resource 流）
 */
function extractDeltaFromResourceSsePayload(parsed: unknown, eventName: string | null): string | null {
  if (parsed == null) return null
  if (typeof parsed === 'string') {
    const s = parsed.trim()
    if (!s || s === '[DONE]') return null
    return parsed
  }
  // Raw SSE text chunks can be valid JSON primitives. For example a model token
  // containing only `5` is parsed as the number 5, but it is still display text.
  if (typeof parsed === 'number' || typeof parsed === 'boolean') {
    return String(parsed)
  }
  if (typeof parsed !== 'object') return null
  const o = parsed as Record<string, unknown>
  const ev = (eventName || '').toLowerCase()

  if (ev === 'error' || o.type === 'error' || (typeof o.error === 'string' && o.error.trim())) {
    const msg =
      typeof o.message === 'string' && o.message.trim()
        ? o.message
        : typeof o.error === 'string' && o.error.trim()
          ? o.error
          : typeof o.detail === 'string' && o.detail.trim()
            ? o.detail
            : '流式响应错误'
    throw new Error(msg)
  }

  if ('type' in o && typeof o.type === 'string') {
    const t = o.type.toLowerCase()
    if (t === 'start' || t === 'end' || t === 'loading' || t === 'thinking' || t === 'card') return null
    if (t === 'message' || t === 'chunk') {
      const delta = normalizeMessageContentToString(o.content)
      return delta === '' ? null : delta
    }
  }

  const choices = o.choices
  if (Array.isArray(choices) && choices[0] && typeof choices[0] === 'object') {
    const c0 = choices[0] as Record<string, unknown>
    const deltaObj = c0.delta
    if (deltaObj && typeof deltaObj === 'object') {
      const d = deltaObj as Record<string, unknown>
      const fromDelta = normalizeMessageContentToString(d.content)
      if (fromDelta !== '') return fromDelta
    }
  }

  if (o.content != null) {
    const s = normalizeMessageContentToString(o.content)
    if (s !== '') return s
  }
  if (typeof o.text === 'string' && o.text !== '') return o.text
  if (typeof o.delta === 'string' && o.delta !== '') return o.delta
  const data = o.data
  if (data && typeof data === 'object') {
    const inner = data as Record<string, unknown>
    if (inner.content != null) {
      const s = normalizeMessageContentToString(inner.content)
      if (s !== '') return s
    }
  }

  return null
}

function parseSseLine(line: string): { event?: string; data?: string } {
  const out: { event?: string; data?: string } = {}
  if (line.startsWith('event:')) {
    out.event = line.slice(6).trim()
  } else if (line.startsWith('data:')) {
    // 只去掉 data: 后的一个空格，保留内容本身的前导/尾随空格
    let d = line.slice(5)
    if (d.startsWith(' ')) d = d.slice(1)
    out.data = d
  }
  return out
}

/**
 * 从 SSE 的 data 行中提取 content。
 * 支持：
 * - 标准 JSON：data: {"role":"ai","content":"..."} 或 data: {"data":{"content":"..."}}
 * - Python 单引号 dict：data: {'role': 'ai', 'content': '...'}（注意不是 JSON）
 */
function parseSSEDataLine(line: string): string | null {
  const trimmed = line.trim()
  if (!trimmed.startsWith('data:')) return null
  const raw = trimmed.slice(5).trimStart()
  if (!raw) return null

  // 1) 标准 JSON（双引号）
  try {
    const delta = extractDeltaFromResourceSsePayload(JSON.parse(raw), null)
    if (delta !== null) return delta
  } catch {
    // 非 JSON，继续尝试 Python 单引号 dict
  }

  // 2) Python 单引号 dict（data: {'role': 'ai', 'content': '...'}）
  const pyMatch = raw.match(/'content'\s*:\s*'((?:[^'\\]|\\.)*)'/)
  if (pyMatch && pyMatch[1] !== undefined) return unescapeContent(pyMatch[1])

  return null
}

/**
 * 解析后端返回的单行格式（兼容多种历史实现）。
 * 1) SSE：event/message 行忽略；data 行用 parseSSEDataLine
 * 2) 旧格式：role=... type=... content='...' session_id=...（可能也会带 data: 前缀）
 */
function parseResourceStreamLine(line: string): string | null {
  const trimmed = line.trim()
  if (!trimmed) return null

  // 标准 SSE：event: xxx 行不包含内容
  if (trimmed.startsWith('event:')) return null

  // SSE data 行（JSON 或 Python dict）
  const fromSse = parseSSEDataLine(trimmed)
  if (fromSse !== null) return normalizeStreamDelta(fromSse)

  // 旧格式（兼容）
  const toParse = trimmed.startsWith('data:') ? trimmed.slice(5).trimStart() : trimmed
  const match = toParse.match(/content='((?:[^'\\]|\\.)*)'/)
  if (!match || match[1] === undefined) return null
  return normalizeStreamDelta(unescapeContent(match[1]))
}

/** 让出主线程，便于流式时界面及时刷新 */
function yieldToBrowser(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

/** 组装 POST /ai/outline 请求体（仅四字段，避免 operation 等被后端忽略或干扰） */
export function buildOutlineGenerateBody(
  params: Pick<
    ResourceGenerateParams,
    'outline_form' | 'previous_content' | 'prompt' | 'selected_text'
  > & { resource_id?: string | null },
): OutlineGenerateParams {
  const body: OutlineGenerateParams = {}
  if (params.outline_form != null) {
    body.outline_form = params.outline_form
  }
  const rid = params.resource_id
  if (rid != null && String(rid).trim() !== '') {
    body.resource_id = String(rid).trim()
  }
  const prev = params.previous_content
  if (prev != null && String(prev).trim() !== '') {
    body.previous_content = String(prev)
  }
  const prompt = params.prompt
  if (prompt != null && String(prompt).trim() !== '') {
    body.prompt = String(prompt).trim()
  }
  const selected = params.selected_text
  if (selected != null && String(selected).trim() !== '') {
    body.selected_text = String(selected).trim()
  }
  return body
}

/**
 * 流式生成教学大纲（POST /ai/outline）
 * 请求体仅包含 outline_form / previous_content / prompt / selected_text（不传 null 字段）
 */
export async function generateOutlineStream(
  params: OutlineGenerateParams,
  callbacks: GenerateResourceStreamCallbacks,
): Promise<void> {
  const body = buildOutlineGenerateBody({
    outline_form: params.outline_form,
    previous_content: params.previous_content,
    resource_id: params.resource_id,
    prompt: params.prompt,
    selected_text: params.selected_text,
  })
  if (!body.outline_form && !body.previous_content && !body.resource_id) {
    callbacks.onError(new Error('表单数据不能为空'))
    return
  }
  return consumeGenerateStreamResponse(
    await postStream('/ai/outline', body),
    callbacks,
    'outline',
  )
}

async function consumeGenerateStreamResponse(
  response: Response,
  callbacks: GenerateResourceStreamCallbacks,
  label: string,
): Promise<void> {
  const { onChunk, onDone, onError, onStage } = callbacks
  try {
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

    const contentType = (response.headers.get('content-type') || '').toLowerCase()
    const body = response.body

    if (!body) {
      onDone('')
      return
    }

    if (contentType.includes('application/json')) {
      const text = await response.text()
      let result = ''
      if (text) {
        try {
          const data = JSON.parse(text) as {
            result?: string
            response?: string
            data?: string
            success?: boolean
            error?: string
          }
          if (data?.success === false && data?.error) {
            onError(new Error(data.error))
            return
          }
          result = data?.result ?? data?.response ?? data?.data ?? ''
        } catch {
          result = text
        }
      }
      if (result) onChunk(result)
      onDone(result)
      return
    }

    const reader = body.getReader()
    const decoder = new TextDecoder()
    let full = ''
    let buffer = ''
    let currentEvent: string | null = null
    let currentData: string | null = null

    /**
     * 标准 SSE：event / data 可多行，空行表示一帧结束（与 sse-starlette /chat 一致）。
     * 旧实现按单 \\n 切行且忽略 event，会导致 data 与 event 不同帧时解析失败或漏字。
     */
    const flushSseMessage = async () => {
      if (currentData == null) {
        currentEvent = null
        return
      }
      let parsed: unknown
      try {
        parsed = JSON.parse(currentData)
      } catch {
        const rawDelta = normalizeStreamDelta(currentData)
        if (rawDelta) {
          full += rawDelta
          onChunk(rawDelta)
          await yieldToBrowser()
        }
        currentEvent = null
        currentData = null
        return
      }
      // 阶段进度（4 步流水线）：loading / card 事件不含正文，单独回调 onStage 后跳过
      const evName = (currentEvent || '').toLowerCase()
      if (evName === 'loading' || evName === 'card') {
        if (onStage && parsed && typeof parsed === 'object') {
          const o = parsed as Record<string, unknown>
          const stage = typeof o.stage === 'string' ? o.stage : ''
          const message =
            typeof o.message === 'string'
              ? o.message
              : typeof o.content === 'string'
                ? o.content
                : ''
          onStage(stage, message)
        }
        currentEvent = null
        currentData = null
        return
      }
      try {
        const extracted = extractDeltaFromResourceSsePayload(parsed, currentEvent)
        if (extracted !== null && extracted !== '') {
          const piece = normalizeStreamDelta(extracted)
          full += piece
          onChunk(piece)
          await yieldToBrowser()
        }
      } finally {
        currentEvent = null
        currentData = null
      }
    }

    const processRawChunk = async (text: string) => {
      buffer += text
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.trim() === '') {
          await flushSseMessage()
        } else {
          const { event, data } = parseSseLine(line)
          if (event !== undefined) currentEvent = event
          if (data !== undefined) {
            // 同一消息内的多行 data 按 \n 拼接（SSE 规范）
            currentData = currentData == null ? data : currentData + '\n' + data
          }
        }
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      await processRawChunk(decoder.decode(value, { stream: true }))
    }
    await processRawChunk('\n')
    await flushSseMessage()

    // 兼容：非标准 SSE、整段无空行分隔时，退回旧行解析
    if (!full.trim() && buffer.trim()) {
      for (const line of buffer.split(/\n/)) {
        const content = parseResourceStreamLine(line)
        if (content !== null) {
          full += content
          onChunk(content)
          await yieldToBrowser()
        }
      }
    }
    // 仍无正文：将残余 buffer 当作纯文本（部分网关会整段返回非 SSE 文本）
    if (!full.trim() && buffer.trim()) {
      const plain = buffer
        .split(/\r?\n/)
        .filter((line) => !line.startsWith('event:') && !line.startsWith(':'))
        .map((line) => (line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line))
        .join('\n')
        .trim()
      if (plain) {
        full = plain
        onChunk(plain)
      }
    }
    onDone(full)
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}

/**
 * 生成资源（流式，根据类型路由到 /ai/outline、/ai/teaching_plan、/ai/question_bank）
 * 后端返回流时逐块调用 onChunk，结束时调用 onDone(fullText)；若后端返回 JSON 则一次性 onChunk(result) + onDone(result)
 */
export async function generateResourceStream(
  params: ResourceGenerateParams,
  callbacks: GenerateResourceStreamCallbacks
): Promise<void> {
  try {
    const path = getGeneratePath(params.resource_type)
    const body =
      params.resource_type === ResourceTypeEnum.Outline
        ? buildOutlineGenerateBody(params)
        : params
    const response = await postStream(path, body)
    return consumeGenerateStreamResponse(
      response,
      callbacks,
      params.resource_type,
    )
  } catch (err) {
    callbacks.onError(err instanceof Error ? err : new Error(String(err)))
  }
}

/** /ai/ppt 本地生成结果：可交互 HTML 预览地址 + 可下载 .pptx 地址 */
export interface PptDeckResult {
  html_url: string
  pptx_url: string
  title: string
  slides: number
}

export interface PptGenerateBody {
  source_resource_id?: string | null
  prompt?: string | null
  resource_id?: string | null
  previous_content?: string | null
}

export interface GeneratePptDeckCallbacks {
  onProgress?: (msg: string) => void
  onComplete: (result: PptDeckResult) => void
  onError: (err: Error) => void
}

/**
 * 本地生成 PPT（SSE）：流式回传进度（loading 事件 {content}），
 * 完成时回传文件地址（end 事件 {html_url, pptx_url, title, slides}）。
 */
export async function generatePptDeck(
  body: PptGenerateBody,
  cb: GeneratePptDeckCallbacks,
): Promise<void> {
  try {
    const response = await postStream('/ai/ppt', body)
    if (!response.ok) {
      const text = await response.text().catch(() => '')
      let message = `HTTP ${response.status}`
      if (text) {
        try {
          const data = JSON.parse(text)
          message = data?.error || data?.detail || message
        } catch {
          message = text.slice(0, 300)
        }
      }
      if (response.status === 401 || /not authenticated/i.test(message)) message = '请先登录'
      throw new Error(message)
    }
    const stream = response.body
    if (!stream) throw new Error('PPT 生成无响应体')

    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let evt: string | null = null
    let data: string | null = null
    let result: PptDeckResult | null = null

    const flush = () => {
      if (data == null) {
        evt = null
        return
      }
      let parsed: unknown = data
      try {
        parsed = JSON.parse(data)
      } catch {
        /* 保留原始字符串 */
      }
      const ev = (evt || '').toLowerCase()
      const obj = (parsed && typeof parsed === 'object') ? (parsed as Record<string, unknown>) : null
      if (ev === 'error' || (obj && typeof obj.error === 'string' && obj.error)) {
        const msg = (obj && ((obj.error as string) || (obj.message as string))) || 'PPT 生成失败'
        throw new Error(msg)
      }
      if (ev === 'loading') {
        const msg = obj ? String(obj.content ?? '') : String(parsed ?? '')
        if (msg && cb.onProgress) cb.onProgress(msg)
      } else if (ev === 'end' && obj && typeof obj.html_url === 'string') {
        result = {
          html_url: obj.html_url as string,
          pptx_url: String(obj.pptx_url ?? ''),
          title: String(obj.title ?? ''),
          slides: Number(obj.slides ?? 0),
        }
      }
      evt = null
      data = null
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.trim() === '') {
          flush()
        } else if (line.startsWith('event:')) {
          evt = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const d = line.slice(5).replace(/^ /, '')
          data = data == null ? d : data + '\n' + d
        }
      }
    }
    flush()

    if (!result) throw new Error('PPT 生成未返回结果')
    cb.onComplete(result)
  } catch (err) {
    cb.onError(err instanceof Error ? err : new Error(String(err)))
  }
}

export interface UploadResourceFileOptions {
  /** 创建资源时的类型，大纲文档链路默认 outline */
  resourceType?: ResourceTypeEnum
  relatedUserId?: string
}

/**
 * 上传资源文件并返回资源主键 id。
 * 1. POST /resource/upload：落盘，回参多为文件路径
 * 2. 若回参已是资源 id 且可查到详情，直接返回
 * 3. 否则 POST /resource/operation（create）：path、resource_type（默认 outline）、editable=false、name
 */
export async function uploadResourceFile(
  file: File,
  opts: UploadResourceFileOptions = {},
): Promise<string> {
  const uploadPath = `${API_PREFIX}/upload`
  const formData = new FormData()
  formData.append('file', file)
  const response = await postFormData<ApiResponse<string | null>>(uploadPath, formData)
  if (!response.success) {
    throw new Error(response.error || '上传资源失败')
  }

  const existingId = await tryResolveExistingResourceId(response.data)
  if (existingId) return existingId

  const raw = typeof response.data === 'string' ? response.data.trim() : ''
  const filePath =
    raw && isLikelyResourceFilePath(raw)
      ? raw
      : raw && !isLikelyResourceFilePath(raw)
        ? null
        : parseResourceIdFromUploadPayload(response.data)

  if (filePath && isLikelyResourceFilePath(filePath)) {
    return createResourceFromUploadedFilePath(filePath, file, {
      resourceType: opts.resourceType,
      relatedUserId: opts.relatedUserId,
    })
  }

  throw new Error('上传资源失败：未返回资源 id 或文件路径')
}

/**
 * 下载资源文件（GET /resource/download）
 * 请求参数：id、format（docx | md）；回参为文件流，触发浏览器下载
 * @param id 资源 ID
 * @param format 导出格式：docx | md
 * @param suggestedName 建议文件名（不含扩展名），用于下载时的文件名
 */
export async function downloadResource(
  id: string,
  format: DownloadFormat,
  suggestedName?: string
): Promise<void> {
  const blob = await getBlob(`${API_PREFIX}/download`, { id, format })
  const ext = format === 'docx' ? '.docx' : '.md'
  const name = (suggestedName || `resource-${id}`).replace(/[/\\?*:|"]/g, '_') + ext
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
