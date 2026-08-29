import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (relativePath: string) => fs.readFileSync(
  path.resolve(process.cwd(), 'src', relativePath),
  'utf8',
)

describe('课程审计与更新边界', () => {
  it('把材料审计与全课调整收入同一课程级链路', () => {
    const assistant = source('components/SideAIPanel.vue')
    const workspace = source('views/CourseWorkspaceView.vue')
    const router = source('router/index.ts')
    const center = source('views/TeacherMaterialAuditReportView.vue')

    expect(assistant).not.toContain('<CourseEvolutionPanel')
    expect(assistant).toContain("emit('openCourseAdjustment'")
    expect(workspace).toContain('class="audit-action"')
    expect(workspace).not.toContain('class="adjustment-action"')
    expect(workspace).toContain("name: 'course-audit-updates'")
    expect(router).toContain("path: '/course/:courseId/audit-updates/:planId?'")
    expect(router).toContain("path: '/course/:courseId/material-audit'")
    expect(router).toContain("path: '/course/:courseId/changes/:planId?'")
    expect(center).toContain('<CourseEvolutionWorkspace')
    expect(center).toContain('embedded-in-center')
  })
})
