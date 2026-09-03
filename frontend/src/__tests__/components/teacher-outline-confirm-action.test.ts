import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const workbenchSource = readFileSync(
  resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'),
  'utf8',
)

describe('teacher outline direct workflow', () => {
  it('keeps editing as the only outline document action and removes the confirmation gate', () => {
    const actionsStart = workbenchSource.indexOf('<TeacherDocumentCommandBar')
    const editAction = workbenchSource.indexOf('data-testid="outline-manual-action"', actionsStart)
    const actionsEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', actionsStart)
    const outlineActions = workbenchSource.slice(actionsStart, actionsEnd)

    expect(actionsStart).toBeGreaterThan(-1)
    expect(editAction).toBeGreaterThan(actionsStart)
    expect(editAction).toBeLessThan(actionsEnd)
    expect(outlineActions).not.toContain('outline-confirm-action')
    expect(outlineActions).not.toContain('confirmInlineOutline')
    expect(workbenchSource).not.toContain("(event: 'outlineConfirmed')")
    expect(workbenchSource).not.toContain('@confirmed="handleInlineOutlineConfirmed"')
  })

  it('uses the stable right-side assistant instead of a duplicate outline toolbar entry', () => {
    const actionsStart = workbenchSource.indexOf('<TeacherDocumentCommandBar')
    const actionsEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', actionsStart)
    const outlineActions = workbenchSource.slice(actionsStart, actionsEnd)

    expect(outlineActions).not.toContain("openAiCollaboration('outline')")
    expect(workbenchSource).toContain('@click="openContextAiTab"')
    expect(workbenchSource).toContain("t('courseWorkbench.contextPane.ai', 'AI 助手')")
  })

  it('opens the non-blocking outline review from a quiet button into a dialog', () => {
    expect(workbenchSource).toContain('data-testid="outline-quality-review-open"')
    expect(workbenchSource).toContain('data-testid="outline-quality-review-dialog"')
    expect(workbenchSource).toContain("t('courseWorkbench.outlineReview.open', '查看大纲审阅')")
    expect(workbenchSource).toContain("t('courseWorkbench.outlineReview.nonBlocking', '仅供参考，不影响后续生成')")
    expect(workbenchSource).toContain('@quality-review-change="handleOutlineQualityReviewChange"')
    expect(workbenchSource).not.toContain('outline-quality-review__content')
  })
})
