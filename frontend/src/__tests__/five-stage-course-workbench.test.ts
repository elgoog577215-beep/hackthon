import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(
  resolve(process.cwd(), 'src', path),
  'utf8',
)

describe('five-stage course workbench boundary', () => {
  it('keeps the question bank optional and places paper composition inside it', () => {
    const workbench = source('components/TeacherCourseWorkbench.vue')
    const questionBank = source('components/QuestionBankReviewPanel.vue')
    const questionBankUsage = workbench.match(/<QuestionBankReviewPanel[\s\S]*?\/>/)?.[0] || ''

    expect(workbench).toContain("type CoreStageId = 'foundation' | 'lesson' | 'question-bank' | 'script' | 'ppt'")
    expect(workbench).toContain("type StageId = CoreStageId | 'companion'")
    expect(workbench.indexOf("id: 'question-bank'")).toBeLessThan(
      workbench.indexOf("id: 'script'"),
    )
    expect(workbench).toContain('<QuestionBankReviewPanel')
    expect(questionBankUsage).not.toContain('initial-node-ids')
    expect(questionBankUsage).not.toContain('material-asset-ids')
    expect(questionBankUsage).toContain('@references-change="handleQuestionBankReferencesChange"')
    expect(questionBank).toContain('v-model="questionReferences"')
    expect(questionBank).toContain('<ExamPaperComposer')
    expect(questionBank).toContain('material_asset_ids: [...effectiveMaterialAssetIds.value]')
  })

  it('keeps companion documents outside the numbered teaching chain', () => {
    const workbench = source('components/TeacherCourseWorkbench.vue')
    const studio = source('components/CompanionDocumentStudio.vue')
    const fileView = source('views/TeacherCourseSpaceView.vue')

    expect(workbench).toContain('class="companion-entry"')
    expect(workbench).toContain('<CompanionDocumentStudio')
    expect(workbench).not.toContain("id: 'companion' as const, step: '06'")
    expect(studio).toContain('class="template-grid"')
    expect(studio).toContain('grading_rubric')
    expect(studio).toContain('material_checklist')
    expect(fileView).toContain("type: 'companion_documents'")
    expect(fileView).toContain("type: 'companion_document'")
    expect(fileView).toContain("emit('openCompanionDocuments')")
  })

  it('manages question banks and exam papers as formal file-view assets', () => {
    const fileView = source('views/TeacherCourseSpaceView.vue')
    const workspace = source('views/CourseWorkspaceView.vue')

    expect(fileView).toContain("type: 'question_bank'")
    expect(fileView).toContain("type: 'exam_paper'")
    expect(fileView).toContain('/question-bank/exam-papers')
    expect(fileView).toContain("emit('openQuestionBank')")
    expect(workspace).toContain('@open-question-bank="openQuestionBankWorkbench"')
    expect(workspace).toContain("requestedWorkbenchStage.value = 'question-bank'")
  })
})
