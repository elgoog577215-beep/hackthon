/** 课程卡片左侧色带配色（按课程 id 稳定分配） */
const COURSE_ACCENT_PALETTE = [
  '#1358E4',
  '#1B8A5A',
  '#C2410C',
  '#7C3AED',
  '#0E7490',
  '#B45309',
  '#BE185D',
  '#4338CA',
  '#047857',
  '#B91C1C',
] as const

function hashCourseId(courseId: string): number {
  let hash = 0
  for (let i = 0; i < courseId.length; i++) {
    hash = (hash * 31 + courseId.charCodeAt(i)) >>> 0
  }
  return hash
}

export function getCourseAccentColor(courseId: string): string {
  const idx = hashCourseId(courseId) % COURSE_ACCENT_PALETTE.length
  return COURSE_ACCENT_PALETTE[idx] ?? COURSE_ACCENT_PALETTE[0]
}

/** 卡片上展示的简短课程编号 */
export function getCourseDisplayCode(courseId: string): string {
  const tail = courseId.replace(/[^a-zA-Z0-9]/g, '').slice(-6).toUpperCase()
  return tail ? `#${tail}` : '#COURSE'
}
