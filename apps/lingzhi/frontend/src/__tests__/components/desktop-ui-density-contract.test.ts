import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function source(path: string) {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

const teacherSpaceSource = source('src/views/TeacherCourseSpaceView.vue')
const taskCenterSource = source('src/components/CourseTaskCenter.vue')
const reviewPanelSource = source('src/components/QuestionBankReviewPanel.vue')
const navigatorSource = source('src/components/CourseNavigatorNode.vue')

describe('desktop UI density contract', () => {

  it('keeps technical diagnostics available without placing raw codes in the primary alert', () => {
    expect(taskCenterSource).toContain('class="task-error-detail"')
    expect(taskCenterSource).toContain("courseTasks.problem.technicalReason")
    expect(taskCenterSource).not.toContain("t('courseTasks.problem.detail'")
  })

  it('removes repeated desktop containers and redundant return actions', () => {
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
