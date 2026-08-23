import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(resolve(process.cwd(), 'src', path), 'utf8')

describe('course workbench web research boundary', () => {
  it('places web sources beside uploaded sources and opens a reviewable research dialog', () => {
    const tray = source('components/CourseReferenceTray.vue')
    const dialog = source('components/WebResearchDialog.vue')
    const workbench = source('components/TeacherCourseWorkbench.vue')

    expect(tray).toContain('source-group--web')
    expect(tray).toContain('<WebResearchDialog')
    expect(tray).toContain("t('courseWorkbench.references.webSources'")
    expect(workbench).toContain(':stage="activeStage"')
    expect(workbench).toContain(':lesson-id="activeReferenceLessonId"')

    expect(dialog).toContain("t('courseWorkbench.webResearch.queryPlan'")
    expect(dialog).toContain('/web-research/search')
    expect(dialog).toContain('selected_source_ids: Array.from(selectedIds.value)')
    expect(dialog).toContain('source.sensitivity?.level')
    expect(dialog).toContain("source.content_status === 'full_text'")
    expect(dialog).toContain('research_summary?.full_text_count')
    expect(dialog).toContain('.slice(0, 8)')
  })

  it('passes selected material assets into generation instead of keeping them as display-only links', () => {
    const workbench = source('components/TeacherCourseWorkbench.vue')
    const lessonStore = source('stores/teacherLessonAuthoring.ts')

    expect(workbench).toContain("item.origin === 'web_search'")
    expect(workbench).toContain('source_metadata: item.source_metadata || {}')
    expect(workbench).toContain('activeReferences.value.map(item => item.material_asset_id)')
    expect(lessonStore).toContain('material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean)))')
  })
})
