import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (relativePath: string) => fs.readFileSync(
  path.resolve(process.cwd(), 'src', relativePath),
  'utf8',
)

describe('课程调整工作区边界', () => {
  it('从教师 AI 侧栏迁出完整表单，并由课程空间承载独立入口', () => {
    const assistant = source('components/SideAIPanel.vue')
    const workspace = source('views/CourseWorkspaceView.vue')

    expect(assistant).not.toContain('<CourseEvolutionPanel')
    expect(assistant).toContain("emit('openCourseAdjustment'")
    expect(workspace).toContain('class="adjustment-action"')
    expect(workspace).toContain("name: 'course-change-workspace'")
    expect(source('router/index.ts')).toContain("path: '/course/:courseId/changes/:planId?'")
    expect(source('views/CourseChangeWorkspaceView.vue')).toContain('standalone')
  })
})
