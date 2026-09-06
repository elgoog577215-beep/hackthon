import type {
  TeacherLessonPptAsset,
  TeacherLessonProjection,
} from '../stores/teacherLessonAuthoring'

export function teacherLessonPlanIsReady(
  lesson?: TeacherLessonProjection | null,
): boolean {
  return lesson?.plan?.ready === true
}

export function teacherLessonPlanCanGenerate(
  lesson?: TeacherLessonProjection | null,
): boolean {
  if (typeof lesson?.plan?.can_generate === 'boolean') return lesson.plan.can_generate
  return Boolean(
    lesson?.arrangement?.blocks?.length
    && lesson.arrangement.source_state === 'current',
  )
}

export function teacherLessonScriptIsReady(
  lesson?: TeacherLessonProjection | null,
): boolean {
  return lesson?.script?.ready === true
}

export function teacherLessonScriptCanGenerate(
  lesson?: TeacherLessonProjection | null,
): boolean {
  if (typeof lesson?.script?.can_generate === 'boolean') return lesson.script.can_generate
  return teacherLessonPlanIsReady(lesson)
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
