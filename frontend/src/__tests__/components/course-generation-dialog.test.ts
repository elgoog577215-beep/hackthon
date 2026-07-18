import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseGenerationDialog from '@/components/CourseGenerationDialog.vue'
import { setLocale } from '@/shared/i18n'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

describe('CourseGenerationDialog', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
  })

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
    await wrapper.findAll('.composition-option')[2]!.trigger('click')
    await wrapper.findAll('.compact-grid select')[0]!.setValue('math_formal')
    await wrapper.find('[data-testid="web-question-enrichment"]').setValue(true)
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
        composition_style: 'example_driven',
        pedagogy_mode: 'math_formal',
        generation_mode: 'review_blueprint',
        requirements: '保留完整推导，并提供独立练习',
        material_bindings: [],
        web_question_enrichment: { enabled: true },
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

  it('保持纵向难度、五种课程编排偏好和第二层课程策略', () => {
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
    expect(wrapper.findAll('.composition-options .composition-option')).toHaveLength(5)
    expect(wrapper.findAll('.strategy-settings .select-input')).toHaveLength(3)
    expect(wrapper.find('[data-testid="web-question-enrichment"]').exists()).toBe(true)
    expect(wrapper.find('.difficulty-option.active').text()).toContain('进阶')
    expect(wrapper.find('.composition-option.active').text()).toContain('智能均衡')
    expect(wrapper.text()).toContain('更多典型案例与真实场景块')
  })

  it('英文模式完整解释五种课程编排偏好，不泄漏中文或翻译键', async () => {
    await setLocale('en')
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: {
        stubs: {
          Teleport: true,
          MaterialInputPanel: { template: '<div class="material-stub" />' },
        },
      },
    })

    expect(wrapper.text()).toContain('Course composition preference')
    expect(wrapper.text()).toContain('Balanced')
    expect(wrapper.text()).toContain('Theory-driven')
    expect(wrapper.text()).toContain('Case practice')
    expect(wrapper.text()).toContain('Project-driven')
    expect(wrapper.text()).toContain('Inquiry-driven')
    expect(wrapper.text()).not.toContain('courseGeneration.')
    expect(wrapper.text()).not.toContain('课程编排偏好')
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
