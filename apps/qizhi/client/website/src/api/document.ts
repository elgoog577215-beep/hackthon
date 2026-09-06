/**
 * 文档分析 API
 */
import { buildApiFullUrl, get, post, del } from './request'
import { buildAuthorizationHeader } from './authToken'

export interface DimensionScore {
  dimension: string
  score: number
  comments: string
  suggestions: string[]
}

export interface DimensionEvaluation {
  dimension: string
  score: number
  strengths: string[]
  weaknesses: string[]
  suggestions: string[]
}

export interface SegmentDetail {
  segment_index: number
  segment_title: string
  dimensions: DimensionEvaluation[]
}

export interface DocumentAnalysisResult {
  file_name: string
  file_type: string
  total_segments: number
  dimension_scores: DimensionScore[]
  overall_score: number
  radar_data: { dimension: string; score: number; fullScore: number }[]
  capability_summary: string
  improvement_suggestions: string[]
  segment_details: SegmentDetail[]
}

export interface AnalyzeDocCallbacks {
  onProgress: (message: string, progress: number) => void
  onDone: (result: DocumentAnalysisResult) => void
  onError: (err: Error) => void
}

export async function analyzeDocument(
  file: File,
  courseName: string,
  callbacks: AnalyzeDocCallbacks,
): Promise<void> {
  const { onProgress, onDone, onError } = callbacks

  const formData = new FormData()
  formData.append('file', file)
  if (courseName) formData.append('course_name', courseName)

  const authorization = buildAuthorizationHeader()
  if (!authorization) {
    onError(new Error('请先登录'))
    return
  }

  try {
    const url = buildApiFullUrl('/document/analyze')
    const response = await fetch(url, {
      method: 'POST',
      headers: { Authorization: authorization },
      body: formData,
    })

    if (!response.ok) {
      const text = await response.text()
      let message = `HTTP ${response.status}`
      try {
        const data = JSON.parse(text)
        if (data?.error) message = data.error
        else if (data?.detail)
          message = typeof data.detail === 'string' ? data.detail : String(data.detail)
      } catch {
        if (text) message = text.slice(0, 300)
      }
      onError(new Error(message))
      return
    }

    const stream = response.body
    if (!stream) {
      onError(new Error('无响应数据'))
      return
    }

    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const raw = line.slice(5).trim()
          if (!raw) continue
          try {
            const data = JSON.parse(raw)
            if (currentEvent === 'error') {
              onError(new Error(data.error || '分析失败'))
              return
            }
            if (currentEvent === 'end') {
              onDone(data as DocumentAnalysisResult)
              return
            }
            if (currentEvent === 'loading') {
              onProgress(data.message || '分析中...', data.progress ?? 0)
            }
          } catch {
            // skip unparseable
          }
          currentEvent = ''
        } else if (line.trim() === '') {
          currentEvent = ''
        }
      }
    }

    onError(new Error('分析流意外终止'))
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}

// ---------------------------------------------------------------------------
// 文档分析结果持久化 API
// ---------------------------------------------------------------------------

export interface DocHistoryItem {
  id: string
  file_name: string
  file_type: string
  overall_score: number
  create_time: string
}

export function saveDocumentResult(result: DocumentAnalysisResult): Promise<{ id: string }> {
  return post('/document/save-result', { result })
}

export function listDocumentHistory(): Promise<DocHistoryItem[]> {
  return get('/document/history')
}

export function getDocumentDetail(id: string): Promise<DocumentAnalysisResult> {
  return get(`/document/history/${id}`)
}

export function deleteDocumentRecord(id: string): Promise<{ message: string }> {
  return del(`/document/history/${id}`)
}
