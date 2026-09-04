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
    expect(lessonToolbarSource).not.toContain('lessonPlanDocument?.openInlineAi()')
    expect(lessonToolbarSource).not.toContain("aiCollaboration.iterateCandidate")
    expect(workbenchSource).toContain("activeStage === 'lesson' && lessonToolbarVisible && !aiCandidatePending")
    expect(workbenchSource).toContain(
      '.workbench-center.is-lesson-workspace .lesson-command-bar,.workbench-center.is-lesson-workspace .script-command-bar{width:100%;max-width:none;justify-content:space-between;gap:12px;margin:0 0 12px;background:transparent}',
    )
    expect(workbenchSource).toContain(
      '.workbench-center.is-lesson-workspace :deep(.lesson-document){overflow:hidden;border:1px solid #e0e4ea',
    )
  })

  it('keeps AI modification and candidate actions out of every document top bar', () => {
    const outlineMarker = workbenchSource.indexOf("t('courseWorkbench.outlineDocument.actions'")
    const outlineStart = workbenchSource.lastIndexOf('<TeacherDocumentCommandBar', outlineMarker)
    const outlineEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', outlineMarker)
    const outlineToolbarSource = workbenchSource.slice(outlineStart, outlineEnd)

    const scriptMarker = workbenchSource.indexOf("t('courseWorkbench.scriptDocument.actions'")
    const scriptStart = workbenchSource.lastIndexOf('<TeacherDocumentCommandBar', scriptMarker)
    const scriptEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', scriptMarker)
    const scriptToolbarSource = workbenchSource.slice(scriptStart, scriptEnd)

    for (const toolbarSource of [outlineToolbarSource, scriptToolbarSource]) {
      expect(toolbarSource).not.toContain('openInlineAi')
      expect(toolbarSource).not.toContain('AI 修改')
      expect(toolbarSource).not.toContain("aiCollaboration.iterateCandidate")
      expect(toolbarSource).not.toContain('resolveAiCandidate')
    }
    expect(workbenchSource).not.toContain('function openScriptInlineAi()')
    expect(workbenchSource).toContain('scriptToolbarVisible && !aiCandidatePending')
  })
})
