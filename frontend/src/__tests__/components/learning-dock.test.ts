import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningDock from '@/components/LearningDock.vue'

describe('LearningDock', () => {
  it('把学习任务和课程资料展示为带数量的父入口', async () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
        activeDomain: 'learning',
        practiceAvailable: true,
        recordCount: 3,
      },
    })

    expect(wrapper.text()).toContain('第一章 · 当前目标')
    const domainButtons = wrapper.findAll('.learning-dock__domain')
    expect(domainButtons).toHaveLength(3)
    expect(domainButtons.map(button => button.text())).toEqual(['学习任务 · 3', '课程资料 · 2', '智能助教'])
    expect(domainButtons[0]!.attributes('aria-haspopup')).toBe('menu')
    expect(domainButtons[0]!.attributes('aria-expanded')).toBe('false')
    expect(domainButtons[1]!.attributes('aria-haspopup')).toBe('menu')
    expect(domainButtons[2]!.attributes('aria-haspopup')).toBeUndefined()
  })

  it('点击学习任务后先展开三个子项目，再由子项目触发具体功能', async () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
        practiceAvailable: true,
        recordCount: 3,
      },
    })

    await wrapper.get('[data-domain="learning"]').trigger('click')

    expect(wrapper.get('[data-domain="learning"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-tool-menu="learning"]').text()).toContain('练习、记录与学习进展')
    expect(wrapper.findAll('[data-tool-menu="learning"] [role="menuitem"]').map(item => item.text())).toEqual([
      '当前练习完成当前章节的正式练习未开始',
      '学习记录查看笔记、问答和待复习内容3 条',
      '学习概况查看阅读、掌握与学习证据',
    ])
    expect(wrapper.emitted('practice')).toBeUndefined()

    await wrapper.get('[data-tool-item="practice"]').trigger('click')
    expect(wrapper.emitted('practice')).toHaveLength(1)
    expect(wrapper.find('[data-tool-menu="learning"]').exists()).toBe(false)
  })

  it('可在两个父入口之间切换，并从课程资料进入两个子项目', async () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
      },
    })

    await wrapper.get('[data-domain="learning"]').trigger('click')
    await wrapper.get('[data-domain="resources"]').trigger('click')

    expect(wrapper.find('[data-tool-menu="learning"]').exists()).toBe(false)
    expect(wrapper.get('[data-tool-menu="resources"]').text()).toContain('知识库与课程配套资料')
    expect(wrapper.findAll('[data-tool-menu="resources"] [role="menuitem"]').map(item => item.text())).toEqual([
      '知识库查看本课知识结构与课程覆盖',
      '教学资源查看大纲、教案、讲义等',
    ])

    await wrapper.get('[data-tool-item="knowledge-library"]').trigger('click')
    expect(wrapper.emitted('knowledge-library')).toHaveLength(1)

    await wrapper.get('[data-domain="resources"]').trigger('click')
    await wrapper.get('[data-tool-item="teaching-resources"]').trigger('click')
    expect(wrapper.emitted('teaching-resources')).toHaveLength(1)

    await wrapper.get('[data-domain="assistant"]').trigger('click')
    expect(wrapper.emitted('ai')).toHaveLength(1)
  })

  it('练习不可用时展示原因且不触发进入事件', async () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
        practiceAvailable: false,
        practiceRepairAvailable: false,
      },
    })

    await wrapper.get('[data-domain="learning"]').trigger('click')
    const practice = wrapper.get('[data-tool-item="practice"]')
    expect(practice.attributes('disabled')).toBeDefined()
    expect(practice.text()).toContain('本节暂无正式练习')
    await practice.trigger('click')
    expect(wrapper.emitted('practice')).toBeUndefined()
  })

  it('按 Escape 收起托盘并把焦点还给父入口', async () => {
    const wrapper = mount(LearningDock, {
      attachTo: document.body,
      props: {
        location: '第一章 · 当前目标',
        practiceAvailable: true,
      },
    })
    const trigger = wrapper.get('[data-domain="learning"]')

    await trigger.trigger('click')
    await wrapper.get('[data-tool-item="practice"]').element.focus()
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
