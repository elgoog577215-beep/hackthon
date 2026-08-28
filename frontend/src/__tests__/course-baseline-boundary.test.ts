import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'


const source = (relativePath: string) => fs.readFileSync(path.resolve(__dirname, '..', relativePath), 'utf8')


describe('course workbench authoring boundary', () => {
  it('uses a structured form, real stream state, and source tray instead of chat as the production core', () => {
    const workbench = source('components/TeacherCourseWorkbench.vue')
    const references = source('components/CourseReferenceTray.vue')
    const workspace = source('views/CourseWorkspaceView.vue')

    expect(workspace).toContain('<TeacherCourseWorkbench')
    expect(workspace).not.toContain('<SideAIPanel')
    expect(workbench).toContain('class="stage-form"')
    expect(workbench).toContain('class="generation-surface"')
    expect(workbench).toContain('generationStore.streamingContent')
    expect(workbench).toContain('<CourseReferenceTray')
    expect(workbench).toContain("'foundation' | 'lesson' | 'question-bank' | 'script' | 'ppt'")
    expect(workbench).toContain('<QuestionBankReviewPanel')
    expect(references).toContain('class="drop-zone"')
    expect(references).toContain("emit('open-course-information')")
    expect(workspace).toContain('<CourseBaselineDialog')
    expect(references).toContain("data.append('course_id', props.courseId)")
    expect(references).toContain("role: 'primary' | 'reference'")
  })

  it('新建课和课程基线只写入正式教学分类', () => {
    const currentWriters = [
      source('components/CourseGenerationDialog.vue'),
      source('components/CourseBaselineDialog.vue'),
      source('components/TeacherCourseWorkbench.vue'),
      source('views/TeacherCourseCreateView.vue'),
    ].join('\n')

    expect(currentWriters).toContain('learning_purpose')
    expect(currentWriters).toContain('course_teaching_type')
    expect(currentWriters).not.toMatch(/(?:course_type|course_purpose|composition_style)\s*:/)
    expect(currentWriters).not.toMatch(/\.(?:course_type|course_purpose|composition_style)\s*=/)
  })
})
