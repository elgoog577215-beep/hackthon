import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TeacherDocumentCommandBar from '@/components/TeacherDocumentCommandBar.vue'

describe('TeacherDocumentCommandBar', () => {
  it('keeps reading mode focused on the document actions', () => {
    const wrapper = mount(TeacherDocumentCommandBar, {
      props: { label: '大纲操作', statusLabel: '已保存' },
      slots: { default: '<button>AI 修改</button><button class="primary-action">编辑大纲</button>' },
    })

    expect(wrapper.find('[aria-label="撤销"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="重做"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="历史版本"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已保存')
    expect(wrapper.get('[role="toolbar"]').text()).not.toContain('已保存')
    expect(wrapper.get('[role="status"]').text()).toContain('已保存')
    expect(wrapper.text()).toContain('AI 修改')
    expect(wrapper.text()).toContain('编辑大纲')
  })

  it('reveals undo and redo only while editing', async () => {
    const wrapper = mount(TeacherDocumentCommandBar, {
      props: {
        label: '大纲操作',
        editing: true,
        canUndo: true,
        canRedo: true,
      },
    })

    await wrapper.get('[aria-label="撤销"]').trigger('click')
    await wrapper.get('[aria-label="重做"]').trigger('click')

    expect(wrapper.emitted('undo')).toHaveLength(1)
    expect(wrapper.emitted('redo')).toHaveLength(1)
  })

  it('can omit a status already shown by surrounding navigation', () => {
    const wrapper = mount(TeacherDocumentCommandBar, {
      props: { label: '教案操作', showStatus: false },
      slots: { default: '<button>编辑教案</button>' },
    })

    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.get('[role="toolbar"]').text()).toContain('编辑教案')
  })
})
