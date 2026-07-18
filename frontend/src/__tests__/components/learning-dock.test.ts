import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningDock from '@/components/LearningDock.vue'

describe('LearningDock', () => {
  it('底栏把知识库提升为独立入口，并只把记录与概况收进学习工具', async () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
        activeDomain: 'course',
        recordCount: 3,
      },
    })

    expect(wrapper.text()).toContain('第一章 · 当前目标')
    const domainButtons = wrapper.findAll('.learning-dock__domain')
    expect(domainButtons).toHaveLength(3)
    expect(domainButtons.map(button => button.text())).toEqual(['学习工具 · 2', '知识库', '智能助教'])
    expect(domainButtons[0]!.attributes('aria-haspopup')).toBe('menu')
    expect(domainButtons[1]!.attributes('aria-haspopup')).toBeUndefined()
    expect(wrapper.find('[data-domain="resources"]').exists()).toBe(false)
  })

  it('学习工具托盘只展示学习记录和学习概况', async () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
        recordCount: 3,
      },
    })

    await wrapper.get('[data-domain="learning"]').trigger('click')

    expect(wrapper.get('[data-domain="learning"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-tool-menu="learning"]').text()).toContain('学习记录与学习概况')
    expect(wrapper.findAll('[data-tool-menu="learning"] [role="menuitem"]').map(item => item.text())).toEqual([
      '学习记录查看笔记、问答和待复习内容3 条',
      '学习概况查看阅读、掌握与学习证据',
    ])
    expect(wrapper.find('[data-tool-item="practice"]').exists()).toBe(false)

    await wrapper.get('[data-tool-item="records"]').trigger('click')
    expect(wrapper.emitted('records')).toHaveLength(1)
    expect(wrapper.find('[data-tool-menu="learning"]').exists()).toBe(false)
  })

  it('知识库和智能助教都从底栏一键触发', async () => {
    const wrapper = mount(LearningDock, {
      props: { location: '第一章 · 当前目标' },
    })

    await wrapper.get('[data-domain="knowledge-library"]').trigger('click')
    await wrapper.get('[data-domain="assistant"]').trigger('click')

    expect(wrapper.emitted('knowledge-library')).toHaveLength(1)
    expect(wrapper.emitted('ai')).toHaveLength(1)
  })

  it('按 Escape 收起托盘并把焦点还给父入口', async () => {
    const wrapper = mount(LearningDock, {
      attachTo: document.body,
      props: { location: '第一章 · 当前目标' },
    })
    const trigger = wrapper.get('[data-domain="learning"]')

    await trigger.trigger('click')
    ;(wrapper.get('[data-tool-item="records"]').element as HTMLElement).focus()
    await wrapper.trigger('keydown', { key: 'Escape' })

    expect(wrapper.find('[data-tool-menu="learning"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
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
