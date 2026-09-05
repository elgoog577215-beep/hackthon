import {
  assessTeacherProductionRequest,
  buildTeacherProductionAiInstruction,
  changedTeacherLessonFields,
  teacherProductionAiBusy,
  transitionTeacherProductionAiPhase,
  type TeacherProductionAiEvent,
  type TeacherProductionAiMessage,
  type TeacherProductionAiPhase,
} from './useTeacherProductionAiCollaboration'

export type TeacherLessonAiEvent = TeacherProductionAiEvent
export type TeacherLessonAiMessage = TeacherProductionAiMessage
export type TeacherLessonAiPhase = TeacherProductionAiPhase

export interface TeacherLessonAiScope {
  courseTitle: string
  lessonTitle: string
  sectionTitle: string
  referenceCount: number
}

export const transitionTeacherLessonAiPhase = transitionTeacherProductionAiPhase
export const teacherLessonAiBusy = teacherProductionAiBusy
export { changedTeacherLessonFields }

export function assessTeacherLessonRequest(value: string): 'clarify' | 'generate' {
  return assessTeacherProductionRequest('lesson', value)
}

export function buildTeacherLessonAiInstruction(
  messages: TeacherLessonAiMessage[],
  scope: TeacherLessonAiScope,
): string {
  return buildTeacherProductionAiInstruction(messages, {
    domain: 'lesson',
    courseTitle: scope.courseTitle,
    primaryTitle: scope.lessonTitle,
    secondaryTitle: scope.sectionTitle || '整讲教案',
    referenceCount: scope.referenceCount,
  })
}
