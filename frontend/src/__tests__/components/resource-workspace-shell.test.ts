import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const readSource = (relativePath: string) => readFileSync(new URL(relativePath, import.meta.url), 'utf8')

describe('resource workspace shell', () => {
  it('uses one shared overlay, shell, and header contract for both resource pages', () => {
    const knowledgeLibrary = readSource('../../components/KnowledgeLibrary.vue')
    const teachingResources = readSource('../../components/TeachingRepresentationsOverlay.vue')

    for (const source of [knowledgeLibrary, teachingResources]) {
      expect(source).toContain('resource-workspace-overlay')
      expect(source).toContain('resource-workspace-shell')
      expect(source).toContain('resource-workspace-header')
    }
  })

  it('keeps the knowledge library as a full-screen resource workspace', () => {
    const workspaceStyles = readSource('../../styles/resource-workspace.css')
    const knowledgeLibrary = readSource('../../components/KnowledgeLibrary.vue')

    expect(workspaceStyles).toContain('place-items: stretch')
    expect(workspaceStyles).toContain('padding: 0')
    expect(workspaceStyles).toContain('width: 100vw')
    expect(workspaceStyles).toContain('height: 100dvh')
    expect(workspaceStyles).toContain('min-height: 0')
    expect(workspaceStyles).toContain('border-radius: 0')
    expect(workspaceStyles).toContain('box-shadow: none')
    expect(workspaceStyles).toContain('min-height: 72px')
    expect(workspaceStyles).not.toContain('width: min(1320px')
    expect(workspaceStyles).not.toContain('backdrop-filter')
    expect(knowledgeLibrary).not.toContain('scale(.995)')
  })

  it('keeps outline and lesson plan inside the course learning surface', () => {
    const teachingResources = readSource('../../components/TeachingRepresentationsOverlay.vue')

    expect(teachingResources).toContain('position:absolute')
    expect(teachingResources).toContain('width:100%')
    expect(teachingResources).toContain('height:100%')
    expect(teachingResources).toContain('grid-template-rows:58px minmax(0,1fr)')
    expect(teachingResources).toContain('min-height:58px')
    expect(teachingResources).toContain('grid-template-rows:52px minmax(0,1fr)')
    expect(teachingResources).not.toContain('aria-modal="true"')
  })

  it('keeps PPT out of teaching resources and exposes it as the fourth course workspace tab', () => {
    const courseTabs = readSource('../../components/CourseWorkspaceTabs.vue')
    const teachingResources = readSource('../../components/TeachingRepresentationsOverlay.vue')
    const pptWorkspace = readSource('../../views/PptWorkspaceView.vue')

    expect(courseTabs).toContain('data-workspace-item="ppt"')
    expect(courseTabs).toContain("emit('ppt')")
    expect(teachingResources).toContain("activeType?: 'outline' | 'lesson_plan'")
    expect(teachingResources).toContain('<CourseWorkspaceTabs')
    expect(teachingResources).not.toContain('<SlideDeckWorkbench')
    expect(pptWorkspace).toContain('standalone')
    expect(pptWorkspace).toContain('<SideAIPanel')
  })

  it('registers the structured diagram renderer used by the teaching workspace', () => {
    const teachingResources = readSource('../../components/TeachingRepresentationsOverlay.vue')

    expect(teachingResources).toContain("import DiagramSpecRenderer from './DiagramSpecRenderer.vue'")
    expect(teachingResources).toContain('<DiagramSpecRenderer')
  })

  it('keeps the knowledge library independent from the course workspace tabs', () => {
    const knowledgeLibrary = readSource('../../components/KnowledgeLibrary.vue')
    const learningDock = readSource('../../components/LearningDock.vue')

    expect(knowledgeLibrary).not.toContain('<LearningContextTabs')
    expect(learningDock).toContain('data-domain="knowledge-library"')
    expect(learningDock).not.toContain('data-domain="resources"')
  })
})
