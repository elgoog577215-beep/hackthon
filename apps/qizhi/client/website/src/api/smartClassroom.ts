import { post, postStream } from './request'

export interface SmartClassroomFetchRequest {
  /**
   * Download Video，是否将回放下载到本地上传目录
   */
  download_video?: boolean
  /**
   * Sub Id，章节 sub_id
   */
  sub_id: string
  /**
   * Tenant Code，租户编码，默认取服务端配置
   */
  tenant_code?: null | string
  [property: string]: any
}

export interface SmartClassroomFetchResult {
  /**
   * Detail，上游 data 对象
   */
  detail: Record<string, unknown>
  /**
   * Video Bytes，已写入本地的字节数
   */
  video_bytes?: number | null
  /**
   * Video Local Url，下载完成后的可访问路径，形如 /static/smart_classroom/xxx.mp4
   */
  video_local_url?: null | string
  /**
   * Video Play Url，上游原始回放地址（短时有效）
   */
  video_play_url?: null | string
  [property: string]: any
}

export interface ApiResponse<T> {
  data?: T | null
  error?: string | null
  success?: boolean
  [property: string]: any
}

const FETCH_URL = '/smart-classroom/sub-detail/fetch'
const FETCH_STREAM_URL = '/smart-classroom/sub-detail/fetch-stream'

export async function fetchSmartClassroomSubDetail(
  params: SmartClassroomFetchRequest
): Promise<SmartClassroomFetchResult> {
  const res = await post<ApiResponse<SmartClassroomFetchResult>>(FETCH_URL, params)
  if (!res.success || !res.data) {
    throw new Error(res.error || '拉取章节详情失败')
  }
  return res.data
}

export type SmartClassroomStreamDetailEvent = {
  detail: Record<string, unknown>
  video_play_url?: string | null
}
export type SmartClassroomStreamProgressEvent = {
  received: number
  total: number | null
}
export type SmartClassroomStreamDoneEvent = {
  video_local_url: string | null
  video_bytes: number | null
  video_play_url?: string | null
}
export type SmartClassroomStreamErrorEvent = {
  error: string
}

export type SmartClassroomStreamEvent =
  | { type: 'detail'; data: SmartClassroomStreamDetailEvent }
  | { type: 'progress'; data: SmartClassroomStreamProgressEvent }
  | { type: 'done'; data: SmartClassroomStreamDoneEvent }
  | { type: 'error'; data: SmartClassroomStreamErrorEvent }
  | { type: 'unknown'; event: string; dataText: string }

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/**
 * POST SSE 解析器：处理形如
 * event: detail
 * data: {...}
 *
 * event: progress
 * data: {...}
 */
export async function fetchSmartClassroomSubDetailStream(
  params: SmartClassroomFetchRequest,
  onEvent: (ev: SmartClassroomStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await postStream(FETCH_STREAM_URL, params)
  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    throw new Error(text?.slice(0, 200) || `HTTP error! status: ${resp.status}`)
  }
  const ct = resp.headers.get('content-type') || ''
  if (!/text\/event-stream/i.test(ct)) {
    // 兼容后端误返回 JSON（例如报错时）
    const text = await resp.text().catch(() => '')
    const maybe = safeJsonParse(text)
    if (maybe && typeof maybe === 'object' && (maybe as any).error) {
      throw new Error(String((maybe as any).error))
    }
    throw new Error('SSE 响应类型错误（非 text/event-stream）')
  }

  if (!resp.body) {
    throw new Error('SSE 响应体为空')
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  let currentEvent = 'message'
  let dataLines: string[] = []

  const flushEvent = () => {
    const dataText = dataLines.join('\n').trim()
    const eventName = currentEvent || 'message'
    if (!dataText) {
      dataLines = []
      currentEvent = 'message'
      return
    }
    const parsed = safeJsonParse(dataText)
    if (eventName === 'detail') {
      onEvent({ type: 'detail', data: (parsed as any) ?? { detail: {} } })
    } else if (eventName === 'progress') {
      onEvent({ type: 'progress', data: (parsed as any) ?? { received: 0, total: null } })
    } else if (eventName === 'done') {
      onEvent({ type: 'done', data: (parsed as any) ?? { video_local_url: null, video_bytes: null } })
    } else if (eventName === 'error') {
      onEvent({ type: 'error', data: (parsed as any) ?? { error: dataText } })
    } else {
      onEvent({ type: 'unknown', event: eventName, dataText })
    }
    dataLines = []
    currentEvent = 'message'
  }

  try {
    while (true) {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以 \n\n 分隔事件块，但可能跨 chunk；用逐行解析更稳
      while (true) {
        const idx = buffer.indexOf('\n')
        if (idx === -1) break
        let line = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 1)
        if (line.endsWith('\r')) line = line.slice(0, -1)

        if (line === '') {
          flushEvent()
          continue
        }
        if (line.startsWith(':')) {
          // comment line
          continue
        }
        if (line.startsWith('event:')) {
          currentEvent = line.slice('event:'.length).trim() || 'message'
          continue
        }
        if (line.startsWith('data:')) {
          dataLines.push(line.slice('data:'.length).trimStart())
          continue
        }
        // 兼容没有 field 的裸行：当作 data
        dataLines.push(line)
      }
    }
    // flush tail
    flushEvent()
  } finally {
    try {
      reader.releaseLock()
    } catch {
      //
    }
  }
}
