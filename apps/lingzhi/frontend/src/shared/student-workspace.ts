export const STUDENT_WORKSPACE_TOOLS = ['reading', 'practice', 'mistakes', 'knowledge', 'overview'] as const
export type StudentWorkspaceTool = typeof STUDENT_WORKSPACE_TOOLS[number]

export function isPublishedExchangeCourse(courseId: string): boolean {
  return /^exchange_[0-9a-f]{32}$/.test(courseId)
}

export function studentWorkspaceTool(value: unknown): StudentWorkspaceTool {
  return typeof value === 'string' && STUDENT_WORKSPACE_TOOLS.includes(value as StudentWorkspaceTool)
    ? value as StudentWorkspaceTool : 'reading'
}

export function studentCourseLink(courseId: string, tool: StudentWorkspaceTool = 'reading') {
  return {
    path: `/course/${encodeURIComponent(courseId)}/learn`,
    query: { returnTo: '/study?view=courses', ...(tool === 'reading' ? {} : { tool }) },
  }
}
