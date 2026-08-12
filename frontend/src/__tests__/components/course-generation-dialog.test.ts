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
    const retrievalToggle = wrapper.get('[data-testid="web-retrieval"]')
    expect((retrievalToggle.element as HTMLInputElement).checked).toBe(false)
    await retrievalToggle.setValue(true)
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
        assessment_generation_profile: 'fast',
        course_type: 'systematic',
        course_intent: {
          schema_version: 'course_intent_v1',
          type: 'systematic',
          learning_goal: '线性代数基础',
          desired_outcome: '保留完整推导，并提供独立练习',
        },
        requirements: '保留完整推导，并提供独立练习',
        material_bindings: [],
        retrieval: { enabled: true },
        teacher_course_brief: expect.objectContaining({
          schema_version: 'teacher_course_brief_v1',
          target_audience: '大学生',
          total_class_hours: 16,
          lesson_duration_minutes: 45,
          teaching_context: 'classroom',
          additional_requirements: '保留完整推导，并提供独立练习',
        }),
      }),
    })
  })

  it('允许显式选择思考版并说明快速版仍保留必要思考', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: { stubs: { Teleport: true, MaterialInputPanel: true } },
    })

    expect(wrapper.text()).toContain('复杂题和关键修复仍会保留必要思考')
    expect(
      wrapper.get('[data-testid="assessment-profile-fast"]')
        .attributes('aria-pressed'),
    ).toBe('true')
    await wrapper.get('[data-testid="assessment-profile-deliberate"]')
      .trigger('click')
    await wrapper.get('#course-subject').setValue('数理逻辑')
    await wrapper.find('.generation-dialog__footer .primary-button')
      .trigger('click')
    await flushPromises()

    expect(
      (wrapper.emitted('generate')?.[0]?.[0] as any)
        .options.assessment_generation_profile,
    ).toBe('deliberate')
  })

  it('把课堂约束写入生成请求，并阻止不合理的章节规模', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: { stubs: { Teleport: true, MaterialInputPanel: true } },
    })

    await wrapper.get('#course-subject').setValue('一次函数')
    await wrapper.get('#teacher-target-audience').setValue('初中二年级学生')
    await wrapper.get('#teacher-total-hours').setValue('12')
    await wrapper.get('#teacher-lesson-minutes').setValue('40')
    await wrapper.get('#teacher-context').setValue('blended')
    await wrapper.get('#teacher-chapter-count').setValue('6')
    await wrapper.get('#teacher-section-count').setValue('4')
    expect(wrapper.find('.generation-dialog__footer .primary-button').attributes('disabled')).toBeDefined()

    await wrapper.get('#teacher-section-count').setValue('18')
    await wrapper.get('#teacher-class-profile').setValue('有基础差异，需要分层讨论')
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()

    expect((wrapper.emitted('generate')?.[0]?.[0] as any).options.teacher_course_brief).toMatchObject({
      target_audience: '初中二年级学生',
      total_class_hours: 12,
      lesson_duration_minutes: 40,
      teaching_context: 'blended',
      chapter_count: 6,
      section_count: 18,
      class_profile: '有基础差异，需要分层讨论',
    })
  })

  it('将非必填的课堂信息收进渐进展开区', () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: { stubs: { Teleport: true, MaterialInputPanel: true } },
    })

    const core = wrapper.get('.teacher-brief-section__core')
    const advanced = wrapper.get('.teacher-brief-section__advanced')

    expect(core.findAll('input, select')).toHaveLength(4)
    expect(advanced.attributes('open')).toBeUndefined()
    expect(advanced.text()).toContain('更多课堂设置')
    expect(advanced.find('#teacher-chapter-count').exists()).toBe(true)
    expect(advanced.find('#teacher-class-profile').exists()).toBe(true)
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

  it('将重复策略收敛为四种可用课程类型', () => {
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
    expect(wrapper.findAll('.course-type-option:disabled')).toHaveLength(0)
    expect(wrapper.findAll('.strategy-settings .select-input')).toHaveLength(3)
    expect(wrapper.find('[data-testid="web-retrieval"]').exists()).toBe(true)
    expect(wrapper.find('.difficulty-option.active').text()).toContain('进阶')
    expect(wrapper.find('.course-type-option.active').text()).toContain('系统学习')
    expect(wrapper.get('.course-type-summary').text()).toContain('按知识结构和先修关系')
    expect(wrapper.get('.difficulty-summary').text()).toContain('独立分析')
    expect(wrapper.get('[data-course-type="systematic"]').attributes('aria-label')).toContain('由基础逐步进阶')
    expect(wrapper.text()).toContain('课程类型决定学习过程如何组织')
    expect(wrapper.text()).not.toContain('即将开放')
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

  it('问题探究提交核心问题、证据边界与预期结论', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: { stubs: { Teleport: true, MaterialInputPanel: true } },
    })

    await wrapper.get('[data-course-type="inquiry"]').trigger('click')
    expect(wrapper.find('[data-testid="inquiry-intent-form"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('已有认识会作为待检验假设')
    expect(wrapper.text()).toContain('问题路径')
    expect(wrapper.find('.generation-dialog__footer .primary-button').attributes('disabled')).toBeDefined()

    await wrapper.get('#inquiry-core-question').setValue('生成式 AI 会如何改变大学教学评价？')
    await wrapper.get('#inquiry-desired-output').setValue('形成一份带证据边界的判断报告')
    await wrapper.get('#inquiry-understanding').setValue('传统作业的区分度可能下降')
    await wrapper.get('#inquiry-evidence-scope').setValue('近三年高校实践与研究论文')
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('generate')?.[0]?.[0]).toEqual({
      subject: '生成式 AI 会如何改变大学教学评价？',
      options: expect.objectContaining({
        course_type: 'inquiry',
        composition_style: 'inquiry_driven',
        course_purpose: 'systematic',
        course_intent: {
          schema_version: 'course_intent_v1',
          type: 'inquiry',
          core_question: '生成式 AI 会如何改变大学教学评价？',
          existing_understanding: '传统作业的区分度可能下降',
          evidence_scope: '近三年高校实践与研究论文',
          desired_output: '形成一份带证据边界的判断报告',
        },
      }),
    })
  })

  it('考试冲刺提交考试日期、考纲范围与当前准备度', async () => {
    const wrapper = mount(CourseGenerationDialog, {
      props: { modelValue: true },
      global: { stubs: { Teleport: true, MaterialInputPanel: true } },
    })

    await wrapper.get('[data-course-type="exam"]').trigger('click')
    expect(wrapper.find('[data-testid="exam-intent-form"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('先定优先级，再用练习校准')
    expect(wrapper.text()).toContain('冲刺计划')

    await wrapper.get('#exam-name').setValue('大学英语六级考试')
    await wrapper.get('#exam-date').setValue('2026-12-20')
    await wrapper.get('#exam-scope').setValue('听力、阅读、翻译与写作')
    await wrapper.get('#exam-preparation').setValue('长对话和写作较弱，每周可投入 8 小时')
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('generate')?.[0]?.[0]).toEqual({
      subject: '大学英语六级考试',
      options: expect.objectContaining({
        course_type: 'exam',
        composition_style: 'example_driven',
        course_purpose: 'exam_sprint',
        course_intent: {
          schema_version: 'course_intent_v1',
          type: 'exam',
          exam_name: '大学英语六级考试',
          exam_date: '2026-12-20',
          exam_scope: '听力、阅读、翻译与写作',
          current_preparation: '长对话和写作较弱，每周可投入 8 小时',
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
    expect(wrapper.text()).not.toContain('Coming soon')
    expect(wrapper.text()).toContain('More classroom settings')
    expect((wrapper.get('#teacher-target-audience').element as HTMLInputElement).value).toBe('University students')
    expect(wrapper.text()).not.toContain('courseGeneration.')
    expect(wrapper.text()).not.toContain('课程类型')
    expect(wrapper.text()).not.toContain('更多课堂设置')
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
