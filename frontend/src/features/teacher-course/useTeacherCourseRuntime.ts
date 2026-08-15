import { useCourseStore } from '../../stores/course'
import { useGenerationStore } from '../../stores/generation'

/**
 * Teacher-side compatibility boundary for shared course capabilities.
 *
 * Teacher pages depend on this entry instead of importing the student-facing
 * stores directly. The stores remain the current engine, while later changes
 * to generation, transport or state projection can be adapted here without
 * rewriting the teacher workspace or changing student routes.
 */
export function useTeacherCourseRuntime() {
  return {
    course: useCourseStore(),
    generation: useGenerationStore(),
  }
}
