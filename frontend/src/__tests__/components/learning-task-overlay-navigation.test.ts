import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import LearningTaskOverlay from '@/components/LearningTaskOverlay.vue'

const MorphingDialogStub = defineComponent({
  emits: ['close'],
  template: '<div class="morphing-dialog-stub"><slot /></div>',
})

describe('LearningTaskOverlay navigation', () => {
  it('使用与学习记录一致的学习工具覆盖层，而不是居中的全局弹窗', () => {
    const wrapper = mount(LearningTaskOverlay, {
      props: {
        courseId: 'course-1',
        nodeId: 'node-1',
        nodeLabel: '哲学的本质与学科边界',
      },
      global: {
        stubs: {
          MorphingDialog: MorphingDialogStub,
          PracticeWorkspace: true,
        },
      },
    })

    expect(wrapper.find('.morphing-dialog-stub').exists()).toBe(false)
    const overlay = wrapper.get('.task-overlay')
    expect(overlay.classes()).toContain('learning-tool-overlay')
    expect(overlay.attributes('role')).toBe('dialog')
    expect(overlay.attributes('aria-modal')).toBe('true')
    expect(overlay.find('.task-overlay__close').exists()).toBe(true)
  })

  it('题库本使用自己的简洁标题，不再复制课程顶栏', () => {
    const wrapper = mount(LearningTaskOverlay, {
      props: {
        courseId: 'course-1',
        nodeId: 'node-1',
        nodeLabel: '哲学的本质与学科边界',
        recordCount: 2,
      },
      global: {
        stubs: {
          MorphingDialog: MorphingDialogStub,
          PracticeWorkspace: true,
        },
      },
    })

    expect(wrapper.find('.course-workspace-tabs').exists()).toBe(false)
    expect(wrapper.get('.task-overlay__identity').text()).toContain('题库本')
  })
})
