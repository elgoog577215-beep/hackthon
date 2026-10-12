import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeMasteryProfile from '@/components/KnowledgeMasteryProfile.vue'
import demo from '@/demo/knowledge-profile.json'
import type { KnowledgeProfile } from '@/types/knowledge-profile'
import { setLocale } from '@/shared/i18n'
import zh from '@/../public/locales/zh/translation.json'

describe('knowledge mastery profile', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
    await setLocale('zh')
  })
  it('shows unknown separately from zero progress, and protects preview identity', async () => {
    const wrapper = mount(KnowledgeMasteryProfile, { props: { profile: demo.cases[0]!.profile as KnowledgeProfile } })
    expect(wrapper.get('[data-testid="profile-progress"]').text()).toBe('0%')
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(wrapper.get('[data-knowledge-id="demo-k1"] .orb-core strong').text()).toBe('—')
    await wrapper.get('[data-knowledge-id="demo-k1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="detail-mastery"]').text()).toBe('—')
    expect(wrapper.text()).toContain('“未评估”不等于不会')
    await wrapper.setProps({ preview: true })
    expect(wrapper.text()).toContain('不读取或写入任何学生的正式画像')
    expect(wrapper.find('.profile-metrics').exists()).toBe(false)
    wrapper.unmount()
  })
  it('follows the relation from either endpoint while retaining the directed meaning',async()=>{
    const profile=structuredClone(demo.cases[0]!.profile) as KnowledgeProfile
    const a=profile.nodes[0]!,b=profile.nodes[1]!
    a.links=[{relation_id:'r',knowledge_id:b.knowledge_id,name:b.name,direction:'outgoing',type:'applies_to',reason:'旧规则用于新方法',conditions:['适用条件'],lecture_names:['第二讲']}]
    b.links=[{...a.links[0]!,knowledge_id:a.knowledge_id,name:a.name,direction:'incoming',lecture_names:['第一讲']}]
    const w=mount(KnowledgeMasteryProfile,{props:{profile,knowledgeOnly:true}})
    await w.get(`[data-knowledge-id="${a.knowledge_id}"]`).trigger('click')
    expect(w.get('.point-connections').text()).toContain('本知识指向的关联')
    await w.get('.point-connection button').trigger('click');await flushPromises()
    expect(w.get('.profile-detail h3').text()).toBe(b.name)
    expect(w.get('.point-connections').text()).toContain('指向本知识的关联')
    await w.get('.point-connection button').trigger('click');await flushPromises()
    expect(w.get('.profile-detail h3').text()).toBe(a.name)
    w.unmount()
  })
  it('filters browsing without changing the global denominator and exposes selected evidence', async () => {
    const wrapper = mount(KnowledgeMasteryProfile, { props: { profile: demo.cases.at(-1)!.profile as KnowledgeProfile } })
    const before = wrapper.get('[data-testid="profile-progress"]').text()
    await wrapper.get('input').setValue('区间')
    expect(wrapper.findAll('.tree-leaf')).toHaveLength(1)
    await wrapper.get('.tree-leaf').trigger('click')
    await flushPromises()
    expect(wrapper.find('.knowledge-detail-inline').exists()).toBe(true)
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ knowledge_id: 'demo-k7' })
    expect(wrapper.get('.profile-detail h3').text()).toContain('区间端点')
    expect(wrapper.get('.point-evaluation').attributes('data-status')).toBe('needs_review')
    expect(wrapper.get('[data-testid="profile-progress"]').text()).toBe(before)
    expect(wrapper.get('.learning-evidence').attributes('open')).toBeUndefined()
    expect(wrapper.findAll('.point-evidence li')).toHaveLength(2)
    expect(wrapper.get('.point-evaluation').text().match(/25%/g)).toHaveLength(1)
    expect(wrapper.find('.point-next').exists()).toBe(false)
    expect(wrapper.find('.mastery-explanation').attributes('open')).toBeUndefined()
    wrapper.unmount()
  })
  it('expands branches and returns focus to the sphere when detail closes', async () => {
    const wrapper = mount(KnowledgeMasteryProfile, { attachTo: document.body, props: { profile: demo.cases.at(-1)!.profile as KnowledgeProfile } })
    expect(wrapper.find('[data-knowledge-id="demo-k7"]').exists()).toBe(false)
    await wrapper.get('[data-branch-id="condition"]').trigger('click')
    const sphere = wrapper.get('[data-knowledge-id="demo-k7"]')
    await sphere.trigger('click')
    await flushPromises()
    expect(wrapper.get('.knowledge-detail-inline h3').text()).toContain('区间端点')
    await wrapper.get('.point-dialog-header button').trigger('click')
    await flushPromises()
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(document.activeElement).toBe(sphere.element)
    wrapper.unmount()
  })
  it('warns when the baseline changes and never presents a missing tree as zero ability', async () => {
    const profile = demo.cases[0]!.profile as KnowledgeProfile
    const wrapper = mount(KnowledgeMasteryProfile, { props: { profile } })
    await wrapper.setProps({ profile: { ...profile, baseline_revision: 'changed' } })
    await flushPromises()
    expect(wrapper.text()).toContain('知识范围已更新')
    await wrapper.setProps({ profile: { ...profile, availability: 'tree_unavailable' } })
    expect(wrapper.text()).toContain('等待课程知识基线')
    expect(wrapper.find('[data-testid="profile-progress"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
