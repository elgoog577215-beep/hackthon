import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KnowledgeMasteryTree from '@/components/KnowledgeMasteryTree.vue'
import demo from '@/demo/knowledge-profile.json'
import type { KnowledgeProfile } from '@/types/knowledge-profile'

const profile = demo.cases.at(-1)!.profile as KnowledgeProfile

describe('mobile knowledge tree', () => {
  it('keeps branch collapse, expand-all, and red/green learning signals available in the vertical view', async () => {
    const wrapper = mount(KnowledgeMasteryTree, { props: { profile, expandAllByDefault: true } })
    const mobile = wrapper.get('.tree-mobile')

    expect(mobile.findAll('.tree-mobile-leaf')).toHaveLength(profile.summary.total_count)
    expect(mobile.findAll('.tree-mobile-signal.is-red').length).toBeGreaterThan(0)
    expect(mobile.findAll('.tree-mobile-signal.is-green').length).toBeGreaterThan(0)

    await mobile.get('[data-mobile-branch-id="condition"]').trigger('click')
    expect(mobile.findAll('.tree-mobile-leaf')).toHaveLength(profile.summary.total_count - 4)

    await wrapper.get('.tree-actions button').trigger('click')
    expect(mobile.findAll('.tree-mobile-leaf')).toHaveLength(profile.summary.total_count)

    wrapper.unmount()
  })
})
