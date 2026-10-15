import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function source(path: string) {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

const reviewPanelSource = source('src/components/QuestionBankReviewPanel.vue')
const learningSource = source('src/views/LearnerCourseView.vue')

describe('mobile UI density contract', () => {

  it('uses one visible generation action, a compact status band, and transform-based progress', () => {
    expect(reviewPanelSource).toMatch(
      /data-testid="question-generation-studio"[\s\S]*?data-testid="generate-question-bank"/,
    )
    expect(reviewPanelSource).toMatch(
      /\.question-bank-summary\s*\{[^}]*border-block:1px solid/,
    )
    expect(reviewPanelSource).toMatch(
      /\.question-bank-summary\s*\{[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/,
    )
    expect(reviewPanelSource).toContain(
      'transform: `scaleX(${rebuildJob.progress / 100})`',
    )
    expect(reviewPanelSource).not.toContain('transition:width')
  })

  it('opens formal course content first when switching to a narrow viewport', () => {
    expect(learningSource).toContain('const wasNarrow = windowWidth.value < 1024')
    expect(learningSource).toContain(
      'windowWidth.value < 1024 && (!wasNarrow || aiVisible.value)',
    )
  })
})
