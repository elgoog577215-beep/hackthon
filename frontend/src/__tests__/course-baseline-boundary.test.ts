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
    expect(workbench).toContain('generationTask.value?.phaseDetail?.lesson_statuses')
    expect(workbench).toContain('data-testid="outline-detail-stream"')
    expect(workbench).toContain('<CourseReferenceTray')
    expect(workbench).toContain("'foundation' | 'lesson' | 'script' | 'ppt'")
    expect(workbench).toContain("requestStageChange('question-bank')")
    expect(workbench).toContain('<QuestionBankReviewPanel')
    expect(references).toContain('class="source-group ppt-smart-sources"')
    expect(references).toContain('class="system-context"')
    expect(references).toContain('workflowLocked')
    expect(references).toContain('source-group--primary')
    expect(references).toContain('source-group--references')
    expect(workbench).toContain("emit('open-course-information')")
    expect(workbench).toContain('@open-course-information="emit(\'open-course-information\')"')
    expect(workbench).not.toContain('class="course-information-entry"')
    expect(workspace).toContain('<CourseBaselineDialog')
    expect(workspace).toContain(':initial-envelope="courseInformationEnvelope"')
    expect(workspace).toContain('void lessonStore.load(requestedCourseId)')
    expect(workspace).toContain('void Promise.allSettled([')
    expect(workspace).toContain('teacherReadRequestConfig')
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

  it('新建课和课程基线提供相同的八种学期选择', () => {
    const termWriters = [
      source('views/TeacherCourseCreateView.vue'),
      source('components/CourseBaselineDialog.vue'),
    ]

    for (const writer of termWriters) {
      for (const term of ['春夏', '秋冬', '春', '夏', '秋', '冬', '暑期课', '寒期课']) {
        expect(writer).toContain(`<option value="${term}">`)
      }
    }
  })
})
