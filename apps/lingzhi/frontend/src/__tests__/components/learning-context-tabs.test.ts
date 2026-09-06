import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningContextTabs from '@/components/LearningContextTabs.vue'

describe('LearningContextTabs', () => {
  it('在学习域展示三个二级入口并保留记录数量', async () => {
    const wrapper = mount(LearningContextTabs, {
      props: {
        domain: 'learning',
        activeItem: 'practice',
        practiceAvailable: true,
        recordCount: 3,
      },
    })

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map(tab => tab.text())).toEqual(['当前练习', '学习记录3', '学习概况'])
    expect(tabs[0]!.attributes('aria-selected')).toBe('true')

    await tabs[0]!.trigger('click')
    await tabs[1]!.trigger('click')
    await tabs[2]!.trigger('click')

    expect(wrapper.emitted('practice')).toHaveLength(1)
    expect(wrapper.emitted('records')).toHaveLength(1)
    expect(wrapper.emitted('stats')).toHaveLength(1)
  })

  it('在资源域只展示知识库和教学资源', async () => {
    const wrapper = mount(LearningContextTabs, {
      props: {
        domain: 'resources',
        activeItem: 'knowledge-library',
      },
    })

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map(tab => tab.text())).toEqual(['知识库', '教学资源'])
    expect(tabs[0]!.attributes('aria-selected')).toBe('true')

    await tabs[0]!.trigger('click')
    await tabs[1]!.trigger('click')

    expect(wrapper.emitted('knowledge-library')).toHaveLength(1)
    expect(wrapper.emitted('resources')).toHaveLength(1)
  })

  it('智能助教作为上下文抽屉时不渲染冗余二级入口', () => {
    const wrapper = mount(LearningContextTabs, {
      props: {
        domain: 'assistant',
        activeItem: 'assistant',
      },
    })

    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
  })

  it('当前章节没有正式练习时禁用练习入口', () => {
    const wrapper = mount(LearningContextTabs, {
      props: {
        domain: 'learning',
        activeItem: 'practice',
        practiceAvailable: false,
      },
    })

    expect(wrapper.find('[data-context-item="practice"]').attributes('disabled')).toBeDefined()
  })

  it('旧课程题库可重建时保持当前练习入口可用', async () => {
    const wrapper = mount(LearningContextTabs, {
      props: {
        domain: 'learning',
        activeItem: 'records',
        practiceAvailable: false,
        practiceRepairAvailable: true,
      },
    })

    const practiceTab = wrapper.get('[data-context-item="practice"]')
    expect(practiceTab.attributes('disabled')).toBeUndefined()

    await practiceTab.trigger('click')
    expect(wrapper.emitted('practice')).toHaveLength(1)
  })
})
