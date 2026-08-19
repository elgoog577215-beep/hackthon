import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(process.cwd(), 'src')
const source = (path: string) => readFileSync(resolve(sourceRoot, path), 'utf8')

describe('unified course workspace boundary', () => {
  it('uses one active course shell for setup, preparation, and formal use', () => {
    const workspace = source('views/CourseWorkspaceView.vue')
    const learning = source('views/LearningView.vue')

    expect(workspace).toContain('<CourseModeTabs :active="activeMode"')
    expect(workspace).toContain('<TeacherCourseSpaceView')
    expect(workspace).toContain('<TeacherCourseCalendarView')
    expect(workspace).toContain('<CourseOutlineReview')
    expect(workspace).toContain('visible-scope="overall"')
    expect(workspace).toContain('visible-scope="sections"')
    expect(learning).toContain('<CourseModeTabs active="formal"')
    expect(workspace).not.toContain('useTeacherCourseRuntime')
    expect(workspace).not.toContain('useTeacherLessonAuthoringStore')
  })

  it('keeps active routes in one namespace and redirects legacy teacher URLs', () => {
    const router = source('router/index.ts')

    expect(router).toContain("path: '/courses'")
    expect(router).toContain("path: '/course/:courseId/workspace/:mode(setup|build)?'")
    expect(router).toContain("path: '/course/:courseId/learn/:nodeId?'")
    expect(router).toContain("path: '/course/:courseId/ppt'")
    expect(router).toMatch(/path:\s*'\/teacher\/course\/:courseId\/files'[\s\S]*?redirect:[\s\S]*?section:\s*'files'/)
    expect(router).toMatch(/path:\s*'\/teacher\/course\/:courseId\/production'[\s\S]*?redirect:[\s\S]*?mode:\s*'build'/)
    expect(router).toMatch(/path:\s*'\/teacher\/:pathMatch\(\.\*\)\*'[\s\S]*?redirect:\s*'\/courses'/)
    expect(router).not.toContain("import('../views/TeacherCourseOverviewView.vue')")
    expect(router).not.toContain("import('../views/TeacherCourseProductionView.vue')")
  })

  it('projects course design and lesson preparation from one teaching plan', () => {
    const workspace = source('views/CourseWorkspaceView.vue')
    const lessonPlan = source('components/GenerationLessonPlan.vue')

    expect(workspace.match(/<GenerationLessonPlan/g)).toHaveLength(2)
    expect(workspace).toContain(':plan="courseStore.currentTeachingPlan"')
    expect(lessonPlan).toContain("visibleScope?: 'both' | 'overall' | 'sections'")
    expect(lessonPlan).not.toContain('teacherLessonAuthoring')
  })

  it('binds the embedded file space to the stable course identity', () => {
    const fileSpace = source('views/TeacherCourseSpaceView.vue')

    expect(fileSpace).toContain("params: embedded.value && props.courseId ? { course_id: props.courseId } : undefined")
    expect(fileSpace).toContain("course_id: embedded.value ? props.courseId : ''")
    expect(fileSpace).toContain("http.patch(`/api/teacher-course-spaces/${legacyMatches[0].package_id}`")
  })

  it('keeps the published formal workspace focused on course, practice, and PPT', () => {
    const learning = source('views/LearningView.vue')

    expect(learning).toContain(':show-lesson-plan="isGenerationPreview"')
    expect(learning).toContain("workspace === 'practice'")
  })
})
