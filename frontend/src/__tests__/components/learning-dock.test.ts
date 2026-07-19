import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningDock from '@/components/LearningDock.vue'

describe('LearningDock', () => {
  it('按三月份结构恢复笔记本与错题本，并保留概况、知识库和助教独立入口', () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
        activeDomain: 'course',
        noteCount: 3,
        mistakeCount: 2,
      },
    })

    expect(wrapper.text()).toContain('第一章 · 当前目标')
    const domainButtons = wrapper.findAll('.learning-dock__domain')
    expect(domainButtons).toHaveLength(5)
    expect(domainButtons.map(button => button.text())).toEqual([
      '笔记本3',
      '错题本2',
      '学习概况',
      '知识库',
      '智能助教',
    ])
    expect(wrapper.find('[data-domain="learning"]').exists()).toBe(false)
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
  })

  it('五个入口都从底栏一键触发', async () => {
    const wrapper = mount(LearningDock, {
      props: { location: '第一章 · 当前目标' },
    })

    await wrapper.get('[data-domain="notebook"]').trigger('click')
    await wrapper.get('[data-domain="mistake-book"]').trigger('click')
    await wrapper.get('[data-domain="overview"]').trigger('click')
    await wrapper.get('[data-domain="knowledge-library"]').trigger('click')
    await wrapper.get('[data-domain="assistant"]').trigger('click')

    expect(wrapper.emitted('notebook')).toHaveLength(1)
    expect(wrapper.emitted('mistake-book')).toHaveLength(1)
    expect(wrapper.emitted('stats')).toHaveLength(1)
    expect(wrapper.emitted('knowledge-library')).toHaveLength(1)
    expect(wrapper.emitted('ai')).toHaveLength(1)
  })

  it('当前打开的本子在底栏保持选中状态', () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
        activeDomain: 'mistake-book',
      },
    })

    expect(wrapper.get('[data-domain="mistake-book"]').classes()).toContain('is-active')
    expect(wrapper.get('[data-domain="mistake-book"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('[data-domain="notebook"]').classes()).not.toContain('is-active')
  })

  it('只把明确的未完成事项显示为恢复提示', async () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第二章 · 高斯消元法',
        resumeActionLabel: '继续未完成练习',
        resumeActionAvailable: true,
      },
    })

    expect(wrapper.text()).toContain('继续未完成练习')
    const resume = wrapper.find('.learning-dock__resume > button')
    await resume.trigger('click')
    expect(wrapper.emitted('resume')).toHaveLength(1)
  })
})
