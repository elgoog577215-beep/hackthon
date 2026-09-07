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

  it('keeps the original learning interface with teacher preview I/O', () => {
    const learningView = source('src/views/LearningView.vue')
    expect(learningView).toContain('<LearnerCourseView />')
    expect(learningView).not.toContain('TeacherCoursePreview')
    expect(source('src/stores/course.ts')).toContain('/preview')
    expect(source('src/stores/courseWorkspace.ts')).toContain('/preview/grade')
    expect(source('src/stores/aiTeacher.ts')).toContain('/preview/ask')
  })
})
