import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function source(path: string) {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

const librarySource = source('src/views/CourseLibraryView.vue')
const teacherSpaceSource = source('src/views/TeacherCourseSpaceView.vue')
const workbenchSource = source('src/components/CourseWorkbench.vue')
const taskCenterSource = source('src/components/CourseTaskCenter.vue')
const reviewCenterSource = source('src/components/QuestionBankReviewCenter.vue')
const reviewPanelSource = source('src/components/QuestionBankReviewPanel.vue')
const navigatorSource = source('src/components/CourseNavigatorNode.vue')

describe('desktop UI density contract', () => {
  it('brings course content forward and keeps the toolbar compact', () => {
    expect(librarySource).toMatch(/class="library-header__copy"/)
    expect(librarySource).toMatch(/--course-card-height:140px/)
    expect(librarySource).toMatch(/\.library-toolbar\s*\{[^}]*margin:16px auto 12px/)
  })

  it('uses the desktop workbench width for content instead of modal margins', () => {
    expect(workbenchSource).toMatch(/width:min\(1320px,calc\(100vw - 40px\)\)/)
    // 表头高度跟随组件：5150a085「simplify teacher workspace ui」把 .course-workbench
    // 改成 64px，本断言原停在 8f4322de（2026-08-12）的 62px，是过期值不是回归。
    expect(workbenchSource).toMatch(/grid-template-rows:64px minmax\(0,1fr\)/)
    expect(taskCenterSource).toMatch(/grid-template-columns:260px minmax\(0,1fr\)/)
  })

  it('keeps technical diagnostics available without placing raw codes in the primary alert', () => {
    expect(taskCenterSource).toContain('class="task-error-detail"')
    expect(taskCenterSource).toContain("courseTasks.problem.technicalReason")
    expect(taskCenterSource).not.toContain("t('courseTasks.problem.detail'")
  })

  it('removes repeated desktop containers and redundant return actions', () => {
    expect(reviewCenterSource).not.toContain("t('questionBank.currentCourse'")
    expect(reviewPanelSource).toMatch(/\.question-bank-panel\s*\{[^}]*padding:0[^}]*background:transparent/s)
    expect(reviewPanelSource).not.toContain('question-generation-studio__policy')
    expect(teacherSpaceSource).toContain('<header v-if="!embedded" class="standalone-header">')
    expect(teacherSpaceSource).toContain('class="file-tree-pane"')
    expect(teacherSpaceSource).toContain('class="file-list-pane"')
    expect(teacherSpaceSource).toContain('class="file-inspector"')
    expect(teacherSpaceSource).not.toContain('knowledge-space')
  })

  it('opens only the active learning path instead of every second-level node', () => {
    expect(navigatorSource).toContain('containsActiveNode')
    expect(navigatorSource).toContain('containsActiveNode(props.node) || (!props.activeId && props.depth < 1)')
    expect(navigatorSource).not.toContain('ref(props.depth < 2)')
  })
})
