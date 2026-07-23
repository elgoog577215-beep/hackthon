import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CourseWorkspaceTabs from '@/components/CourseWorkspaceTabs.vue'

describe('CourseWorkspaceTabs', () => {
  it('按教案、课程、练习、PPT 的顺序展示一级工作区', async () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'course',
        practiceAvailable: true,
      },
    })

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map(tab => tab.text())).toEqual(['教案', '课程', '练习', 'PPT'])
    expect(tabs[1]!.attributes('aria-selected')).toBe('true')

    await tabs[0]!.trigger('click')
    await tabs[1]!.trigger('click')
    await tabs[2]!.trigger('click')
    await tabs[3]!.trigger('click')

    expect(wrapper.emitted('lesson-plan')).toHaveLength(1)
    expect(wrapper.emitted('course')).toHaveLength(1)
    expect(wrapper.emitted('practice')).toHaveLength(1)
    expect(wrapper.emitted('ppt')).toHaveLength(1)
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

  it('课程生成期间保留练习入口但明确禁用到发布后', () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'lesson-plan',
        practicePending: true,
      },
    })

    const practice = wrapper.get('[data-workspace-item="practice"]')
    expect(practice.attributes('disabled')).toBeDefined()
    expect(practice.attributes('title')).toContain('发布后')
  })

  it('课程生成期间保留 PPT 位置但禁用到发布后', () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'course',
        pptAvailable: false,
      },
    })

    const ppt = wrapper.get('[data-workspace-item="ppt"]')
    expect(ppt.attributes('disabled')).toBeDefined()
    expect(ppt.attributes('title')).toContain('发布后')
  })

  it('目录确认前保留教案位置但不允许进入空白教案页', async () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'course',
        lessonPlanPending: true,
        practicePending: true,
      },
    })

    const lessonPlan = wrapper.get('[data-workspace-item="lesson-plan"]')
    expect(lessonPlan.attributes('disabled')).toBeDefined()
    expect(lessonPlan.attributes('title')).toContain('目录确认后')
    await lessonPlan.trigger('click')
    expect(wrapper.emitted('lesson-plan')).toBeUndefined()
  })

  it('教案在后台生成时保留课程视图并显示轻量进行中状态', async () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'course',
        lessonPlanBuilding: true,
        practicePending: true,
      },
    })

    const lessonPlan = wrapper.get('[data-workspace-item="lesson-plan"]')
    const course = wrapper.get('[data-workspace-item="course"]')
    expect(course.attributes('aria-selected')).toBe('true')
    expect(lessonPlan.classes()).toContain('is-building')
    expect(lessonPlan.attributes('disabled')).toBeUndefined()
    expect(lessonPlan.attributes('title')).toContain('后台')
    await lessonPlan.trigger('click')
    expect(wrapper.emitted('lesson-plan')).toHaveLength(1)
  })
})
