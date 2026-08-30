import { t } from '../shared/i18n'

export type CoursePreparationState = 'preparing' | 'prepared'

export interface CoursePreparationCourse {
  course_status?: string | null
  is_published?: boolean
  preparation_state?: CoursePreparationState | null
}

export interface CoursePreparationTask {
  status?: string
  publicationAllowed?: boolean
  recovery?: { state?: string }
}

export function coursePreparationState(
  course?: CoursePreparationCourse | null,
  _task?: CoursePreparationTask | null,
): CoursePreparationState {
  if (course?.preparation_state === 'prepared') return 'prepared'
  return 'preparing'
}

export function coursePreparationLabel(state: CoursePreparationState): string {
  return state === 'prepared'
    ? t('coursePreparation.prepared', '备课完成')
    : t('coursePreparation.preparing', '备课中')
}
