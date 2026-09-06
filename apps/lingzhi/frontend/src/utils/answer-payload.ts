const STEP_BOOKKEEPING_FIELDS = new Set(['step_index', 'step_id'])

function hasMeaningfulStep(step: unknown): boolean {
  if (!step || typeof step !== 'object' || Array.isArray(step)) {
    return hasMeaningfulAnswer(step)
  }
  // A step carries `step_index`/`step_id` for ordering only. Those are always
  // populated, so counting them would make an untouched stepwise editor look
  // like a real answer — enabling submit and earning a server-side 422.
  return Object.entries(step as Record<string, unknown>)
    .filter(([field]) => !STEP_BOOKKEEPING_FIELDS.has(field))
    .some(([, fieldValue]) => hasMeaningfulAnswer(fieldValue))
}

export function hasMeaningfulAnswer(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.some(hasMeaningfulAnswer)
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).some(([field, fieldValue]) => (
      field === 'steps' && Array.isArray(fieldValue)
        ? fieldValue.some(hasMeaningfulStep)
        : hasMeaningfulAnswer(fieldValue)
    ))
  }
  return true
}
