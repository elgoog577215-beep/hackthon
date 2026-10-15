export function configuredStudyPortal(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return ''
  const target = value.trim()
  if (/^\/study(?:[/?#]|$)/.test(target)) return target
  try {
    const url = new URL(target)
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return ''
    return url.href
  } catch { return '' }
}
