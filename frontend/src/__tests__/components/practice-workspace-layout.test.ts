import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const componentSource = readFileSync(
  resolve(process.cwd(), 'src/components/PracticeWorkspace.vue'),
  'utf8',
)

describe('PracticeWorkspace expanded desktop layout', () => {
  it('uses a wider stage with a taller answer editor and compact bottom spacing', () => {
    expect(componentSource).toContain(
      '.question-stage,.history-list { width:min(1280px,calc(100% - 64px));',
    )
    expect(componentSource).toContain('padding:24px 0 36px;')
    expect(componentSource).toContain('min-height:clamp(360px,54vh,680px);')
  })

  it('keeps the compact mobile layout bounded', () => {
    expect(componentSource).toContain(
      '.question-stage,.history-list { width:calc(100% - 28px); padding-top:18px;',
    )
    expect(componentSource).toContain('.answer-editor { min-height:180px; }')
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

  it('shows independent answer diagnosis and the single next action', () => {
    expect(componentSource).toContain('题目解析与本次判断')
    expect(componentSource).toContain('你采用了什么思路')
    expect(componentSource).toContain('当前最关键的差距')
    expect(componentSource).toContain('下一步只做这一件事')
    expect(componentSource).toContain('answerDiagnosis.value?.diagnosis')
  })
})
