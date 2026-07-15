import type { AxiosError } from 'axios'

export const MATERIAL_MAX_FILE_BYTES = 50 * 1024 * 1024

export const MATERIAL_ALLOWED_EXTENSIONS = new Set([
  'pdf', 'docx', 'pptx', 'xlsx', 'md', 'markdown', 'txt', 'csv', 'json', 'py', 'js', 'ts', 'html', 'css',
])

type FastApiIssue = { msg?: string; loc?: Array<string | number> }

const detailText = (detail: unknown): string => {
  if (typeof detail === 'string') return detail.trim()
  if (!Array.isArray(detail)) return ''
  return detail
    .map((issue: FastApiIssue) => {
      const field = issue.loc?.at(-1)
      if (field === 'file' && issue.msg === 'Field required') return '上传请求中没有识别到文件，请重新选择后重试'
      return issue.msg?.trim() || ''
    })
    .filter(Boolean)
    .join('；')
}

export const materialUploadErrorMessage = (error: unknown, fallback: string): string => {
  const response = (error as AxiosError<{ detail?: unknown; message?: unknown }>)?.response
  const detail = detailText(response?.data?.detail)
  if (detail) return detail
  const message = response?.data?.message
  if (typeof message === 'string' && message.trim()) return message.trim()
  return fallback
}

export const validateMaterialFile = (
  file: File,
  messages: { unsupported: (extension: string) => string; tooLarge: (maxMb: number) => string; empty: string },
): string => {
  const extension = file.name.split('.').pop()?.toLowerCase() || ''
  if (!MATERIAL_ALLOWED_EXTENSIONS.has(extension)) return messages.unsupported(extension || '—')
  if (file.size === 0) return messages.empty
  if (file.size > MATERIAL_MAX_FILE_BYTES) return messages.tooLarge(MATERIAL_MAX_FILE_BYTES / 1024 / 1024)
  return ''
}

export const formatFileSize = (bytes?: number): string => {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
