import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CourseWorkspaceTabs from '@/components/CourseWorkspaceTabs.vue'

describe('CourseWorkspaceTabs', () => {
  it('按大纲、教案、课程、练习的顺序展示一级工作区', async () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'course',
        practiceAvailable: true,
      },
    })

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map(tab => tab.text())).toEqual(['大纲', '教案', '课程', '练习'])
    expect(tabs[2]!.attributes('aria-selected')).toBe('true')

    await tabs[0]!.trigger('click')
    await tabs[1]!.trigger('click')
    await tabs[2]!.trigger('click')
    await tabs[3]!.trigger('click')

    expect(wrapper.emitted('outline')).toHaveLength(1)
    expect(wrapper.emitted('lesson-plan')).toHaveLength(1)
    expect(wrapper.emitted('course')).toHaveLength(1)
    expect(wrapper.emitted('practice')).toHaveLength(1)
  })

  it('当前范围没有练习且不可重建时禁用练习入口', () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'course',
        practiceAvailable: false,
        practiceRepairAvailable: false,
      },
    })

    expect(wrapper.get('[data-workspace-item="practice"]').attributes('disabled')).toBeDefined()
  })

  it('旧课程题库可重建时仍允许进入练习', async () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'course',
        practiceRepairAvailable: true,
      },
    })

    const practice = wrapper.get('[data-workspace-item="practice"]')
    expect(practice.attributes('disabled')).toBeUndefined()
    await practice.trigger('click')
    expect(wrapper.emitted('practice')).toHaveLength(1)
  })
})
