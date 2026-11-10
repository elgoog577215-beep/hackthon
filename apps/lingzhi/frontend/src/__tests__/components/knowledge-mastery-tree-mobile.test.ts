import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KnowledgeMasteryTree from '@/components/KnowledgeMasteryTree.vue'
import demo from '@/demo/knowledge-profile.json'
import type { KnowledgeProfile } from '@/types/knowledge-profile'

const profile = demo.cases.at(-1)!.profile as KnowledgeProfile

describe('mobile knowledge tree', () => {
  it('opens as a full-screen map at a high-density phone CSS width', async () => {
    const previousWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 480 })
    const wrapper = mount(KnowledgeMasteryTree, { props: { profile } })
    try {
      const viewport = wrapper.get('.tree-viewport')

      expect(wrapper.get('.mastery-tree').classes()).toContain('mobile-fullscreen')
      await wrapper.get('.tree-actions button').trigger('click')
      expect(viewport.findAll('.tree-leaf')).toHaveLength(profile.summary.total_count)
      expect(viewport.findAll('.tree-leaf-signal.is-red').length).toBeGreaterThan(0)
      expect(viewport.findAll('.tree-leaf-signal.is-green').length).toBeGreaterThan(0)

      await viewport.get('[data-branch-id="condition"]').trigger('click')
      expect(viewport.findAll('.tree-leaf')).toHaveLength(profile.summary.total_count - 4)

      await wrapper.get('.tree-actions button').trigger('click')
      expect(viewport.findAll('.tree-leaf')).toHaveLength(profile.summary.total_count)
    } finally {
      wrapper.unmount()
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: previousWidth })
    }
  })

  it('pans in both directions and does not treat a drag on a branch as a tap', async () => {
    const previousWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    const wrapper = mount(KnowledgeMasteryTree, { props: { profile } })
    try {
      const viewport = wrapper.get('.tree-viewport')
      const element = viewport.element as HTMLElement
      const branch = viewport.get('[data-branch-id="condition"]')
      const initialExpanded = branch.attributes('aria-expanded')
      element.scrollLeft = 80
      element.scrollTop = 60

      await branch.trigger('pointerdown', { button: 0, pointerId: 7, clientX: 100, clientY: 100 })
      await branch.trigger('pointermove', { pointerId: 7, clientX: 74, clientY: 81 })
      expect(element.scrollLeft).toBe(106)
      expect(element.scrollTop).toBe(79)

      await branch.trigger('pointerup', { pointerId: 7 })
      await branch.trigger('click')
      expect(branch.attributes('aria-expanded')).toBe(initialExpanded)
    } finally {
      wrapper.unmount()
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: previousWidth })
    }
  })
})
