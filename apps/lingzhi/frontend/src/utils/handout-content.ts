import catalog from '../../../shared/handout-content-v1.json'

export type HandoutContentGroup = 'explanation' | 'practice' | 'question'
export type HandoutContentLocale = 'zh' | 'en'
export type HandoutContentType = {
  id: string; group: string | null; role: string; legacy?: boolean
  label: Record<HandoutContentLocale, string>
  purpose?: Record<HandoutContentLocale, string>
  checkpoints?: Record<HandoutContentLocale, string[]>
  example?: Record<HandoutContentLocale, string>
  body_guide?: Record<HandoutContentLocale, string>
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

// One semantic palette for the handout and its directory. Group badges describe
// teaching purpose; they must not override a subtype's learned color identity.
const typeTones: Record<string, string> = {
  definition: 'definition', theorem: 'theorem', rule: 'theorem', derivation: 'derivation',
  result: 'result', summary: 'result', example: 'example', case: 'example', exercise: 'exercise',
  misconception: 'warning', warning: 'warning', counterexample: 'warning',
  method: 'method', checklist: 'method', comparison: 'comparison',
  review_question: 'question', guiding_question: 'question', question: 'question',
}
const palettes: Record<string, [string, string, string]> = {
  prose: ['#657080', 'transparent', '#e1e5ec'],
  definition: ['#17815a', '#edf7f2', '#cbe5d8'],
  theorem: ['#6e4a9c', '#f0ecf7', '#d8cce9'],
  derivation: ['#356ca6', '#edf4fc', '#cfdef0'],
  result: ['#126d9b', '#eef7fb', '#cce3ef'],
  exercise: ['#126d9b', '#eef7fb', '#cce3ef'],
  example: ['#9a531d', '#fcf2e9', '#ead5c3'],
  warning: ['#a64355', '#fcf0f2', '#efd1d7'],
  method: ['#247a80', '#edf7f8', '#cce4e6'],
  comparison: ['#247a80', '#edf7f8', '#cce4e6'],
  question: ['#78579b', '#f4eff9', '#ded2ed'],
}
export function handoutPresentation(type: string, locale: HandoutContentLocale, fallback = '') {
  const normalized = handoutContentType(type)
  const tone = typeTones[normalized] || 'prose'
  const [accent, tint, edge] = palettes[tone]!
  const label = handoutTypeDefinition(type)?.label[locale] || fallback || type
  return { tone, label, style: { '--handout-accent': accent, '--handout-tint': tint, '--handout-edge': edge } }
}
