import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QuestionBankReviewPanel from '@/components/QuestionBankReviewPanel.vue'
import { setLocale } from '@/shared/i18n'
import zhMessages from '@/../public/locales/zh/translation.json'
import enMessages from '@/../public/locales/en/translation.json'

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
vi.mock('@/utils/http', () => ({
  default: { get, post },
  teacherReadRequestConfig: (config = {}) => config,
  teacherRequestConfig: (config = {}) => ({ ...config, identityScope: 'teacher' }),
}))
vi.mock('@/utils/question-bank-rebuild', () => ({
  resumeQuestionBankRebuild,
  runQuestionBankRebuild,
}))
vi.mock('@/components/CourseReferenceTray.vue', () => ({
  default: {
    name: 'CourseReferenceTray',
    props: ['modelValue', 'variant'],
    emits: ['update:modelValue'],
    template: '<aside data-testid="question-bank-generation-sources" :data-variant="variant">真题资料</aside>',
  },
}))
vi.mock('@/components/QuestionBankImportWorkspace.vue', () => ({
  default: {
    emits: ['show-bank', 'imported'],
    template: '<section data-testid="question-import-workspace">导入文件队列</section>',
  },
}))

describe('QuestionBankReviewPanel', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    await setLocale('zh')
    vi.stubGlobal('confirm', vi.fn(() => false))
    localStorage.clear()
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
              factual_validation: { status: 'unverified', source_bindings: [
                { reference_id: 'course-source-1', claim: '每次扩容将容量翻倍。', quote: '每次扩容将容量翻倍。', status: 'matched' },
              ] },
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
          knowledge_binding_status: 'bound',
          knowledge_points: [{ knowledge_id: 'k-stack', name: '栈的后进先出规则', statement: '最后入栈的元素先出栈' }],
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

  it('allows keyboard users to focus the question reading region and scroll its full contents', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'course-1' }, attachTo: document.body })
    await flushPromises()
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    const reader = wrapper.get('.question-reader__scroll')
    expect(reader.attributes('tabindex')).toBe('0')
    expect(reader.attributes('aria-label')).toBeTruthy()
    ;(reader.element as HTMLElement).focus()
    expect(document.activeElement).toBe(reader.element)
    wrapper.unmount()
  })

  it('shows the exact atomic knowledge binding on the selected question', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { attachTo: document.body, props: { courseId: 'course-1' } })
    await flushPromises()
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    expect(wrapper.get('[data-testid="question-knowledge-binding"]').text()).toContain('栈的后进先出规则')
    expect(wrapper.get('[data-testid="question-knowledge-binding"]').text()).toContain('已绑定')
    wrapper.unmount()
  })

  it('loads binding automation even while the knowledge settings are collapsed', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'course-1' } })
    await flushPromises()
    expect(wrapper.get('.question-settings-binding').attributes('open')).toBeUndefined()
    expect(get.mock.calls.some(([url]) => url.endsWith('/question-bank/knowledge-bindings'))).toBe(true)
    wrapper.unmount()
  })

  it.each([
    ['invalid_evidence', '匹配依据未能定位到题面原文'],
    ['matching_unavailable', '自动匹配服务暂不可用，题目已保留'],
  ])('explains a pending binding instead of hiding the cause: %s', async (reason, expected) => {
    const read = get.getMockImplementation()!
    get.mockImplementation(async (...args) => {
      const response = await read(...args)
      if (response.data?.items?.[0]) Object.assign(response.data.items[0], {
        knowledge_binding_status: 'pending', knowledge_points: [], knowledge_binding_review_reason: reason,
      })
      return response
    })
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'course-1' } })
    await flushPromises()
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    expect(wrapper.get('[data-testid="question-knowledge-binding"]').text()).toContain(expected)
    wrapper.unmount()
  })

  it('opens a question as the full center page and returns to its list without changing settings', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { attachTo: document.body, props: { courseId: 'course-1' } })
    await flushPromises()
    const middle = wrapper.get('.question-bank-workspace-main')
    expect(middle.find('.question-reader').exists()).toBe(false)
    expect(middle.find('[data-testid="question-search-input"]').exists()).toBe(false)
    expect(middle.find('[data-testid="question-status-filter"]').exists()).toBe(false)
    expect(middle.find('.question-index__toolbar').exists()).toBe(false)
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    expect(middle.find('.question-index').exists()).toBe(false)
    expect(middle.get('.question-reader').text()).toContain('给定材料，完成跨章节分析并检查结论。')
    expect(wrapper.get('[data-testid="question-settings-pane"]').isVisible()).toBe(true)
    await middle.get('[data-testid="back-to-question-list"]').trigger('click')
    expect(middle.find('.question-reader').exists()).toBe(false)
    expect(middle.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
    expect(document.activeElement).toBe(middle.get('[data-testid="toggle-question-details"]').element)
    expect(post).not.toHaveBeenCalled()
    expect(runQuestionBankRebuild).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not show an empty bank while its first read is pending', async () => {
    let resolveRead!: (response: any) => void
    get.mockImplementationOnce(() => new Promise(resolve => { resolveRead = resolve }))
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'course-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('正在读取题库')
    expect(wrapper.find('.question-bank-empty-state').exists()).toBe(false)
    resolveRead({ data: { items: [] } })
    await flushPromises()
    expect(wrapper.find('.question-bank-empty-state').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows read failure with retry without claiming the bank is empty', async () => {
    get.mockRejectedValueOnce(new Error('网络连接失败'))
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'course-1' } })
    await flushPromises()
    const error = wrapper.get('.question-bank-panel__state--error')
    expect(wrapper.find('.question-bank-empty-state').exists()).toBe(false)
    await error.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.question-bank-panel__state--error').exists()).toBe(false)
    expect(wrapper.find('.question-browser').exists()).toBe(true)
    wrapper.unmount()
  })

  it('submits per-lecture additions while preserving existing questions and bounds the count', async () => {
    const wrapper=mount(QuestionBankReviewPanel,{props:{courseId:'course-1',initialWorkspaceMode:'generate',initialNodeIds:['node-1']}})
    await flushPromises()
    await wrapper.get('[data-testid="questions-per-lesson"]').setValue('5')
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()
    expect(runQuestionBankRebuild).toHaveBeenCalledWith('course-1',expect.objectContaining({
      questions_per_lesson:5,append_only:true,mode:'incremental',resume_existing:true,
    }),expect.any(Object))
    await wrapper.get('.question-quantity-mode input[value="false"]').setValue(true)
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()
    expect(runQuestionBankRebuild).toHaveBeenLastCalledWith('course-1',expect.objectContaining({
      scope:'nodes',node_ids:['node-1'],questions_per_lesson:5,append_only:false,
    }),expect.any(Object))
    await wrapper.get('[data-testid="questions-per-lesson"]').setValue('0')
    expect(wrapper.get('[data-testid="generate-question-bank"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="questions-per-lesson"]').setValue('21')
    expect(wrapper.get('[data-testid="generate-question-bank"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('用同一个课程题库外壳承载管理、导入和 AI 生成任务', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1' },
    })
    await flushPromises()

    expect(wrapper.get('.question-bank-page-heading').text()).toContain('课程题库')
    expect(wrapper.get('.question-bank-quality-trigger').text()).toContain('1 道待审核')
    expect(wrapper.get('.question-bank-page-heading').text()).toContain('导入题目文件')
    expect(wrapper.find('.question-bank-workspace-header').exists()).toBe(false)
    expect(wrapper.find('.question-bank-workspace-main').exists()).toBe(true)
    expect(wrapper.get('[data-testid="question-bank-generation-sources"]').attributes('data-variant')).toBe('question-bank')
    expect(wrapper.get('.question-bank-workspace-side').text()).toContain('真题资料')

    await wrapper.get('.question-bank-import-action').trigger('click')
    expect(wrapper.get('.question-bank-page-heading').text()).toContain('导入与校对')
    expect(wrapper.find('[data-testid="question-import-workspace"]').exists()).toBe(true)
    expect(wrapper.get('.question-bank-workspace-side').text()).toContain('真题资料')

    await wrapper.get('.question-bank-back').trigger('click')
    await wrapper.get('.question-bank-ai-action').trigger('click')
    expect(wrapper.get('.question-bank-page-heading').text()).toContain('AI 生成题目')
    expect(wrapper.find('[data-testid="question-generation-studio"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="question-bank-generation-sources"]').text()).toBe('真题资料')
    await wrapper.get('.question-generation-studio__ai').trigger('click')
    expect(wrapper.emitted('open-ai')).toHaveLength(1)
  })

  it('shows why web retrieval fell back to local question sources', async () => {
    get.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-timeout',
        coverage: {},
        review_queue: {},
        generation_summary: {},
        assessment_profile: {},
        assessment_objectives: [],
        chapter_rebuild: {},
        items: [],
        web_enrichment: {
          status: 'failed_fallback_local',
          source_count: 0,
          error_codes: ['timeout'],
        },
      },
    })

    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-timeout', initialWorkspaceMode: 'generate' },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="question-bank-retrieval-error"]').text())
      .toContain('联网搜索超时')
  })

  it('展示覆盖矩阵并允许浏览全部题目', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
    })
    await flushPromises()

    expect(get).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank',
      { silentError: true },
    )
    expect(wrapper.text()).toContain('4 / 4')
    expect(wrapper.text()).toContain('已发布')
    expect(wrapper.text()).toContain('1 道题等待发布前复核')
    expect(wrapper.find('.question-index').exists()).toBe(true)
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
    expect(audit.text()).toContain('生成与质量检查')
    expect(audit.text()).toContain('life_science.case_analysis.v1')
    expect(audit.text()).toContain('修复 1 次')
    expect(audit.text()).toContain('MATERIAL_BINDING_INVALID')
    expect(audit.text()).toContain('重复 86%')
    expect(audit.text()).toContain('item-history-1')
  })

  it('keeps generation controls in the right pane while browsing and preserves settings when collapsed', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { attachTo: document.body, props: { courseId: 'course-1' } })
    await flushPromises()
    const side = wrapper.get('[data-testid="question-settings-pane"]')
    expect(side.find('[data-testid="question-generation-studio"]').exists()).toBe(true)
    expect(wrapper.get('.question-bank-workspace-main').find('[data-testid="question-generation-studio"]').exists()).toBe(false)
    await side.get('[data-testid="questions-per-lesson"]').setValue('5')
    await side.get('[data-testid="collapse-question-settings"]').trigger('click')
    expect(side.isVisible()).toBe(false)
    await wrapper.get('[data-testid="expand-question-settings"]').trigger('click')
    expect(wrapper.get('[data-testid="question-settings-pane"]').isVisible()).toBe(true)
    expect((side.get('[data-testid="questions-per-lesson"]').element as HTMLInputElement).value).toBe('5')
    expect(post).not.toHaveBeenCalled()
    expect(runQuestionBankRebuild).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps empty lectures available in the left rail without starting generation on navigation', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'course-1', chapterOptions: [
      { node_id: 'node-1', number: 1, title: '已有题的讲次' },
      { node_id: 'empty-lesson', number: 2, title: '还没有题的讲次' },
    ] } })
    await flushPromises()
    const rail = wrapper.get('[data-testid="question-lesson-rail"]')
    await rail.get('[data-testid="question-chapter-empty-lesson"]').trigger('click')
    expect(wrapper.get('.question-bank-workspace-main').text()).toContain('没有符合条件的题目')
    expect(rail.get('[data-testid="question-chapter-empty-lesson"]').attributes('aria-current')).toBe('page')
    expect(runQuestionBankRebuild).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="question-settings-pane"]').find('[data-testid="generate-question-bank"]').exists()).toBe(true)
  })

  it('按讲次分层浏览题目并只显示当前讲次题目', async () => {
    get.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-by-lesson',
        assessment_profile: {},
        assessment_objectives: [],
        coverage: {},
        review_queue: {},
        web_enrichment: {},
        chapter_rebuild: {},
        items: [
          { item_id: 'l1-q1', revision_id: 'l1-r1', prompt: '第一讲第一题', assessment_role: 'concept', lifecycle_status: 'approved', risk_flags: [], node_id: 'lesson-1-section-1', quality_report: { passed: true } },
          { item_id: 'l1-q2', revision_id: 'l1-r2', prompt: '第一讲第二题', assessment_role: 'practice', lifecycle_status: 'approved', risk_flags: [], node_id: 'lesson-1', quality_report: { passed: true } },
          { item_id: 'l2-q1', revision_id: 'l2-r1', prompt: '第二讲唯一题目', assessment_role: 'transfer', lifecycle_status: 'rejected', risk_flags: [], node_id: 'lesson-2', quality_report: { passed: false } },
          { item_id: 'legacy-q1', revision_id: 'legacy-r1', prompt: '历史导入题目', assessment_role: 'imported', lifecycle_status: 'approved', risk_flags: [], node_id: 'legacy-node', quality_report: { passed: true } },
        ],
      },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: {
        courseId: 'course-1',
        chapterOptions: [
          { node_id: 'lesson-1', number: 1, title: '游戏逻辑基础', node_ids: ['lesson-1', 'lesson-1-section-1'] },
          { node_id: 'lesson-2', number: 2, title: '状态机与存档' },
        ],
      },
    })
    await flushPromises()

    expect(wrapper.findAll('[data-testid="question-chapter-item"]')).toHaveLength(3)
    expect(wrapper.get('[data-testid="question-chapter-lesson-1"]').attributes('aria-current')).toBe('page')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('第一讲第二题')
    expect(wrapper.text()).not.toContain('第二讲唯一题目')

    await wrapper.findAll('[data-testid="toggle-question-details"]')[0]!.trigger('click')
    wrapper.get('.question-reader__scroll').element.scrollTop = 220
    await wrapper.get('[data-testid="question-chapter-lesson-2"]').trigger('click')
    expect(wrapper.find('.question-reader').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    expect(wrapper.get('.question-reader__scroll').element.scrollTop).toBe(0)

    expect(wrapper.get('[data-testid="question-chapter-lesson-2"]').attributes('aria-current')).toBe('page')
    expect(wrapper.text()).toContain('第二讲唯一题目')
    expect(wrapper.text()).not.toContain('第一讲第一题')
    expect(wrapper.get('.question-reader__header').text()).toContain('第 2 讲 · 状态机与存档')

    await wrapper.get('[data-testid="question-chapter-__unassigned__"]').trigger('click')
    expect(wrapper.text()).toContain('其他题目')
    expect(wrapper.text()).toContain('历史导入题目')
  })

  it('讲次节点无法覆盖任何题目时回退到全部题目列表', async () => {
    get.mockResolvedValueOnce({
      data: {
        bundle_revision_id: 'qbb-unmapped',
        assessment_profile: {},
        assessment_objectives: [],
        coverage: {},
        review_queue: {},
        web_enrichment: {},
        chapter_rebuild: {},
        items: [
          { item_id: 'old-q1', revision_id: 'old-r1', prompt: '旧课程第一题', assessment_role: 'legacy', lifecycle_status: 'approved', risk_flags: [], node_id: 'old-section-1', quality_report: { passed: true } },
          { item_id: 'old-q2', revision_id: 'old-r2', prompt: '旧课程第二题', assessment_role: 'legacy', lifecycle_status: 'approved', risk_flags: [], node_id: 'old-section-2', quality_report: { passed: true } },
        ],
      },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: {
        courseId: 'course-1',
        chapterOptions: [
          { node_id: 'new-lesson-1', number: 1, title: '新版第一讲' },
          { node_id: 'new-lesson-2', number: 2, title: '新版第二讲' },
        ],
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="question-lesson-rail"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('旧课程第一题')
    expect(wrapper.text()).toContain('旧课程第二题')
  })

  it('题目列表分页并在详情返回后保留原页码', async () => {
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
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
    })
    await flushPromises()

    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(10)
    expect(wrapper.text()).toContain('分页题目 01')
    expect(wrapper.text()).not.toContain('分页题目 11')
    expect(wrapper.get('[data-testid="question-pagination"]').text()).toContain(
      '第 1–10 题，共 23 题',
    )
    const detailToggles = wrapper.findAll(
      '[data-testid="toggle-question-details"]',
    )
    expect(detailToggles).toHaveLength(10)
    expect(wrapper.find('.question-reader').exists()).toBe(false)
    await detailToggles[1]!.trigger('click')
    expect(wrapper.find('.question-index').exists()).toBe(false)
    expect(wrapper.get('.question-reader').text()).toContain('分页题目 02')
    await wrapper.get('[data-testid="back-to-question-list"]').trigger('click')
    await wrapper.get('[data-testid="question-page-select"]').setValue('2')
    expect(wrapper.text()).toContain('分页题目 11')
    expect(wrapper.text()).not.toContain('分页题目 01')
    await wrapper.findAll('[data-testid="toggle-question-details"]')[1]!.trigger('click')
    expect(wrapper.get('.question-reader').text()).toContain('分页题目 12')
    await wrapper.get('[data-testid="back-to-question-list"]').trigger('click')
    expect((wrapper.get('[data-testid="question-page-select"]').element as HTMLSelectElement).value).toBe('2')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(10)
    await wrapper.get('[data-testid="question-page-select"]').setValue('3')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('分页题目 23')
    expect(wrapper.get('[data-testid="question-pagination"]').text()).toContain('第 21–23 题，共 23 题')

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
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
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
      '第 1–10 项，共 23 项',
    )

    await wrapper.get('[data-testid="objective-page-select"]').setValue('2')
    expect(wrapper.text()).toContain('已覆盖目标 11')
    expect(wrapper.text()).not.toContain('已覆盖目标 01')

    await wrapper.get('[data-testid="objective-page-select"]').setValue('3')
    expect(wrapper.findAll('[data-testid="objective-covered-row"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('已覆盖目标 23')
    expect(wrapper.get('[data-testid="objective-pagination"]').text()).toContain(
      '第 21–23 项，共 23 项',
    )
  })

  it('携带题库版本批准高风险题并保留在浏览列表', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
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
      { identityScope: 'teacher' },
    )
    expect(get.mock.calls.filter(([url]) => !url.endsWith('/knowledge-bindings'))).toHaveLength(2)
    await wrapper.get('[data-testid="back-to-question-list"]').trigger('click')
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
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('已发布')
    expect(wrapper.text()).toContain('已发布')
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
  })

  it('重新生成已发布题时保持原题生效并按题目修订异步重做', async () => {
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
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    await wrapper.get('[data-testid="rework-question"]').trigger('click')
    await flushPromises()

    expect(post).not.toHaveBeenCalled()
    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'items',
        node_ids: [],
        revision_ids: ['revision-published'],
        mode: 'incremental',
        retrieval_enabled: false,
        material_asset_ids: [],
        teacher_instruction: '',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
  })

  it('支持按节点异步重建并展示真实阶段', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
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
        retrieval_enabled: false,
        material_asset_ids: [],
        questions_per_lesson: 3,
        append_only: true,
        resume_existing: true,
        teacher_instruction: '',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
    expect(wrapper.text()).toContain('发布完成')
    expect(wrapper.text()).toContain('100%')
  })

  it('从课次入口按当前小节范围生成并保留同一正式题库', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: {
        courseId: 'course-1',
        initialWorkspaceMode: 'generate',
        initialNodeIds: ['section-1', 'section-2'],
        initialScopeLabel: '1. 内存管理',
      },
    })
    await flushPromises()
    wrapper.getComponent({ name: 'CourseReferenceTray' }).vm.$emit('update:modelValue', [{
      package_id: 'package-1', asset_id: 'asset-primary', material_asset_id: 'mat-primary', filename: '期末真题.pdf', relative_path: '', size_bytes: 100, role: 'question_source',
    }, {
      package_id: 'package-1', asset_id: 'asset-reference', material_asset_id: 'mat-reference', filename: '历年题库.docx', relative_path: '', size_bytes: 100, role: 'question_source',
    }])
    await flushPromises()

    expect(wrapper.get('[data-testid="question-generation-studio"]').text())
      .toContain('1. 内存管理')
    expect(wrapper.get('[data-testid="question-generation-studio"]').text())
      .not.toContain('覆盖 2 个小节')
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()

    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'nodes',
        node_ids: ['section-1', 'section-2'],
        mode: 'incremental',
        retrieval_enabled: false,
        material_asset_ids: ['mat-primary', 'mat-reference'],
        questions_per_lesson: 3,
        append_only: true,
        resume_existing: true,
        teacher_instruction: '',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
  })

  it('shows the actionable scope error beside the failed generation', async () => {
    runQuestionBankRebuild.mockRejectedValueOnce({
      isAxiosError: true,
      message: 'Request failed with status code 422',
      config: { method: 'post', url: '/api/courses/course-1/question-bank/rebuild' },
      response: { status: 422, data: { detail: { code: 'question_bank_rebuild_nodes_unknown' } } },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['L1-2'] },
    })
    await flushPromises()
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('重新选择')
    expect(wrapper.text()).toContain('题目生成未启动')
    expect(wrapper.text()).not.toContain('等待生成')
    expect(wrapper.text()).not.toContain('Request failed with status code 422')
  })

  it('uses the selected lecture content and freezes AI candidates before later navigation', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { props: {
      courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['L2-1-1'],
      chapterOptions: [
        { node_id: 'L1-1', node_ids: ['L2-1-1'], number: 1, title: '第一讲' },
        { node_id: 'L1-2', node_ids: ['L2-2-1', 'L2-2-2'], number: 2, title: '第二讲' },
        { node_id: 'L1-3', node_ids: ['L2-3-1'], number: 3, title: '第三讲' },
      ],
    } })
    await flushPromises()
    expect(wrapper.find('[data-testid="question-scope-course"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="question-scope-range"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="question-scope-custom"]').exists()).toBe(false)
    await wrapper.get('[data-testid="question-chapter-L1-2"]').trigger('click')
    expect(wrapper.get('[data-testid="question-generation-target"]').text()).toContain('第 2 讲 · 第二讲')
    expect(runQuestionBankRebuild).not.toHaveBeenCalled()
    const candidate = await (wrapper.vm as any).requestAiCandidate('按当前讲次生成')
    expect(candidate).toMatchObject({ scope: 'nodes', node_ids: ['L2-2-1', 'L2-2-2'] })
    await wrapper.get('[data-testid="question-chapter-L1-3"]').trigger('click')
    expect(candidate.node_ids).toEqual(['L2-2-1', 'L2-2-2'])
    expect(wrapper.get('.question-ai-candidate').text()).toContain('第 2 讲 · 第二讲')
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()
    expect(runQuestionBankRebuild).toHaveBeenCalledWith('course-1', expect.objectContaining({
      scope: 'nodes', node_ids: ['L2-3-1'], questions_per_lesson: 3,
    }), expect.any(Object))
  })

  it.each([false, true])('reads published partial results when generation fails (recovery=%s)', async (recover) => {
    let bankReads = 0
    get.mockImplementation(async (url: string) => {
      if (!url.endsWith('/question-bank')) return { data: {} }
      bankReads += 1
      return { data: { items: bankReads > 1 ? [{
        item_id: 'partial-one', revision_id: 'partial-revision', node_id: 'section-2',
        prompt: '已通过校验并保存的均摊分析题', lifecycle_status: 'approved',
        assessment_role: 'practice', risk_flags: [], quality_report: { passed: true },
      }] : [] } }
    })
    const failure = Object.assign(new Error('部分题目未通过质量检查'), { job: {
      job_id: 'partial-job', status: 'failed', progress: 59, status_url: '/jobs/partial-job',
      stage_details: { chapter_status: 'partial', settled_practice_levels: ['concept_check'] },
    } })
    if (recover) resumeQuestionBankRebuild.mockRejectedValueOnce(failure)
    else runQuestionBankRebuild.mockRejectedValueOnce(failure)
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['section-2'] },
    })
    await flushPromises()
    if (!recover) {
      await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
      await flushPromises()
    }
    expect(wrapper.text()).toContain('已通过校验并保存的均摊分析题')
    expect(wrapper.text()).toContain('题目生成未完成，已发布题目继续有效')
    expect(wrapper.text()).not.toContain('没有符合条件的题目')
  })

  it.each(['zh', 'en'] as const)('shows concise lecture settings in %s', async locale => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => locale === 'zh' ? zhMessages : enMessages })))
    await setLocale(locale)
    const wrapper = mount(QuestionBankReviewPanel, { props: {
      courseId: 'course-1', initialNodeIds: ['lesson-2'],
      chapterOptions: [{ node_id: 'lesson-2', number: 2, title: '第2讲 栈、队列与递归' }],
    } })
    await flushPromises()
    const settings = wrapper.get('[data-testid="question-settings-pane"]')
    expect(wrapper.get('[data-testid="question-generation-target"]').text()).toContain(
      locale === 'zh' ? '第 2 讲 · 栈、队列与递归' : 'Lesson 2 · 栈、队列与递归',
    )
    expect(settings.text()).toContain(locale === 'zh' ? '难度与题型根据本讲内容自动编排' : 'Difficulty and question types follow this lecture’s content')
    expect(settings.text()).not.toContain(locale === 'zh' ? '连续讲次' : 'Chapter range')
    expect(settings.find('input[type="checkbox"][disabled]').exists()).toBe(false)
  })

  it('follows the selected empty lecture and subsequent entry lecture changes', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { props: {
      courseId: 'course-1', initialNodeIds: ['lesson-1'], chapterOptions: [
        { node_id: 'lesson-1', number: 1, title: '课程导论' },
        { node_id: 'lesson-2', number: 2, title: '核心概念' },
        { node_id: 'lesson-3', number: 3, title: '综合应用' },
      ],
    } })
    await flushPromises()
    await wrapper.get('[data-testid="question-chapter-lesson-2"]').trigger('click')
    await wrapper.get('[data-testid="questions-per-lesson"]').setValue('5')
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()
    expect(runQuestionBankRebuild).toHaveBeenLastCalledWith('course-1', expect.objectContaining({
      scope: 'nodes', node_ids: ['lesson-2'], questions_per_lesson: 5,
    }), expect.any(Object))
    await wrapper.setProps({ initialNodeIds: ['lesson-3'] })
    expect(wrapper.get('[data-testid="question-generation-target"]').text()).toContain('第 3 讲 · 综合应用')
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()
    expect(runQuestionBankRebuild).toHaveBeenLastCalledWith('course-1', expect.objectContaining({
      scope: 'nodes', node_ids: ['lesson-3'], questions_per_lesson: 5,
    }), expect.any(Object))
  })

  it('disables generation and AI candidates without a lecture or for unassigned questions', async () => {
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'course-1' } })
    await flushPromises()
    expect(wrapper.get('[data-testid="generate-question-bank"]').attributes('disabled')).toBeDefined()
    expect(await (wrapper.vm as any).requestAiCandidate('出题')).toBeNull()
    await wrapper.setProps({ chapterOptions: [{ node_id: 'lesson-1', title: '课程导论' }] })
    await wrapper.get('[data-testid="question-chapter-__unassigned__"]').trigger('click')
    expect(wrapper.get('[data-testid="generate-question-bank"]').attributes('disabled')).toBeDefined()
    expect(await (wrapper.vm as any).requestAiCandidate('出题')).toBeNull()
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    expect(runQuestionBankRebuild).not.toHaveBeenCalled()
  })

  it('通过智能出题工作台生成当前讲次题目并展示真实进度', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
    })
    await flushPromises()

    const button = wrapper.get(
      '[data-testid="generate-question-bank"]',
    )
    expect(button.text()).toContain('开始生成')
    await button.trigger('click')
    await flushPromises()

    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'nodes',
        node_ids: ['node-1'],
        mode: 'incremental',
        resume_existing: true,
        retrieval_enabled: false,
        material_asset_ids: [],
        questions_per_lesson: 3,
        append_only: true,
        teacher_instruction: '',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
    const progress = wrapper.get('[data-testid="question-bank-progress"]')
    expect(progress.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('100')
    expect(progress.text()).toContain('课程题目已重新生成并发布')
    expect(progress.text()).toContain('100%')
  })

  it('题库缺失时重新整理而不是重复读取', async () => {
    get.mockRejectedValueOnce({
      response: { status: 404 },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
    })
    await flushPromises()

    const studio = wrapper.get('[data-testid="question-generation-studio"]')
    expect(studio.text()).not.toContain('首次生成后，合格题目会自动进入课程题库')
    expect(studio.text()).not.toContain('选择范围，系统会结合课程资料和已有题目自动编排')
    expect(wrapper.find('.question-bank-panel__state--error').exists()).toBe(false)
    expect(wrapper.find('.question-quality-details').exists()).toBe(false)
    expect(wrapper.find('.question-browser').exists()).toBe(false)

    const button = wrapper.get(
      '[data-testid="generate-question-bank"]',
    )
    await button.trigger('click')
    await flushPromises()

    expect(runQuestionBankRebuild).toHaveBeenCalledWith(
      'course-1',
      {
        request_id: expect.any(String),
        scope: 'nodes',
        node_ids: ['node-1'],
        mode: 'incremental',
        resume_existing: true,
        retrieval_enabled: false,
        material_asset_ids: [],
        questions_per_lesson: 3,
        append_only: true,
        teacher_instruction: '',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
    expect(get.mock.calls.filter(([url]) => !url.endsWith('/knowledge-bindings'))).toHaveLength(3)
  })

  it('does not offer a whole-course continuation while generating the current lecture', async () => {
    get.mockResolvedValueOnce({ data: {
      bundle_revision_id: 'qbb-partial', items: [],
      chapter_rebuild: { status: 'partial', total_chapters: 63, completed_chapters: 9, remaining_chapters: 54, can_resume: true },
    } })
    const wrapper = mount(QuestionBankReviewPanel, { props: {
      courseId: 'course-1', initialWorkspaceMode: 'generate',
      chapterOptions: [{ node_id: 'lesson-2', number: 2, title: '核心概念' }],
    } })
    await flushPromises()
    expect(wrapper.find('[data-testid="continue-course-question-bank"]').exists()).toBe(false)
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()
    expect(runQuestionBankRebuild).toHaveBeenCalledWith('course-1', expect.objectContaining({
      scope: 'nodes', node_ids: ['lesson-2'], mode: 'incremental',
    }), expect.any(Object))
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
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
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
    const progress = wrapper.get('[data-testid="question-bank-progress"]')
    expect(progress.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('52')
    expect(progress.text()).toContain(
      '正在生成第 48/189 道候选题',
    )
    expect(progress.text()).toContain(
      '讲次发布 15/63 · 当前 4.5 装饰器（2/3）',
    )
    expect(
      wrapper.get('[data-testid="generate-question-bank"]')
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
          error: { retryable: true },
          stage_details: {
            failed_chapters: [{
              node_id: 'node-failed',
              node_name: '失败章节',
            }],
          },
        },
      },
    )
    runQuestionBankRebuild.mockRejectedValueOnce(failure)
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
    })
    await flushPromises()

    await wrapper
      .get('[data-testid="generate-question-bank"]')
      .trigger('click')
    await flushPromises()

    expect(wrapper.findAll(
      '[data-testid="question-review-item"]',
    )).toHaveLength(1)
    expect(wrapper.text()).toContain(
      '给定材料，完成跨章节分析并检查结论。',
    )
    const progress = wrapper.get('[data-testid="question-bank-progress"]')
    expect(progress.classes()).toContain('question-bank-progress--compact')
    expect(progress.get('[data-testid="question-progress-details"]').element.tagName).toBe('DETAILS')
    expect(progress.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('48')
    expect(progress.text()).toContain(
      '题目生成未完成，已发布题目继续有效',
    )
    expect(progress.text()).toContain('模型服务暂时不可用')
    runQuestionBankRebuild.mockResolvedValueOnce({
      job_id: 'job-retry',
      status: 'waiting_review',
      progress: 100,
      status_url: '/jobs/job-retry',
    })
    await wrapper
      .get('[data-testid="retry-failed-question-bank-chapters"]')
      .trigger('click')
    await flushPromises()
    expect(runQuestionBankRebuild).toHaveBeenLastCalledWith(
      'course-1',
      expect.objectContaining({
        scope: 'nodes',
        node_ids: ['node-failed'],
        mode: 'incremental',
      }),
      expect.any(Object),
    )
  })

  it.each([
    ['zh', '题目已生成，待事实复核'],
    ['en', 'Questions generated; factual verification pending'],
  ] as const)('事实待复核显示为完成生成而非失败：%s', async (locale, expected) => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => locale === 'zh' ? zhMessages : enMessages })))
    await setLocale(locale)
    const read = get.getMockImplementation()!
    get.mockImplementation(async (...args) => {
      const response = await read(...args)
      if (response.data?.items?.[0]) response.data.items[0].risk_flags = ['facts_unverified']
      return response
    })
    runQuestionBankRebuild.mockImplementationOnce(async (_course, _body, options) => {
      const job = { job_id: 'fact-review', status: 'waiting_review', progress: 100, status_url: '/jobs/fact-review', error: null }
      options.onUpdate(job)
      return job
    })
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] } })
    await flushPromises()
    await wrapper.get('[data-testid="generate-question-bank"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="question-bank-progress"]').text()).toContain(expected)
    expect(wrapper.find('[data-testid="retry-failed-question-bank-chapters"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="question-review-item"]')).toHaveLength(1)
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    expect(wrapper.text()).toContain(locale === 'zh' ? '结构检查通过，事实待复核' : 'Structure checked; factual verification pending')
  })

  it('教师可按需读取私有答案与独立验证差异', async () => {
    const wrapper = mount(QuestionBankReviewPanel, {
      props: { courseId: 'course-1', initialWorkspaceMode: 'generate', initialNodeIds: ['node-1'] },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="question-fact-evidence"]').exists()).toBe(false)

    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    await wrapper.get('[data-testid="load-question-solution"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank/items/revision-1/solution',
      { identityScope: 'teacher' },
    )
    expect(wrapper.get('[data-testid="question-fact-evidence"]').text()).toContain('每次扩容将容量翻倍。')
    expect(wrapper.get('[data-testid="question-fact-evidence"]').text()).toContain('待事实复核')
    expect(wrapper.text()).toContain('应包含跨章节证据链')
    expect(wrapper.text()).toContain('先定位章节结论')
    expect(wrapper.text()).toContain('用第二章证据验证结论')
    expect(wrapper.text()).toContain('只罗列结论')
    expect(wrapper.text()).toContain('独立求解结果')
  })

  it('AI 候选冻结当前范围并在教师采用后创建正式任务', async () => {
    post.mockResolvedValueOnce({
      data: {
        job_id: 'job-ai',
        status: 'queued',
        progress: 0,
        current_stage: 'queued',
      },
    })
    const wrapper = mount(QuestionBankReviewPanel, {
      props: {
        courseId: 'course-1',
        initialWorkspaceMode: 'generate',
        initialNodeIds: ['section-1'],
      },
    })
    await flushPromises()
    wrapper.getComponent({ name: 'CourseReferenceTray' }).vm.$emit('update:modelValue', [{
      package_id: 'package-1', asset_id: 'asset-1', material_asset_id: 'material-1', filename: '期末真题.pdf', relative_path: '', size_bytes: 100, role: 'question_source',
    }])
    await flushPromises()

    const candidate = await (wrapper.vm as any).requestAiCandidate('增加一道应用题')
    expect(candidate).toMatchObject({
      base_bundle_revision_id: 'qbb-1',
      scope: 'nodes',
      node_ids: ['section-1'],
      material_asset_ids: ['material-1'],
      teacher_instruction: '增加一道应用题',
    })
    expect(post).not.toHaveBeenCalled()

    await (wrapper.vm as any).resolveAiCandidate(true)
    expect(post).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank/rebuild',
      expect.objectContaining({
        scope: 'nodes',
        node_ids: ['section-1'],
        material_asset_ids: ['material-1'],
        teacher_instruction: '增加一道应用题',
      }),
      { identityScope: 'teacher' },
    )
  })
})

