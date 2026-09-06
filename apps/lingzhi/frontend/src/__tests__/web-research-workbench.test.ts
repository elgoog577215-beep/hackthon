import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(resolve(process.cwd(), 'src', path), 'utf8')

describe('course workbench web research boundary', () => {
  it('keeps the implementation parked without mounting it in the active workbench', () => {
    const tray = source('components/CourseReferenceTray.vue')
    const dialog = source('components/WebResearchDialog.vue')
    const workbench = source('components/TeacherCourseWorkbench.vue')

    expect(tray).not.toContain("from './WebResearchDialog.vue'")
    expect(tray).not.toContain('<WebResearchDialog')
    expect(tray).not.toContain('/web-research')
    expect(workbench).toContain(':stage="activeStage"')
    expect(workbench).toContain(':lesson-id="activeReferenceLessonId"')
    expect(workbench).toContain("activeReferences.value.filter(item => item.origin !== 'web_search')")

    // 文件仍在仓库中，重新启用前可以继续审阅和测试原实现。
    expect(dialog).toContain("t('courseWorkbench.webResearch.queryPlan'")
    expect(dialog).toContain('/web-research/search')
    expect(dialog).toContain('selected_source_ids: Array.from(selectedIds.value)')
    expect(dialog).toContain('source.sensitivity?.level')
    expect(dialog).toContain("source.content_status === 'full_text'")
    expect(dialog).toContain('research_summary?.full_text_count')
    expect(dialog).toContain('.slice(0, 8)')
  })

  it('passes only uploaded material assets into generation', () => {
    const workbench = source('components/TeacherCourseWorkbench.vue')
    const lessonStore = source('stores/teacherLessonAuthoring.ts')

    expect(workbench).toContain("references.filter(item => item.origin !== 'web_search')")
    expect(workbench).toContain('source_metadata: item.source_metadata || {}')
    expect(workbench).toContain('activeCourseReferences.value.map(item => item.material_asset_id)')
    expect(lessonStore).toContain('material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean)))')
  })
})
