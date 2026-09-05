import { useCourseStore } from '../../stores/course'
import { useGenerationStore } from '../../stores/generation'
import { useTeacherLessonAuthoringStore } from '../../stores/teacherLessonAuthoring'
import type { RouteLocationRaw } from 'vue-router'

export const TEACHER_COURSE_CAPABILITY_CONTRACT = 'teacher-course-capabilities/v1' as const

type TeacherPptRouteOptions = {
  nodeId?: string
  returnTo?: string
}

export function teacherPptRoute(
  courseId: string,
  options: TeacherPptRouteOptions = {},
): RouteLocationRaw {
  return {
    name: 'ppt-workspace',
    params: { courseId },
    query: {
      ...(options.returnTo ? { returnTo: options.returnTo } : {}),
      ...(options.nodeId ? { lesson: options.nodeId } : {}),
    },
  }
}

/**
 * Teacher-side compatibility boundary for shared course capabilities.
 *
 * Teacher pages depend on this entry instead of importing the student-facing
 * stores directly. The stores remain the current engine, while later changes
 * to generation, transport or state projection can be adapted here without
 * rewriting the teacher workspace or changing student routes.
 */
export function useTeacherCourseRuntime() {
  const course = useCourseStore()
  const generation = useGenerationStore()
  const lessonAuthoring = useTeacherLessonAuthoringStore()

  return {
    contractVersion: TEACHER_COURSE_CAPABILITY_CONTRACT,
    course,
    generation,
    lessonAuthoring,
    loadCourse: (courseId: string) => course.loadCourse(courseId, {
      includeLearningRecords: false,
      taskType: 'teacher_outline_generation',
      monitorTask: false,
      previewSurface: 'teacher',
    }),
    pptRoute: teacherPptRoute,
  }
}
