import { describe, expect, it } from 'vitest'
import type { TeachingCalendar } from '../../stores/teachingCalendar'
import { sessionImportKey, teachingCalendarFromCsv, teachingCalendarToCsv } from '../../utils/teaching-calendar-csv'

const calendar: TeachingCalendar = {
  schema_version: 'teaching_calendar_v1',
  course_id: 'course-1',
  course_title: '设计思维与创新设计',
  academic_year: '2025-2026',
  term: '春夏',
  timezone: 'Asia/Shanghai',
  status: 'draft',
  source_outline_revision: 'outline-1',
  revision: 2,
  created_at: '',
  updated_at: '',
  sessions: [{
    lesson_unit_id: 'lesson-1', sequence: 1, date: '2026-03-02', start_time: '08:00', end_time: '09:35',
    content_summary: '导论，包含“设计”与创新', requirements: '阅读案例\n完成作业', location: '紫金港东2-105',
    teacher_name: '张老师', teaching_type: '理论课', group_code: 'A组', credit_hours: 2, notes: '首讲', status: 'scheduled', source: 'outline',
  }],
}

describe('teaching calendar CSV exchange', () => {
  it('round-trips Chinese content, commas, quotes, and newlines', () => {
    const sessions = teachingCalendarFromCsv(teachingCalendarToCsv(calendar))
    expect(sessions).toHaveLength(1)
    expect(sessions[0]).toMatchObject({
      content_summary: '导论，包含“设计”与创新',
      requirements: '阅读案例\n完成作业',
      date: '2026-03-02',
      start_time: '08:00',
      end_time: '09:35',
      lesson_unit_id: 'lesson-1',
      source: 'import',
    })
  })

  it('reports the exact invalid row', () => {
    expect(() => teachingCalendarFromCsv('教学内容,日期\n第一讲,03/02/2026')).toThrow('第 2 行：日期')
    expect(() => teachingCalendarFromCsv('教学内容,日期\n第一讲,2026-02-31')).toThrow('第 2 行：日期')
    expect(() => teachingCalendarFromCsv('教学内容,课次\n第一讲,-1')).toThrow('第 2 行：课次')
  })

  it('treats API second precision and CSV minute precision as the same session', () => {
    const imported = teachingCalendarFromCsv(teachingCalendarToCsv(calendar))[0]!
    const saved = { ...calendar.sessions[0]!, start_time: '08:00:00' }
    expect(sessionImportKey(imported)).toBe(sessionImportKey(saved))
  })
})
