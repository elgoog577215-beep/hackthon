import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const workbenchSource = readFileSync(
  resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'),
  'utf8',
)

describe('teacher lesson toolbar placement', () => {
  it('keeps document actions above the section tabs so the tabs attach to the document', () => {
    const toolbar = workbenchSource.indexOf('class="lesson-command-bar"')
    const sectionTabs = workbenchSource.indexOf('class="lesson-section-tabs"')

    expect(toolbar).toBeGreaterThan(-1)
    expect(sectionTabs).toBeGreaterThan(toolbar)
    expect(workbenchSource).toContain(
      '.workbench-center.is-lesson-workspace .lesson-section-tabs{border:1px solid #e0e6ef',
    )
    expect(workbenchSource).toContain(
      '.workbench-center.is-lesson-workspace :deep(.lesson-document){overflow:hidden;border:1px solid #e0e6ef;border-top:0',
    )
  })
})
