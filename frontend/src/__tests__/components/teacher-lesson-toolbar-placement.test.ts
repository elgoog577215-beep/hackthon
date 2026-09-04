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
    expect(workbenchSource).toContain(':show-history="false"')
    expect(workbenchSource).toContain(':show-status="false"')
    expect(workbenchSource).not.toContain(':selection-ai-enabled="false"')
    expect(workbenchSource).toContain(':request-busy="aiCollaborationBusy"')
    const lessonToolbarStart = workbenchSource.indexOf('class="lesson-command-bar"')
    const lessonToolbarEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', lessonToolbarStart)
    const lessonToolbarSource = workbenchSource.slice(lessonToolbarStart, lessonToolbarEnd)
    expect(lessonToolbarSource).not.toContain("lessonDocument.aiImprove")
    expect(lessonToolbarSource).toContain('lessonPlanDocument?.openInlineAi()')
    expect(workbenchSource).toContain(
      '.workbench-center.is-lesson-workspace .lesson-command-bar{width:calc(100% - 8px);justify-content:flex-end;gap:8px;margin:0 4px 10px;background:transparent}',
    )
    expect(workbenchSource).toContain(
      '.workbench-center.is-lesson-workspace :deep(.lesson-document){overflow:hidden;border:1px solid #e0e6ef',
    )
  })
})
