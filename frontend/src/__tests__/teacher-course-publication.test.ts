import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8')

describe('teacher course publication', () => {
  it('keeps publication in the existing course workbench and requires confirmation', () => {
    const workbench = source('src/components/TeacherCourseWorkbench.vue')

    expect(workbench).toContain('/lesson-authoring/publication-readiness')
    expect(workbench).toContain('/lesson-authoring/publish')
    expect(workbench).toContain('expected_document_revision')
    expect(workbench).toContain('publicationConfirmationOpen')
    expect(workbench).toContain("window.location.assign(`/course/${props.courseId}/learn`)")
  })

  it('explains that questions awaiting review stay private in both locales', () => {
    const zh = source('public/locales/zh/translation.json')
    const en = source('public/locales/en/translation.json')

    expect(zh).toContain('待审核题目不会公开')
    expect(en).toContain('Questions awaiting review stay private')
  })
})
