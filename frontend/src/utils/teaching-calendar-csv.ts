import type { ClassSession, TeachingCalendar } from '../stores/teachingCalendar'

const columns = [
  '课次', '日期', '开始时间', '结束时间', '教学内容', '教学要求（含作业）',
  '上课地点', '教师', '教学类型', '实验小组', '教学时数', '备注', '关联教学单元',
] as const

const quote = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`

export function teachingCalendarToCsv(calendar: TeachingCalendar) {
  const rows = calendar.sessions.map((session, index) => [
    session.sequence || index + 1,
    session.date || '',
    session.start_time || '',
    session.end_time || '',
    session.content_summary,
    session.requirements,
    session.location,
    session.teacher_name,
    session.teaching_type,
    session.group_code,
    session.credit_hours ?? '',
    session.notes,
    session.lesson_unit_id || '',
  ])
  return `\uFEFF${[columns, ...rows].map(row => row.map(quote).join(',')).join('\r\n')}`
}

function parseRows(input: string) {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const text = input.replace(/^\uFEFF/, '')

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') { cell += '"'; index += 1 }
      else if (char === '"') quoted = false
      else cell += char
      continue
    }
    if (char === '"') quoted = true
    else if (char === ',') { row.push(cell); cell = '' }
    else if (char === '\n') { row.push(cell.replace(/\r$/, '')); rows.push(row); row = []; cell = '' }
    else cell += char
  }
  if (quoted) throw new Error('CSV 中的引号没有成对出现')
  if (cell || row.length) { row.push(cell.replace(/\r$/, '')); rows.push(row) }
  return rows.filter(item => item.some(value => value.trim()))
}

const cleanTime = (value: string) => {
  const text = value.trim()
  if (!text) return null
  if (!/^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(text)) throw new Error(`时间“${text}”格式应为 HH:mm`)
  return text.slice(0, 5)
}

const cleanDate = (value: string) => {
  const text = value.trim()
  if (!text) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)
  if (!match) throw new Error(`日期“${text}”格式应为 YYYY-MM-DD`)
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) {
    throw new Error(`日期“${text}”不是有效日期`)
  }
  return text
}

export function teachingCalendarFromCsv(input: string): ClassSession[] {
  const rows = parseRows(input)
  if (rows.length < 2) throw new Error('CSV 没有可导入的课次')
  const header = rows[0]!.map(value => value.trim())
  const indexOf = (name: typeof columns[number]) => header.indexOf(name)
  const contentIndex = indexOf('教学内容')
  if (contentIndex < 0) throw new Error('CSV 缺少“教学内容”列')
  const get = (row: string[], name: typeof columns[number]) => row[indexOf(name)]?.trim() || ''

  return rows.slice(1).map((row, offset) => {
    const line = offset + 2
    try {
      const content = row[contentIndex]?.trim()
      if (!content) throw new Error('教学内容不能为空')
      const date = cleanDate(get(row, '日期'))
      const startTime = cleanTime(get(row, '开始时间'))
      const endTime = cleanTime(get(row, '结束时间'))
      if ((startTime && !endTime) || (!startTime && endTime)) throw new Error('开始时间和结束时间必须同时填写')
      if (startTime && endTime && endTime <= startTime) throw new Error('结束时间必须晚于开始时间')
      const hoursText = get(row, '教学时数')
      const hours = hoursText ? Number(hoursText) : null
      if (hoursText && (!Number.isFinite(hours) || Number(hours) < 0 || Number(hours) > 24)) throw new Error('教学时数必须是 0 到 24 的数字')
      const sequenceText = get(row, '课次')
      const sequence = sequenceText ? Number(sequenceText) : offset + 1
      if (!Number.isInteger(sequence) || sequence < 1) throw new Error('课次必须是大于 0 的整数')
      return {
        lesson_unit_id: get(row, '关联教学单元') || null,
        sequence,
        date,
        start_time: startTime,
        end_time: endTime,
        content_summary: content,
        requirements: get(row, '教学要求（含作业）'),
        location: get(row, '上课地点'),
        teacher_name: get(row, '教师'),
        teaching_type: get(row, '教学类型') || '理论课',
        group_code: get(row, '实验小组'),
        credit_hours: hours,
        notes: get(row, '备注'),
        status: date ? 'scheduled' : 'unscheduled',
        source: 'import',
      } satisfies ClassSession
    } catch (error) {
      throw new Error(`第 ${line} 行：${(error as Error).message}`)
    }
  })
}

export function sessionImportKey(session: ClassSession) {
  return [session.date || '', session.start_time?.slice(0, 5) || '', session.content_summary.trim(), session.group_code.trim()].join('|')
}
