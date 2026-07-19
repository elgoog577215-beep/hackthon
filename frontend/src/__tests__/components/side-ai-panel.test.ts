import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SideAIPanel from '@/components/SideAIPanel.vue'
import enMessages from '@/../public/locales/en/translation.json'
import zhMessages from '@/../public/locales/zh/translation.json'
import { setLocale } from '@/shared/i18n'
import { useAITeacherStore, type AIConversation } from '@/stores/aiTeacher'
import { useCourseStore } from '@/stores/course'
import { useLearningProgressStore } from '@/stores/learningProgress'
import { useChangeProposalsStore } from '@/stores/changeProposals'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import type { ChangeProposal } from '@/types/changeProposal'
import type { CourseBlockEditTarget } from '@/stores/types'

const conversation = (): AIConversation => ({
  conversation_id: 'conversation-1',
  course_id: 'course-1',
  title: '线性空间答疑',
  revision: 1,
  created_at: '2026-07-13T00:00:00Z',
  updated_at: '2026-07-13T00:00:00Z',
  messages: [],
})

function mountPanel(
  messages: AIConversation['messages'] = [],
  quoteText = '',
  blockTarget?: CourseBlockEditTarget,
  configureCourseStore?: (store: ReturnType<typeof useCourseStore>) => void,
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const courseStore = useCourseStore()
  const aiStore = useAITeacherStore()
  const progressStore = useLearningProgressStore()
  const node = {
    node_id: 'node-1',
    node_name: '向量空间与线性相关',
    node_level: 2,
    parent_node_id: 'chapter-1',
    node_content: '课程正文',
  } as any

  courseStore.currentCourseId = 'course-1'
  courseStore.nodes = [node]
  courseStore.currentNode = node
  configureCourseStore?.(courseStore)
  const seededConversation = conversation()
  seededConversation.messages = messages
  aiStore.conversations = [seededConversation]
  aiStore.currentConversationId = seededConversation.conversation_id
  progressStore.runtime = {
    learner_model: {
      data_sufficiency: { level: 'limited' },
    },
  } as any
  vi.spyOn(aiStore, 'load').mockResolvedValue()

  return mount(SideAIPanel, {
    props: {
      visible: true,
      quoteText,
      quoteNodeId: node.node_id,
      quoteAnchor: quoteText ? { block_id: 'block-1' } : undefined,
      blockTarget,
      prefill: blockTarget ? '把定义讲得更清楚' : undefined,
    },
    global: {
      plugins: [pinia],
      stubs: {
        MarkdownRenderer: { props: ['content'], template: '<div class="markdown-stub">{{ content }}</div>' },
      },
    },
  })
}

function personalizationTarget(blockId = 'block-1', revision = 'cbr-1'): CourseBlockEditTarget {
  return {
    nodeId: 'node-1',
    nodeName: '向量空间与线性相关',
    block: {
      block_id: blockId, section_id: 'node-1', position: 0, kind: 'rich_text', role: 'concept',
      payload: { title: `正文 ${blockId}`, markdown: `旧正文 ${blockId}` }, asset_refs: [], objective_refs: ['lo-1'],
      concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: revision, status: 'final',
    },
  }
}

