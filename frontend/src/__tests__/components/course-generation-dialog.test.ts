import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CourseGenerationDialog from '@/components/CourseGenerationDialog.vue'

describe('CourseGenerationDialog', () => {
  it('默认走六步确认流程，不提供直接生成入口', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: {
        stubs: {
          Teleport: true,
          MaterialInputPanel: { template: '<div class="material-stub" />' },
        },
      },
    })

    await wrapper.get('#course-subject').setValue('线性代数基础')
    await wrapper.findAll('.difficulty-option')[2]!.trigger('click')
    await wrapper.findAll('.style-option')[2]!.trigger('click')
    await wrapper.findAll('.compact-grid select')[0]!.setValue('math_formal')
    expect(wrapper.text()).toContain('分六步完成课程')
    expect(wrapper.text()).not.toContain('直接生成')
    await wrapper.get('#course-requirements').setValue('保留完整推导，并提供独立练习')
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('generate')).toHaveLength(1)
    expect(wrapper.emitted('generate')?.[0]?.[0]).toEqual({
      subject: '线性代数基础',
      options: expect.objectContaining({
        request_id: expect.any(String),
        difficulty: 'advanced',
        style: 'socratic',
        pedagogy_mode: 'math_formal',
        generation_mode: 'review_blueprint',
        requirements: '保留完整推导，并提供独立练习',
        material_bindings: [],
      }),
    })
  })

  it('同一份失败重试参数沿用请求号，参数变化后才创建新请求号', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: {
        stubs: {
          Teleport: true,
          MaterialInputPanel: { template: '<div class="material-stub" />' },
        },
      },
    })
    await wrapper.get('#course-subject').setValue('网络重试课程')

    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()

    const firstId = (wrapper.emitted('generate')?.[0]?.[0] as any).options.request_id
    const retryId = (wrapper.emitted('generate')?.[1]?.[0] as any).options.request_id
    expect(retryId).toBe(firstId)

    await wrapper.get('#course-subject').setValue('修改后的课程')
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()
    const changedId = (wrapper.emitted('generate')?.[2]?.[0] as any).options.request_id
    expect(changedId).not.toBe(firstId)

    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()
    const reopenedId = (wrapper.emitted('generate')?.[3]?.[0] as any).options.request_id
    expect(reopenedId).not.toBe(changedId)
  })

  it('保持纵向难度、四种教学风格和第二层课程策略', () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: {
        stubs: {
          Teleport: true,
          MaterialInputPanel: { template: '<div class="material-stub" />' },
        },
      },
    })

    expect(wrapper.findAll('.difficulty-options .difficulty-option')).toHaveLength(3)
    expect(wrapper.findAll('.style-options .style-option')).toHaveLength(4)
    expect(wrapper.findAll('.strategy-settings .select-input')).toHaveLength(3)
    expect(wrapper.find('.difficulty-option.active').text()).toContain('进阶')
    expect(wrapper.find('.style-option.active').text()).toContain('学术严谨')
  })

  it('生成过程中禁止关闭和重复提交', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true, busy: true },
      global: { stubs: { Teleport: true, MaterialInputPanel: true } },
    })

    expect(wrapper.find('.generation-dialog__footer .primary-button').attributes('disabled')).toBeDefined()
    await wrapper.find('.generation-dialog__header .icon-button').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
