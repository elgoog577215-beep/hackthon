import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UploadedPptReviewWorkspace from '@/components/UploadedPptReviewWorkspace.vue'
import http from '@/utils/http'

const review = {
  review_id: 'review-1',
  source_filename: '老师原稿.pptx',
  source_state: 'current',
  status: 'reviewing',
  revision_id: 'revision-1',
  slides: [{
    slide_id: 'slide-1', slide_number: 1, title: '旧标题', content_hash: 'hash-1',
    blocks: [
      { block_id: 'block-title', shape_index: 0, kind: 'title', text: '旧标题', original_text: '旧标题', editable: true },
      { block_id: 'block-body', shape_index: 1, kind: 'text', text: '旧内容', original_text: '旧内容', editable: true },
    ],
  }],
  report: {
    sources: [
      { kind: 'lesson_plan', label: '已确认教案', revision_id: 'plan-1', status: 'confirmed' },
      { kind: 'script', label: '已确认讲稿', revision_id: 'script-1', status: 'confirmed' },
    ],
    findings: [{
      finding_id: 'finding-1', code: 'slide_alignment_unresolved', title: '与已确认教学内容的对应关系不明确',
      detail: '请确认该页是补充材料还是需要调整。', severity: 'suggestion', confidence: 'high',
      slide_id: 'slide-1', slide_number: 1, status: 'open',
    }],
    summary: { slide_count: 1, finding_count: 1, high_confidence_count: 1 },
  },
  ai_candidates: [],
}

describe('uploaded PPT review workspace', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('显示客观对照依据，且手动修改以新修订保存', async () => {
    const sourceSlide = review.slides[0]!
    const sourceTitle = sourceSlide.blocks[0]!
    const sourceBody = sourceSlide.blocks[1]!
    vi.spyOn(http, 'get').mockResolvedValue({ data: { review } })
    const patch = vi.spyOn(http, 'patch').mockResolvedValue({
      data: { review: { ...review, revision_id: 'revision-2', slides: [{ ...sourceSlide, title: '新标题', blocks: [{ ...sourceTitle, text: '新标题' }, sourceBody] }] } },
    })
    const wrapper = mount(UploadedPptReviewWorkspace, {
      props: { courseId: 'course-1', courseTitle: 'C 语言', lessonId: 'L1-1', lessonTitle: '第一讲', canGenerate: true },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('已确认教案')
    expect(wrapper.text()).toContain('已确认讲稿')
    expect(wrapper.text()).toContain('高置信建议')
    expect(wrapper.text()).not.toContain('100%')

    await wrapper.get('.ppt-slide-workarea>header button').trigger('click')
    const title = wrapper.findAll('textarea')[0]!
    await title.setValue('新标题')
    await wrapper.get('.ppt-slide-canvas .save').trigger('click')
    await flushPromises()

    expect(patch).toHaveBeenCalledWith(
      expect.stringContaining('/slides/slide-1'),
      expect.objectContaining({ base_revision_id: 'revision-1' }),
      expect.any(Object),
    )
    expect(wrapper.get('.ppt-slide-canvas h3').text()).toBe('新标题')
  })
})
