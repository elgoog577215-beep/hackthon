/**
 * 通用附件上传（智能对话、反馈表单等共用）
 * POST /attachment/upload，multipart 字段 file；回参 ApiResponse[str]，data 为存储路径
 */

import { postFormData } from './request'
import type { ApiResponse } from './types'

/** 前端允许的扩展名（小写、带点），与各页面 accept / 校验保持一致 */
export const COMMON_ATTACHMENT_EXTENSIONS = [
  '.txt',
  '.md',
  '.pdf',
  '.doc',
  '.docx',
  '.ppt',
  '.pptx',
  '.xls',
  '.xlsx',
  '.jpg',
  '.jpeg',
  '.png',
  '.gif',
  '.webp',
  '.bmp',
  '.svg',
  '.mp4',
  '.webm',
  '.mov',
  '.mkv',
  '.avi',
  '.m4v',
] as const

export function fileExtensionLower(file: File): string {
  const parts = file.name.split('.')
  if (parts.length < 2) return ''
  return '.' + parts.pop()!.toLowerCase()
}

export function isExtensionAllowed(file: File, allowed: readonly string[] = COMMON_ATTACHMENT_EXTENSIONS): boolean {
  const ext = fileExtensionLower(file)
  return ext !== '' && (allowed as readonly string[]).includes(ext)
}

export async function uploadAttachment(file: File): Promise<string> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await postFormData<ApiResponse<string | null>>('/attachment/upload', formData)
  if (!response.success || response.data == null || response.data === '') {
    throw new Error(response.error || '上传失败')
  }
  return response.data
}
