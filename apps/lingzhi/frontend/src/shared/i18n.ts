import { ref } from 'vue'
import { resolvePublicAssetUrl } from '../utils/publicAssetUrl'

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

export function localeResourceUrl(
  locale: Locale,
  baseUrl: string = import.meta.env.BASE_URL,
): string {
  return resolvePublicAssetUrl(`/locales/${locale}/translation.json`, baseUrl)
}

function syncDocumentLanguage(locale: Locale): void {
  if (typeof document !== 'undefined') document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
}

async function loadMessages(locale: Locale): Promise<void> {
  const resourceUrl = localeResourceUrl(locale)
  const response = await fetch(resourceUrl, {
    cache: 'no-cache',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new Error(`Could not load locale ${locale} from ${resourceUrl}: HTTP ${response.status}`)
  }
  const payload = await response.json() as MessageTree
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error(`Invalid locale payload for ${locale} from ${resourceUrl}`)
  }
  messages.value = payload
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
    initializationPromise = loadMessages(activeLocale.value).catch((error) => {
      messages.value = {}
      initializationPromise = null
      console.error('[i18n] Failed to initialize translations', error)
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
