import { withApiBase } from '../utils/http'

export interface GenerationStreamEvent<T = unknown> {
  event: string
  id?: string
  data: T
}

export interface GenerationProgress {
  status?: 'running' | 'completed' | 'failed'
  stage?: string
  message?: string
  delivery_mode?: 'token_stream' | 'buffered_fallback' | 'progress_stream'
  elapsed_ms?: number
}

export class GenerationStreamError extends Error {
  code: string
  httpStatus: number
  detail: Record<string, unknown>

  constructor(payload: Record<string, unknown>) {
    super(String(payload.message || payload.code || 'generation_failed'))
    this.name = 'GenerationStreamError'
    this.code = String(payload.code || 'generation_failed')
    this.httpStatus = Number(payload.http_status || 500)
    this.detail = payload
  }
}

export function parseSseBlock(block: string): GenerationStreamEvent | null {
  let event = ''
  let id = ''
  const dataLines: string[] = []
  block.replace(/\r\n/g, '\n').split('\n').forEach((line) => {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('id:')) id = line.slice(3).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  })
  if (!event || !dataLines.length) return null
  return {
    event,
    ...(id ? { id } : {}),
    data: JSON.parse(dataLines.join('\n')),
  }
}

export async function consumeEventStream(
  response: Response,
  onEvent: (event: GenerationStreamEvent) => void,
) {
  if (!response.body) throw new Error('generation_stream_unavailable')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    blocks.forEach((block) => {
      const event = parseSseBlock(block)
      if (event) onEvent(event)
    })
    if (done) break
  }
  if (buffer.trim()) {
    const event = parseSseBlock(buffer)
    if (event) onEvent(event)
  }
}

export async function postGenerationStream<T>(
  url: string,
  body: unknown,
  options: {
    headers?: HeadersInit
    signal?: AbortSignal
    onProgress?: (progress: GenerationProgress) => void
  } = {},
): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'text/event-stream')
  headers.set('Content-Type', 'application/json')
  const response = await fetch(withApiBase(url), {
    method: 'POST',
    headers,
    body: JSON.stringify(body ?? {}),
    signal: options.signal,
  })
  if (!response.ok) {
    const text = await response.text()
    let detail: Record<string, unknown> = { message: text || `HTTP ${response.status}` }
    try {
      const parsed = JSON.parse(text)
      detail = (parsed?.detail || parsed) as Record<string, unknown>
    } catch {
      // Keep the readable response text.
    }
    throw new GenerationStreamError({ ...detail, http_status: response.status })
  }
  if (!String(response.headers.get('Content-Type') || '').includes('text/event-stream')) {
    return await response.json() as T
  }

  let result: T | undefined
  let failure: GenerationStreamError | null = null
  await consumeEventStream(response, ({ event, data }) => {
    const payload = (data || {}) as Record<string, unknown>
    if (event === 'started' || event === 'heartbeat') {
      options.onProgress?.(payload as GenerationProgress)
    } else if (event === 'complete') {
      options.onProgress?.(payload as GenerationProgress)
      result = payload.result as T
    } else if (event === 'error') {
      failure = new GenerationStreamError(payload)
    }
  })
  if (failure) throw failure
  if (result === undefined) throw new Error('generation_stream_incomplete')
  return result
}
