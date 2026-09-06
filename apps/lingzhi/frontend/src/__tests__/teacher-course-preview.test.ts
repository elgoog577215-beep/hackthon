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

  it('routes teacher trials to the disposable component without mounting learner runtime', () => {
    const learningView = source('src/views/LearningView.vue')
    const trial = source('src/views/TeacherCoursePreview.vue')
    expect(learningView).toContain('<TeacherCoursePreview v-if="teacherPreview" />')
    expect(learningView).toContain('<LearnerCourseView v-else />')
    expect(trial).toContain('/preview')
    expect(trial).not.toContain('useLearningProgressStore')
    expect(trial).not.toContain('useNoteStore')
    expect(trial).not.toContain('localStorage')
  })
})
