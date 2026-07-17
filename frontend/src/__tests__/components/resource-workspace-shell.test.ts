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

  it('defines the shared desktop and mobile dimensions in one stylesheet', () => {
    const workspaceStyles = readSource('../../styles/resource-workspace.css')

    expect(workspaceStyles).toContain('width: min(1320px, calc(100vw - 48px))')
    expect(workspaceStyles).toContain('height: min(850px, calc(100vh - 48px))')
    expect(workspaceStyles).toContain('min-height: 560px')
    expect(workspaceStyles).toContain('min-height: 72px')
    expect(workspaceStyles).toContain('@media (max-width: 700px)')
  })

  it('keeps PPT out of teaching resources and exposes a first-class workspace entry', () => {
    const app = readSource('../../App.vue')
    const teachingResources = readSource('../../components/TeachingRepresentationsOverlay.vue')
    const pptWorkspace = readSource('../../views/PptWorkspaceView.vue')

    expect(app).toContain('header-ppt-button')
    expect(app).toContain("name: 'ppt-workspace'")
    expect(teachingResources).toContain("item.representation_type !== 'slide_deck'")
    expect(teachingResources).not.toContain('<SlideDeckWorkbench')
    expect(pptWorkspace).toContain('standalone')
    expect(pptWorkspace).toContain('<SideAIPanel')
  })
})