describe('question bank course switching', () => {
  beforeEach(() => {
    get.mockReset(); post.mockReset(); resumeQuestionBankRebuild.mockReset(); runQuestionBankRebuild.mockReset()
    resumeQuestionBankRebuild.mockResolvedValue(null)
  })

  it('does not restore old questions when an earlier course read finishes last', async () => {
    let resolveOld!: (value: unknown) => void
    get.mockImplementation((url: string) => url === '/api/courses/old/question-bank'
      ? new Promise(resolve => { resolveOld = resolve })
      : Promise.resolve({ data: { items: [], papers: [] } }))
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'old' } })
    await wrapper.setProps({ courseId: 'new' })
    await flushPromises()
    resolveOld({ data: { items: [{ revision_id: 'old', prompt: 'OLD COURSE QUESTION', lifecycle_status: 'approved' }] } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('OLD COURSE QUESTION')
    wrapper.unmount()
  })

  it('detaches a single-question rework and rejects late updates on course switch', async () => {
    get.mockImplementation((url: string) => Promise.resolve({ data: {
      items: url.includes('/old/') ? [{ revision_id: 'old-item', prompt: 'old question', lifecycle_status: 'approved', quality_report: { passed: true } }] : [], papers: [],
    } }))
    let resolveJob!: (value: unknown) => void
    runQuestionBankRebuild.mockReturnValue(new Promise(resolve => { resolveJob = resolve }))
    const wrapper = mount(QuestionBankReviewPanel, { props: { courseId: 'old', initialWorkspaceMode: 'generate' } })
    await flushPromises()
    await wrapper.get('[data-testid="toggle-question-details"]').trigger('click')
    await wrapper.get('[data-testid="rework-question"]').trigger('click')
    const options = runQuestionBankRebuild.mock.calls[0]![2]
    expect(options.signal.aborted).toBe(false)
    await wrapper.setProps({ courseId: 'new' })
    await flushPromises()
    expect(options.signal.aborted).toBe(true)
    options.onUpdate({ job_id: 'old-job', status: 'running', progress: 70, message: 'OLD JOB PROGRESS' })
    resolveJob({ status: 'completed' })
    await flushPromises()
    expect(wrapper.text()).not.toContain('OLD JOB PROGRESS')
    expect(wrapper.emitted('updated')).toBeUndefined()
    wrapper.unmount()
  })
})
