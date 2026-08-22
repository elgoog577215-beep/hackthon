import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'


const source = (relativePath: string) => fs.readFileSync(path.resolve(__dirname, '..', relativePath), 'utf8')


describe('course baseline authoring boundary', () => {
  it('makes every framing card editable and routes AI discussion through a reviewable draft', () => {
    const space = source('views/TeacherCourseSpaceView.vue')
    const workspace = source('views/CourseWorkspaceView.vue')
    const assistant = source('components/SideAIPanel.vue')

    expect(space).toContain("@click=\"emit('editBaseline')\"")
    expect(space).toContain("emit('discussBaseline')")
    expect(workspace).toContain('<CourseBaselineDialog')
    expect(workspace).toContain('/generation-request/draft')
    expect(workspace).toContain("source: baselineEditorSource.value")
    expect(assistant).toContain("emit('courseBaselineDraft'")
    expect(assistant).not.toContain('/generation-request')
  })
})
