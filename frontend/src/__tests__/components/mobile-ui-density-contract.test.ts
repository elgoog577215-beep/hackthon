import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function source(path: string) {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

const librarySource = source('src/views/CourseLibraryView.vue')
const workbenchSource = source('src/components/CourseWorkbench.vue')
const taskCenterSource = source('src/components/CourseTaskCenter.vue')
const reviewCenterSource = source('src/components/QuestionBankReviewCenter.vue')
const reviewPanelSource = source('src/components/QuestionBankReviewPanel.vue')

describe('mobile UI density contract', () => {
  it('keeps course pagination in content flow and brings courses into the first screen', () => {
    expect(librarySource).not.toMatch(
      /<Teleport to="body">[\s\S]*?class="library-pagination-dock"/,
    )
    expect(librarySource).toMatch(
      /\.library-pagination-dock\s*\{[^}]*position:relative[^}]*margin:20px auto 0/s,
    )
    expect(librarySource).toMatch(
      /@media\s*\(max-width:700px\)[\s\S]*?\.library-toolbar\s*\{[^}]*flex-wrap:nowrap[^}]*gap:8px/,
    )
    expect(librarySource).toMatch(
      /@media\s*\(max-width:700px\)[\s\S]*?\.library-toolbar label\s*\{[^}]*min-width:112px[^}]*flex:0 1 42%/,
    )
    expect(librarySource).toMatch(
      /@media\s*\(max-width:700px\)[\s\S]*?\.pagination-jump\s*\{\s*display:none/,
    )
  })

  it('uses a compact workbench header and a horizontal mobile task selector', () => {
    expect(workbenchSource).toMatch(
      /\.course-workbench__mark,\.course-workbench__identity p\s*\{\s*display:none/,
    )
    expect(taskCenterSource).toMatch(
      /\.task-center__body\s*\{[^}]*grid-template-rows:76px minmax\(0,1fr\)/,
    )
    expect(taskCenterSource).toMatch(
      /\.task-list\s*\{[^}]*display:flex[^}]*overflow-x:auto/,
    )
    expect(taskCenterSource).toMatch(
      /\.task-center--embedded\s*\{[^}]*height:100%/,
    )
  })

  it('keeps the mobile course selector compact and removes repeated helper copy', () => {
    expect(reviewCenterSource).not.toContain('questionBank.openToInspect')
    expect(reviewCenterSource).toMatch(
      /\.review-center__body\s*\{[^}]*grid-template-rows:112px minmax\(0,1fr\)/,
    )
    expect(reviewCenterSource).toMatch(
      /\.review-course-rows\s*\{[^}]*display:flex[^}]*overflow-x:auto/,
    )
    expect(reviewCenterSource).toMatch(
      /\.selected-course-heading > div\s*\{[^}]*display:contents/,
    )
  })

  it('uses one recovery action, a compact status band, and transform-based progress', () => {
    expect(reviewPanelSource).toMatch(
      /v-if="!errorMessage"[\s\S]*?data-testid="rebuild-course-question-bank"/,
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
})
