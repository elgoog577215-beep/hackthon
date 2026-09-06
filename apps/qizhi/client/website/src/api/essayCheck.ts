/**
 * 论文检查 API
 */
import { get, del, postFormDataWithProgress, post } from './request'
import { buildAuthorizationHeader } from './authToken'

/** 任务列表/详情页自动刷新间隔（毫秒） */
export const ESSAY_AUTO_REFRESH_INTERVAL_MS = 300_000

export interface EssayTaskItem {
  id: string
  filename: string
  task_id: string
  status: string
  total_pages: number | null
  create_time: string
}

export interface EssayStatusData {
  task_id: string
  micro_task_id: string
  filename: string
  status: string
  current_stage: string
  progress: {
    total_pages: number
    completed_pages: number
    failed_pages: number
    pending_pages: number
    processing_pages: number
    percentage: number
  }
  pages: EssayPage[]
  total_pages: number | null
  overall_score: string | null
  summary: string | null
  check_domains: CheckDomain[] | null
  reference_issues: string[] | null
  recommendations: string[] | null
}

export interface EssayPage {
  id: string
  page_number: number
  image_url: string | null
  page_type: string | null
  extracted_content: Record<string, unknown> | null
  check_results: CheckResult[] | null
  status: string
  error_message: string | null
  retry_count: number
  created_at: string
  updated_at: string
}

export interface CheckResult {
  name: string
  check_point?: string
  passed: boolean
  detail: string | null
}

export interface EssayReport {
  task_id: string
  overall_score: string
  summary: string
  check_domains: CheckDomain[]
  reference_issues: string[] | null
  recommendations: string[] | null
}

export interface CheckDomain {
  domain: string
  check_points: CheckPoint[]
}

export interface CheckPoint {
  name: string
  passed: boolean
  detail: string | null
}

export async function uploadEssay(
  file: File,
  onUploadProgress?: (percentage: number) => void,
): Promise<{ success: boolean; data: string }> {
  const formData = new FormData()
  formData.append('file', file)
  return postFormDataWithProgress('/essay/upload', formData, onUploadProgress)
}

export interface EssayScoreCounts {
  qualified: number
  need_revision: number
  unqualified: number
}

export interface EssayDomainProblemStat {
  domain: string
  paper_count: number
  percentage: number
}

export interface EssayOverviewOtherStatus {
  processing: number
  failed: number
}

export interface EssayOverview {
  total_completed: number
  score_counts: EssayScoreCounts
  score_known: number
  top_problem_domains: EssayDomainProblemStat[]
  other_status: EssayOverviewOtherStatus
}

export async function listEssays(): Promise<{ success: boolean; data: EssayTaskItem[] }> {
  return get('/essay/list')
}

export async function getEssayOverview(): Promise<{ success: boolean; data: EssayOverview }> {
  return get('/essay/overview')
}

export async function getEssayStatus(taskId: string): Promise<{ success: boolean; data: EssayStatusData }> {
  return get(`/essay/status/${taskId}`)
}

export async function deleteEssay(taskId: string): Promise<{ success: boolean; data: null }> {
  return del(`/essay/${taskId}`)
}

/**
 * 导出进度回调参数
 */
export interface ExportProgress {
  current: number
  total: number
  filename: string
  status: 'done' | 'skipped' | 'error'
  message?: string
  phase?: 'collecting' | 'generating'
}

/**
 * 导出结果
 */
export interface ExportResult {
  token: string
  filename: string
  exportedCount: number
  total: number
}

/** Word 导出范围 */
export type EssayExportScope = 'summary_only' | 'summary_problem_pages' | 'full'

export const ESSAY_EXPORT_SCOPE_OPTIONS: {
  value: EssayExportScope
  label: string
  description: string
}[] = [
  {
    value: 'summary_only',
    label: '仅汇总报告',
    description: '总体评价、检查详情、参考文献问题与修改建议（不含逐页检查）',
  },
  {
    value: 'summary_problem_pages',
    label: '汇总 + 有问题页面',
    description: '在汇总报告基础上，附录未通过检查的页面明细',
  },
  {
    value: 'full',
    label: '完整报告',
    description: '包含全部页面的逐页检查结果',
  },
]

/**
 * 导出论文审查报告（SSE 进度流 + 最终下载）。
 * onProgress 回调用于展示进度，完成后自动触发下载。
 */
export async function exportReports(
  taskIds: string[],
  exportScope: EssayExportScope = 'summary_only',
  onProgress?: (progress: ExportProgress | { generating: true; message: string }) => void,
): Promise<ExportResult> {
  const { buildApiFullUrl } = await import('./request')
  const fullUrl = buildApiFullUrl('/essay/export/stream')

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  const authorization = buildAuthorizationHeader()
  if (authorization) headers.Authorization = authorization

  const response = await fetch(fullUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify({ task_ids: taskIds, export_scope: exportScope }),
  })

  if (!response.ok) {
    const text = await response.text()
    let message = `导出请求失败: ${response.status}`
    try {
      const data = JSON.parse(text)
      if (data?.error) message = data.error
    } catch {}
    throw new Error(message)
  }

  // 解析 SSE 流
  const reader = response.body?.getReader()
  if (!reader) throw new Error('不支持的响应流')

  const decoder = new TextDecoder()
  let buffer = ''

  return new Promise((resolve, reject) => {
    const readStream = async () => {
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          // 保留最后一个可能不完整的行
          buffer = lines.pop() || ''

          let eventType = ''
          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed || trimmed.startsWith(':')) continue
            if (trimmed.startsWith('event:')) {
              eventType = trimmed.slice(6).trim()
            } else if (trimmed.startsWith('data:')) {
              const dataStr = trimmed.slice(5).trim()
              try {
                const data = JSON.parse(dataStr)

                if (eventType === 'export_progress') {
                  onProgress?.(data as ExportProgress)
                } else if (eventType === 'export_generating') {
                  onProgress?.({ generating: true, message: data.message || '正在生成文件...' })
                } else if (eventType === 'export_complete') {
                  // 触发下载
                  const result = data as ExportResult
                  await downloadWithToken(result.token, result.filename)
                  resolve(result)
                  return
                } else if (eventType === 'error') {
                  reject(new Error(data.error || '导出失败'))
                  return
                }
              } catch {
                // 忽略解析错误
              }
            }
          }
        }
        reject(new Error('导出流异常结束'))
      } catch (e) {
        reject(e instanceof Error ? e : new Error('导出流读取失败'))
      }
    }
    void readStream()
  })
}

/**
 * 通过 token 下载导出文件。
 */
async function downloadWithToken(token: string, filename: string): Promise<void> {
  const { buildApiFullUrl } = await import('./request')
  const fullUrl = buildApiFullUrl(`/essay/export/download/${token}`)

  const headers: HeadersInit = {}
  const authorization = buildAuthorizationHeader()
  if (authorization) headers.Authorization = authorization

  const response = await fetch(fullUrl, { method: 'GET', headers })
  if (!response.ok) {
    const text = await response.text()
    let message = `下载失败: ${response.status}`
    try {
      const data = JSON.parse(text)
      if (data?.error) message = data.error
    } catch {}
    throw new Error(message)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
