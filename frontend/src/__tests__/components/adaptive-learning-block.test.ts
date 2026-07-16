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

  it('动态演示不可用时仍展示完整静态步骤', () => {
    const animation: AdaptiveBlock = {
      ...block,
      adaptive_block_id: 'animation-1',
      kind: 'animation',
      role: 'accepted_personal_course_growth',
      payload: {
        ...block.payload,
        body: '观察两个线性变换依次作用。',
        steps: [
          { index: 1, label: '先应用右侧变换' },
          { index: 2, label: '再应用左侧变换' },
        ],
      },
    }

    const wrapper = mount(AdaptiveLearningBlock, { props: { block: animation } })

    expect(wrapper.attributes('data-kind')).toBe('animation')
    expect(wrapper.findAll('.adaptive-block__steps li')).toHaveLength(2)
    expect(wrapper.find('.adaptive-block__fallback').text()).toContain('静态分步演示')
  })

  it('正式 AnimationSpec 在正文原位提供可播放关键帧', async () => {
    const animation: AdaptiveBlock = {
      ...block,
      adaptive_block_id: 'animation-spec-1',
      kind: 'animation',
      role: 'accepted_personal_course_growth',
      payload: {
        ...block.payload,
        animation_spec: {
          schema_version: 'animation_spec_v1',
          animation_id: 'ans-1',
          title: '矩阵复合：分步变换演示',
          scene: { kind: 'state_transition', renderer: 'step_timeline_v1' },
          object_bindings: [{ object_id: 'block-1' }],
          knowledge_refs: ['matrix-composition'],
          keyframes: [
            { index: 1, label: '确定输入', state: { description: '标出起始对象' }, transformations: ['highlight'], duration_ms: 500, pause_after: true },
            { index: 2, label: '观察结果', state: { description: '连接中间状态和结论' }, transformations: ['connect'], duration_ms: 500, pause_after: true },
          ],
          fallback_frames: [{ index: 1, label: '确定输入' }, { index: 2, label: '观察结果' }],
          accessibility_text: '依次展示输入和结果。',
        },
      },
    }

    const wrapper = mount(AdaptiveLearningBlock, { props: { block: animation } })

    expect(wrapper.find('.structured-animation').exists()).toBe(true)
    expect(wrapper.find('.structured-animation').text()).toContain('矩阵复合：分步变换演示')
    await wrapper.find('.structured-animation__timeline button:nth-child(2)').trigger('click')
    expect(wrapper.find('.structured-animation__frame').text()).toContain('观察结果')
    expect(wrapper.find('.adaptive-block__fallback').text()).toContain('关键帧')
  })
})
