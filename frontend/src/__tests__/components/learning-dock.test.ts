import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningDock from '@/components/LearningDock.vue'

describe('LearningDock', () => {
  it('在正文底部聚合低频学习工具，并保留记录数量', async () => {
    const wrapper = mount(LearningDock, {
      props: { location: '第一章 · 当前目标', recordCount: 3, practiceAvailable: true },
    })

    expect(wrapper.text()).toContain('第一章 · 当前目标')
    expect(wrapper.find('.learning-dock__count').text()).toBe('3')

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(6)
    for (const button of buttons) await button.trigger('click')

    expect(wrapper.emitted('records')).toHaveLength(1)
    expect(wrapper.emitted('practice')).toHaveLength(1)
    expect(wrapper.emitted('stats')).toHaveLength(1)
    expect(wrapper.emitted('knowledge-library')).toHaveLength(1)
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

  it('当前章节没有正式题目时禁用练习入口', async () => {
    const wrapper = mount(LearningDock, {
      props: { location: '第一章 · 当前目标', practiceAvailable: false },
    })

    const practice = wrapper.find('.learning-dock__practice')
    expect(practice.attributes('disabled')).toBeDefined()
    await practice.trigger('click')
    expect(wrapper.emitted('practice')).toBeUndefined()
  })
})
