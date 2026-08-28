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

  it('loads the teacher current projection in student-view preview', () => {
    const learningView = source('src/views/LearningView.vue')

    expect(learningView).toContain("previewSurface: 'teacher'")
    expect(learningView).toContain("taskType: 'teacher_outline_generation'")
    expect(learningView).toContain('isGenerationPreview.value || isTeacherPreview.value')
  })
})
