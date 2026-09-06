import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8')

describe('teacher course preview', () => {
  it('does not expose a second whole-course publication flow', () => {
    const workbench = source('src/components/TeacherCourseWorkbench.vue')

    expect(workbench).not.toContain('course-publication')
    expect(workbench).not.toContain('/lesson-authoring/publication-readiness')
    expect(workbench).not.toContain('/lesson-authoring/publish')
  })

  it('loads the teacher current projection as a complete student learning surface', () => {
    const learningView = source('src/views/LearningView.vue')
    const contentArea = source('src/components/ContentArea.vue')

    expect(learningView).toContain("previewSurface: 'teacher'")
    expect(learningView).toContain("taskType: 'teacher_outline_generation'")
    expect(learningView).toContain(':teacher-preview="isTeacherPreview"')
    expect(learningView).toContain("courseStore.currentCourseProjection === 'generation_preview' && !isTeacherPreview.value")
    expect(contentArea).toContain("courseStore.currentCourseProjection === 'generation_preview' && !props.teacherPreview")
  })
})
