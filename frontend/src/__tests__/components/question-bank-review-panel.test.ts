import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QuestionBankReviewPanel from '@/components/QuestionBankReviewPanel.vue'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))
const {
  resumeQuestionBankRebuild,
  runQuestionBankRebuild,
} = vi.hoisted(() => ({
  resumeQuestionBankRebuild: vi.fn(),
  runQuestionBankRebuild: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get, post } }))
vi.mock('@/utils/question-bank-rebuild', () => ({
  resumeQuestionBankRebuild,
  runQuestionBankRebuild,
}))

describe('QuestionBankReviewPanel', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    resumeQuestionBankRebuild.mockReset()
    runQuestionBankRebuild.mockReset()
    resumeQuestionBankRebuild.mockResolvedValue(null)
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

  it('展示覆盖矩阵并允许浏览全部题目', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    expect(get).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank',
      { silentError: true },
    )
    expect(wrapper.text()).toContain('4 / 4')
    expect(wrapper.text()).toContain('当前可用题目')
    expect(wrapper.text()).toContain('1 道高风险题等待发布前确认')
    expect(wrapper.text()).toContain('浏览全部题目')
    expect(wrapper.text()).toContain('thermodynamics')
    expect(wrapper.text()).toContain('解释热力学过程并验证能量守恒')
    expect(wrapper.text()).toContain('给定材料，完成跨章节分析并检查结论。')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
  })

  it('携带题库版本批准高风险题并保留在浏览列表', async () => {
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
    expect(get).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('已发布')
  })

  it('普通题自动发布并出现在完整浏览列表', async () => {
    get.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-sample',
        assessment_profile: {
          subject_family: 'programming_engineering',
          domain: 'python',
          education_stage: 'undergraduate',
          confidence: 0.96,
        },
        assessment_objectives: [],
        coverage: {
          required_objective_count: 1,
          covered_objective_count: 1,
          coverage_ratio: 1,
        },
        review_queue: { blocking_count: 0, sample_count: 0 },
        web_enrichment: { status: 'not_needed', source_count: 0 },
        items: [{
          item_id: 'sample-1',
          revision_id: 'sample-revision-1',
          prompt: '解释 Python 对象模型中的类型关系。',
          assessment_role: 'concept_check',
          lifecycle_status: 'approved',
          review_status: 'approved',
          review_tier: 'auto_publish',
          risk_flags: [],
          quality_report: { passed: true, status: 'passed' },
          source_records: [{ source_type: 'course_knowledge_base' }],
          objective_id: 'objective-1',
          archetype_id: 'concept_explanation',
          validation_mode: 'rubric_validator',
          generation_status: 'published',
        }],
      },
    })

    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('当前可用题目')
    expect(wrapper.text()).toContain('已发布')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
  })

  it('打回已发布题后按题目修订异步重做', async () => {
    get.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-published',
        assessment_profile: {},
        assessment_objectives: [],
        coverage: {
          required_objective_count: 1,
          covered_objective_count: 1,
          coverage_ratio: 1,
        },
        review_queue: { blocking_count: 0 },
        web_enrichment: {},
        items: [{
          item_id: 'item-published',
          revision_id: 'revision-published',
          prompt: '这是一道已经发布的练习题。',
          assessment_role: 'practice',
          lifecycle_status: 'approved',
          review_status: 'approved',
          review_tier: 'auto_publish',
          risk_flags: [],
          quality_report: { passed: true, status: 'passed' },
          node_id: 'node-1',
          generation_status: 'published',
        }],
      },
    })
    post.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-rejected',
        review_queue: { blocking_count: 0 },
        item: {
          revision_id: 'revision-published',
          lifecycle_status: 'rejected',
          generation_status: 'rework_requested',
        },
      },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    await wrapper.get('[data-testid="rework-question"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank/items/revision-published/reviews',
      {
        decision: 'rejected',
        note: '',
        expected_bundle_revision_id: 'qbb-published',
      },
    )
    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'items',
        node_ids: [],
        revision_ids: ['revision-published'],
        mode: 'incremental',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
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

  it('提供整门课程题目重新生成按钮和真实进度条', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    const button = wrapper.get(
      '[data-testid="rebuild-course-question-bank"]',
    )
    expect(button.text()).toContain('重新生成整门课程题目')
    await button.trigger('click')
    await flushPromises()

    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'course',
        node_ids: [],
        mode: 'full',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
    const progress = wrapper.get('[role="progressbar"]')
    expect(progress.attributes('aria-valuenow')).toBe('100')
    expect(progress.text()).toContain('课程题目已重新生成并发布')
    expect(progress.text()).toContain('100%')
  })

  it('重新打开面板时恢复后台任务并继续展示进度', async () => {
    resumeQuestionBankRebuild.mockImplementation(async (
      courseId: string,
      options: {
        onUpdate?: (job: Record<string, unknown>) => void
      },
    ) => {
      expect(courseId).toBe('course-1')
      options.onUpdate?.({
        job_id: 'job-recovered',
        status: 'running',
        progress: 52,
        current_stage: 'question_generation',
        message: '正在生成第 48/189 道候选题',
        status_url: '/jobs/job-recovered',
        stage_details: {
          published_chapters: 15,
          total_chapters: 63,
          current_chapter: '4.5 装饰器',
          current_chapter_item: 2,
          chapter_item_total: 3,
        },
      })
      return new Promise(() => {})
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    expect(resumeQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      expect.objectContaining({
        maxPolls: 3600,
        signal: expect.any(AbortSignal),
        onUpdate: expect.any(Function),
      }),
    )
    const progress = wrapper.get('[role="progressbar"]')
    expect(progress.attributes('aria-valuenow')).toBe('52')
    expect(progress.text()).toContain(
      '正在生成第 48/189 道候选题',
    )
    expect(progress.text()).toContain(
      '章节发布 15/63 · 当前 4.5 装饰器（2/3）',
    )
    expect(
      wrapper.get('[data-testid="rebuild-course-question-bank"]')
        .attributes('disabled'),
    ).toBeDefined()
    wrapper.unmount()
  })

  it('重新生成失败时保留当前有效题库并显示失败进度', async () => {
    const failure = Object.assign(
      new Error('模型服务暂时不可用'),
      {
        job: {
          job_id: 'job-failed',
          status: 'failed',
          progress: 48,
          current_stage: 'question_generation',
          message: '生成题目时中断',
          status_url: '/jobs/job-failed',
        },
      },
    )
    runQuestionBankRebuild.mockRejectedValueOnce(failure)
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    await wrapper
      .get('[data-testid="rebuild-course-question-bank"]')
      .trigger('click')
    await flushPromises()

    expect(wrapper.findAll(
      '[data-testid="question-review-item"]',
    )).toHaveLength(1)
    expect(wrapper.text()).toContain(
      '给定材料，完成跨章节分析并检查结论。',
    )
    const progress = wrapper.get('[role="progressbar"]')
    expect(progress.attributes('aria-valuenow')).toBe('48')
    expect(progress.text()).toContain(
      '重新生成失败，当前有效题库保持不变',
    )
    expect(progress.text()).toContain('模型服务暂时不可用')
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
