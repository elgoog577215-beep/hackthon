export interface ZjuClassPeriod {
  number: number
  start: string
  end: string
  section: 'morning' | 'afternoon' | 'evening'
}

export const ZJU_CLASS_PERIODS: readonly ZjuClassPeriod[] = [
  { number: 1, start: '08:00', end: '08:45', section: 'morning' },
  { number: 2, start: '08:50', end: '09:35', section: 'morning' },
  { number: 3, start: '10:00', end: '10:45', section: 'morning' },
  { number: 4, start: '10:50', end: '11:35', section: 'morning' },
  { number: 5, start: '11:40', end: '12:25', section: 'morning' },
  { number: 6, start: '13:25', end: '14:10', section: 'afternoon' },
  { number: 7, start: '14:15', end: '15:00', section: 'afternoon' },
  { number: 8, start: '15:05', end: '15:50', section: 'afternoon' },
  { number: 9, start: '16:15', end: '17:00', section: 'afternoon' },
  { number: 10, start: '17:05', end: '17:50', section: 'afternoon' },
  { number: 11, start: '18:50', end: '19:35', section: 'evening' },
  { number: 12, start: '19:40', end: '20:25', section: 'evening' },
  { number: 13, start: '20:30', end: '21:15', section: 'evening' },
]

const clockMinutes = (value?: string | null) => {
  const match = String(value || '').trim().match(/^([01]\d|2[0-3]):([0-5]\d)/)
  return match ? Number(match[1]) * 60 + Number(match[2]) : null
}

export function resolveZjuClassPeriodRange(startTime?: string | null, endTime?: string | null) {
  const start = clockMinutes(startTime)
  const end = clockMinutes(endTime)
  if (start === null || end === null || end <= start) return null

  const indexes = ZJU_CLASS_PERIODS.flatMap((period, index) => {
    const periodStart = clockMinutes(period.start)!
    const periodEnd = clockMinutes(period.end)!
    return start < periodEnd && end > periodStart ? [index] : []
  })
  if (!indexes.length) return null
  const startIndex = indexes[0]
  const endIndex = indexes[indexes.length - 1]
  if (startIndex === undefined || endIndex === undefined) return null
  return {
    startIndex,
    endIndex,
  }
}
