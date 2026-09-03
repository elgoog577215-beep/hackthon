import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const workbenchSource = readFileSync(
  resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'),
  'utf8',
)

describe('teacher outline direct workflow', () => {
  it('keeps editing and embedded AI as outline document actions while removing the confirmation gate', () => {
    const actionsStart = workbenchSource.indexOf('<TeacherDocumentCommandBar')
    const editAction = workbenchSource.indexOf('data-testid="outline-manual-action"', actionsStart)
    const actionsEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', actionsStart)
    const outlineActions = workbenchSource.slice(actionsStart, actionsEnd)

    expect(actionsStart).toBeGreaterThan(-1)
    expect(editAction).toBeGreaterThan(actionsStart)
    expect(editAction).toBeLessThan(actionsEnd)
    expect(outlineActions).not.toContain('outline-confirm-action')
    expect(outlineActions).not.toContain('confirmInlineOutline')
    expect(outlineActions).toContain('@click="openOutlineInlineAi"')
    expect(workbenchSource).toContain('function openOutlineInlineAi() { outlineEditor.value?.openInlineAi?.() }')
    expect(workbenchSource).not.toContain("(event: 'outlineConfirmed')")
    expect(workbenchSource).not.toContain('@confirmed="handleInlineOutlineConfirmed"')
  })

  it('replaces the right-side assistant with the embedded outline AI entry', () => {
    const actionsStart = workbenchSource.indexOf('<TeacherDocumentCommandBar')
    const actionsEnd = workbenchSource.indexOf('</TeacherDocumentCommandBar>', actionsStart)
    const outlineActions = workbenchSource.slice(actionsStart, actionsEnd)

    expect(outlineActions).not.toContain("openAiCollaboration('outline')")
    expect(workbenchSource).not.toContain('@click="openContextAiTab"')
    expect(workbenchSource).not.toContain("t('courseWorkbench.contextPane.ai', 'AI 助手')")
    expect(workbenchSource).not.toContain('data-testid="teacher-ai-dialog"')
    expect(workbenchSource).toContain('@open-ai-selection="openAiFromSelection(\'outline\', $event)"')
  })

  it('keeps outline review available as a quiet, non-blocking reference action', () => {
    expect(workbenchSource).toContain('data-testid="outline-quality-review-open"')
    expect(workbenchSource).toContain('data-testid="outline-quality-review-dialog"')
    expect(workbenchSource).toContain("t('courseWorkbench.outlineReview.nonBlocking', '仅供参考，不影响后续生成')")
    expect(workbenchSource).toContain('@quality-review-change="handleOutlineQualityReviewChange"')
    expect(workbenchSource).not.toContain('outline-quality-review__content')
  })
})
