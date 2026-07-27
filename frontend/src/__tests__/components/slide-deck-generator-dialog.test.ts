import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SlideDeckGeneratorDialog from '@/components/SlideDeckGeneratorDialog.vue'

describe('SlideDeckGeneratorDialog', () => {
  it('offers three content modes and five original visual themes', () => {
    const wrapper = mount(SlideDeckGeneratorDialog, {
      props: { open: true, fragmentCount: 18 },
    })

    expect(wrapper.findAll('.deck-generator__modes > button')).toHaveLength(3)
    expect(wrapper.findAll('.deck-generator__themes > button')).toHaveLength(5)
    expect(wrapper.text()).toContain('完整课件')
    expect(wrapper.text()).toContain('授课课件')
    expect(wrapper.text()).toContain('精简课件')
    expect(wrapper.text()).toContain('启智课堂')
    expect(wrapper.text()).toContain('深色科技')
    expect(wrapper.text()).toContain('课程正文将原样进入课件')
  })

  it('emits the selected mode and theme without generating body text', async () => {
    const wrapper = mount(SlideDeckGeneratorDialog, {
      props: { open: true },
    })
    const concise = wrapper.findAll('.deck-generator__modes > button')
      .find(item => item.text().includes('精简课件'))
    await concise!.trigger('click')
    await wrapper.get('[data-theme="dark-tech"]').trigger('click')
    await wrapper.find('.deck-generator__panel > footer > button').trigger('click')

    expect(wrapper.emitted('confirm')?.[0]?.[0]).toEqual({
      mode: 'concise',
      theme: 'dark-tech',
    })
  })
})
