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
    expect(wrapper.find('.deck-canvas').attributes('data-layout')).toBe('cover')

    await wrapper.findAll('.slide-thumbnails > button')[1]!.trigger('click')
    expect(wrapper.find('.deck-canvas').attributes('data-layout')).toBe('concept')
    expect(wrapper.find('.deck-canvas').text()).toContain('向量同时具有大小和方向')
    expect(wrapper.find('.slide-inspector__refs').text()).toContain('向量定义')
    expect(wrapper.find('.slide-inspector__refs').text()).toContain('识别向量')

    await wrapper.find('.slide-workbench__commands button').trigger('click')
    const event = wrapper.emitted('ask-ai')?.[0]?.[0] as Record<string, any>
    expect(event.nodeId).toBe('section-a')
    expect(event.anchor.slide_unit_id).toBe('slide:section-a')
  })

  it('presents the same slide full screen and exports from the top command bar', async () => {
    const store = useTeachingRepresentationsStore()
    const download = vi.spyOn(store, 'downloadSlides').mockResolvedValue(undefined)
    const wrapper = mount(SlideDeckWorkbench, {
      attachTo: document.body,
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: '数据结构', slides,
        staleUnitIds: [], building: false, progress: 100, stage: 'complete', error: '',
        quality: { passed: true, score: 1 }, standalone: true,
      },
    })

    const present = wrapper.findAll('.slide-workbench__commands button')
      .find(button => button.attributes('title') === '全屏演示')
    await present!.trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.deck-presentation')).not.toBeNull()
    expect(document.body.querySelector('.deck-presentation .deck-canvas')?.getAttribute('data-layout')).toBe('cover')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b' }))
    await flushPromises()
    expect(document.body.querySelector('.deck-presentation__blank')?.textContent).toContain('临时黑屏')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b' }))

    const exportButton = wrapper.find('.slide-workbench__export')
    await exportButton.trigger('click')
    await flushPromises()
    expect(download).toHaveBeenCalledWith('slides-1', '数据结构')

    wrapper.unmount()
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
          semantic_change: {
            summary: '教学目标从「计算技能」转向「概念理解」',
            from_label: '计算技能',
            to_label: '概念理解',
            interpretation: '课堂重心从正确执行步骤升级为解释概念关系与运算顺序。',
            instructional_implications: ['讲解增加为什么', '例题解释理由', '检查加入概念说明'],
          },
          impact: {
            affected_unit_count: 5,
            unaffected_unit_count: 12,
            change_items: [
              { representation_type: 'slide_deck', unit_id: 'slide:section-a', label: 'PPT · 学习目标', role: 'PPT 学习目标', reason: '修改起点', origin: true },
              { representation_type: 'lesson_plan', unit_id: 'lesson:section-a', label: '教案 · 向量加法', role: '教案重点', reason: '课堂重点需要对齐', origin: false },
              { representation_type: 'handout', unit_id: 'handout:section-a', label: '讲义 · 向量加法', role: '讲义解释', reason: '讲义引导需要更新', origin: false },
            ],
            protected_items: [
              { representation_type: 'lesson_plan', unit_id: 'lesson:section-b', label: '教案 · 矩阵导论' },
            ],
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
            changed_unit_count: 2,
            verified_unit_count: 1,
            changes: [
              {
                representation_type: 'lesson_plan',
                units: [{
                  unit_id: 'lesson:section-a',
                  label: '教案重点 · 向量加法',
                  change_kind: 'content_changed',
                  before: '教学重点放在规则与步骤',
                  after: '教学重点放在概念关系与为什么成立',
                }],
              },
              {
                representation_type: 'slide_deck',
                units: [{
                  unit_id: 'slide:section-a:content:1',
                  label: 'PPT 核心讲解 · 向量加法',
                  change_kind: 'source_verified',
                  before: '向量加法',
                  after: '向量加法',
                }],
              },
            ],
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
      attachTo: document.body,
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
    expect(document.body.querySelector('.impact-dialog')?.textContent).toContain('系统理解了这次教学修改')
    expect(document.body.querySelector('.impact-dialog')?.textContent).toContain('教案重点')
    expect(document.body.querySelector('.impact-dialog')?.textContent).toContain('矩阵导论')

    ;(document.body.querySelector('.impact-dialog__actions .primary') as HTMLButtonElement).click()
    await flushPromises()
    expect(wrapper.find('.slide-inspector__confirmation').text()).toContain('回写课程目标真源')
    expect(document.body.querySelector('.impact-dialog')?.textContent).toContain('等待教师确认')

    ;(document.body.querySelector('.impact-dialog__actions .primary') as HTMLButtonElement).click()
    await flushPromises()
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('2 项实际更新')
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('1 项仅校验')
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('12 项确认无需处理')
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('1 改 · 0 验')
    expect(document.body.querySelector('.impact-dialog')?.textContent).toContain('相关内容已精准同步')
    expect(document.body.querySelector('.impact-dialog')?.textContent).toContain('教学重点放在概念关系与为什么成立')
    expect(document.body.querySelector('.impact-dialog')?.textContent).toContain('来源版本已重新校验')

    ;(document.body.querySelector('.impact-dialog__actions .primary') as HTMLButtonElement).click()
    await wrapper.find('.slide-inspector__edit textarea').setValue('理解向量加法为什么表示位移复合，并能解释顺序')
    await flushPromises()
    expect(wrapper.find('.slide-inspector__receipt').exists()).toBe(false)
    expect(document.body.querySelector('.impact-dialog')).toBeNull()

    await wrapper.find('.slide-inspector__edit-actions button').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.impact-dialog')?.textContent).toContain('系统理解了这次教学修改')
    expect(document.body.querySelector('.impact-dialog')?.textContent).not.toContain('相关内容已精准同步')
    wrapper.unmount()
  })
})
