import { ref } from 'vue'

type Locale = 'zh' | 'en'
type MessageTree = Record<string, unknown>

const initialLocale: Locale = (() => {
  const saved = localStorage.getItem('app-locale')
  if (saved === 'zh' || saved === 'en') return saved
  return 'zh'
})()

export const activeLocale = ref<Locale>(initialLocale)
const messages = ref<MessageTree>({})
let initializationPromise: Promise<void> | null = null

function syncDocumentLanguage(locale: Locale): void {
  if (typeof document !== 'undefined') document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
}

async function loadMessages(locale: Locale): Promise<void> {
  const response = await fetch(`/locales/${locale}/translation.json`)
  if (!response.ok) throw new Error(`Could not load locale: ${locale}`)
  messages.value = await response.json() as MessageTree
}

export async function setLocale(locale: Locale): Promise<void> {
  activeLocale.value = locale
  localStorage.setItem('app-locale', locale)
  syncDocumentLanguage(locale)
  await loadMessages(locale)
}

export function initializeI18n(): Promise<void> {
  syncDocumentLanguage(activeLocale.value)
  if (!initializationPromise) {
    initializationPromise = loadMessages(activeLocale.value).catch(() => {
      messages.value = {}
    })
  }
  return initializationPromise
}

export function t(key: string, fallback = key): string {
  let current: unknown = messages.value
  for (const segment of key.split('.')) {
    if (!current || typeof current !== 'object') return fallback
    current = (current as MessageTree)[segment]
  }
  return typeof current === 'string' ? current : fallback
}
