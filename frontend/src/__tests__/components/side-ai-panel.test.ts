import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SideAIPanel from '@/components/SideAIPanel.vue'
import { useAITeacherStore, type AIConversation } from '@/stores/aiTeacher'
import { useCourseStore } from '@/stores/course'
import { useLearningProgressStore } from '@/stores/learningProgress'
import { useChangeProposalsStore } from '@/stores/changeProposals'
import type { ChangeProposal } from '@/types/changeProposal'
import type { BlockRegenerationCandidate, CourseBlockEditTarget } from '@/stores/types'

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

  it('在移动视口使用同一 AI 工作区的覆盖形态', () => {
    Object.defineProperty(window, 'innerWidth', { value: 390, configurable: true })
    const wrapper = mountPanel()

    expect(wrapper.get('.ai-teacher-panel').classes()).toContain('is-overlay')
    expect(wrapper.find('.ai-teacher-backdrop').exists()).toBe(true)
    expect(wrapper.find('.ai-teacher-surface').exists()).toBe(true)
    expect(wrapper.findAll('.quick-actions button')).toHaveLength(2)
  })

  it('在右侧 AI 老师内预览候选，确认后才应用正式课程块', async () => {
    const blockTarget: CourseBlockEditTarget = {
      nodeId: 'node-1',
      nodeName: '向量空间与线性相关',
      block: {
        block_id: 'block-1', section_id: 'node-1', position: 0, kind: 'rich_text', role: 'concept',
        payload: { title: '线性相关定义', markdown: '旧正文' }, asset_refs: [], objective_refs: ['lo-1'],
        concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-1', status: 'final',
      },
    }
    const candidate: BlockRegenerationCandidate = {
      candidate_id: 'candidate-1', request_id: 'request-1', course_id: 'course-1', block_id: 'block-1', section_id: 'node-1',
      status: 'ready', action_type: 'rewrite', instruction: '把定义讲得更清楚',
      expected_document_revision: 'cdr-1', expected_block_revision: 'cbr-1',
      proposed_block: { ...blockTarget.block, payload: { title: '线性相关定义', markdown: '经过检查的新正文' } },
      quality_report: { passed: true, status: 'passed', gates: [], issues: [] },
      attempts: [{ attempt: 1, quality_report: { passed: true, status: 'passed', gates: [], issues: [] } }],
    }
    const wrapper = mountPanel([], '', blockTarget)
    const courseStore = useCourseStore()
    vi.spyOn(courseStore, 'createBlockRegenerationCandidate').mockResolvedValue(candidate)
    vi.spyOn(courseStore, 'applyBlockRegenerationCandidate').mockResolvedValue({
      candidate: { ...candidate, status: 'applied', receipt: { command_id: 'apply-candidate-1' } },
      receipt: { command_id: 'apply-candidate-1' },
      document: {} as any,
    })

    expect(wrapper.find('.conversation-shell').exists()).toBe(false)
    expect(wrapper.find('.block-edit-workspace').exists()).toBe(true)
    expect(wrapper.text()).toContain('旧正文')

    await wrapper.get('textarea').setValue('把定义讲得更清楚')
    await wrapper.get('.send-button').trigger('click')
    await flushPromises()

    expect(courseStore.createBlockRegenerationCandidate).toHaveBeenCalledWith(blockTarget, '把定义讲得更清楚')
    expect(wrapper.find('.block-candidate-preview').text()).toContain('经过检查的新正文')
    expect(wrapper.find('.block-candidate-actions .primary-command').exists()).toBe(true)

    await wrapper.get('.block-candidate-actions .primary-command').trigger('click')
    await flushPromises()

    expect(courseStore.applyBlockRegenerationCandidate).toHaveBeenCalledWith(candidate)
    expect(wrapper.emitted('blockApplied')).toEqual([[blockTarget]])
    expect(wrapper.find('.block-applied-receipt').exists()).toBe(true)
  })

  it('重新打开正文工具时找回中断候选，并继续同一个候选', async () => {
    const blockTarget: CourseBlockEditTarget = {
      nodeId: 'node-1',
      nodeName: '向量空间与线性相关',
      block: {
        block_id: 'block-1', section_id: 'node-1', position: 0, kind: 'rich_text', role: 'concept',
        payload: { title: '线性相关定义', markdown: '旧正文' }, asset_refs: [], objective_refs: ['lo-1'],
        concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-1', status: 'final',
      },
    }
    const interrupted: BlockRegenerationCandidate = {
      candidate_id: 'candidate-interrupted', request_id: 'request-interrupted', course_id: 'course-1',
      block_id: 'block-1', section_id: 'node-1', status: 'generation_failed', action_type: 'rewrite',
      instruction: '把定义讲得更清楚', expected_document_revision: 'cdr-1', expected_block_revision: 'cbr-1',
      proposed_block: { ...blockTarget.block }, quality_report: null, attempts: [], retryable: true,
      failure_code: 'process_interrupted', failure_reason: '这段后端原始文案不应直接展示',
    }
    const ready: BlockRegenerationCandidate = {
      ...interrupted,
      status: 'ready',
      proposed_block: { ...blockTarget.block, payload: { ...blockTarget.block.payload, markdown: '恢复后生成的新正文' } },
      quality_report: { passed: true, status: 'passed', gates: [], issues: [] },
      attempts: [{ attempt: 1, quality_report: { passed: true, status: 'passed', gates: [], issues: [] } }],
    }
    let latest: any
    let retry: any
    const wrapper = mountPanel([], '', blockTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
      latest = vi.spyOn(store, 'getLatestBlockRegenerationCandidate').mockResolvedValue(interrupted)
      retry = vi.spyOn(store, 'retryBlockRegenerationCandidate').mockResolvedValue(ready)
    })
    await flushPromises()

    expect(latest!).toHaveBeenCalledWith(blockTarget)
    expect(wrapper.text()).toContain('生成已中断，可继续')
    expect(wrapper.text()).toContain('生成服务曾中断，请从当前候选继续')
    expect(wrapper.text()).not.toContain('这段后端原始文案不应直接展示')
    await wrapper.get('.block-candidate-actions .primary-command').trigger('click')
    await flushPromises()

    expect(retry!).toHaveBeenCalledWith(interrupted)
    expect(wrapper.find('.block-candidate-preview').text()).toContain('恢复后生成的新正文')
  })

  it('kg_node 变更提案条目不展示接受按钮，改为提示人工核对知识库', () => {
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
      expect(card.text()).toContain('该建议涉及知识库节点，暂不支持在线接受，请人工核对知识库后处理。')
      expect(card.findAll('.change-item-actions .primary-command')).toHaveLength(0)
      expect(card.text()).toContain('拒绝')
    })
  })
})
