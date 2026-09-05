import type { ResourceResponse } from '../api/types'
import { getResourceTypeLabel } from '../api/types'
import iconAirplayUrl from '../../image_materials/icon_airplay.svg'
import iconFiletextUrl from '../../image_materials/icon_filetext.svg'
import iconFileUrl from '../../image_materials/icon_file.svg'
import iconBookUrl from '../../image_materials/icon_book.svg'

export type ResourceCardDisplayKind = 'ppt' | 'outline' | 'teaching_plan' | 'question_bank' | 'file'

const RESOURCE_TYPE_CARD_META: Record<
  Exclude<ResourceCardDisplayKind, 'file'>,
  { typeLabel: string; typeColor: string; iconUrl: string }
> = {
  ppt: { typeLabel: 'PPT', typeColor: '#EF4444', iconUrl: iconAirplayUrl },
  outline: { typeLabel: '教学大纲', typeColor: '#3B82F6', iconUrl: iconFiletextUrl },
  teaching_plan: { typeLabel: '教案', typeColor: '#1E40AF', iconUrl: iconFileUrl },
  question_bank: { typeLabel: '习题集', typeColor: '#6B7280', iconUrl: iconBookUrl },
}

const RESOURCE_FILE_FALLBACK = {
  typeLabel: '文件',
  typeColor: '#6B7280',
  iconUrl: iconFileUrl,
  displayKind: 'file' as const,
}

export function getResourceTypeIconUrl(kind: ResourceCardDisplayKind): string {
  if (kind === 'file') return RESOURCE_FILE_FALLBACK.iconUrl
  return RESOURCE_TYPE_CARD_META[kind].iconUrl
}

export function formatResourceSize(resource: ResourceResponse): string {
  const fileSize = resource.file_size ?? 0
  if (fileSize > 0) {
    if (fileSize >= 1024 * 1024) {
      return `${(fileSize / (1024 * 1024)).toFixed(1)} MB`
    }
    if (fileSize >= 1024) {
      return `${(fileSize / 1024).toFixed(1)} KB`
    }
    return `${fileSize} B`
  }
  const wordCount = resource.word_count ?? 0
  if (wordCount > 0) return `${wordCount} 字`
  return '—'
}

export function resolveResourceDisplay(resource: ResourceResponse): {
  typeLabel: string
  displayKind: ResourceCardDisplayKind
  typeColor: string
} {
  const rt = (resource.resource_type ?? '').toString().toLowerCase()
  if (rt === 'ppt' || rt === 'outline' || rt === 'teaching_plan' || rt === 'question_bank') {
    const meta = RESOURCE_TYPE_CARD_META[rt]
    return { typeLabel: meta.typeLabel, displayKind: rt, typeColor: meta.typeColor }
  }

  const fmt = (resource.file_format ?? '').toLowerCase()
  const ext = resource.name?.includes('.')
    ? resource.name.split('.').pop()?.toLowerCase() ?? ''
    : ''
  const token = fmt || ext
  if (token === 'ppt' || token === 'pptx') {
    const meta = RESOURCE_TYPE_CARD_META.ppt
    return { typeLabel: meta.typeLabel, displayKind: 'ppt', typeColor: meta.typeColor }
  }

  const fallback = getResourceTypeLabel(resource.resource_type)
  return {
    typeLabel: fallback === '—' ? RESOURCE_FILE_FALLBACK.typeLabel : fallback,
    displayKind: 'file',
    typeColor: RESOURCE_FILE_FALLBACK.typeColor,
  }
}

export function buildResourceCardModel(resource: ResourceResponse, options?: { fallbackTags?: string[] }) {
  let modifiedDays = resource.modified_days ?? 0
  if (resource.update_time && !modifiedDays) {
    const updateTime = new Date(resource.update_time)
    modifiedDays = Math.floor((Date.now() - updateTime.getTime()) / (1000 * 60 * 60 * 24))
  }
  const { typeLabel, displayKind, typeColor } = resolveResourceDisplay(resource)
  const tags = resource.tags?.length
    ? resource.tags
    : options?.fallbackTags?.length
      ? options.fallbackTags
      : resource.related_course?.name
        ? [resource.related_course.name]
        : []
  return {
    id: resource.id,
    name: resource.name,
    typeLabel,
    displayKind,
    typeColor,
    modifiedDays,
    size: formatResourceSize(resource),
    tags,
  }
}
