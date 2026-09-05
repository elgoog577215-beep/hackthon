import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const componentSource = readFileSync(
  resolve(process.cwd(), 'src/components/PracticeWorkspace.vue'),
  'utf8',
)

describe('PracticeWorkspace question-book dialog layout', () => {
  it('lets the dialog own the three view buttons without adding a content row', () => {
    expect(componentSource).toContain('hideViewSwitch?: boolean')
    expect(componentSource).toContain("(event: 'viewChange', view: 'current' | 'history' | 'needs_review'): void")
    expect(componentSource).toContain('defineExpose({ openHistory, selectView })')
    expect(componentSource).toContain('.question-book-views {')
    expect(componentSource).toContain("t('courseWorkspace.practice.needsReview', '错题本')")
    expect(componentSource).toContain('.practice-workspace.has-external-view-switch .question-book-empty')
    expect(componentSource).toContain('width: min(820px, calc(100% - 48px));')
    expect(componentSource).not.toContain('.practice-header')
    expect(componentSource).not.toContain('.practice-tabs')
  })

  it('rebuilds the empty state as a clear generation setup instead of a full-page blank canvas', () => {
    expect(componentSource).toContain('class="question-book-empty"')
    expect(componentSource).toContain('class="question-bank-rebuild__heading"')
    expect(componentSource).toContain('class="question-bank-rebuild__retrieval"')
    expect(componentSource).toContain('.question-book-empty {')
    expect(componentSource).toContain('flex-direction: column;')
    expect(componentSource).toContain('width: min(420px, 100%);')
    expect(componentSource).toContain('@media (max-width: 760px)')
  })

  it('renders structured solution steps, final answer, checks and representation', () => {
    expect(componentSource).toContain('solution-steps')
    expect(componentSource).toContain('solution-final-answer')
    expect(componentSource).toContain('workspace.revealedSolution.checks')
    expect(componentSource).toContain('workspace.revealedSolution.representation')
    expect(componentSource).toContain('formatSolutionValue')
    expect(componentSource).toContain("representation?.kind !== 'reasoning_path'")
    expect(componentSource).not.toContain('JSON.stringify(value, null, 2)')
  })

  it('exposes a manual refresh command backed by the frozen-question API', () => {
    expect(componentSource).toContain('data-testid="refresh-practice-question"')
    expect(componentSource).toContain('workspace.refreshPracticeQuestion')
    expect(componentSource).toContain('当前未提交草稿会结束并保留为一次已放弃记录')
  })

  it('renders the question body through the Markdown presentation pipeline', () => {
    expect(componentSource).toContain('data-testid="practice-question-markdown"')
    expect(componentSource).toContain('data-testid="practice-question-task"')
    expect(componentSource).toContain('data-testid="practice-question-material"')
    expect(componentSource).toContain(':content="currentQuestionMarkdown.task"')
    expect(componentSource).toContain(':content="currentQuestionMarkdown.material"')
    expect(componentSource).toContain('splitPracticeQuestionMarkdown')
    expect(componentSource).toContain('<details')
    expect(componentSource).toContain(':key="currentQuestion?.revision_id || currentQuestion?.asset_id || currentQuestion?.question_id"')
    expect(componentSource).not.toContain('<h3>{{ currentQuestion.prompt }}</h3>')
  })

  it('shows independent answer diagnosis and the single next action', () => {
    expect(componentSource).toContain('题目解析与本次判断')
    expect(componentSource).toContain('你采用了什么思路')
    expect(componentSource).toContain('当前最关键的差距')
    expect(componentSource).toContain('下一步只做这一件事')
    expect(componentSource).toContain('answerDiagnosis.value?.diagnosis')
  })
})
