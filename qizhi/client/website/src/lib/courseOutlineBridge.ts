import type { ChapterNodeModel } from '../components/ChapterNode.vue'

/** 课程 ↔ 大纲表单预填快照（localStorage 持久化） */
export interface CourseOutlinePrefill {
  courseName?: string
  courseCategory?: string
  credits?: string
  hours?: string
  major?: string
  grade?: string
  teachingMethod?: string
  offlineHoursRatio?: string
  offlineScoreRatio?: string
  prerequisites?: string
  courseDescription?: string
  teachingObjectives?: string
  ideologicalPolitical?: string
  labels?: string[]
  chapterTree?: ChapterNodeModel[]
}

const storageKey = (courseId: string) => `course_outline_prefill_${courseId}`

/** 后端/历史数据中的占位介绍，应视为未填写 */
const PLACEHOLDER_COURSE_DESCRIPTIONS = new Set([
  '无',
  '暂无',
  '暂无介绍',
  '无介绍',
  '无描述',
  '-',
  '—',
  'n/a',
  'N/A',
  'none',
  'None',
])

export function isPlaceholderCourseDescription(text: string | null | undefined): boolean {
  const trimmed = (text ?? '').trim()
  return !trimmed || PLACEHOLDER_COURSE_DESCRIPTIONS.has(trimmed)
}

export function normalizeCourseDescriptionText(text: string | null | undefined): string {
  const trimmed = (text ?? '').trim()
  if (!trimmed || PLACEHOLDER_COURSE_DESCRIPTIONS.has(trimmed)) return ''
  return trimmed
}

/** 从 localStorage 预填快照读取课程简介 */
export function getPrefillCourseDescription(courseId: string): string {
  const prefill = loadCourseOutlinePrefill(courseId)
  return normalizeCourseDescriptionText(prefill?.courseDescription)
}

/** 从大纲 Markdown 正文中提取「课程简介」章节（无预填时的兜底） */
export function extractCourseIntroFromOutlineMarkdown(content: string): string {
  const text = content.trim()
  if (!text) return ''
  const section = text.match(
    /^#{1,3}\s*(?:[一二三四五六七八九十百\d]+[、.．]?\s*)?课程简介\s*\n+([\s\S]*?)(?=\n#{1,3}\s|$)/im,
  )
  if (!section?.[1]) return ''
  const intro = section[1]
    .replace(/^[-*]\s+/gm, '')
    .replace(/\n+/g, ' ')
    .trim()
  return normalizeCourseDescriptionText(intro)
}

export function saveCourseOutlinePrefill(courseId: string, data: CourseOutlinePrefill) {
  try {
    localStorage.setItem(storageKey(courseId), JSON.stringify(data))
  } catch (e) {
    console.warn('[courseOutlineBridge] save failed', e)
  }
}

export function loadCourseOutlinePrefill(courseId: string): CourseOutlinePrefill | null {
  try {
    const raw = localStorage.getItem(storageKey(courseId))
    if (!raw) return null
    return JSON.parse(raw) as CourseOutlinePrefill
  } catch {
    return null
  }
}

export function getStoredCourseCredits(courseId: string): number | null {
  const prefill = loadCourseOutlinePrefill(courseId)
  if (!prefill?.credits) return null
  const n = parseFloat(String(prefill.credits))
  return Number.isNaN(n) ? null : n
}

type OutlineFormState = {
  courseName: string
  courseCategory: string
  credits: string
  hours: string
  major: string
  grade: string
  teachingMethod: string
  offlineHoursRatio: string
  offlineScoreRatio: string
  prerequisites: string
  courseDescription: string
  teachingObjectives: string
  ideologicalPolitical: string
}

export function buildPrefillSnapshot(
  form: OutlineFormState,
  chapterTree: ChapterNodeModel[],
  labels: string[]
): CourseOutlinePrefill {
  return {
    courseName: form.courseName,
    courseCategory: form.courseCategory,
    credits: form.credits,
    hours: form.hours,
    major: form.major,
    grade: form.grade,
    teachingMethod: form.teachingMethod,
    offlineHoursRatio: form.offlineHoursRatio,
    offlineScoreRatio: form.offlineScoreRatio,
    prerequisites: form.prerequisites,
    courseDescription: form.courseDescription,
    teachingObjectives: form.teachingObjectives,
    ideologicalPolitical: form.ideologicalPolitical,
    labels: labels.length ? [...labels] : undefined,
    chapterTree: chapterTree.length ? JSON.parse(JSON.stringify(chapterTree)) : undefined,
  }
}

export function applyPrefillSnapshot(
  prefill: CourseOutlinePrefill,
  form: { value: OutlineFormState },
  chapterTree: { value: ChapterNodeModel[] },
  labels: { value: string[] }
) {
  if (prefill.courseName != null) form.value.courseName = prefill.courseName
  if (prefill.courseCategory != null) form.value.courseCategory = prefill.courseCategory
  if (prefill.credits != null) form.value.credits = prefill.credits
  if (prefill.hours != null) form.value.hours = prefill.hours
  if (prefill.major != null) form.value.major = prefill.major
  if (prefill.grade != null) form.value.grade = prefill.grade
  if (prefill.teachingMethod != null) form.value.teachingMethod = prefill.teachingMethod
  if (prefill.offlineHoursRatio != null) form.value.offlineHoursRatio = prefill.offlineHoursRatio
  if (prefill.offlineScoreRatio != null) form.value.offlineScoreRatio = prefill.offlineScoreRatio
  if (prefill.prerequisites != null) form.value.prerequisites = prefill.prerequisites
  const storedDesc = (prefill.courseDescription ?? '').trim()
  const normalizedDesc = normalizeCourseDescriptionText(storedDesc)
  if (normalizedDesc) form.value.courseDescription = normalizedDesc
  if (prefill.teachingObjectives != null) form.value.teachingObjectives = prefill.teachingObjectives
  if (prefill.ideologicalPolitical != null) form.value.ideologicalPolitical = prefill.ideologicalPolitical
  if (prefill.labels?.length) labels.value = [...prefill.labels]
  if (prefill.chapterTree?.length) chapterTree.value = JSON.parse(JSON.stringify(prefill.chapterTree))
}
