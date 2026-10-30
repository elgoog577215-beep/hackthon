export function configuredStudyPortal(value: unknown): string {
  return configuredPortal(value, /^\/study(?:[/?#]|$)/)
}

export function configuredTeacherPortal(value: unknown): string {
  return configuredPortal(value, /^\/courses(?:[/?#]|$)/)
}

function configuredPortal(value: unknown, internalPath: RegExp): string {
  if (typeof value !== 'string' || !value.trim()) return ''
  const target = value.trim()
  if (internalPath.test(target) && !/[\\\r\n\t]/.test(target)) return target
  try {
    const url = new URL(target)
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return ''
    return url.href
  } catch { return '' }
}
