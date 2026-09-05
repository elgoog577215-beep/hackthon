import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const productionAcademicSurfaces = [
  'components/AdaptiveLearningBlock.vue',
  'components/CompanionDocumentStudio.vue',
  'components/CourseBlockStream.vue',
  'components/CourseEvolutionContentBlock.vue',
  'components/CourseNavigatorNode.vue',
  'components/CourseNode.vue',
  'components/CourseOutlineReview.vue',
  'components/CourseProductionStage.vue',
  'components/DiagramSpecRenderer.vue',
  'components/FeedbackReviewBlock.vue',
  'components/InlineRecordPopover.vue',
  'components/KnowledgeCommandPanel.vue',
  'components/KnowledgeLibrary.vue',
  'components/KnowledgeRelationGraph.vue',
  'components/LearningTaskOverlay.vue',
  'components/MistakeNotebookPanel.vue',
  'components/NotesPanel.vue',
  'components/OutlineGrowthStream.vue',
  'components/PptManuscriptWorkflow.vue',
  'components/PracticeAnswerRenderer.vue',
  'components/PracticeWorkspace.vue',
  'components/QuestionBankImportWorkspace.vue',
  'components/QuestionBankReviewPanel.vue',
  'components/SlideCanvas.vue',
  'components/SlideDeckWorkbench.vue',
  'components/SlideVisualRenderer.vue',
  'components/TeacherCourseWorkbench.vue',
  'components/TeacherLessonAiWorkspace.vue',
  'components/TeacherLessonArrangementSummary.vue',
  'components/TeacherLessonPlanDocument.vue',
  'components/TeacherScriptDocument.vue',
  'components/TeachingRepresentationsOverlay.vue',
  'components/UploadedPptReviewWorkspace.vue',
  'views/PptWorkspaceView.vue',
] as const

describe('生产界面的公式渲染合同', () => {
  it.each(productionAcademicSurfaces)('%s 复用共享的安全学科内容渲染入口', (relativePath) => {
    const source = readFileSync(resolve(process.cwd(), 'src', relativePath), 'utf8')
    expect(source).toMatch(/<(?:MathText|MarkdownRenderer)\b/)
  })
})
