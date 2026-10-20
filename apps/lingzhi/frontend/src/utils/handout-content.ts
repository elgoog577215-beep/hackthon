import catalog from '../../../shared/handout-content-v1.json'

export type HandoutContentGroup = 'explanation' | 'practice' | 'question'
export type HandoutContentLocale = 'zh' | 'en'
export type HandoutContentType = {
  id: string; group: string | null; role: string; legacy?: boolean
  label: Record<HandoutContentLocale, string>
  purpose?: Record<HandoutContentLocale, string>
  checkpoints?: Record<HandoutContentLocale, string[]>
  example?: Record<HandoutContentLocale, string>
}

export const handoutContentCatalog = catalog
export const handoutContentGroups = catalog.groups
export const handoutContentTypes: HandoutContentType[] = catalog.types
const typesById = new Map(handoutContentTypes.map(item => [item.id, item]))
const aliases: Record<string, string> = {
  ...Object.fromEntries(handoutContentTypes.flatMap(item => Object.values(item.label).map(label => [label, item.id]))),
  ...catalog.aliases,
}

// Only explicit metadata determines classification; custom types stay readable.
export function handoutContentType(type: string): string {
  const value = type.trim()
  return aliases[value] || value
}

export function handoutContentGroup(type: string): HandoutContentGroup | undefined {
  return (handoutTypeDefinition(type)?.group || undefined) as HandoutContentGroup | undefined
}

export function handoutTypeDefinition(type: string): HandoutContentType | undefined {
  return typesById.get(handoutContentType(type))
}

export function handoutTypesForGroup(group: string): HandoutContentType[] {
  return handoutContentTypes.filter(item => item.group === group && !item.legacy)
}
