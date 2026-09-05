export type WeekRangeMode = 'academic_calendar' | 'custom'

export type TeachingWeekRange = {
  start: number
  end: number
  weeks: number
  term: '春夏' | '秋冬' | '春' | '夏' | '秋' | '冬'
}

const TERM_TEACHING_WEEKS: Record<TeachingWeekRange['term'], number> = {
  春夏: 16,
  秋冬: 16,
  春: 8,
  夏: 8,
  秋: 8,
  冬: 8,
}

export function canonicalZjuTerm(value: unknown): TeachingWeekRange['term'] | '' {
  const text = String(value || '').replace(/\s+/g, '')
  for (const term of ['春夏', '秋冬'] as const) {
    if (text.includes(term)) return term
  }
  for (const term of ['春', '夏', '秋', '冬'] as const) {
    if (text.includes(`${term}学期`) || text.includes(`${term}季`)) return term
  }
  return (['春', '夏', '秋', '冬'] as const).find(term => text === term) || ''
}

export function zjuTeachingWeekRange(value: unknown): TeachingWeekRange | null {
  const term = canonicalZjuTerm(value)
  if (!term) return null
  const weeks = TERM_TEACHING_WEEKS[term]
  return { start: 1, end: weeks, weeks, term }
}

export function resolveTeachingWeekRange(
  term: unknown,
  mode: unknown,
  activeWeekStart: unknown,
  activeWeekEnd: unknown,
): { start: number; end: number; weeks: number; mode: WeekRangeMode; term: TeachingWeekRange['term'] | '' } {
  const calendarRange = zjuTeachingWeekRange(term)
  const legacyStart = Math.max(1, Number(activeWeekStart || 1))
  const legacyEnd = Math.max(legacyStart, Number(activeWeekEnd || 16))
  const normalizedMode: WeekRangeMode = mode === 'academic_calendar' || mode === 'custom'
    ? mode
    : calendarRange && (
      (legacyStart === 1 && legacyEnd === 16)
      || (legacyStart === calendarRange.start && legacyEnd === calendarRange.end)
    )
      ? 'academic_calendar'
      : 'custom'
  if (normalizedMode === 'academic_calendar' && calendarRange) {
    return { ...calendarRange, mode: 'academic_calendar' }
  }
  const start = legacyStart
  const end = Math.max(start, Number(activeWeekEnd || calendarRange?.end || 16))
  return {
    start,
    end,
    weeks: end - start + 1,
    mode: 'custom',
    term: calendarRange?.term || '',
  }
}

export function inferredSessionsPerWeek(lectureCount: number, range: { weeks: number }) {
  return Math.max(1, Math.ceil(Math.max(1, lectureCount) / Math.max(1, range.weeks)))
}

export function projectedLectureWeek(
  lectureIndex: number,
  range: { start: number; end: number },
  sessionsPerWeek: number,
) {
  const week = range.start + Math.floor(Math.max(0, lectureIndex) / Math.max(1, sessionsPerWeek))
  return week <= range.end ? week : null
}
