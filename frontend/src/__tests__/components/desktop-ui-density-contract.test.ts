import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function source(path: string) {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

const librarySource = source('src/views/CourseLibraryView.vue')
const teacherSpaceSource = source('src/views/TeacherCourseSpaceView.vue')
const teacherFilesSource = source('src/views/TeacherCourseFilesView.vue')
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
    expect(workbenchSource).toMatch(/grid-template-rows:62px minmax\(0,1fr\)/)
    expect(taskCenterSource).toMatch(/grid-template-columns:260px minmax\(0,1fr\)/)
  })

  it('keeps technical diagnostics available without placing raw codes in the primary alert', () => {
    expect(taskCenterSource).toContain('class="task-error-detail"')
    expect(taskCenterSource).toContain("courseTasks.problem.technicalReason")
    expect(taskCenterSource).not.toContain("t('courseTasks.problem.detail'")
  })

  it('removes repeated desktop containers and redundant return actions', () => {
    expect(reviewCenterSource).not.toContain("t('questionBank.currentCourse'")
    expect(reviewPanelSource).toMatch(/\.question-bank-panel\s*\{[^}]*border-top:1px solid[^}]*background:transparent/s)
    // 「多余的返回入口」指的是嵌入到已有面包屑的宿主里还自带一个返回按钮。
    // 原断言直接禁掉这个文案串，但它是源码 grep，看不出按钮有没有被条件挡住——
    // 而 TeacherCourseSpaceView 还有独立路由 /teacher-course-space，
    // 那里这个按钮是唯一的出口，禁掉会把人困在页面上。
    // 所以改成钉真正要保护的东西：返回入口必须整体挂在 !embedded 之下。
    expect(teacherSpaceSource).toMatch(
      /<header v-if="!embedded"[\s\S]*?teacherCourseSpace\.backToCourses[\s\S]*?<\/header>/,
    )
    // 嵌入时的返回路径由宿主的面包屑提供，不需要页面自己再来一个。
    expect(teacherFilesSource).toContain("router.push({ name: 'teacher-course-library' })")
    expect(teacherSpaceSource).toMatch(/\.knowledge-space\s*\{[^}]*margin:\s*18px auto 0/s)
  })

  it('opens only the active learning path instead of every second-level node', () => {
    expect(navigatorSource).toContain('containsActiveNode')
    expect(navigatorSource).toContain('containsActiveNode(props.node) || (!props.activeId && props.depth < 1)')
    expect(navigatorSource).not.toContain('ref(props.depth < 2)')
  })
})
