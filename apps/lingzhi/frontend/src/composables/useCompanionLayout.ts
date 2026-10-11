import { ref, watch } from 'vue'

const STORAGE_KEY = 'lingzhi-companion-layout'

/** Only presentation preferences are persisted; conversation state stays in its store. */
export function useCompanionLayout() {
  let saved: string | null = null
  try { saved = localStorage.getItem(STORAGE_KEY) } catch { /* Storage may be unavailable. */ }
  const floating = ref(saved === 'floating')
  watch(floating, value => {
    try { localStorage.setItem(STORAGE_KEY, value ? 'floating' : 'docked') } catch { /* Keep the in-memory preference. */ }
  }, { flush: 'sync' })
  return floating
}
