import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PracticeAnswerRenderer from '@/components/PracticeAnswerRenderer.vue'
import http from '@/utils/http'

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
  },
}))

describe('PracticeAnswerRenderer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('按 choice 契约渲染选项并提交结构化选项 ID', async () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: {
          schema_version: 'input_contract_v2',
          mode: 'choice',
          selection: { multiple: false },
        },
        options: [
          { id: 'A', label: '选项 A' },
          { id: 'B', label: '选项 B' },
        ],
        modelValue: {},
      },
    })

    await wrapper.get('input[value="B"]').setValue(true)

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      selected_option_id: 'B',
    })
  })

  it('旧 structured_text 题目会根据选项恢复为选择题', async () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: {
          mode: 'structured_text',
        },
        questionType: 'output_prediction',
        options: [
          { option_id: 'A', option_text: '输出 A' },
          { option_id: 'B', option_text: '输出 B' },
        ],
        modelValue: {},
      },
    })

    expect(wrapper.attributes('data-mode')).toBe('choice')
    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('输出 A')

    await wrapper.get('input[value="B"]').setValue(true)
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      selected_option_id: 'B',
    })
  })

  it.each([
    ['numeric_response', 'numeric_unit', 'input[type="number"]'],
    ['implementation_task', 'code', '.code-editor'],
    ['debugging_trace', 'structured_fields', 'textarea'],
  ])('旧契约的 %s 会恢复为 %s 组件', (questionType, mode, selector) => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: { mode: 'structured_text' },
        questionType,
        options: [],
        modelValue: {},
      },
    })

    expect(wrapper.attributes('data-mode')).toBe(mode)
    expect(wrapper.find(selector).exists()).toBe(true)
  })

  it('多选契约保存结构化选项 ID 数组', async () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: {
          schema_version: 'input_contract_v2',
          mode: 'choice',
          selection: { multiple: true },
        },
        questionType: 'multiple_choice',
        options: [
          { id: 'A', label: '选项 A' },
          { id: 'B', label: '选项 B' },
        ],
        modelValue: { selected_option_ids: ['A'] },
      },
    })

    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(2)
    await wrapper.get('input[value="B"]').setValue(true)
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      selected_option_ids: ['A', 'B'],
    })
  })

  it.each([
    ['short_text', 'textarea'],
    ['rich_text', 'textarea'],
    ['numeric_unit', 'input[type="number"]'],
    ['structured_fields', 'textarea'],
  ])('按 %s 契约渲染对应字段', (mode, selector) => {
    const fields = mode === 'numeric_unit'
      ? [
          { field_id: 'value', kind: 'number', label: '数值', required: true },
          { field_id: 'unit', kind: 'short_text', label: '单位', required: true },
          { field_id: 'work', kind: 'rich_text', label: '过程', required: true },
        ]
      : mode === 'structured_fields'
        ? [
            { field_id: 'claim', kind: 'short_text', label: '观点', required: true },
            { field_id: 'evidence', kind: 'rich_text', label: '证据', required: true },
          ]
        : [{ field_id: 'text', kind: mode, label: '作答', required: true }]
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: {
          schema_version: 'input_contract_v2',
          mode,
          fields,
        },
        modelValue: {},
      },
    })

    expect(wrapper.find(selector).exists()).toBe(true)
  })

  it('代码模式保存语言、代码和脱敏运行结果', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { output: 'ok', error: '' },
    } as any)
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: {
          schema_version: 'input_contract_v2',
          mode: 'code',
          language: 'python',
          allowed_languages: ['python', 'javascript'],
          fields: [
            { field_id: 'code', kind: 'code', label: '代码', required: true },
          ],
        },
        modelValue: {
          language: 'python',
          code: 'print("ok")',
        },
      },
    })

    await wrapper.get('.run-command').trigger('click')
    await vi.waitFor(() => {
      expect(http.post).toHaveBeenCalledWith('/api/execute', {
        code: 'print("ok")',
        language: 'python',
        timeout: 10,
      })
    })
    expect(wrapper.text()).toContain('ok')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      language: 'python',
      code: 'print("ok")',
      run_result: {
        status: 'completed',
        output: 'ok',
      },
    })
  })
})

