import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QuestionBankReviewPanel from '@/components/QuestionBankReviewPanel.vue'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))
const { runQuestionBankRebuild } = vi.hoisted(() => ({
  runQuestionBankRebuild: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get, post } }))
vi.mock('@/utils/question-bank-rebuild', () => ({ runQuestionBankRebuild }))

describe('QuestionBankReviewPanel', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    runQuestionBankRebuild.mockReset()
    get.mockImplementation((url: string) => {
      if (url.endsWith('/solution')) {
        return Promise.resolve({
          data: {
            solution_envelope: {
              canonical_answer: '应包含跨章节证据链。',
              rubric: [{ criterion: '证据对应', points: 4 }],
            },
            solution_validation: {
              passed: true,
              independent_answer: '独立求解结果',
              conflicts: [],
            },
          },
        })
      }
      return Promise.resolve({ data: {
        bundle_revision_id: 'qbb-1',
        assessment_profile: {
          subject_family: 'natural_science',
          domain: 'thermodynamics',
          education_stage: 'undergraduate',
          confidence: 0.91,
        },
        assessment_objectives: [{
          objective_id: 'objective-1',
          node_id: 'node-1',
          objective: '解释热力学过程并验证能量守恒',
          source_sufficiency: 'sufficient',
          preferred_archetype_ids: ['numeric_calculation'],
          generation_status: 'ready',
          risk_level: 'auto_publish',
        }],
        coverage: {
          required_objective_count: 4,
          covered_objective_count: 4,
          coverage_ratio: 1,
        },
        review_queue: { blocking_count: 1 },
        web_enrichment: { status: 'completed', source_count: 2 },
        items: [{
          item_id: 'item-1',
          revision_id: 'revision-1',
          prompt: '给定材料，完成跨章节分析并检查结论。',
          assessment_role: 'cross_chapter_transfer',
          lifecycle_status: 'needs_review',
          risk_flags: ['comprehensive_task'],
          quality_report: { passed: true, status: 'passed' },
          source_records: [{ source_type: 'course_knowledge_base' }],
          node_id: 'node-1',
          objective_id: 'objective-1',
          archetype_id: 'integrated_performance',
          validation_mode: 'expert_rubric_validator',
          generation_status: 'waiting_review',
        }],
      } })
    })
    post.mockResolvedValue({
      data: {
        bundle_revision_id: 'qbb-2',
        review_queue: { blocking_count: 0 },
        item: { revision_id: 'revision-1', lifecycle_status: 'approved' },
      },
    })
    runQuestionBankRebuild.mockImplementation(async (
      _courseId: string,
      _request: unknown,
      options: { onUpdate?: (job: Record<string, unknown>) => void },
    ) => {
      options.onUpdate?.({
        status: 'running',
        progress: 55,
        current_stage: 'question_generation',
        message: '正在生成题目',
      })
      options.onUpdate?.({
        status: 'completed',
        progress: 100,
        current_stage: 'publication',
        message: '发布完成',
      })
      return { status: 'completed', progress: 100 }
    })
  })

  it('展示覆盖矩阵摘要并只要求处理阻断题', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/api/courses/course-1/question-bank')
    expect(wrapper.text()).toContain('4 / 4')
    expect(wrapper.text()).toContain('待审核 1')
    expect(wrapper.text()).toContain('thermodynamics')
    expect(wrapper.text()).toContain('解释热力学过程并验证能量守恒')
    expect(wrapper.text()).toContain('给定材料，完成跨章节分析并检查结论。')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
  })

  it('携带题库版本批准候选并刷新审核队列', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()
    await wrapper.get('[data-testid="approve-question"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank/items/revision-1/reviews',
      {
        decision: 'approved',
        note: '',
        expected_bundle_revision_id: 'qbb-1',
      },
    )
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('支持按节点异步重建并展示真实阶段', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    await wrapper.get('[data-testid="rebuild-objective-node-1"]').trigger('click')
    await flushPromises()

    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'nodes',
        node_ids: ['node-1'],
        mode: 'incremental',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
    expect(wrapper.text()).toContain('发布完成')
    expect(wrapper.text()).toContain('100%')
  })

  it('教师可按需读取私有答案与独立验证差异', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    await wrapper.get('[data-testid="load-question-solution"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank/items/revision-1/solution',
    )
    expect(wrapper.text()).toContain('应包含跨章节证据链')
    expect(wrapper.text()).toContain('独立求解结果')
  })
})
