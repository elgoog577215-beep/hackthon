import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import LearningTaskOverlay from '@/components/LearningTaskOverlay.vue'

const MorphingDialogStub = defineComponent({
  emits: ['close'],
  template: '<div class="morphing-dialog-stub"><slot /></div>',
})

describe('LearningTaskOverlay navigation', () => {
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

    const tabs = wrapper.findAll('.task-overlay > header [role="tab"]')
    expect(tabs.map(tab => tab.text())).toEqual(['当前练习', '学习记录2', '学习概况'])
    expect(tabs[0]!.attributes('aria-selected')).toBe('true')

    await tabs[1]!.trigger('click')
    await tabs[2]!.trigger('click')

    expect(wrapper.emitted('records')).toHaveLength(1)
    expect(wrapper.emitted('stats')).toHaveLength(1)
  })
})
