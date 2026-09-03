import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const workbenchSource = readFileSync(
  resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'),
  'utf8',
)
const outlineSource = readFileSync(
  resolve(process.cwd(), 'src/components/CourseOutlineReview.vue'),
  'utf8',
)

describe('teacher outline confirmation placement', () => {
  it('places the pending confirmation beside the outline edit action', () => {
    const actionsStart = workbenchSource.indexOf('<TeacherDocumentCommandBar')
    const editAction = workbenchSource.indexOf('data-testid="outline-manual-action"', actionsStart)
    const confirmAction = workbenchSource.indexOf('data-testid="outline-confirm-action"', actionsStart)
    const actionsEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', confirmAction)

    expect(actionsStart).toBeGreaterThan(-1)
    expect(editAction).toBeGreaterThan(actionsStart)
    expect(confirmAction).toBeGreaterThan(editAction)
    expect(confirmAction).toBeLessThan(actionsEnd)
    expect(workbenchSource.slice(editAction, actionsEnd)).toContain('v-if="outlineAwaitingReview"')
    expect(workbenchSource.slice(confirmAction, actionsEnd)).toContain('@click="confirmInlineOutline"')
    expect(workbenchSource.slice(confirmAction, actionsEnd)).toContain(':disabled="stageSwitching || outlineConfirming"')
    expect(workbenchSource.slice(confirmAction, actionsEnd)).toContain("t('courseWorkbench.confirmOutline', '确认课程大纲')")
    expect(workbenchSource.slice(confirmAction, actionsEnd)).not.toContain('outlineCanConfirm')
    expect(workbenchSource.slice(confirmAction, actionsEnd)).not.toContain('TriangleAlert')
  })

  it('uses the stable right-side assistant instead of a duplicate outline toolbar entry', () => {
    const actionsStart = workbenchSource.indexOf('<TeacherDocumentCommandBar')
    const actionsEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', actionsStart)
    const outlineActions = workbenchSource.slice(actionsStart, actionsEnd)

    expect(outlineActions).not.toContain("openAiCollaboration('outline')")
    expect(workbenchSource).toContain('@click="openContextAiTab"')
    expect(workbenchSource).toContain("t('courseWorkbench.contextPane.ai', 'AI 助手')")
  })

  it('keeps the document scroll layout unchanged and delegates confirmation outward', () => {
    const bodyStart = outlineSource.indexOf('<div class="outline-review__body">')
    const footerStart = outlineSource.indexOf('<footer class="outline-review__footer"')

    expect(outlineSource).not.toContain('outline-review__action-bar')
    expect(bodyStart).toBeGreaterThan(-1)
    expect(footerStart).toBeGreaterThan(bodyStart)
    expect(outlineSource).toContain('grid-template-rows:minmax(0,1fr) auto')
    expect(workbenchSource).toContain('confirmation-placement="external"')
    expect(outlineSource).toMatch(
      /defineExpose\(\{[\s\S]*finishEditing,[\s\S]*confirmOutline,/,
    )
    expect(outlineSource).not.toContain('class="outline-quality"')
    expect(outlineSource).not.toContain('outlineQualityStatusLabel')
    expect(outlineSource).not.toContain("t('courseGeneration.outlineReview.documentQuality', '整篇审读')")
    expect(workbenchSource).toContain('data-testid="outline-quality-review"')
    expect(workbenchSource).toContain("t('courseWorkbench.contextPane.references', '课程资料')")
    expect(workbenchSource).toContain("t('courseWorkbench.outlineReview.nonBlocking', '不影响确认')")
    expect(workbenchSource).toContain('@quality-review-change="handleOutlineQualityReviewChange"')
  })
})