describe('SideAIPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(window, 'innerWidth', { value: 1440, configurable: true })
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
  })

  it('默认收起会话管理，并把章节与选区组织成上下文', async () => {
    const wrapper = mountPanel([], '线性无关意味着不存在非零系数组合。')

    expect(wrapper.find('.conversation-drawer').exists()).toBe(false)
    expect(wrapper.find('.context-line').text()).toContain('向量空间与线性相关')
    expect(wrapper.find('.context-evidence').text()).toBe('有限证据')
    expect(wrapper.find('.context-quote').text()).toContain('线性无关')
    expect(wrapper.findAll('.quick-actions button')).toHaveLength(2)
    expect(wrapper.text()).not.toContain('解释下一步')

    await wrapper.get('.conversation-toggle').trigger('click')
    expect(wrapper.find('.conversation-drawer').exists()).toBe(true)
    expect((wrapper.get('.conversation-select').element as HTMLSelectElement).value).toBe('conversation-1')
  })

  it('在同一回答下保留来源、动作提案和持久回执表达', () => {
    const wrapper = mountPanel([
      { message_id: 'user-1', role: 'user', content: '为什么零向量组一定线性相关？', status: 'complete' },
      {
        message_id: 'assistant-1',
        role: 'assistant',
        content: '因为可以让零向量对应的系数非零，其余系数为零。',
        status: 'complete',
        sources: [{ source_id: 'block-1', title: '线性相关的定义' }],
        proposal: {
          proposal_id: 'proposal-1',
          action_type: 'create_note',
          target_ref: {},
          payload_preview: {},
          reason: '这条解释可以帮助复习。',
          expected_effect: '保存为学习笔记',
          confirmation_mode: 'explicit',
          runtime_revision_id: 'runtime-1',
          status: 'presented',
        },
      },
      {
        message_id: 'assistant-2',
        role: 'assistant',
        content: '笔记已经保存。',
        status: 'complete',
        receipt: {
          receipt_id: 'receipt-1',
          proposal_id: 'proposal-1',
          status: 'succeeded',
          action_type: 'create_note',
          affected_refs: [],
          summary: '已保存到当前章节。',
          undo_capability: 'archive_record',
        },
      },
    ])

    expect(wrapper.find('.user-message-bubble').text()).toContain('零向量组')
    expect(wrapper.findAll('.assistant-answer')).toHaveLength(2)
    expect(wrapper.find('.message-sources').text()).toContain('线性相关的定义')
    expect(wrapper.find('.action-proposal').text()).toContain('保存为学习笔记')
    expect(wrapper.find('.action-receipt').text()).toContain('已保存到当前章节')
  })

  it('AI 提问写入事实后立即刷新统一课程生长状态', async () => {
    const wrapper = mountPanel()
    const aiStore = useAITeacherStore()
    const progressStore = useLearningProgressStore()
    const refreshRuntime = vi.spyOn(progressStore, 'loadRuntime').mockResolvedValue(null)
    vi.spyOn(aiStore, 'sendMessage').mockImplementation(async payload => {
      await payload.onQuestionRecorded?.()
    })

    await wrapper.get('textarea').setValue('为什么是先做右边的变换？')
    await wrapper.get('.send-button').trigger('click')
    await flushPromises()

    expect(aiStore.sendMessage).toHaveBeenCalledWith(expect.objectContaining({
      courseId: 'course-1',
      nodeId: 'node-1',
      question: '为什么是先做右边的变换？',
      onQuestionRecorded: expect.any(Function),
    }))
    expect(refreshRuntime).toHaveBeenCalledWith('course-1', 'node-1')
    expect(refreshRuntime).toHaveBeenCalledTimes(1)
  })

  it('在移动视口使用同一 AI 工作区的覆盖形态', () => {
    Object.defineProperty(window, 'innerWidth', { value: 390, configurable: true })
    const wrapper = mountPanel()

    expect(wrapper.get('.ai-teacher-panel').classes()).toContain('is-overlay')
    expect(wrapper.find('.ai-teacher-backdrop').exists()).toBe(true)
    expect(wrapper.find('.ai-teacher-surface').exists()).toBe(true)
    expect(wrapper.findAll('.quick-actions button')).toHaveLength(2)
  })

  it('当前内容通过统一课程方案生成、审阅并应用', async () => {
    const blockTarget = personalizationTarget()
    const wrapper = mountPanel([], '', blockTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const courseStore = useCourseStore()
    const progressStore = useLearningProgressStore()
    const evolutionStore = useCourseEvolutionStore()
    evolutionStore.applyPayload('course-1', {
      evidence_items: [],
      hypotheses: [],
      course_evolution_plans: [],
    })
    const operation = {
      operation_id: 'operation-1',
      operation_type: 'REPLACE_COURSE_BLOCK',
      target_block_id: 'block-1',
      target_section_id: 'node-1',
      scope: 'current' as const,
      reason: '直接响应当前内容的调整要求',
      payload: {
        action: 'REPLACE',
        role: 'concept',
        candidate_status: 'ready',
        before_block: blockTarget.block,
        proposed_block: {
          ...blockTarget.block,
          payload: { ...blockTarget.block.payload, markdown: '调整后正文' },
        },
      },
    }
    const plan = {
      change_set_id: 'adjustment-plan-1',
      hypothesis_id: 'hypothesis-1',
      source_kind: 'manual_request' as const,
      target_section_id: 'node-1',
      request_text: '把定义讲得更清楚',
      generation_status: 'ready' as const,
      evidence_ids: [],
      operations: [operation],
      scope_selection: 'current_block' as const,
      allowed_scopes: ['current' as const],
      impact_summary: {
        anchor_block_id: 'block-1',
        affected_section_ids: ['node-1'],
      },
      expected_effect: '当前内容更容易理解',
      status: 'pending' as const,
      effect_evaluation: {},
    }
    const createPlan = vi.spyOn(evolutionStore, 'createPlan').mockImplementation(async () => {
      evolutionStore.plans = [plan]
      return {} as any
    })
    const accept = vi.spyOn(evolutionStore, 'accept').mockImplementation(async () => {
      evolutionStore.plans = [{
        ...plan,
        status: 'applied',
        applied_block_ids: ['block-1'],
        application_receipt: {
          representation_sync: { status: 'synchronized', rebuilt: [] },
        },
      }]
      return {} as any
    })
    vi.spyOn(courseStore, 'refreshCourseData').mockResolvedValue()
    vi.spyOn(progressStore, 'loadRuntime').mockResolvedValue(null)

    expect(wrapper.get('[data-scope="current_block"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.findAll('.personalization-scope button')).toHaveLength(3)
    await wrapper.findAll('.personalization-direction-chip')[1]!.trigger('click')
    await wrapper.get('.personalization-feedback').setValue('请补充推导过程')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()

    expect(createPlan).toHaveBeenCalledWith(expect.objectContaining({
      sectionId: 'node-1',
      blockId: 'block-1',
      scopeSelection: 'current_block',
      expectedDocumentRevision: 'cdr-1',
      expectedBlockRevision: 'cbr-1',
      direction: 'expand',
    }))
    expect(wrapper.findAll('.personalization-diff-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('调整后正文')

    await wrapper.get('.personalization-apply').trigger('click')
    await flushPromises()

    expect(accept).toHaveBeenCalledWith(
      'adjustment-plan-1',
      'current',
      ['operation-1'],
    )
    expect(wrapper.emitted('blockApplied')).toEqual([[blockTarget]])
    expect(wrapper.get('.personalization-apply-receipt').text()).toContain('block-1')
  })

  it('当前小节找到多处后自动转入居中审阅任务', async () => {
    const blockTarget = personalizationTarget()
    const wrapper = mountPanel([], '', blockTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const evolutionStore = useCourseEvolutionStore()
    evolutionStore.applyPayload('course-1', {
      evidence_items: [],
      hypotheses: [],
      course_evolution_plans: [],
    })
    vi.spyOn(evolutionStore, 'createPlan').mockImplementation(async () => {
      evolutionStore.plans = [{
        change_set_id: 'section-plan-1',
        hypothesis_id: 'hypothesis-1',
        source_kind: 'manual_section_request',
        target_section_id: 'node-1',
        request_text: '调整本节',
        generation_status: 'ready',
        evidence_ids: [],
        operations: [1, 2].map(index => ({
          operation_id: `operation-${index}`,
          operation_type: 'REPLACE_COURSE_BLOCK',
          target_block_id: `block-${index}`,
          target_section_id: 'node-1',
          scope: 'current',
          reason: '协同调整',
          payload: { candidate_status: 'ready' },
        })),
        scope_selection: 'current_section',
        allowed_scopes: ['current'],
        impact_summary: { affected_section_ids: ['node-1'] },
        expected_effect: '本节更清楚',
        status: 'pending',
        effect_evaluation: {},
      }]
      return {} as any
    })

    await wrapper.get('[data-scope="current_section"]').trigger('click')
    await wrapper.get('.personalization-feedback').setValue('把本节相关解释都讲清楚')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('clearBlockTarget')).toHaveLength(1)
    expect(wrapper.find('.personalization-diff-card').exists()).toBe(false)
  })

  it('重新打开正文入口会恢复同一条未处理课程调整任务', async () => {
    const wrapper = mountPanel()
    const evolutionStore = useCourseEvolutionStore()
    const target = personalizationTarget('block-resume', 'cbr-resume')
    evolutionStore.applyPayload('course-1', {
      evidence_items: [],
      hypotheses: [],
      course_evolution_plans: [{
        change_set_id: 'resume-plan',
        hypothesis_id: 'hypothesis-resume',
        source_kind: 'manual_request',
        target_section_id: 'node-1',
        request_text: '换一种直观讲法',
        generation_status: 'ready',
        evidence_ids: [],
        operations: [{
          operation_id: 'resume-operation',
          operation_type: 'REPLACE_COURSE_BLOCK',
          target_block_id: 'block-resume',
          target_section_id: 'node-1',
          scope: 'current',
          reason: '恢复原任务',
          payload: {
            candidate_status: 'ready',
            before_block: target.block,
            proposed_block: {
              ...target.block,
              payload: { ...target.block.payload, markdown: '已恢复的候选正文' },
            },
          },
        }],
        scope_selection: 'current_block',
        allowed_scopes: ['current'],
        impact_summary: {
          anchor_block_id: 'block-resume',
          affected_section_ids: ['node-1'],
          scene_analysis: { direction: 'simplify' },
        },
        expected_effect: '更直观',
        status: 'pending',
        effect_evaluation: {},
      }],
    })

    await wrapper.setProps({ blockTarget: target, prefill: '' })
    await flushPromises()

    expect(wrapper.findAll('.personalization-diff-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('已恢复的候选正文')
    expect((wrapper.get('.personalization-item-check').element as HTMLInputElement).checked).toBe(true)
  })

  it('kg_node 变更提案条目展示接受按钮，并提示接受后仅记录复核备注', () => {
    const wrapper = mountPanel()
    const changeProposalsStore = useChangeProposalsStore()
    changeProposalsStore.courseId = 'course-1'
    const kgNodeProposal: ChangeProposal = {
      proposal_id: 'proposal-kg-1',
      course_id: 'course-1',
      scope: 'block',
      target_block_ids: ['math.la.system.gaussian_elimination'],
      source: 'kb_link',
      status: 'pending',
      created_at: '2026-07-15T00:00:00Z',
      items: [
        {
          item_id: 'item-kg-1',
          block_id: 'math.la.system.gaussian_elimination',
          target_kind: 'kg_node',
          before: '高斯消元法',
          after: '高斯消元法（更新定义）',
          reason: '内容变更同步到知识库节点',
          status: 'pending',
        },
      ],
    }
    changeProposalsStore.proposals = [kgNodeProposal]

    return flushPromises().then(() => {
      const card = wrapper.get('.change-proposal-card')
      expect(card.find('.change-item-unsupported-note').exists()).toBe(true)
      expect(card.text()).toContain('该建议涉及知识库节点：接受后仅会在知识库目录上记录一条待人工复核的备注，不会自动改写知识节点的正式定义。')
      expect(card.findAll('.change-item-actions .primary-command')).toHaveLength(1)
      expect(card.text()).toContain('拒绝')
    })
  })

  it('after 为空（待重新生成）的条目不渲染空白 diff，且禁用接受按钮', () => {
    const wrapper = mountPanel()
    const changeProposalsStore = useChangeProposalsStore()
    changeProposalsStore.courseId = 'course-1'
    const awaitingProposal: ChangeProposal = {
      proposal_id: 'proposal-evidence-1',
      course_id: 'course-1',
      scope: 'block',
      target_block_ids: ['block-1'],
      source: 'evidence',
      status: 'pending',
      created_at: '2026-07-15T00:00:00Z',
      items: [
        {
          item_id: 'item-awaiting-1',
          block_id: 'block-1',
          target_kind: 'course_block',
          before: '旧正文',
          after: null,
          reason: '学习证据触发变更',
          status: 'pending',
        },
      ],
    }
    changeProposalsStore.proposals = [awaitingProposal]

    return flushPromises().then(() => {
      const card = wrapper.get('.change-proposal-card')
      expect(card.find('.diff-awaiting-generation').exists()).toBe(true)
      expect(card.text()).toContain('该条目正在等待重新生成，请稍后刷新或联系管理员。')
      expect(card.find('.diff-after').exists()).toBe(false)
      const acceptButton = card.get('.change-item-actions .primary-command')
      expect((acceptButton.element as HTMLButtonElement).disabled).toBe(true)
    })
  })

  it('点击拒绝/重新生成按钮后展开对应条目的输入面板', () => {
    const wrapper = mountPanel()
    const changeProposalsStore = useChangeProposalsStore()
    changeProposalsStore.courseId = 'course-1'
    const proposal: ChangeProposal = {
      proposal_id: 'proposal-1',
      course_id: 'course-1',
      scope: 'block',
      target_block_ids: ['block-1'],
      source: 'evidence',
      status: 'pending',
      created_at: '2026-07-15T00:00:00Z',
      items: [
        {
          item_id: 'item-1',
          block_id: 'block-1',
          target_kind: 'course_block',
          before: '旧正文',
          after: '新正文',
          reason: '学习证据触发变更',
          status: 'pending',
        },
      ],
    }
    changeProposalsStore.proposals = [proposal]

    return flushPromises().then(async () => {
      const card = wrapper.get('.change-proposal-card')
      expect(card.find('.change-item-prompt').exists()).toBe(false)
      const rejectButtons = card.findAll('.change-item-actions .secondary-command')
      expect(rejectButtons.length).toBeGreaterThan(0)
      await rejectButtons[0]!.trigger('click')
      expect(card.find('.change-item-prompt').exists()).toBe(true)
    })
  })

  it('renders structured proposal payloads as readable markdown', async () => {
    const wrapper = mountPanel()
    const changeProposalsStore = useChangeProposalsStore()
    changeProposalsStore.courseId = 'course-1'
    changeProposalsStore.proposals = [{
      proposal_id: 'proposal-structured-1',
      course_id: 'course-1',
      scope: 'section',
      target_block_ids: ['block-1'],
      source: 'evidence',
      status: 'pending',
      created_at: '2026-07-16T00:00:00Z',
      items: [{
        item_id: 'item-structured-1',
        block_id: 'block-1',
        target_kind: 'course_block',
        before: {
          title: 'internal old title',
          markdown: 'visible original markdown',
          summary: 'internal old summary',
        },
        after: {
          payload: {
            title: 'internal new title',
            markdown: 'visible regenerated markdown',
            summary: 'internal new summary',
          },
        },
        reason: 'improve the explanation',
        status: 'pending',
      }],
    } as unknown as ChangeProposal]

    await flushPromises()

    const cardText = wrapper.get('.change-proposal-card').text()
    expect(cardText).toContain('visible original markdown')
    expect(cardText).toContain('visible regenerated markdown')
    expect(cardText).not.toContain('payload')
    expect(cardText).not.toContain('internal old title')
    expect(cardText).not.toContain('internal new summary')
  })

  it('英文移动模式完整呈现块级范围选择且没有中文回退文案', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/')
        ? enMessages
        : zhMessages,
    })))
    await setLocale('en')
    Object.defineProperty(window, 'innerWidth', { value: 390, configurable: true })

    try {
      const wrapper = mountPanel([], '', personalizationTarget())
      expect(wrapper.get('.ai-teacher-panel').classes()).toContain('is-overlay')
      expect(wrapper.get('[data-scope="current_block"]').text()).toContain(
        'Current content only',
      )
      expect(wrapper.get('[data-scope="current_section"]').text()).toContain(
        'Adjust current section',
      )
      expect(wrapper.get('[data-scope="whole_course"]').text()).toContain(
        'Apply to matching content across the course',
      )
      expect(wrapper.text()).not.toContain('应用范围')
    } finally {
      await setLocale('zh')
      vi.unstubAllGlobals()
    }
  })
})
