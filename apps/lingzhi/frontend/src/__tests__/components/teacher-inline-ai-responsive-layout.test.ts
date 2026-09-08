import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (path: string) =>
  readFileSync(resolve(process.cwd(), path), 'utf8')

describe('讲义 AI 修改建议响应式布局', () => {
  it('工作台中间列允许收缩，不再由固定最小宽度触发裁切', () => {
    const workbench = source('src/components/TeacherCourseWorkbench.vue')
    expect(workbench).not.toMatch(/minmax\(520px,\s*1fr\)/)
    expect(workbench).toMatch(
      /grid-template-columns:\s*210px\s+minmax\(0,\s*1fr\)\s+310px/,
    )
  })

  it('建议卡按自身宽度降级为上下对比并约束长内容', () => {
    const component = source('src/components/TextSelectionAiAction.vue')
    expect(component).toContain('container-name: ai-suggestion')
    expect(component).toContain('container-type: inline-size')
    expect(component).toMatch(
      /@container\s+ai-suggestion\s+\(max-width:\s*899px\)/,
    )
    expect(component).toContain('overflow-wrap: anywhere')
  })

  it('讲义正文的每一级容器都允许随右栏收缩', () => {
    const workbench = source('src/components/TeacherCourseWorkbench.vue')
    const document = source('src/components/TeacherScriptDocument.vue')
    expect(workbench).toMatch(
      /lesson-stage-content\{[^}]*min-width:0[^}]*overflow-x:clip/,
    )
    expect(document).toMatch(
      /script-continuous\{[^}]*min-width:0[^}]*max-width:100%[^}]*box-sizing:border-box/,
    )
    expect(document).toMatch(/script-body\{[^}]*min-width:0[^}]*box-sizing:border-box/)
    expect(document).toMatch(/script-content\{[^}]*min-width:0[^}]*max-width:100%/)
  })

  it('建议操作行可换行，提示文字不能把按钮推出可视区域', () => {
    const component = source('src/components/TextSelectionAiAction.vue')
    expect(component).toMatch(
      /\.inline-edit-decisions\s*\{[^}]*min-width:\s*0[^}]*flex-wrap:\s*wrap/,
    )
    expect(component).toMatch(
      /\.inline-edit-decisions\s*>\s*span\s*\{[^}]*min-width:\s*0[^}]*flex:\s*1\s+1\s+240px/,
    )
    expect(component).toMatch(
      /\.inline-edit-decisions\s*>\s*button\s*\{[^}]*flex:\s*none/,
    )
  })

  it('中英文都提供对比布局与专注模式文案', () => {
    for (const locale of ['zh', 'en']) {
      const messages = JSON.parse(
        source(`public/locales/${locale}/translation.json`),
      )
      expect(messages.teacherInlineEdit).toMatchObject({
        compareLayout: expect.any(String),
        compareSideBySide: expect.any(String),
        compareStacked: expect.any(String),
        focusCompare: expect.any(String),
        closeFocusCompare: expect.any(String),
        sideBySideUnavailable: expect.any(String),
      })
    }
  })
})
