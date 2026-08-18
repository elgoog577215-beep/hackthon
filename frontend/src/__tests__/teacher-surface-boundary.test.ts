import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(process.cwd(), 'src')
const teacherViewsRoot = resolve(sourceRoot, 'views')
const teacherViews = readdirSync(teacherViewsRoot)
  .filter(name => /^Teacher.*\.vue$/.test(name))
  .map(name => ({ name, source: readFileSync(resolve(teacherViewsRoot, name), 'utf8') }))

describe('teacher and learner surface boundary', () => {
  it('keeps teacher pages behind the teacher runtime adapter', () => {
    expect(teacherViews.length).toBeGreaterThan(0)
    const directStoreImport = /from\s+['"][^'"]*stores\/(?:course|generation)['"]/
    for (const view of teacherViews) {
      expect(view.source, view.name).not.toMatch(directStoreImport)
      expect(view.source, view.name).not.toMatch(/\buse(?:Course|Generation)Store\s*\(/)
    }
  })

  it('keeps learner defaults and teacher routes in separate namespaces', () => {
    const routerSource = readFileSync(resolve(sourceRoot, 'router/index.ts'), 'utf8')
    expect(routerSource).toContain("path: '/courses'")
    expect(routerSource).toContain("path: '/course/:courseId/learn/:nodeId?'")
    expect(routerSource).toContain("path: '/teacher/courses'")
    expect(routerSource).toContain("path: '/teacher/course/:courseId/production'")
    expect(routerSource).toContain("path: '/teacher/course/:courseId/ppt'")
    expect(routerSource).toMatch(/path:\s*'\/course\/:courseId'[\s\S]*name:\s*'learning'/)
  })

  it('uses one adapter without duplicating course or generation state', () => {
    const adapterSource = readFileSync(
      resolve(sourceRoot, 'features/teacher-course/useTeacherCourseRuntime.ts'),
      'utf8',
    )
    expect(adapterSource).toContain('useCourseStore()')
    expect(adapterSource).toContain('useGenerationStore()')
    expect(adapterSource).toContain("TEACHER_COURSE_CAPABILITY_CONTRACT = 'teacher-course-capabilities/v1'")
    expect(adapterSource).toContain("taskType: 'teacher_outline_generation'")
    expect(adapterSource).toContain("name: 'teacher-ppt-workspace'")
    expect(adapterSource).not.toMatch(/reactive\s*\(|ref\s*\(|defineStore\s*\(/)
  })

  it('routes every teacher course loader through the teacher adapter', () => {
    for (const fileName of [
      'TeacherCourseOverviewView.vue',
      'TeacherCourseProductionView.vue',
      'TeacherCourseFilesView.vue',
    ]) {
      const source = readFileSync(resolve(teacherViewsRoot, fileName), 'utf8')
      expect(source, fileName).toContain('loadTeacherCourse')
      expect(source, fileName).not.toMatch(/courseStore\.loadCourse\s*\(/)
    }
  })

  it('keeps teacher lesson plans on lesson assets and skips learner content generation gates', () => {
    const source = readFileSync(
      resolve(teacherViewsRoot, 'TeacherCourseProductionView.vue'),
      'utf8',
    )

    expect(source).toContain(':plan="selectedLessonPlan"')
    expect(source).toContain(':live="true"')
    expect(source).not.toMatch(/<GenerationLessonPlan[\s\S]*?:task="task"[\s\S]*?\/>/)
    expect(source).not.toContain('selectedLessonPlan || courseStore.currentTeachingPlan')
    expect(source).toContain("reviewStep === 'release'")
    expect(source).not.toContain("reviewStep === 'teaching'")
    expect(source).toContain('旧课程正文不会作为教师教案显示')
    expect(source).toContain('@click="optimizeSelectedLesson"')
  })

  it('keeps teacher copy out of the learner course-library namespace', () => {
    const zh = JSON.parse(readFileSync(
      resolve(process.cwd(), 'public/locales/zh/translation.json'),
      'utf8',
    ))
    const en = JSON.parse(readFileSync(
      resolve(process.cwd(), 'public/locales/en/translation.json'),
      'utf8',
    ))
    const teacherLibrarySource = readFileSync(
      resolve(sourceRoot, 'views/TeacherCourseLibraryView.vue'),
      'utf8',
    )

    expect(zh.courseLibrary.title).toBe('选择一门课程继续学习')
    expect(zh.courseLibrary.status.ready).toBe('可以学习')
    expect(zh.teacherCourseLibrary.title).toBe('课程工作台')
    expect(en.courseLibrary.title).toBe('Choose a course and continue learning')
    expect(en.courseLibrary.status.ready).toBe('Ready to learn')
    expect(en.teacherCourseLibrary.title).toBe('Course workspace')
    expect(teacherLibrarySource).toContain("teacherCourseLibrary.title")
    expect(teacherLibrarySource).not.toContain("courseLibrary.teacherSummary")
    expect(teacherLibrarySource).not.toContain('<Teleport to="#app-header-route-actions">')
  })
})
