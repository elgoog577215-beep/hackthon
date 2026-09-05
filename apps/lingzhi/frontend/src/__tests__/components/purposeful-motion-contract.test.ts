import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(process.cwd(), 'src')
const source = (path: string) => readFileSync(resolve(sourceRoot, path), 'utf8')

describe('purposeful motion contract', () => {
  it('uses bounded transitions for navigation and primary workspace changes', () => {
    const app = source('App.vue')
    const home = source('views/TeacherTeachingCalendarView.vue')
    const workspace = source('views/CourseWorkspaceView.vue')

    expect(app).toContain('<Transition name="route-surface" mode="out-in">')
    expect(home).toContain('<Transition name="home-surface" mode="out-in">')
    expect(home).toContain('animation:calendar-view-arrive .22s')
    expect(workspace).toContain('<Transition name="workspace-load" mode="out-in">')
    expect(workspace).toContain('<Transition name="workspace-surface" mode="out-in">')
  })

  it('keeps the create dialog entrance subtle and honors reduced motion everywhere', () => {
    const app = source('App.vue')
    const home = source('views/TeacherTeachingCalendarView.vue')
    const workspace = source('views/CourseWorkspaceView.vue')
    const create = source('views/TeacherCourseCreateView.vue')

    expect(create).toContain('animation:course-create-dialog-in .24s')
    for (const target of [app, home, workspace, create]) {
      expect(target).toMatch(/prefers-reduced-motion:\s*reduce/)
    }
    expect(workspace).not.toMatch(/transition:\s*(?:width|height|top|left|margin)/)
  })
})
