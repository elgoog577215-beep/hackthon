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
            solution_spec: {
              summary: '先定位章节结论，再建立跨章节证据关系。',
              steps: ['提取第一章结论', '用第二章证据验证结论'],
              final_answer: '应包含跨章节证据链。',
              checks: ['每条结论均有对应证据'],
              option_analysis: [],
              common_errors: ['只罗列结论，没有说明证据关系'],
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
        generation_summary: {
          diversity_rejection_count: 2,
          diversity_regeneration_count: 1,
          historical_diversity_comparison_count: 6,
        },
        web_enrichment: { status: 'completed', source_count: 2 },
        chapter_rebuild: {},
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
          question_type: 'case_analysis',
          design_brief_summary: {
            schema_version: 'question_design_brief_v1',
            semantics_registry_id: 'life_science.case_analysis.v1',
            content_coverage: true,
            method_coverage: true,
          },
          semantic_preflight: {
            passed: true,
            issues: [],
          },
          generation_audit_summary: {
            first_pass_passed: false,
            repair_count: 1,
            semantic_reviewer_trigger: true,
            issue_codes: ['MATERIAL_BINDING_INVALID'],
          },
          diversity_report: {
            passed: false,
            max_similarity: 0.86,
            closest_question_id: 'item-history-1',
            reasons: ['shared_subject_anchors'],
          },
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
    expect(wrapper.get('[data-testid="question-diversity-monitor"]').text())
      .toContain('2 次拦截')
    expect(wrapper.get('[data-testid="question-diversity-monitor"]').text())
      .toContain('历史比较 6 道')
    expect(wrapper.text()).toContain('解释热力学过程并验证能量守恒')
    expect(wrapper.text()).toContain('给定材料，完成跨章节分析并检查结论。')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    const audit = wrapper.get('[data-testid="question-generation-audit"]')
    expect(audit.text()).toContain('生成与质量闭环')
    expect(audit.text()).toContain('life_science.case_analysis.v1')
    expect(audit.text()).toContain('修复 1 次')
    expect(audit.text()).toContain('MATERIAL_BINDING_INVALID')
    expect(audit.text()).toContain('重复 86%')
    expect(audit.text()).toContain('item-history-1')
  })

  it('题目列表按每页十条分页并在筛选时回到第一页', async () => {
    const paginatedItems = Array.from({ length: 23 }, (_, index) => ({
      item_id: `page-item-${index + 1}`,
      revision_id: `page-revision-${index + 1}`,
      prompt: index === 0
        ? `分页题目 01\n${'这是一段需要默认收起的长题干。'.repeat(40)}`
        : `分页题目 ${String(index + 1).padStart(2, '0')}`,
      assessment_role: 'candidate',
      lifecycle_status: index === 22 ? 'rejected' : 'approved',
      risk_flags: [],
      quality_report: { passed: true, status: 'passed' },
      source_records: [{ source_type: 'course_knowledge_base' }],
      node_id: `page-node-${index + 1}`,
      objective_id: `page-objective-${index + 1}`,
      validation_mode: 'code_validator',
      generation_status: 'published',
    }))
    get.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-question-pages',
        assessment_profile: {},
        assessment_objectives: [],
        coverage: {
          required_objective_count: 0,
          covered_objective_count: 0,
          coverage_ratio: 1,
        },
        review_queue: {},
        web_enrichment: {},
        chapter_rebuild: {},
        items: paginatedItems,
      },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(10)
    expect(wrapper.text()).toContain('分页题目 01')
    expect(wrapper.text()).not.toContain('分页题目 11')
    expect(wrapper.get('[data-testid="question-pagination"]').text()).toContain(
      '第 1–10 条，共 23 条',
    )
    const detailToggles = wrapper.findAll(
      '[data-testid="toggle-question-details"]',
    )
    expect(detailToggles).toHaveLength(10)
    expect(detailToggles[0]!.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.question-review-item__details').exists()).toBe(false)
    await detailToggles[0]!.trigger('click')
    expect(detailToggles[0]!.attributes('aria-expanded')).toBe('true')
    expect(wrapper.findAll('.question-review-item__details')).toHaveLength(1)
    await detailToggles[1]!.trigger('click')
    expect(detailToggles[0]!.attributes('aria-expanded')).toBe('false')
    expect(detailToggles[1]!.attributes('aria-expanded')).toBe('true')
    expect(wrapper.findAll('.question-review-item__details')).toHaveLength(1)

    await wrapper.get('[data-testid="question-page-2"]').trigger('click')
    expect(wrapper.find('.question-review-item__details').exists()).toBe(false)
    expect(wrapper.text()).toContain('分页题目 11')
    expect(wrapper.text()).not.toContain('分页题目 01')

    await wrapper.get('[data-testid="question-page-jump-input"]').setValue('3')
    await wrapper.get('[data-testid="question-page-jump-form"]').trigger('submit')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('分页题目 23')
    expect(wrapper.get('[data-testid="question-pagination"]').text()).toContain(
      '第 21–23 条，共 23 条',
    )

    await wrapper.get('[data-testid="question-search-input"]').setValue('分页题目 12')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('分页题目 12')
    expect(wrapper.find('[data-testid="question-pagination"]').exists()).toBe(false)

    await wrapper.get('[data-testid="question-search-input"]').setValue('')
    await wrapper.get('[data-testid="question-status-filter"]').setValue('rework')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('分页题目 23')
    expect(wrapper.text()).not.toContain('没有符合条件的题目')
  })

  it('异常项置顶并将已覆盖目标按每页十条分页', async () => {
    const coveredObjectives = Array.from({ length: 23 }, (_, index) => ({
      objective_id: `covered-${index + 1}`,
      node_id: `covered-node-${index + 1}`,
      objective: `已覆盖目标 ${String(index + 1).padStart(2, '0')}`,
      source_sufficiency: 'sufficient',
      preferred_archetype_ids: ['implementation_task'],
    }))
    get.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-objective-pages',
        assessment_profile: {},
        assessment_objectives: [
          ...coveredObjectives,
          {
            objective_id: 'failed-objective',
            node_id: 'failed-node',
            objective: '验证失败目标',
            source_sufficiency: 'sufficient',
          },
          {
            objective_id: 'source-objective',
            node_id: 'source-node',
            objective: '资料不足目标',
            source_sufficiency: 'insufficient',
          },
        ],
        coverage: {
          required_objective_count: 25,
          covered_objective_count: 23,
          coverage_ratio: 0.92,
        },
        review_queue: {},
        web_enrichment: {},
        chapter_rebuild: {},
        items: [
          ...coveredObjectives.map((objective, index) => ({
            item_id: `covered-item-${index + 1}`,
            revision_id: `covered-revision-${index + 1}`,
            prompt: `已覆盖题目 ${index + 1}`,
            assessment_role: 'coverage_task',
            lifecycle_status: 'retired',
            risk_flags: [],
            objective_id: objective.objective_id,
            node_id: objective.node_id,
            archetype_id: 'implementation_task',
            validation_mode: 'code_validator',
            generation_status: 'published',
          })),
          {
            item_id: 'failed-item',
            revision_id: 'failed-revision',
            prompt: '失败题目',
            assessment_role: 'coverage_task',
            lifecycle_status: 'retired',
            risk_flags: [],
            objective_id: 'failed-objective',
            node_id: 'failed-node',
            generation_status: 'validation_failed',
          },
        ],
      },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    expect(wrapper.findAll('[data-testid="objective-issue-row"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('验证失败目标')
    expect(wrapper.text()).toContain('资料不足目标')
    expect(wrapper.text()).not.toContain('已覆盖目标 01')

    const toggle = wrapper.get('[data-testid="toggle-covered-objectives"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.text()).toContain('查看全部已覆盖项')
    await toggle.trigger('click')

    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.findAll('[data-testid="objective-covered-row"]')).toHaveLength(10)
    expect(wrapper.text()).toContain('已覆盖目标 01')
    expect(wrapper.text()).not.toContain('已覆盖目标 11')
    expect(wrapper.get('[data-testid="objective-pagination"]').text()).toContain(
      '第 1–10 条，共 23 条',
    )

    await wrapper.get('[data-testid="objective-page-2"]').trigger('click')
    expect(wrapper.text()).toContain('已覆盖目标 11')
    expect(wrapper.text()).not.toContain('已覆盖目标 01')

    await wrapper.get('[data-testid="objective-page-jump-input"]').setValue('3')
    await wrapper.get('[data-testid="objective-page-jump-form"]').trigger('submit')
    expect(wrapper.findAll('[data-testid="objective-covered-row"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('已覆盖目标 23')
    expect(wrapper.get('[data-testid="objective-pagination"]').text()).toContain(
      '第 21–23 条，共 23 条',
    )
  })

  it('携带题库版本批准高风险题并保留在浏览列表', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
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

    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
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
        resume_existing: false,
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
    const progress = wrapper.get('[role="progressbar"]')
    expect(progress.attributes('aria-valuenow')).toBe('100')
    expect(progress.text()).toContain('课程题目已重新生成并发布')
    expect(progress.text()).toContain('100%')
  })

  it('题库缺失时重新整理而不是重复读取', async () => {
    get.mockRejectedValueOnce({
      response: { status: 404 },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    const button = wrapper.get(
      '[data-testid="rebuild-missing-question-bank"]',
    )
    await button.trigger('click')
    await flushPromises()

    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'course',
        node_ids: [],
        mode: 'full',
        resume_existing: false,
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('识别已发布新版章节并从剩余章节继续生成', async () => {
    get.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-partial',
        assessment_profile: {},
        assessment_objectives: [],
        coverage: {},
        review_queue: {},
        web_enrichment: {},
        chapter_rebuild: {
          status: 'partial',
          total_chapters: 63,
          completed_chapters: 9,
          remaining_chapters: 54,
          can_resume: true,
        },
        items: [],
      },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    expect(
      wrapper.get('[data-testid="chapter-generation-checkpoint"]').text(),
    ).toContain('已发布新版章节 9/63')
    const button = wrapper.get(
      '[data-testid="continue-course-question-bank"]',
    )
    expect(button.text()).toContain('继续生成剩余 54 章')
    await button.trigger('click')
    await flushPromises()

    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'course',
        node_ids: [],
        mode: 'full',
        resume_existing: true,
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
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

    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    await wrapper.get('[data-testid="load-question-solution"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank/items/revision-1/solution',
    )
    expect(wrapper.text()).toContain('应包含跨章节证据链')
    expect(wrapper.text()).toContain('先定位章节结论')
    expect(wrapper.text()).toContain('用第二章证据验证结论')
    expect(wrapper.text()).toContain('只罗列结论')
    expect(wrapper.text()).toContain('独立求解结果')
  })
})
