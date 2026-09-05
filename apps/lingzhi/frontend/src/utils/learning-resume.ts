import { t } from '../shared/i18n'

type Translate = (key: string, fallback?: string) => string

export interface ResumableActionLike {
  action_type?: string
}

export interface CourseWithResumeLike {
  [key: string]: unknown
  resume?: {
    node_id?: string
    activity_at?: string
  }
}

export function isResumableLearningAction(action: ResumableActionLike | null | undefined): boolean {
  return String(action?.action_type || '').startsWith('resume_')
}

export function latestResumableCourse<T extends CourseWithResumeLike>(courses: T[]): T | null {
  return courses.reduce<T | null>((latest, course) => {
    if (!course.resume?.node_id) return latest
    if (!latest) return course
    const currentTime = Date.parse(course.resume.activity_at || '') || 0
    const latestTime = Date.parse(latest.resume?.activity_at || '') || 0
    return currentTime > latestTime ? course : latest
  }, null)
}

export function resumeKindLabel(kind: string, translate: Translate = t): string {
  const normalized = String(kind || 'reading')
  if (normalized === 'practice') {
    return translate('courseLibrary.resume.practice', '继续未完成练习')
  }
  if (normalized === 'diagnostic') {
    return translate('courseLibrary.resume.diagnostic', '继续未完成诊断')
  }
  if (normalized === 'remediation') {
    return translate('courseLibrary.resume.remediation', '继续未完成补救')
  }
  if (normalized === 'validation') {
    return translate('courseLibrary.resume.validation', '继续未完成复验')
  }
  return translate('courseLibrary.resume.reading', '继续上次学习')
}
