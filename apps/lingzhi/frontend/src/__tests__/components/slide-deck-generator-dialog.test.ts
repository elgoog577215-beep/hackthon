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

  it('estimates a 45-minute teacher manuscript from lesson time instead of tripled fragments', () => {
    const wrapper = mount(SlideDeckGeneratorDialog, {
      props: {
        open: true,
        manuscriptFirst: true,
        durationMinutes: 45,
        fragmentCount: 29,
      },
    })

    expect(wrapper.text()).toContain('预计 12–18 页')
    expect(wrapper.text()).not.toContain('30–34 页')
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
      webImageRetrieval: { enabled: false, mode: 'wide_safe' },
    })
  })

  it('lets the teacher explicitly enable licensed web image retrieval', async () => {
    const wrapper = mount(SlideDeckGeneratorDialog, {
      props: { open: true },
    })

    const toggle = wrapper.get('[data-testid="ppt-web-image-retrieval"]')
    expect((toggle.element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.text()).toContain('仅使用公共领域、CC0 或 CC BY 图片')

    await toggle.setValue(true)
    await wrapper.find('.deck-generator__panel > footer > button').trigger('click')

    expect(wrapper.emitted('confirm')?.[0]?.[0]).toMatchObject({
      webImageRetrieval: { enabled: true, mode: 'wide_safe' },
    })
  })

  it('shows personal templates and emits the locked template version', async () => {
    const wrapper = mount(SlideDeckGeneratorDialog, {
      props: {
        open: true,
        personalTemplates: [{
          pack_id: 'pptp-demo',
          name: '学院蓝',
          base_theme: 'academic-editorial',
          status: 'published',
          latest_version: 2,
          v6_eligible: true,
          preview: {},
        }],
      },
    })

    await wrapper.get('[data-testid="personal-template-tab"]').trigger('click')
    expect(wrapper.text()).toContain('学院蓝')
    await wrapper.get('[data-template-pack-id="pptp-demo"]').trigger('click')
    await wrapper.find('.deck-generator__panel > footer > button').trigger('click')

    expect(wrapper.emitted('confirm')?.[0]?.[0]).toMatchObject({
      theme: 'academic-editorial',
      templatePackId: 'pptp-demo',
      templatePackVersion: 2,
    })
  })

  it('does not allow an unpublished V6 template contract to be selected', async () => {
    const wrapper = mount(SlideDeckGeneratorDialog, {
      props: {
        open: true,
        personalTemplates: [{
          pack_id: 'pptp-unverified',
          name: '未校验模板',
          base_theme: 'academic-editorial',
          status: 'published',
          latest_version: 1,
          v6_eligible: false,
        }],
      },
    })

    await wrapper.get('[data-testid="personal-template-tab"]').trigger('click')
    const template = wrapper.get('[data-template-pack-id="pptp-unverified"]')
    expect(template.attributes('disabled')).toBeDefined()
    await template.trigger('click')
    await wrapper.find('.deck-generator__panel > footer > button').trigger('click')

    expect(wrapper.emitted('confirm')?.[0]?.[0]).not.toHaveProperty('templatePackId')
  })

  it('offers a template creator entry without requiring a pptpack file', async () => {
    const wrapper = mount(SlideDeckGeneratorDialog, { props: { open: true } })

    await wrapper.get('[data-testid="personal-template-tab"]').trigger('click')
    await wrapper.get('[data-testid="create-template-pack"]').trigger('click')

    expect(wrapper.emitted('create-template')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('.pptpack')
  })
})
