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

  it('进入练习后在覆盖层顶栏切换学习记录和学习概况', async () => {
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

    const tabs = wrapper.findAll('.task-overlay > .learning-context-tabs [role="tab"]')
    expect(tabs.map(tab => tab.text())).toEqual(['当前练习', '学习记录2', '学习概况'])
    expect(tabs[0]!.attributes('aria-selected')).toBe('true')

    await tabs[1]!.trigger('click')
    await tabs[2]!.trigger('click')

    expect(wrapper.emitted('records')).toHaveLength(1)
    expect(wrapper.emitted('stats')).toHaveLength(1)
  })
})
