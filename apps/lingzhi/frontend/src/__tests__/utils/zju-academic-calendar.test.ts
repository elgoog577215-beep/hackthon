import { describe, expect, it } from 'vitest'
import {
  canonicalZjuTerm,
  inferredSessionsPerWeek,
  projectedLectureWeek,
  resolveTeachingWeekRange,
  zjuTeachingWeekRange,
} from '@/utils/zju-academic-calendar'

describe('Zhejiang University academic calendar projection', () => {
  it('maps long and short terms to sixteen or eight teaching weeks', () => {
    expect(canonicalZjuTerm('2026-2027 春夏学期')).toBe('春夏')
    expect(canonicalZjuTerm('2026-2027 秋季学期')).toBe('秋')
    expect(zjuTeachingWeekRange('秋冬')).toEqual({ start: 1, end: 16, weeks: 16, term: '秋冬' })
    expect(zjuTeachingWeekRange('春学期')).toEqual({ start: 1, end: 8, weeks: 8, term: '春' })
    expect(zjuTeachingWeekRange('暑期课')).toBeNull()
  })

  it('uses the academic calendar by default and allows a custom exception', () => {
    expect(resolveTeachingWeekRange('秋', 'academic_calendar', 2, 12)).toMatchObject({
      start: 1,
      end: 8,
      mode: 'academic_calendar',
    })
    expect(resolveTeachingWeekRange('秋', 'custom', 2, 7)).toMatchObject({
      start: 2,
      end: 7,
      mode: 'custom',
    })
    expect(resolveTeachingWeekRange('秋', undefined, 1, 16)).toMatchObject({
      start: 1,
      end: 8,
      mode: 'academic_calendar',
    })
    expect(resolveTeachingWeekRange('秋', undefined, 2, 7)).toMatchObject({
      start: 2,
      end: 7,
      mode: 'custom',
    })
  })

  it('places sixteen lectures twice per week in an eight-week term', () => {
    const range = resolveTeachingWeekRange('秋', 'academic_calendar', 1, 16)
    const density = inferredSessionsPerWeek(16, range)
    expect(density).toBe(2)
    expect(Array.from({ length: 16 }, (_, index) => projectedLectureWeek(index, range, density)))
      .toEqual([1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8])
  })
})
