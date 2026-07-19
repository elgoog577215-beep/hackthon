export function hasMeaningfulAnswer(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.some(hasMeaningfulAnswer)
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).some(hasMeaningfulAnswer)
  }
  return true
}
