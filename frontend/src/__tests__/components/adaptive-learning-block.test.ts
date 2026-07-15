import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMock }))

import AdaptiveLearningBlock from '@/components/AdaptiveLearningBlock.vue'
import { useCourseStore } from '@/stores/course'
import { useLearningProgressStore, type AdaptiveLearningBlock as AdaptiveBlock } from '@/stores/learningProgress'

const block: AdaptiveBlock = {
  adaptive_block_id: 'ab1',
  anchor: { node_id: 'n1', content_block_id: 'b1', placement: 'after_block' },
  kind: 'counterexample',
  role: 'low_risk_support',
  payload: {
    body: '先分别检查大小和方向。',
    contrast: '比较同向与反向向量。',
    prompt: '',
    objective: '澄清向量方向',
  },
  reason_code: 'confirmed_gap_under_remediation',
  evidence_refs: ['a1', 'a2'],
  status: 'active',
  expires_at: '2099-01-01T00:00:00Z',
  feedback: { value: 'unrated', options: ['helpful', 'not_helpful', 'dismissed'] },
}

describe('AdaptiveLearningBlock', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    httpMock.post.mockReset().mockResolvedValue({ data: { status: 'recorded' } })
    useCourseStore().currentCourseId = 'c1'
    useLearningProgressStore().runtime = {
      adaptive_blocks: [{ ...block }],
    } as any
  })

  it('记录反馈并允许从正文跳过临时支持块', async () => {
    const wrapper = mount(AdaptiveLearningBlock, { props: { block } })

    await wrapper.find('button[title="有帮助"]').trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/c1/learning-runtime/adaptive-blocks/feedback',
      expect.objectContaining({ adaptive_block_id: 'ab1', feedback: 'helpful' }),
    )

    await wrapper.find('button[title="跳过这条支持"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.adaptive-block').exists()).toBe(false)
    expect(useLearningProgressStore().runtime?.adaptive_blocks).toEqual([])
  })
})
