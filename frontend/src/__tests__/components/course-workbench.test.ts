import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import CourseWorkbench from '@/components/CourseWorkbench.vue'

const CourseTaskCenterStub = defineComponent({
  name: 'CourseTaskCenter',
  props: {
    modelValue: Boolean,
    courseId: String,
    embedded: Boolean,
  },
  template: '<div data-testid="embedded-task-center">{{ courseId }}</div>',
})

const mountWorkbench = () => mount(CourseWorkbench, {
  props: {
    modelValue: true,
    courseId: 'course-1',
    surface: 'teacher',
  },
  global: {
    plugins: [createPinia()],
    stubs: {
      Teleport: true,
      CourseTaskCenter: CourseTaskCenterStub,
    },
  },
})

describe('CourseWorkbench', () => {
  it('课程工作台只承载生成任务，不再包含教师出题页', () => {
    const wrapper = mountWorkbench()

    expect(wrapper.get('[data-testid="course-workbench"]').attributes('role')).toBe('dialog')
    expect(wrapper.get('[data-testid="course-workbench"]').classes()).toContain('course-workbench--compact')
    expect(wrapper.text()).toContain('课程任务')
    const taskCenter = wrapper.getComponent({ name: 'CourseTaskCenter' })
    expect(taskCenter.props()).toMatchObject({
      modelValue: true,
      courseId: 'course-1',
      embedded: true,
    })

    expect(wrapper.find('[data-testid="course-workbench-tab-question-bank"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="embedded-question-bank"]').exists()).toBe(false)
  })

  it('通过 Escape 关闭任务工作台', async () => {
    const wrapper = mountWorkbench()

    await wrapper.get('[data-testid="course-workbench"]').trigger('keydown', { key: 'Escape' })

    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
})
