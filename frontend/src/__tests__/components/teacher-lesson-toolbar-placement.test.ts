import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const workbenchSource = readFileSync(
  resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'),
  'utf8',
)

describe('teacher lesson toolbar placement', () => {
  it('keeps document actions above the formal document without restoring section tabs', () => {
    const toolbar = workbenchSource.indexOf('class="lesson-command-bar"')
    const document = workbenchSource.indexOf('<TeacherLessonPlanDocument')

    expect(toolbar).toBeGreaterThan(-1)
    expect(document).toBeGreaterThan(toolbar)
    expect(workbenchSource).not.toContain('class="lesson-section-tabs"')
    expect(workbenchSource).toContain(
      '.workbench-center.is-lesson-workspace :deep(.lesson-document){overflow:hidden;border:1px solid #e0e6ef',
    )
  })
})
