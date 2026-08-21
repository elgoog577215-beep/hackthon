import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CourseWorkspaceTabs from '@/components/CourseWorkspaceTabs.vue'

describe('CourseWorkspaceTabs', () => {
  it('顶栏只保留教案、课程与 PPT，练习归入底栏题库本', async () => {
    const wrapper = mount(CourseWorkspaceTabs, {
      props: {
        activeItem: 'course',
      },
    })

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map(tab => tab.text())).toEqual(['教案', '课程', 'PPT'])
    expect(tabs[1]!.attributes('aria-selected')).toBe('true')

    await tabs[0]!.trigger('click')
    await tabs[1]!.trigger('click')
    await tabs[2]!.trigger('click')
    expect(wrapper.find('[data-workspace-item="practice"]').exists()).toBe(false)

    expect(wrapper.emitted('lesson-plan')).toHaveLength(1)
    expect(wrapper.emitted('course')).toHaveLength(1)
    expect(wrapper.emitted('ppt')).toHaveLength(1)
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

  it('移动端将三个一级视图等宽收纳，英文标签不会把 PPT 挤出屏幕', () => {
    const component = readFileSync(
      resolve(process.cwd(), 'src/components/CourseWorkspaceTabs.vue'),
      'utf8',
    )

    expect(component).toContain('grid-template-columns:repeat(3,minmax(0,1fr))')
    expect(component).toContain('.course-workspace-tabs button svg { display:none; }')
    expect(component).toContain('.course-workspace-tabs button span { overflow:hidden; text-overflow:ellipsis; }')
  })
})
