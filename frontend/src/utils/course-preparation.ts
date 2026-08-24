import { t } from '../shared/i18n'

export type CoursePreparationState = 'preparing' | 'prepared'

export interface CoursePreparationCourse {
  course_status?: string | null
  is_published?: boolean
}

export interface CoursePreparationTask {
  status?: string
  publicationAllowed?: boolean
  recovery?: { state?: string }
}

export function coursePreparationState(
  course?: CoursePreparationCourse | null,
  task?: CoursePreparationTask | null,
): CoursePreparationState {
  if (task) {
    if (task.status === 'completed') return 'prepared'
    if (
      task.status === 'completed_with_warnings'
      && (task.publicationAllowed === true || task.recovery?.state === 'completed')
    ) return 'prepared'
    return 'preparing'
  }
  if (course?.course_status === 'draft' && course.is_published !== true) return 'preparing'
  return 'prepared'
}

export function coursePreparationLabel(state: CoursePreparationState): string {
  return state === 'prepared'
    ? t('coursePreparation.prepared', '备课完成')
    : t('coursePreparation.preparing', '正在备课')
}
