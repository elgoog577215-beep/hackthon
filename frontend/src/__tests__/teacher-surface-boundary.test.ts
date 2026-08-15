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
    expect(routerSource).toMatch(/path:\s*'\/course\/:courseId'[\s\S]*name:\s*'learning'/)
  })

  it('uses one adapter without duplicating course or generation state', () => {
    const adapterSource = readFileSync(
      resolve(sourceRoot, 'features/teacher-course/useTeacherCourseRuntime.ts'),
      'utf8',
    )
    expect(adapterSource).toContain('useCourseStore()')
    expect(adapterSource).toContain('useGenerationStore()')
    expect(adapterSource).not.toMatch(/reactive\s*\(|ref\s*\(|defineStore\s*\(/)
  })
})
