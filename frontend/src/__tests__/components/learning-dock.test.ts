import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningDock from '@/components/LearningDock.vue'

describe('LearningDock', () => {
  it('只展示学习、资源和智能助教三个一级入口', async () => {
    const wrapper = mount(LearningDock, {
      props: {
        location: '第一章 · 当前目标',
        activeDomain: 'learning',
      },
    })

    expect(wrapper.text()).toContain('第一章 · 当前目标')
    const domainButtons = wrapper.findAll('.learning-dock__domain')
    expect(domainButtons).toHaveLength(3)
    expect(domainButtons.map(button => button.text())).toEqual(['学习', '资源', '智能助教'])
    expect(domainButtons[0]!.classes()).toContain('is-active')

    await domainButtons[0]!.trigger('click')
    await domainButtons[1]!.trigger('click')
    await domainButtons[2]!.trigger('click')

    expect(wrapper.emitted('learning')).toHaveLength(1)
    expect(wrapper.emitted('resources')).toHaveLength(1)
    expect(wrapper.emitted('ai')).toHaveLength(1)
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
