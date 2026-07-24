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

  it('默认走四步确认流程，不提供直接生成入口', async () => {
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
    await wrapper.findAll('.compact-grid select')[0]!.setValue('math_formal')
    expect(wrapper.findAll('select[data-testid="secondary-pedagogy-mode"] option').map(option => option.attributes('value'))).not.toContain('math_formal')
    await wrapper.find('[data-testid="secondary-pedagogy-mode"]').setValue('natural_science')
    await wrapper.find('[data-testid="web-question-enrichment"]').setValue(true)
    expect(wrapper.text()).toContain('四步完成课程')
    expect(wrapper.findAll('.guided-intro__steps li')).toHaveLength(4)
    expect(wrapper.findAll('.guided-intro__steps strong').map(item => item.text())).toEqual([
      '目录确认',
      '教案确认',
      '正文生成',
      '确认发布',
    ])
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
        composition_style: 'balanced',
        pedagogy_mode: 'math_formal',
        secondary_mode: 'natural_science',
        secondary_intensity: 'collaborative',
        generation_mode: 'review_blueprint',
        course_type: 'systematic',
        course_intent: {
          schema_version: 'course_intent_v1',
          type: 'systematic',
          learning_goal: '线性代数基础',
          desired_outcome: '保留完整推导，并提供独立练习',
        },
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

  it('将重复策略收敛为四种课程类型，并只开放系统学习与项目实战', () => {
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
    expect(wrapper.findAll('.course-type-option')).toHaveLength(4)
    expect(wrapper.findAll('.course-type-option:disabled')).toHaveLength(2)
    expect(wrapper.findAll('.strategy-settings .select-input')).toHaveLength(3)
    expect(wrapper.find('[data-testid="web-question-enrichment"]').exists()).toBe(true)
    expect(wrapper.find('.difficulty-option.active').text()).toContain('进阶')
    expect(wrapper.find('.course-type-option.active').text()).toContain('系统学习')
    expect(wrapper.text()).toContain('课程类型决定学习过程如何组织')
    expect(wrapper.text()).toContain('即将开放')
  })

  it('辅助学科不能与手动选择的主学科相同', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: { stubs: { Teleport: true, MaterialInputPanel: true } },
    })

    const selects = wrapper.findAll('.compact-grid select')
    await selects[1]!.setValue('natural_science')
    await selects[0]!.setValue('natural_science')

    expect((wrapper.get('[data-testid="secondary-pedagogy-mode"]').element as HTMLSelectElement).value).toBe('')
    expect(wrapper.get('[data-testid="secondary-pedagogy-mode"]').findAll('option').map(option => option.attributes('value'))).not.toContain('natural_science')
  })

  it('项目实战提交独立的项目目标、交付成果与暂定学习起点', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: {
        stubs: {
          Teleport: true,
          MaterialInputPanel: { template: '<div class="material-stub" />' },
        },
      },
    })

    await wrapper.get('[data-course-type="project"]').trigger('click')
    expect(wrapper.find('[data-testid="project-intent-form"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('系统会标记起点信息不足')
    expect(wrapper.text()).toContain('提交项目后，四步形成个人课程')
    expect(wrapper.text()).toContain('个人路径')
    expect(wrapper.text()).toContain('能力与知识')
    expect(wrapper.text()).toContain('项目课程')
    expect(wrapper.text()).toContain('确认课程')
    expect(wrapper.find('.generation-dialog__footer .primary-button').attributes('disabled')).toBeDefined()

    await wrapper.get('#project-goal').setValue('设计一款适合大学生使用的环保保温玻璃杯')
    await wrapper.get('#project-deliverable').setValue('产品设计方案和可验证原型')
    expect(wrapper.find('.generation-dialog__footer .primary-button').attributes('disabled')).toBeUndefined()
    await wrapper.get('#project-prior-experience').setValue('学过产品设计，熟悉造型和结构')
    await wrapper.get('#project-current-uncertainty').setValue('不了解玻璃材料、隔热原理和制造工艺')
    expect(wrapper.text()).toContain('根据你的自述形成第一版个人路径')
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('generate')?.[0]?.[0]).toEqual({
      subject: '设计一款适合大学生使用的环保保温玻璃杯',
      options: expect.objectContaining({
        request_id: expect.any(String),
        course_type: 'project',
        composition_style: 'project_driven',
        course_intent: {
          schema_version: 'course_intent_v1',
          type: 'project',
          project_goal: '设计一款适合大学生使用的环保保温玻璃杯',
          expected_deliverable: '产品设计方案和可验证原型',
          prior_experience: '学过产品设计，熟悉造型和结构',
          current_uncertainty: '不了解玻璃材料、隔热原理和制造工艺',
          project_constraints: '',
        },
      }),
    })
  })

  it('英文模式完整解释四种课程类型，不泄漏中文或翻译键', async () => {
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

    expect(wrapper.text()).toContain('Course type')
    expect(wrapper.text()).toContain('Systematic learning')
    expect(wrapper.text()).toContain('Project practice')
    expect(wrapper.text()).toContain('Inquiry learning')
    expect(wrapper.text()).toContain('Exam sprint')
    expect(wrapper.text()).toContain('Coming soon')
    expect(wrapper.text()).not.toContain('courseGeneration.')
    expect(wrapper.text()).not.toContain('课程类型')
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
