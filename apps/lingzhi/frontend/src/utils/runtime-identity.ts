import {t} from '../shared/i18n'

export const RUNTIME_ID = String(import.meta.env.VITE_RUNTIME_ID || '')
export function generationStorageKey(dataId = String(import.meta.env.VITE_RUNTIME_DATA_ID || '')) {
  return `course-generation-state-v1${dataId ? ':' + dataId : ''}`
}
const apiBase = String(import.meta.env.VITE_API_BASE_URL || import.meta.env.BASE_URL || '').replace(/\/+$/, '')

export async function verifyRuntime(expected = RUNTIME_ID, fetcher: typeof fetch = fetch) {
  if (!expected) return null
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetcher(`${apiBase}/api/runtime`, {cache:'no-store',signal:controller.signal})
    if (!response.ok) throw new Error('Runtime endpoint unavailable')
    const manifest = await response.json()
    if (manifest.runtime_id !== expected) throw new Error('Runtime identity mismatch')
    return manifest
  } catch {
    throw new Error(t('runtime.mismatch','页面与当前服务版本不匹配或连接不可用，请刷新页面后重试。'))
  } finally { clearTimeout(timer) }
}
