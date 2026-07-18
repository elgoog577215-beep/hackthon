import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QuestionBankReviewPanel from '@/components/QuestionBankReviewPanel.vue'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get, post } }))

describe('QuestionBankReviewPanel', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    get.mockResolvedValue({
      data: {
        bundle_revision_id: 'qbb-1',
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
        }],
      },
    })
    post.mockResolvedValue({
      data: {
        bundle_revision_id: 'qbb-2',
        review_queue: { blocking_count: 0 },
        item: { revision_id: 'revision-1', lifecycle_status: 'approved' },
      },
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
})
