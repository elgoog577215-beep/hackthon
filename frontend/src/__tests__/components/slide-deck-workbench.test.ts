import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SlideDeckWorkbench from '@/components/SlideDeckWorkbench.vue'
import { useTeachingRepresentationsStore } from '@/stores/teachingRepresentations'
import { PPT_SAME_SOURCE_STORAGE_KEY } from '@/utils/ppt-same-source'

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
  sessionStorage.clear()
})

describe('SlideDeckWorkbench', () => {
  it('shows a ten-step build progress panel with specific page, image, and render phases', async () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1',
        representationId: 'slides-1',
        deckTitle: '数据结构',
        slides,
        staleUnitIds: [],
        building: true,
        progress: 46,
        stage: 'slide_build',
        error: '',
        quality: null,
        standalone: true,
        buildDetail: {
          event: 'slide_upsert',
          itemTitle: '向量的定义',
          completed: 2,
          total: 12,
        },
        estimatedSlideCount: 12,
      },
    })

    const panel = wrapper.find('[data-testid="slide-build-progress"]')
    expect(panel.exists()).toBe(true)
    expect(panel.attributes('aria-live')).toBe('polite')
    expect(panel.text()).toContain('正在逐页生成教学内容')
    expect(panel.text()).toContain('第 2 / 12 页')
    expect(panel.text()).toContain('向量的定义')
    expect(panel.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('46')
    expect(panel.findAll('[data-build-step]')).toHaveLength(10)
    expect(panel.text()).toContain('设计教学主线')
    expect(panel.text()).toContain('编排章节场景')
    expect(panel.text()).toContain('规划页面结构')
    expect(panel.text()).toContain('匹配语义版式')
    expect(panel.text()).toContain('准备视觉素材')
    expect(panel.text()).toContain('补图与语义修复')
    expect(panel.text()).toContain('内容视觉质检')
    expect(panel.text()).toContain('渲染与发布')
    expect(panel.findAll('[data-build-step][data-state="done"]')).toHaveLength(6)
    expect(panel.findAll('[data-build-step][data-state="active"]')).toHaveLength(1)

    await wrapper.setProps({
      progress: 97,
      stage: 'image_search',
      buildDetail: {
        event: 'image_search',
        completed: 2,
        total: 4,
        itemTitle: '向量的几何意义',
      },
    })
    expect(panel.text()).toContain('正在检索并核验教学图片')
    expect(panel.text()).toContain('正在为「向量的几何意义」查找可用教学图片')
    expect(panel.findAll('[data-build-step][data-state="done"]')).toHaveLength(7)

    await wrapper.setProps({
      progress: 99,
      stage: 'render_repair',
      buildDetail: {
        event: 'render_repair',
        completed: 12,
        total: 12,
        repairAttempt: 2,
      },
    })
    expect(panel.text()).toContain('正在执行第 2 轮版式修复')
    expect(panel.findAll('[data-build-step][data-state="done"]')).toHaveLength(9)

    await wrapper.setProps({ building: false })
    expect(wrapper.find('[data-testid="slide-build-progress"]').exists()).toBe(false)
  })

  it('keeps the toolbar focused on teaching materials and opens the material overview', async () => {
    const store = useTeachingRepresentationsStore()
    const build = vi.spyOn(store, 'buildProgressive')
    const demoSlides = Array.from({ length: 15 }, (_, index) => ({
      ...slides[index % slides.length]!,
      unit_id: `slide:${index + 1}`,
      title: `Demo ${index + 1}`,
    }))
    const wrapper = mount(SlideDeckWorkbench, {
      attachTo: document.body,
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: '数据结构', slides: demoSlides,
        staleUnitIds: [], building: false, progress: 100, stage: 'complete', error: '',
        quality: { passed: true, score: 1 }, standalone: true,
      },
    })

    expect(wrapper.find('.deck-canvas').attributes('data-theme')).toBe('qingfeng-classroom')
    expect(wrapper.find('.slide-workbench__count').text()).toContain('15')
    expect(wrapper.find('.slide-workbench__count').text()).not.toContain('12–18')

    expect(wrapper.find('[data-theme-option]').exists()).toBe(false)
    const materials = wrapper.findAll('.slide-workbench__commands button')
      .find(button => button.attributes('title') === '教学材料总览')
    await materials!.trigger('click')
    expect(wrapper.emitted('open-materials')).toHaveLength(1)
    expect(wrapper.emitted('rebuild')).toBeUndefined()
    expect(build).not.toHaveBeenCalled()

    const present = wrapper.findAll('.slide-workbench__commands button')
      .find(button => button.attributes('title') === '全屏演示')
    await present!.trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.deck-presentation .deck-canvas')?.getAttribute('data-theme'))
      .toBe('qingfeng-classroom')

    wrapper.unmount()
  })

  it('labels teaching mainline and appendix counts without a demo target', () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1',
        representationId: 'slides-1',
        deckTitle: 'Linear algebra',
        slides,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'complete',
        error: '',
        quality: {
          passed: true,
          main_slide_count: 56,
          appendix_slide_count: 741,
          large_deck_warning: true,
        },
      },
    })

    const count = wrapper.find('.slide-workbench__count').text()
    expect(count).toContain('56 页主线')
    expect(count).toContain('741 页附录')
    expect(count).toContain('建议按章节拆分')
  })

  it('shows the actual V5 slide total after structural pages are inserted', () => {
    const fullDeck = Array.from({ length: 91 }, (_, index) => ({
      ...slides[index % slides.length]!,
      unit_id: `slide:${index + 1}`,
    }))
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1',
        representationId: 'slides-v5',
        deckTitle: 'Thermodynamics',
        slides: fullDeck,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'complete',
        error: '',
        quality: {
          passed: true,
          main_slide_count: 74,
          appendix_slide_count: 0,
          total_slide_count: 91,
        },
      },
    })

    const count = wrapper.find('.slide-workbench__count').text()
    expect(count).toContain('91')
    expect(count).not.toContain('74')
  })

  it('shows the concrete course-logic blocker and replaces rebuild with its recovery action', async () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1',
        representationId: 'slides-legacy',
        deckTitle: '高等代数',
        slides,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'build_blocked',
        error: 'course_teaching_plan_not_ready',
        buildFailure: {
          code: 'course_teaching_plan_not_ready',
          message: '当前课程尚未完成正式教学计划，请先补全课程逻辑。',
          action: 'upgrade_course_logic',
          retryable: false,
        },
        quality: { passed: true },
        previewSource: 'published',
        engineStatus: 'blocked',
        standalone: true,
      },
    })

    expect(wrapper.find('.slide-workbench__status').text()).toContain('生成受阻')
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain(
      '课件生成受阻：课程逻辑尚未就绪',
    )
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain(
      '当前课程尚未完成正式教学计划，请先补全课程逻辑。',
    )
    expect(wrapper.find('.slide-inspector').text()).toContain('上一版本本页质量')
    expect(wrapper.find('.slide-workbench__upgrade-logic').exists()).toBe(true)
    expect(wrapper.find('.slide-workbench__commands').text()).not.toContain('重新生成当前组合')

    await wrapper.find('.slide-workbench__upgrade-logic').trigger('click')
    expect(wrapper.emitted('upgrade-course-logic')).toHaveLength(1)
  })

  it('shows V5 schema facts, manual-edit guidance, and structured hard failures', async () => {
    const manualSlides = [
      slides[0]!,
      {
        ...slides[1]!,
        quality: {
          ...slides[1]!.quality,
          manual_edit_required: true,
          manual_edit_reasons: [{
            code: 'render_review_manual_adjustment',
            message: '本页内容完整，但建议人工微调视觉间距。',
          }],
        },
      },
    ]
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1',
        representationId: 'slides-v5',
        deckTitle: '高等代数',
        slides: manualSlides,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'source_commit',
        error: 'v5_source_revision_conflict',
        previewSource: 'published',
        buildFailure: {
          stage: 'source_commit',
          code: 'v5_source_revision_conflict',
          message: '课程内容在 PPT 生成期间发生变化。',
          retryable: true,
          source_revision: 'revision-1',
        },
        quality: { passed: true },
        targetSchema: 'slide_deck_v5',
        candidateSchema: 'slide_deck_v5',
        publishedSchema: 'slide_deck_v3',
        candidateStatus: 'v5_needs_manual_edit',
      },
    })

    expect(wrapper.get('[data-testid="ppt-schema-facts"]').text()).toContain(
      '目标 V5 · 候选 V5 · 已发布 V3',
    )
    expect(wrapper.get('[data-testid="ppt-manual-edit-status"]').text()).toContain(
      '部分页面需要人工调整',
    )
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain(
      'v5_source_revision_conflict',
    )
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain(
      '失败阶段：source_commit · 可以重试',
    )

    await wrapper.findAll('.slide-thumbnails > button')[1]!.trigger('click')
    expect(wrapper.find('[data-state="manual_edit_required"]').text()).toContain(
      '本页内容完整，但建议人工微调视觉间距。',
    )
  })

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

    const askAiButton = wrapper.findAll('.slide-workbench__commands button')
      .find(button => button.attributes('title') === '交给 AI 老师讨论')
    await askAiButton!.trigger('click')
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
    expect(download).toHaveBeenCalledWith('slides-1', '数据结构', 'qingfeng-classroom')

    wrapper.unmount()
  })

  it('shows unpublished slide and layout quality issues with actionable suggestions', async () => {
    const store = useTeachingRepresentationsStore()
    const download = vi.spyOn(store, 'downloadSlides').mockResolvedValue(undefined)
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: '数据结构', slides,
        staleUnitIds: [], building: false, progress: 100, stage: 'quality', error: 'quality_gate_failed',
        previewSource: 'draft',
        quality: {
          passed: false,
          issues: [{
            severity: 'critical',
            code: 'slide_item_overflow',
            slide_id: 'slide:section-a',
            layout: 'concept',
            responsibility: 'course_generation',
            message: '页面要点数量超过版式容量。',
            suggestion: '将可见要点压缩到版式允许的数量。',
          }],
        },
      },
    })

    const preview = wrapper.find('.slide-workbench__failed-preview')
    expect(preview.text()).toContain('未发布问题预览')
    expect(preview.text()).toContain('slide:section-a')
    expect(preview.text()).toContain('概念')
    expect(preview.text()).toContain('课程内容链路')
    expect(preview.text()).toContain('页面要点数量超过版式容量。')
    expect(preview.text()).toContain('将可见要点压缩到版式允许的数量。')
    expect(wrapper.attributes('data-preview-source')).toBe('draft')
    expect(wrapper.find('.slide-workbench__export').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.slide-workbench__export').attributes('title')).toContain('问题草稿不可导出')
    await wrapper.find('.slide-workbench__export').trigger('click')
    expect(download).not.toHaveBeenCalled()
  })

  it('separates release blockers from non-blocking quality advice', () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: 'Quality levels', slides,
        staleUnitIds: [], building: false, progress: 100, stage: 'quality', error: 'quality_gate_failed',
        previewSource: 'draft',
        quality: {
          passed: false,
          blockers: [{
            severity: 'critical', code: 'enumeration_cardinality_mismatch', page_id: 'slide:section-a',
            message: 'Four promised items are not visible.', suggestion: 'Keep all four items together.',
          }],
          issues: [{
            severity: 'minor', code: 'knowledge_binding_missing', page_id: 'deck',
            message: 'Some pages have no formal knowledge id.', suggestion: 'Bind them upstream when available.',
          }],
        },
      },
    })

    const preview = wrapper.find('.slide-workbench__failed-preview')
    expect(preview.find('header b').text()).toBe('1')
    expect(preview.findAll('li[data-severity="critical"]')).toHaveLength(1)
    expect(preview.findAll('li[data-severity="minor"]')).toHaveLength(1)
    expect(preview.find('.slide-workbench__failed-preview-advisories').exists()).toBe(true)
  })

  it('shows the backend blocker total instead of presenting the first issue code as the whole failure', () => {
    const blockers = [
      ...Array.from({ length: 9 }, (_, index) => ({
        severity: 'critical', code: 'dangling_fragment', page_id: `slide:dangling:${index}`,
        message: 'Page ends with an incomplete fragment.',
      })),
      ...Array.from({ length: 6 }, (_, index) => ({
        severity: 'critical', code: 'continuation_sequence_missing', page_id: `slide:continuation:${index}`,
        message: 'Continuation numbering is missing.',
      })),
    ]
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: 'Quality summary', slides,
        staleUnitIds: [], building: false, progress: 100, stage: 'build_blocked',
        error: 'quality_gate_failed', previewSource: 'published',
        quality: { passed: false, blocker_count: 99, blockers },
      },
    })

    const receipt = wrapper.find('.slide-inspector__receipt').text()
    expect(receipt).toContain('99')
    expect(receipt).toContain('15')
    expect(receipt).toContain('9')
    expect(receipt).toContain('6')
  })

  it('restores export when a successful rebuild changes the preview from draft to published', async () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: '数据结构', slides,
        staleUnitIds: [], building: false, progress: 100, stage: 'quality', error: 'quality_gate_failed',
        previewSource: 'draft', quality: { passed: false },
      },
    })

    expect(wrapper.find('.slide-workbench__export').attributes('disabled')).toBeDefined()

    await wrapper.setProps({
      previewSource: 'published', error: '', stage: 'complete', quality: { passed: true },
    })

    expect(wrapper.attributes('data-preview-source')).toBe('published')
    expect(wrapper.find('.slide-workbench__export').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('.slide-workbench__export').attributes('title')).toBe('导出 PPTX')
  })

  it('keeps a useful fallback for legacy failed payloads without issues', () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1', representationId: 'slides-1', deckTitle: '数据结构', slides,
        staleUnitIds: [], building: false, progress: 100, stage: 'quality', error: 'quality_gate_failed',
        quality: { passed: false },
      },
    })

    expect(wrapper.find('.slide-workbench__failed-preview').text()).toContain('未发布问题预览')
    expect(wrapper.find('.slide-workbench__failed-preview').text()).toContain('未返回逐页问题')
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
            block_ids: ['block-a'],
            section_ids: ['section-a'],
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
    expect(document.body.querySelector('.impact-workspace')?.textContent).toContain('系统理解了这次教学修改')
    expect(document.body.querySelector('.impact-workspace')?.textContent).toContain('该动的动，不该动的不动')
    expect(document.body.querySelector('.impact-workspace')?.textContent).toContain('教案重点')
    expect(document.body.querySelector('.impact-workspace')?.textContent).toContain('矩阵导论')
    expect(document.body.querySelector('.impact-detail-card')?.textContent).toContain('课堂重点需要对齐')
    expect(document.body.querySelector('.impact-workspace__footer')?.textContent).toContain('确认前课程不会发生变化')

    ;(document.body.querySelector('.impact-workspace__actions .primary') as HTMLButtonElement).click()
    await flushPromises()
    expect(wrapper.find('.slide-inspector__confirmation').text()).toContain('回写课程目标真源')
    expect(document.body.querySelector('.impact-workspace')?.textContent).toContain('等待教师决定')
    expect(document.body.querySelector('.impact-workspace__actions .primary')?.textContent).toContain('确认联动 5 处')
    expect(document.body.querySelector('.impact-workspace__actions .primary')?.textContent).toContain('保留 12 处')

    ;(document.body.querySelector('.impact-workspace__actions .primary') as HTMLButtonElement).click()
    await flushPromises()
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('2 项实际更新')
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('1 项仅校验')
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('12 项确认无需处理')
    expect(wrapper.find('.slide-inspector__receipt').text()).toContain('1 改 · 0 验')
    expect(document.body.querySelector('.impact-workspace')?.textContent).toContain('一处改变，相关内容已精准联动')
    expect(document.body.querySelector('.impact-workspace')?.textContent).toContain('教学重点放在概念关系与为什么成立')
    const resultItems = Array.from(document.body.querySelectorAll<HTMLButtonElement>('.impact-list > button'))
    const verifiedItem = resultItems.find(button => button.textContent?.includes('已校验'))
    verifiedItem?.click()
    await flushPromises()
    expect(document.body.querySelector('.impact-detail-card')?.textContent).toContain('内容无需改写')
    expect(document.body.querySelector('.impact-detail-card')?.textContent).toContain('重新校验来源')
    const openCourse = wrapper.get('.same-source-course-link')
    expect(openCourse.text()).toContain('进入课程查看同源改动')
    await openCourse.trigger('click')
    const savedState = JSON.parse(sessionStorage.getItem(PPT_SAME_SOURCE_STORAGE_KEY) || '{}')
    expect(savedState).toEqual(expect.objectContaining({
      courseId: 'course-1',
      sectionId: 'section-a',
      blockIds: ['block-a'],
      primaryBlockId: 'block-a',
      beforeText: '掌握向量加法的计算规则',
      afterText: '理解向量加法为什么表示位移的复合',
    }))
    expect(wrapper.emitted('open-course')?.[0]?.[0]).toEqual(expect.objectContaining({
      courseId: 'course-1',
      sectionId: 'section-a',
    }))

    ;(document.body.querySelector('.impact-workspace__actions .primary') as HTMLButtonElement).click()
    await wrapper.find('.slide-inspector__edit textarea').setValue('理解向量加法为什么表示位移复合，并能解释顺序')
    await flushPromises()
    expect(wrapper.find('.slide-inspector__receipt').exists()).toBe(false)
    expect(document.body.querySelector('.impact-workspace')).toBeNull()

    await wrapper.find('.slide-inspector__edit-actions button').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.impact-workspace')?.textContent).toContain('系统理解了这次教学修改')
    expect(document.body.querySelector('.impact-workspace')?.textContent).not.toContain('一处改变，相关内容已精准联动')
    wrapper.unmount()
  })
})
