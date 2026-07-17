import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SlideDeckWorkbench from '@/components/SlideDeckWorkbench.vue'
import { useTeachingRepresentationsStore } from '@/stores/teachingRepresentations'

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

  it('shows semantic impact, confirms in place, and reports changed versus reused units', async () => {
    const proposal = {
      proposal_id: 'proposal-objective',
      course_id: 'course-1',
      scope: 'section',
      target_block_ids: ['section-a'],
      source: 'representation_semantic',
      status: 'pending',
      created_at: '2026-07-17T00:00:00Z',
      items: [{
        item_id: 'objective-item',
        block_id: 'section-a',
        target_kind: 'course_objective',
        before: { learning_objective: '掌握向量加法的计算规则' },
        after: { learning_objective: '理解向量加法为什么表示位移的复合' },
        reason: '回写课程目标真源',
        status: 'pending',
      }],
    }
    httpMock.post.mockImplementation((url: string) => {
      if (url.endsWith('/edits/preview')) {
        return Promise.resolve({ data: {
          classification: 'semantic',
          reason: '教学目标发生变化',
          semantic_change: { summary: '教学目标从「计算技能」转向「概念理解」' },
          impact: {
            affected_unit_count: 5,
            unaffected_unit_count: 12,
            affected_representations: [
              { representation_id: 'lesson', representation_type: 'lesson_plan', unit_ids: ['lesson:section-a'] },
              { representation_id: 'slides', representation_type: 'slide_deck', unit_ids: ['slide:section-a'] },
            ],
          },
        } })
      }
      if (url.endsWith('/edits/apply')) {
        return Promise.resolve({ data: { authoring_change: proposal } })
      }
      if (url.endsWith('/items/objective-item/apply')) {
        return Promise.resolve({ data: {
          representation_sync: {
            status: 'synchronized',
            rebuilt_unit_count: 5,
            reused_unit_count: 12,
            rebuilt: [],
          },
        } })
      }
      return Promise.resolve({ data: {} })
    })
    httpMock.get.mockImplementation((url: string) => {
      if (url.endsWith('/authoring-changes')) return Promise.resolve({ data: [proposal] })
      if (url.endsWith('/teaching-representations')) {
        return Promise.resolve({ data: {
          registry: {
            representations: [{ representation_id: 'slides-1', representation_type: 'slide_deck', spec_id: 'spec-1' }],
            specs: [],
          },
        } })
      }
      if (url.endsWith('/spec')) {
        return Promise.resolve({
          data: {
            spec: {
              payload: {
                content: {
                  schema_version: 'slide_deck_v2',
                  slides: structuredClone(slides),
                },
              },
            },
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
    const store = useTeachingRepresentationsStore()
    store.courseId = 'course-1'
    const objectiveSlides = [
      slides[0]!,
      {
        ...slides[1]!,
        slide_purpose: 'learning_objective',
        key_message: '掌握向量加法的计算规则',
      },
    ]
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: '数据结构', slides: objectiveSlides,
        staleUnitIds: [], building: false, progress: 100, stage: 'complete', error: '',
        quality: { passed: true, score: 1 },
      },
    })

    await wrapper.findAll('.slide-thumbnails > button')[1]!.trigger('click')
    await wrapper.find('.slide-inspector__edit select').setValue('key_message')
    await wrapper.find('.slide-inspector__edit textarea').setValue('理解向量加法为什么表示位移的复合')
    await wrapper.find('.slide-inspector__edit-actions button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.slide-inspector__impact').text()).toContain('计算技能')
    expect(wrapper.find('.slide-inspector__impact').text()).toContain('保持 12 处不变')

    const semanticButton = wrapper.findAll('.slide-inspector__edit-actions button')
      .find(button => button.text().includes('改变课程含义'))
    await semanticButton!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.slide-inspector__confirmation').text()).toContain('回写课程目标真源')

    await wrapper.find('.slide-inspector__confirmation button.semantic').trigger('click')
    await flushPromises()
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('5 处已更新')
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('12 处确认无需修改')
  })
})
