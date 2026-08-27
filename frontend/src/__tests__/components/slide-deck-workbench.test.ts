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
  it('consolidates V6 planning diagnostics into one compact build-details menu', () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'generic-course',
        representationId: 'slides-v6',
        deckTitle: 'Evidence workflow',
        slides,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'complete',
        error: '',
        quality: { passed: true },
        candidateStatus: 'v6_needs_manual_edit',
        planningStatus: {
          story_ai: { status: 'completed', batch_count: 2 },
          visual_ai: { status: 'partial_degraded', degraded_page_count: 1 },
          cost: {
            model_call_count: 4,
            input_tokens: 12500,
            output_tokens: 2400,
            ai_busy_duration_ms: 12500,
          },
        },
        pptManuscript: {
          schema_version: 'ppt_manuscript_v1',
          page_count: 2,
          pages: [
            {
              page_id: 'page-1',
              page_number: 1,
              title: '建立问题',
              page_goal: '让学生明确本讲要解决的问题',
              primary_claim: '可靠结论必须绑定现场证据',
              audience_question: '哪些证据能支撑这个结论？',
              visible_copy: ['先记录对象、时间与环境条件。'],
              reveal_steps: ['question', 'evidence', 'conclusion'],
              transition: '带着证据进入下一页验证',
              page_type: 'concept',
              layout_id: 'qizhi-classroom/content-stack',
              composition_notes: '标题在上，证据链在下。',
              source_script_block_ids: ['b1', 'b2'],
            },
            { page_id: 'page-2', page_number: 2, title: '验证结论', source_script_block_ids: ['b3', 'b4', 'b5'] },
          ],
        },
      },
    })

    const details = wrapper.get('[data-testid="ppt-build-details"]')
    expect(details.get('summary').text()).toContain('生成详情')
    expect(details.get('[data-testid="ppt-story-ai-status"]').text()).toContain('2 批')
    expect(details.get('[data-testid="ppt-planning-cost"]').text()).toContain('4 次')
    expect(details.get('[data-testid="ppt-planning-cost"]').text()).toContain('1.3万 Token')
    expect(details.get('[data-testid="ppt-planning-cost"]').text()).toContain('12.5 秒')
    expect(details.get('[data-testid="ppt-storyboard-status"]').text()).toContain('2 页')
    expect(details.get('[data-testid="ppt-storyboard-pages"]').text()).toContain('建立问题')
    expect(details.get('[data-testid="ppt-storyboard-pages"]').text()).toContain('3 个讲稿来源块')
    expect(details.get('[data-testid="ppt-storyboard-pages"]').text()).toContain('让学生明确本讲要解决的问题')
    expect(details.get('[data-testid="ppt-storyboard-pages"]').text()).toContain('可靠结论必须绑定现场证据')
    expect(details.get('[data-testid="ppt-storyboard-pages"]').text()).toContain('concept · qizhi-classroom/content-stack')
    expect(details.get('[data-testid="ppt-storyboard-pages"]').text()).toContain('哪些证据能支撑这个结论？')
    expect(details.get('[data-testid="ppt-storyboard-pages"]').text()).toContain('先记录对象、时间与环境条件。')
    expect(details.get('[data-testid="ppt-storyboard-pages"]').text()).toContain('question → evidence → conclusion')
    expect(details.get('[data-testid="ppt-visual-ai-status"]').text()).toContain('1 页需检查')
    expect(details.get('[data-testid="ppt-manual-edit-status"]').text()).toContain('完整课件')
    expect(wrapper.get('.slide-workbench__identity').find('[data-testid="ppt-story-ai-status"]').exists()).toBe(false)
  })

  it('offers page-level visual repair only for a degraded V6 candidate', async () => {
    const store = useTeachingRepresentationsStore()
    const repair = vi.spyOn(store, 'repairDegradedVisuals').mockResolvedValue({
      status: 'accepted',
      task_id: 'visual-repair-task',
      target_page_ids: ['page-1'],
    })
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'generic-course',
        representationId: 'slides-v6',
        deckTitle: 'Evidence workflow',
        slides,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'complete',
        error: '',
        quality: { passed: true },
        candidateStatus: 'v6_needs_manual_edit',
        planningStatus: {
          story_ai: { status: 'completed', batch_count: 2 },
          visual_ai: {
            status: 'partial_degraded',
            degraded_page_count: 1,
            degraded_pages: [{ page_id: 'page-1', reason: 'visual_ai_batch_failed' }],
          },
        },
      },
    })

    expect(wrapper.get('[data-testid="ppt-degraded-visual-list"]').text()).toContain('page-1')
    expect(wrapper.get('[data-testid="ppt-degraded-visual-list"]').text()).toContain('visual_ai_batch_failed')
    const button = wrapper.get('[data-testid="ppt-repair-degraded-visuals"]')
    expect(button.attributes('title')).toBeTruthy()
    await button.trigger('click')

    expect(repair).toHaveBeenCalledWith('generic-course', 'slides-v6')
  })

  it('requires explicit PPT manuscript confirmation before formal export', async () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1',
        representationId: 'slides-v6',
        deckTitle: '数据结构',
        slides,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'complete',
        error: '',
        standalone: true,
        quality: { passed: true },
        manuscriptConfirmationRequired: true,
        manuscriptStatus: 'draft',
        pptManuscript: {
          schema_version: 'ppt_manuscript_v1',
          page_count: 1,
          pages: [{
            page_id: 'page-1',
            page_number: 1,
            title: '向量的定义',
            source_script_block_ids: ['block-a'],
          }],
        },
      },
    })

    const confirm = wrapper.get('[data-testid="ppt-confirm-manuscript"]')
    expect(confirm.text()).toContain('确认 PPT 文书')
    expect(wrapper.get('.slide-workbench__export').attributes('disabled')).toBeDefined()
    await confirm.trigger('click')
    expect(wrapper.emitted('confirm-manuscript')).toHaveLength(1)

    await wrapper.setProps({ manuscriptStatus: 'confirmed' })
    expect(confirm.text()).toContain('查看 PPT 文书')
    expect(confirm.attributes('disabled')).toBeUndefined()
    await confirm.trigger('click')
    expect(wrapper.emitted('review-manuscript')).toHaveLength(1)
    expect(wrapper.get('.slide-workbench__export').attributes('disabled')).toBeUndefined()
  })

  it('does not allow confirming a manuscript that failed narrative quality', () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1',
        representationId: 'slides-v6-blocked',
        deckTitle: '数据结构',
        slides,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'complete',
        error: '',
        standalone: true,
        quality: { passed: false },
        manuscriptConfirmationRequired: true,
        manuscriptStatus: 'draft',
        pptManuscript: {
          schema_version: 'ppt_manuscript_v1',
          quality_status: 'blocked',
          quality_issues: [{
            code: 'ppt_manuscript_title_not_audience_ready',
            page_id: 'page-1',
            message: '原始 LaTeX 不能作为页面标题',
          }],
          page_count: 1,
          pages: [{
            page_id: 'page-1',
            page_number: 1,
            title: '$f\\circ g$',
            source_script_block_ids: ['block-a'],
          }],
        },
      },
    })

    const confirm = wrapper.get('[data-testid="ppt-confirm-manuscript"]')
    expect(confirm.attributes('disabled')).toBeDefined()
    expect(confirm.text()).toContain('PPT 文书需修改')
    expect(wrapper.get('[data-testid="ppt-storyboard-status"]').text()).toContain('不能生成 PPT')
    expect(wrapper.get('[data-testid="ppt-manuscript-quality-issues"]').text()).toContain('原始 LaTeX 不能作为页面标题')
  })

  it('keeps a legacy storyboard separate from a formal PPT manuscript', async () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'course-1',
        representationId: 'slides-v6-legacy',
        deckTitle: '旧版课件',
        slides,
        staleUnitIds: [],
        building: false,
        progress: 100,
        stage: 'complete',
        error: '',
        standalone: true,
        quality: { passed: true },
        manuscriptConfirmationRequired: false,
        storyboard: {
          page_count: 1,
          pages: [{
            page_id: 'legacy-page-1',
            page_ordinal: 0,
            title: '旧版规划',
            source_block_count: 2,
          }],
        },
      },
    })

    const details = wrapper.get('[data-testid="ppt-build-details"]')
    expect(details.get('[data-testid="ppt-legacy-storyboard-status"]').text()).toContain('旧版页面规划')
    expect(details.get('[data-testid="ppt-legacy-storyboard-pages"]').text()).toContain('2 个内容来源块')
    expect(wrapper.find('[data-testid="ppt-confirm-manuscript"]').exists()).toBe(false)
    expect(wrapper.get('.slide-workbench__export').attributes('disabled')).toBeUndefined()
  })

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
        buildStepIndex: 6,
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
    expect(panel.findAll('[data-step-description]')).toHaveLength(10)
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
    const taskList = panel.find('[data-testid="build-task-list"]')
    expect(taskList.exists()).toBe(true)
    expect(taskList.findAll('[data-build-task]')).toHaveLength(3)
    expect(taskList.text()).toContain('读取当前页面计划')
    expect(taskList.text()).toContain('生成页面内容与讲者备注')
    expect(taskList.text()).toContain('写入并校验全部页面')
    expect(taskList.findAll('[data-build-task][data-state="done"]')).toHaveLength(1)
    expect(taskList.findAll('[data-build-task][data-state="active"]')).toHaveLength(1)
    expect(taskList.findAll('[data-build-task][data-state="pending"]')).toHaveLength(1)
    expect(taskList.find('[data-current-activity]').text()).toContain('第 2 / 12 页 · 向量的定义')

    await wrapper.setProps({
      progress: 97,
      stage: 'image_search',
      buildStepIndex: 8,
      buildDetail: {
        event: 'image_search',
        completed: 2,
        total: 4,
        itemTitle: '向量的几何意义',
      },
    })
    expect(panel.text()).toContain('正在检索并核验教学图片')
    expect(panel.text()).toContain('正在为「向量的几何意义」查找可用教学图片')
    expect(panel.findAll('[data-build-step][data-state="done"]')).toHaveLength(8)
    expect(taskList.text()).toContain('检查知识点与目标覆盖')
    expect(taskList.text()).toContain('检查文字密度和可读性')
    expect(taskList.text()).toContain('修复问题页并重新质检')
    expect(taskList.findAll('[data-build-task][data-state="done"]')).toHaveLength(2)
    expect(taskList.findAll('[data-build-task][data-state="active"]')).toHaveLength(1)
    expect(taskList.find('[data-current-activity]').text()).toContain('向量的几何意义')

    await wrapper.setProps({
      progress: 99,
      stage: 'render_repair',
      buildStepIndex: 9,
      buildDetail: {
        event: 'render_repair',
        completed: 12,
        total: 12,
        repairAttempt: 2,
      },
    })
    expect(panel.text()).toContain('正在执行第 2 轮版式修复')
    expect(panel.findAll('[data-build-step][data-state="done"]')).toHaveLength(9)
    expect(taskList.text()).toContain('渲染全部页面')
    expect(taskList.text()).toContain('修复溢出、遮挡与错位')
    expect(taskList.text()).toContain('发布可下载课件')
    expect(taskList.findAll('[data-build-task][data-state="done"]')).toHaveLength(1)
    expect(taskList.findAll('[data-build-task][data-state="active"]')).toHaveLength(1)

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

  it('labels a retryable failed build as continuing from its saved checkpoint', async () => {
    const wrapper = mount(SlideDeckWorkbench, {
      props: {
        courseId: 'generic-course', representationId: 'slides-v6', deckTitle: 'Evidence workflow', slides,
        staleUnitIds: [], building: false, progress: 63, stage: 'build_blocked', error: 'provider_timeout',
        quality: null, standalone: true, buildResumable: true,
      },
    })

    const resume = wrapper.findAll('.slide-workbench__commands button')
      .find(button => button.attributes('title') === '从保存点继续')
    expect(resume?.text()).toContain('从保存点继续')
    await resume!.trigger('click')
    expect(wrapper.emitted('rebuild')).toHaveLength(1)
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
