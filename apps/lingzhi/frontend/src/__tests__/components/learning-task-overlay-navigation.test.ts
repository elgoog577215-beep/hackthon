import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningTaskOverlay from '@/components/LearningTaskOverlay.vue'

describe('LearningTaskOverlay navigation', () => {
  it('桌面嵌入模式保留练习并把提问传给旁边的助手，不创建全屏遮罩', async () => {
    const wrapper = mount(LearningTaskOverlay, {
      props: { courseId: 'course-1', nodeId: 'node-1', embedded: true },
      global: { stubs: { PracticeWorkspace: true } },
    })
    expect(wrapper.get('[data-testid="question-book-dialog"]').attributes('role')).toBe('region')
    expect(wrapper.get('[data-testid="question-book-dialog"]').attributes('aria-modal')).toBeUndefined()
    expect(wrapper.find('.question-book-modal__backdrop').exists()).toBe(false)
    wrapper.getComponent({ name: 'PracticeWorkspace' }).vm.$emit('ask-teacher', { text: '请解释这一步', nodeId: 'node-1' })
    expect(wrapper.emitted('askTeacher')?.[0]).toEqual([{ text: '请解释这一步', nodeId: 'node-1' }])
    expect(wrapper.emitted('close')).toBeUndefined()
    wrapper.unmount()
  })

  it('题库本作为居中的模态弹窗打开，而不是占满学习页面', () => {
    const wrapper = mount(LearningTaskOverlay, {
      props: {
        courseId: 'course-1',
        nodeId: 'node-1',
        nodeLabel: '哲学的本质与学科边界',
      },
      global: {
        stubs: {
          PracticeWorkspace: true,
        },
      },
    })

    const dialog = wrapper.get('[data-testid="question-book-dialog"]')
    expect(dialog.attributes('role')).toBe('dialog')
    expect(dialog.attributes('aria-modal')).toBe('true')
    expect(wrapper.find('.task-overlay').exists()).toBe(false)
    expect(wrapper.find('.learning-tool-overlay').exists()).toBe(false)
    expect(wrapper.find('.question-book-modal__backdrop').exists()).toBe(true)
    expect(dialog.find('.question-book-dialog__close').exists()).toBe(true)
    expect(dialog.findAll('.question-book-dialog__views button')).toHaveLength(3)
  })

  it('题库本保留当前范围，并可从遮罩或关闭按钮返回正文', async () => {
    const wrapper = mount(LearningTaskOverlay, {
      props: {
        courseId: 'course-1',
        nodeId: 'node-1',
        nodeLabel: '哲学的本质与学科边界',
        recordCount: 2,
      },
      global: {
        stubs: {
          PracticeWorkspace: true,
        },
      },
    })

    expect(wrapper.find('.course-workspace-tabs').exists()).toBe(false)
    expect(wrapper.get('.question-book-dialog__identity').text()).toContain('题库本')
    expect(wrapper.get('.question-book-dialog__identity').text()).toContain('哲学的本质与学科边界')
    expect(wrapper.getComponent({ name: 'PracticeWorkspace' }).props('nodeLabel')).toBe('哲学的本质与学科边界')
    expect(wrapper.getComponent({ name: 'PracticeWorkspace' }).props('hideViewSwitch')).toBe(true)
    await wrapper.get('.question-book-modal__backdrop').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    await wrapper.get('.question-book-dialog__close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)
  })
})