describe('PracticeAnswerRenderer 分步作答 (J3)', () => {
  const stepwiseContract = {
    schema_version: 'input_contract_v2',
    mode: 'rich_text',
    stepwise: true,
  }

  it('题目未开分步时不显示分步入口', () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: { contract: { mode: 'rich_text' }, modelValue: {} },
    })

    expect(wrapper.find('[data-testid="stepwise-toggle"]').exists()).toBe(false)
  })

  it('选择题即使契约开了分步也不提供——一次选择没有可拆的推导', () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: { mode: 'choice', stepwise: true, selection: { multiple: false } },
        options: [{ id: 'A', label: '选项 A' }, { id: 'B', label: '选项 B' }],
        modelValue: {},
      },
    })

    expect(wrapper.find('[data-testid="stepwise-toggle"]').exists()).toBe(false)
  })

  it('开启分步后写入 answer_payload.steps[]', async () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: { contract: stepwiseContract, modelValue: {} },
    })

    await wrapper.get('[data-testid="stepwise-toggle"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      steps: [{ text: '', step_index: 1, step_id: '' }],
    })
  })

  it('逐步输入按顺序编号', async () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: stepwiseContract,
        modelValue: { steps: [{ text: '先配方', step_index: 1, step_id: '' }] },
      },
    })

    await wrapper.get('[data-testid="stepwise-add"]').trigger('click')
    const emitted = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as any

    expect(emitted.steps.map((step: any) => step.step_index)).toEqual([1, 2])
  })

  it('降级路径：切回整体作答时保留已写内容且不再带 steps', async () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: stepwiseContract,
        modelValue: {
          steps: [
            { text: '先配方得 (x-2)^2-1', step_index: 1, step_id: '' },
            { text: '顶点是 (2,-1)', step_index: 2, step_id: '' },
          ],
        },
      },
    })

    await wrapper.get('[data-testid="stepwise-toggle"]').trigger('click')
    const emitted = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as any

    // 学生写过的东西一个字都不能丢。
    expect(emitted.text).toContain('先配方得 (x-2)^2-1')
    expect(emitted.text).toContain('顶点是 (2,-1)')
    // 没有 steps 就是后端认的"整体作答"形状。
    expect(emitted.steps).toBeUndefined()
  })

  it('删除某一步后其余步骤重新编号', async () => {
    const wrapper = mount(PracticeAnswerRenderer, {
      props: {
        contract: stepwiseContract,
        modelValue: {
          steps: [
            { text: '第一步', step_index: 1, step_id: '' },
            { text: '第二步', step_index: 2, step_id: '' },
            { text: '第三步', step_index: 3, step_id: '' },
          ],
        },
      },
    })

    await wrapper.findAll('.step-remove')[0]!.trigger('click')
    const emitted = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as any

    expect(emitted.steps.map((step: any) => step.text)).toEqual(['第二步', '第三步'])
    expect(emitted.steps.map((step: any) => step.step_index)).toEqual([1, 2])
  })

  it('分步与代码题文案都经过 i18n 入口', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/components/PracticeAnswerRenderer.vue'),
      'utf-8',
    )

    // 这些标签此前是硬编码中文，违反 AGENTS.md 0.2。
    expect(source).toContain("t('courseWorkspace.practice.stepwiseOn'")
    expect(source).toContain("t('courseWorkspace.practice.codeLanguage'")
    expect(source).toContain("t('courseWorkspace.practice.fieldValue'")
    expect(source).not.toMatch(/<span>编程语言<\/span>/)
    expect(source).not.toMatch(/label: '数值'/)
  })
})
