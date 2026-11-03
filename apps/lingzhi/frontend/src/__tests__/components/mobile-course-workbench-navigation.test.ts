import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const workbench = readFileSync(
  resolve(process.cwd(), 'src/components/TeacherCourseWorkbench.vue'),
  'utf8',
)
const zh = JSON.parse(readFileSync(resolve(process.cwd(), 'public/locales/zh/translation.json'), 'utf8'))
const en = JSON.parse(readFileSync(resolve(process.cwd(), 'public/locales/en/translation.json'), 'utf8'))

describe('mobile course-workbench navigation', () => {
  it('keeps the four teaching stages directly reachable and separates course tools', () => {
    expect(workbench).toContain("{ id: 'foundation' as const, step: '01'")
    expect(workbench).toContain("{ id: 'lesson' as const, step: '02'")
    expect(workbench).toContain("{ id: 'script' as const, step: '03'")
    expect(workbench).toContain("{ id: 'ppt' as const, step: '04'")
    expect(workbench).toContain('stagePrerequisiteBlocked(stage.id)')
    expect(workbench).toContain('class="mobile-workbench-tools"')
    expect(workbench).toContain("t('courseWorkspaceFlow.tools', '课程工具')")
    expect(workbench).toContain('@change="handleMobileToolChange"')
    expect(workbench).toContain("if (value === 'knowledge') { void openKnowledge(); return }")
    expect(workbench).toContain("if (value === 'question-bank') { void requestStageChange('question-bank'); return }")
    expect(workbench).toContain('openCompanionTemplate(GRADING_RUBRIC_TEMPLATE_ID)')
    expect(workbench).toContain('openCompanionTemplate(MATERIAL_CHECKLIST_TEMPLATE_ID)')
  })

  it('shows the compact tool row only on narrow screens without duplicating the desktop tool list', () => {
    expect(workbench).toMatch(/\.mobile-workbench-tools\s*\{\s*display:\s*none/)
    expect(workbench).toMatch(/@media\s*\(max-width:\s*760px\)[\s\S]*?\.stage-rail>nav\s*\{[^}]*grid-template-columns:\s*repeat\(4,minmax\(0,1fr\)\)/)
    expect(workbench).toContain('.stage-rail>header,.stage-rail>footer,.stage-rail>.course-settings-entry,.stage-rail>.rail-group-label,.stage-rail>.companion-entry { display:none; }')
    expect(workbench).toMatch(/\.mobile-workbench-tools\s*\{[^}]*display:\s*flex/)
    expect(workbench).not.toContain('.stage-rail nav { display:flex;')
  })

  it('provides a translated label for the mobile tools selector', () => {
    expect(zh.courseWorkspaceFlow.tools).toBe('课程工具')
    expect(en.courseWorkspaceFlow.tools).toBe('Course tools')
  })
})
