import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SlideDeckWorkbench from '@/components/SlideDeckWorkbench.vue'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  withApiBase: (path: string) => path,
  learnerIdentityHeaders: (initial: HeadersInit = {}) => new Headers(initial),
}))

const slides = [
  {
    unit_id: 'slide:title', layout: 'cover', slide_purpose: 'orientation', eyebrow: '课程演示',
    title: '数据结构', subtitle: '原理与 AI 应用', key_message: '从问题出发组织学习。', blocks: [],
    source_keys: ['course_title'], quality: { passed: true, character_count: 28 },
  },
  {
    unit_id: 'slide:section-a', layout: 'concept', slide_purpose: 'concept', eyebrow: '核心概念',
    title: '向量的定义', key_message: '向量同时具有大小和方向。', section_id: 'section-a',
    source_block_ids: ['block-a'], knowledge_refs: ['kp-vector'], knowledge_labels: ['向量定义'],
    ability_refs: ['skill-vector'], ability_labels: ['识别向量'], misconception_refs: ['mis-vector'],
    blocks: [{ block_id: 'block-a', type: 'bullets', title: '判断线索', items: ['大小', '方向'], metadata: {} }],
    quality: { passed: true, character_count: 42 },
  },
]

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

describe('SlideDeckWorkbench', () => {
  it('uses the same structured slide spec for thumbnails, canvas, and source inspection', async () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: '数据结构', slides,
        staleUnitIds: [], building: false, progress: 100, stage: 'complete', error: '',
        quality: { passed: true, score: 1 },
      },
    })

    expect(wrapper.findAll('.slide-thumbnails > button')).toHaveLength(2)
    expect(wrapper.find('.slide-canvas').attributes('data-layout')).toBe('cover')

    await wrapper.findAll('.slide-thumbnails > button')[1]!.trigger('click')
    expect(wrapper.find('.slide-canvas').attributes('data-layout')).toBe('concept')
    expect(wrapper.find('.slide-canvas').text()).toContain('向量同时具有大小和方向')
    expect(wrapper.find('.slide-inspector__refs').text()).toContain('向量定义')
    expect(wrapper.find('.slide-inspector__refs').text()).toContain('识别向量')

    await wrapper.find('.slide-workbench__commands button').trigger('click')
    const event = wrapper.emitted('ask-ai')?.[0]?.[0] as Record<string, any>
    expect(event.nodeId).toBe('section-a')
    expect(event.anchor.slide_unit_id).toBe('slide:section-a')
  })
})
