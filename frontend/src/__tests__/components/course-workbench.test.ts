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

const QuestionBankReviewCenterStub = defineComponent({
  name: 'QuestionBankReviewCenter',
  props: {
    modelValue: Boolean,
    courseId: String,
    embedded: Boolean,
  },
  template: '<div data-testid="embedded-question-bank">{{ courseId }}</div>',
})

const mountWorkbench = (initialSection: 'tasks' | 'question-bank' = 'tasks') => mount(CourseWorkbench, {
  props: {
    modelValue: true,
    initialSection,
    courseId: 'course-1',
  },
  global: {
    plugins: [createPinia()],
    stubs: {
      Teleport: true,
      CourseTaskCenter: CourseTaskCenterStub,
      QuestionBankReviewCenter: QuestionBankReviewCenterStub,
    },
  },
})

describe('CourseWorkbench', () => {
  it('在同一个工作台内切换生成任务和题库管理', async () => {
    const wrapper = mountWorkbench()

    expect(wrapper.get('[data-testid="course-workbench"]').attributes('role')).toBe('dialog')
    expect(wrapper.get('[data-testid="course-workbench"]').classes()).toContain('course-workbench--compact')
    expect(wrapper.get('[data-testid="course-workbench-tab-tasks"]').attributes('aria-selected')).toBe('true')
    const taskCenter = wrapper.getComponent({ name: 'CourseTaskCenter' })
    expect(taskCenter.props()).toMatchObject({
      modelValue: true,
      courseId: 'course-1',
      embedded: true,
    })

    await wrapper.get('[data-testid="course-workbench-tab-question-bank"]').trigger('click')

    expect(wrapper.get('[data-testid="course-workbench-tab-question-bank"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-testid="course-workbench"]').classes()).not.toContain('course-workbench--compact')
    const questionBank = wrapper.getComponent({ name: 'QuestionBankReviewCenter' })
    expect(questionBank.props()).toMatchObject({
      modelValue: true,
      courseId: 'course-1',
      embedded: true,
    })
  })

  it('支持从课程卡片直接打开题库模块，并通过 Escape 关闭', async () => {
    const wrapper = mountWorkbench('question-bank')

    expect(wrapper.get('[data-testid="course-workbench-tab-question-bank"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-testid="embedded-question-bank"]').text()).toBe('course-1')

    await wrapper.get('[data-testid="course-workbench"]').trigger('keydown', { key: 'Escape' })

    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
})
