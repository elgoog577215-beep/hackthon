import type {
  TeacherLessonPptAsset,
  TeacherLessonProjection,
} from '../stores/teacherLessonAuthoring'

export function teacherLessonPlanIsReady(
  lesson?: TeacherLessonProjection | null,
): boolean {
  return lesson?.plan?.ready === true
}

export function teacherLessonScriptIsReady(
  lesson?: TeacherLessonProjection | null,
): boolean {
  return lesson?.script?.ready === true
}

export function teacherLessonPptAssetIsReady(
  asset?: TeacherLessonPptAsset | null,
): boolean {
  return asset?.ready === true
}

export function teacherLessonPptIsReady(
  lesson?: TeacherLessonProjection | null,
): boolean {
  return Boolean(lesson?.plan?.ppt_assets?.some(teacherLessonPptAssetIsReady))
}
