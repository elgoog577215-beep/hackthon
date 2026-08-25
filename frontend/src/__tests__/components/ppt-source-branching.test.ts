import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('teacher PPT source branching contract', () => {
  it('keeps a PPT-specific source scope and the three-column source tray', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'),
      'utf8',
    )

    expect(source).toContain("`ppt-v6:${selectedLessonId.value}`")
    expect(source).toContain("activeStage.value === 'ppt'")
    expect(source).toContain("? 'ppt'")
    expect(source).toContain(':reference-count="activeReferences.length"')
    expect(source).not.toContain("v-if=\"activeStage !== 'ppt'")
    expect(source).not.toContain('.teacher-workbench.is-ppt-stage:not(.is-ai-collaboration){grid-template-columns:196px minmax(0,1fr)}')
  })
})
