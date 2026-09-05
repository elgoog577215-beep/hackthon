import { describe, expect, it } from 'vitest'
import { ZJU_CLASS_PERIODS, resolveZjuClassPeriodRange } from '@/utils/zju-class-periods'

describe('Zhejiang University class periods', () => {
  it('keeps the regular 13-period timetable used by the weekly calendar', () => {
    expect(ZJU_CLASS_PERIODS).toHaveLength(13)
    expect(ZJU_CLASS_PERIODS[0]).toMatchObject({ number: 1, start: '08:00', end: '08:45' })
    expect(ZJU_CLASS_PERIODS[12]).toMatchObject({ number: 13, start: '20:30', end: '21:15' })
  })

  it('maps a scheduled session to every standard period it overlaps', () => {
    expect(resolveZjuClassPeriodRange('08:00', '09:35')).toEqual({ startIndex: 0, endIndex: 1 })
    expect(resolveZjuClassPeriodRange('09:00', '09:45')).toEqual({ startIndex: 1, endIndex: 1 })
    expect(resolveZjuClassPeriodRange('14:00', '15:30')).toEqual({ startIndex: 5, endIndex: 7 })
  })

  it('does not silently force an invalid or out-of-hours session into the grid', () => {
    expect(resolveZjuClassPeriodRange(null, null)).toBeNull()
    expect(resolveZjuClassPeriodRange('12:30', '13:00')).toBeNull()
    expect(resolveZjuClassPeriodRange('22:00', '22:45')).toBeNull()
  })
})
