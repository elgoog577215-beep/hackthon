import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SideAIPanel from '@/components/SideAIPanel.vue'
import { useAITeacherStore, type AIConversation } from '@/stores/aiTeacher'
import { useCourseStore } from '@/stores/course'
import { useLearningProgressStore } from '@/stores/learningProgress'
import { useChangeProposalsStore } from '@/stores/changeProposals'
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

function personalizationProposal(target: CourseBlockEditTarget, itemCount = 3): ChangeProposal {
  const relatedBlocks = [
    target.block,
    {
      ...target.block,
      block_id: 'block-2',
      role: 'example' as const,
      payload: { title: '相关例子', markdown: '旧例子' },
      internal_revision: 'cbr-2',
    },
    {
      ...target.block,
      block_id: 'block-3',
      role: 'summary' as const,
      payload: { title: '相关小结', markdown: '旧小结' },
      internal_revision: 'cbr-3',
    },
  ].slice(0, itemCount)
  return {
    proposal_id: 'personalization-1',
    course_id: 'course-1',
    scope: 'section',
    target_block_ids: relatedBlocks.map(block => block.block_id),
    source: 'personalization',
    status: 'pending',
    created_at: '2026-07-18T00:00:00Z',
    generation_meta: { base_document_revision: 'cdr-1', direction: 'expand' },
    items: relatedBlocks.map((block, index) => ({
      item_id: `item-${index + 1}`,
      block_id: block.block_id,
      before: block,
      after: { ...block, payload: { ...block.payload, markdown: `优化后正文 ${index + 1}` } },
      reason: index === 0 ? '直接响应反馈' : '同步相关课程块',
      selected: true,
      expected_block_revision: block.internal_revision,
      status: 'pending',
    })),
  }
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

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
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
    vi.spyOn(aiStore, 'sendMessage').mockResolvedValue()
    const refreshRuntime = vi.spyOn(progressStore, 'loadRuntime').mockResolvedValue(null)

    await wrapper.get('textarea').setValue('为什么是先做右边的变换？')
    await wrapper.get('.send-button').trigger('click')
    await flushPromises()

    expect(aiStore.sendMessage).toHaveBeenCalledWith(expect.objectContaining({
      courseId: 'course-1',
      nodeId: 'node-1',
      question: '为什么是先做右边的变换？',
    }))
    expect(refreshRuntime).toHaveBeenCalledWith('course-1', 'node-1')
  })

  it('在移动视口使用同一 AI 工作区的覆盖形态', () => {
    Object.defineProperty(window, 'innerWidth', { value: 390, configurable: true })
    const wrapper = mountPanel()

    expect(wrapper.get('.ai-teacher-panel').classes()).toContain('is-overlay')
    expect(wrapper.find('.ai-teacher-backdrop').exists()).toBe(true)
    expect(wrapper.find('.ai-teacher-surface').exists()).toBe(true)
    expect(wrapper.findAll('.quick-actions button')).toHaveLength(2)
  })

  it('在唯一个性化分区生成 1–3 项对比，默认勾选并一次应用所选项', async () => {
    const blockTarget: CourseBlockEditTarget = {
      nodeId: 'node-1',
      nodeName: '向量空间与线性相关',
      block: {
        block_id: 'block-1', section_id: 'node-1', position: 0, kind: 'rich_text', role: 'concept',
        payload: { title: '线性相关定义', markdown: '旧正文' }, asset_refs: [], objective_refs: ['lo-1'],
        concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-1', status: 'final',
      },
    }
    const proposal = personalizationProposal(blockTarget)
    const wrapper = mountPanel([], '', blockTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const courseStore = useCourseStore()
    const changeProposalsStore = useChangeProposalsStore()
    const createProposal = vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockResolvedValue(proposal)
    const applySelected = vi.spyOn(changeProposalsStore, 'applySelectedItems').mockResolvedValue({
      proposal: {
        ...proposal,
        status: 'resolved',
        items: proposal.items.map(item => ({ ...item, status: 'applied' })),
      },
      receipt: { affected_block_ids: ['block-1', 'block-3'] },
      document: {
        course_id: 'course-1',
        document: { course_id: 'course-1', title: '课程', document_revision: 'cdr-2', sections: [], blocks: [] },
      } as any,
      representation_sync: { status: 'synchronized', rebuilt: [] },
    })
    const refreshCourse = vi.spyOn(courseStore, 'refreshCourseData').mockResolvedValue()

    expect(wrapper.find('.conversation-shell').exists()).toBe(false)
    expect(wrapper.findAll('.personalization-workspace')).toHaveLength(1)
    expect(wrapper.find('.block-edit-workspace').exists()).toBe(false)
    expect(wrapper.text()).toContain('旧正文')
    expect(wrapper.findAll('.personalization-direction-chip')).toHaveLength(3)

    await wrapper.findAll('.personalization-direction-chip')[1]!.trigger('click')
    await wrapper.get('.personalization-feedback').setValue('请补充推导过程')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()

    expect(createProposal).toHaveBeenCalledWith(expect.objectContaining({
      courseId: 'course-1',
      blockId: 'block-1',
      expectedDocumentRevision: 'cdr-1',
      expectedBlockRevision: 'cbr-1',
      direction: 'expand',
      feedback: '请补充推导过程',
    }))
    expect(wrapper.findAll('.personalization-diff-card')).toHaveLength(3)
    expect(wrapper.findAll('.personalization-item-check').every(check => (
      (check.element as HTMLInputElement).checked
    ))).toBe(true)
    expect(wrapper.text()).toContain('优化后正文 1')

    await wrapper.findAll('.personalization-item-check')[1]!.setValue(false)
    await wrapper.get('.personalization-apply').trigger('click')
    await flushPromises()

    expect(applySelected).toHaveBeenCalledTimes(1)
    expect(applySelected).toHaveBeenCalledWith('personalization-1', ['item-1', 'item-3'], 'cdr-1')
    expect(refreshCourse).toHaveBeenCalledWith('course-1')
    expect(wrapper.emitted('blockApplied')).toEqual([[blockTarget]])
    expect(wrapper.get('.personalization-apply-receipt').text()).toContain('block-1')
    expect(wrapper.get('.personalization-apply-receipt').text()).toContain('表示同步')
  })

  it('取消全部对比项后禁用应用所选优化', async () => {
    const blockTarget: CourseBlockEditTarget = {
      nodeId: 'node-1',
      nodeName: '向量空间与线性相关',
      block: {
        block_id: 'block-1', section_id: 'node-1', position: 0, kind: 'rich_text', role: 'concept',
        payload: { title: '线性相关定义', markdown: '旧正文' }, asset_refs: [], objective_refs: ['lo-1'],
        concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-1', status: 'final',
      },
    }
    const wrapper = mountPanel([], '', blockTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockResolvedValue(
      personalizationProposal(blockTarget, 1),
    )

    await wrapper.get('.personalization-feedback').setValue('请按我的理解方式调整')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.personalization-diff-card')).toHaveLength(1)
    for (const checkbox of wrapper.findAll('.personalization-item-check')) {
      await checkbox.setValue(false)
    }
    expect((wrapper.get('.personalization-apply').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('应用前发现提案版本已过期时不发送请求，并使旧提案失效', async () => {
    const target = personalizationTarget()
    const proposal = personalizationProposal(target, 1)
    const wrapper = mountPanel([], '', target, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const courseStore = useCourseStore()
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockResolvedValue(proposal)
    const applySelected = vi.spyOn(changeProposalsStore, 'applySelectedItems').mockResolvedValue({} as any)

    await wrapper.get('.personalization-feedback').setValue('请补充推导过程')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()
    courseStore.currentDocumentRevision = 'cdr-2'
    await wrapper.get('.personalization-apply').trigger('click')
    await flushPromises()

    expect(applySelected).not.toHaveBeenCalled()
    expect(wrapper.find('.personalization-diff-card').exists()).toBe(false)
    expect(wrapper.get('.personalization-error').text()).toContain('课程内容已变化')
  })

  it('提案生成后锁定输入，prefill 变化会清除旧提案', async () => {
    const target = personalizationTarget()
    const wrapper = mountPanel([], '', target, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockResolvedValue(
      personalizationProposal(target, 1),
    )

    await wrapper.get('.personalization-feedback').setValue('初始反馈')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()

    expect((wrapper.get('.personalization-direction-chip').element as HTMLButtonElement).disabled).toBe(true)
    expect((wrapper.get('.personalization-feedback').element as HTMLTextAreaElement).disabled).toBe(true)

    await wrapper.setProps({ prefill: '新的反馈' })
    await flushPromises()

    expect(wrapper.find('.personalization-diff-card').exists()).toBe(false)
    expect((wrapper.get('.personalization-feedback').element as HTMLTextAreaElement).value).toBe('新的反馈')
  })

  it('在同一内容生成进行中时显示专属 503 提示，而不是课程冲突', async () => {
    const blockTarget = personalizationTarget()
    const wrapper = mountPanel([], '', blockTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockRejectedValue({
      response: { status: 503, data: { detail: { code: 'personalization_generation_in_progress' } } },
    })

    await wrapper.get('.personalization-feedback').setValue('请补充推导过程')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()

    expect(wrapper.get('.personalization-error').text()).toContain('同一内容的优化正在生成')
    expect(wrapper.text()).not.toContain('课程内容已变化')
  })

  it('在新目标已得到结果后忽略旧生成请求的成功写回', async () => {
    const first = deferred<ChangeProposal>()
    const second = deferred<ChangeProposal>()
    const firstTarget = personalizationTarget('block-1', 'cbr-1')
    const secondTarget = personalizationTarget('block-2', 'cbr-2')
    const wrapper = mountPanel([], '', firstTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal')
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)

    await wrapper.get('.personalization-feedback').setValue('优化第一个正文')
    await wrapper.get('.personalization-generate').trigger('click')
    await wrapper.setProps({ blockTarget: secondTarget })
    await wrapper.get('.personalization-feedback').setValue('优化第二个正文')
    await wrapper.get('.personalization-generate').trigger('click')
    second.resolve({ ...personalizationProposal(secondTarget, 1), proposal_id: 'personalization-2' })
    await flushPromises()

    first.resolve(personalizationProposal(firstTarget, 1))
    await flushPromises()

    expect(wrapper.get('.personalization-diff-card').text()).toContain('正文 block-2')
    expect(wrapper.get('.personalization-diff-card').text()).not.toContain('正文 block-1')
  })

  it('在新目标已得到结果后忽略旧生成请求的失败写回', async () => {
    const first = deferred<ChangeProposal>()
    const firstTarget = personalizationTarget('block-1', 'cbr-1')
    const secondTarget = personalizationTarget('block-2', 'cbr-2')
    const wrapper = mountPanel([], '', firstTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal')
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValueOnce({ ...personalizationProposal(secondTarget, 1), proposal_id: 'personalization-2' })

    await wrapper.get('.personalization-feedback').setValue('优化第一个正文')
    await wrapper.get('.personalization-generate').trigger('click')
    await wrapper.setProps({ blockTarget: secondTarget })
    await wrapper.get('.personalization-feedback').setValue('优化第二个正文')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()

    first.reject({ response: { status: 503, data: { detail: { code: 'personalization_generation_in_progress' } } } })
    await flushPromises()

    expect(wrapper.find('.personalization-error').exists()).toBe(false)
    expect(wrapper.get('.personalization-diff-card').text()).toContain('正文 block-2')
  })

  it('切换目标后不让旧生成请求的 loading 禁用新目标', async () => {
    const first = deferred<ChangeProposal>()
    const firstTarget = personalizationTarget('block-1', 'cbr-1')
    const secondTarget = personalizationTarget('block-2', 'cbr-2')
    const wrapper = mountPanel([], '', firstTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockImplementation(async () => {
      changeProposalsStore.personalizationLoading = true
      try {
        return await first.promise
      } finally {
        changeProposalsStore.personalizationLoading = false
      }
    })

    await wrapper.get('.personalization-feedback').setValue('优化第一个正文')
    await wrapper.get('.personalization-generate').trigger('click')
    await wrapper.setProps({ blockTarget: secondTarget })
    await flushPromises()

    expect((wrapper.get('.personalization-generate').element as HTMLButtonElement).disabled).toBe(false)

    first.resolve(personalizationProposal(firstTarget, 1))
    await flushPromises()
  })

  it('同一课程块的文档版本变化后，旧生成成功不写回但清理自身 busy', async () => {
    const first = deferred<ChangeProposal>()
    const target = personalizationTarget('block-1', 'cbr-1')
    const wrapper = mountPanel([], '', target, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const courseStore = useCourseStore()
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockReturnValue(first.promise)

    await wrapper.get('.personalization-feedback').setValue('优化正文')
    await wrapper.get('.personalization-generate').trigger('click')
    courseStore.currentDocumentRevision = 'cdr-2'
    first.resolve(personalizationProposal(target, 1))
    await flushPromises()

    expect(wrapper.find('.personalization-diff-card').exists()).toBe(false)
    expect((wrapper.get('.personalization-generate').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('同一课程块的文档版本变化后，旧生成失败不写错错误但清理自身 busy', async () => {
    const first = deferred<ChangeProposal>()
    const target = personalizationTarget('block-1', 'cbr-1')
    const wrapper = mountPanel([], '', target, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const courseStore = useCourseStore()
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockReturnValue(first.promise)

    await wrapper.get('.personalization-feedback').setValue('优化正文')
    await wrapper.get('.personalization-generate').trigger('click')
    courseStore.currentDocumentRevision = 'cdr-2'
    first.reject({ response: { status: 503, data: { detail: { code: 'personalization_generation_in_progress' } } } })
    await flushPromises()

    expect(wrapper.find('.personalization-error').exists()).toBe(false)
    expect((wrapper.get('.personalization-generate').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('请求中 prefill 变化后不展示旧提案，并清理旧 attempt 的 busy', async () => {
    const pending = deferred<ChangeProposal>()
    const target = personalizationTarget('block-1', 'cbr-1')
    const wrapper = mountPanel([], '', target, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockReturnValue(pending.promise)

    await wrapper.get('.personalization-feedback').setValue('初始反馈')
    await wrapper.get('.personalization-generate').trigger('click')
    await wrapper.setProps({ prefill: '新的反馈' })
    pending.resolve(personalizationProposal(target, 1))
    await flushPromises()

    expect(wrapper.find('.personalization-diff-card').exists()).toBe(false)
    expect((wrapper.get('.personalization-generate').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('切换目标后不让旧应用请求的 loading 禁用新目标', async () => {
    const applied = deferred<any>()
    const firstTarget = personalizationTarget('block-1', 'cbr-1')
    const secondTarget = personalizationTarget('block-2', 'cbr-2')
    const proposal = personalizationProposal(firstTarget, 1)
    const wrapper = mountPanel([], '', firstTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const courseStore = useCourseStore()
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockResolvedValue(proposal)
    vi.spyOn(courseStore, 'refreshCourseData').mockResolvedValue()
    vi.spyOn(changeProposalsStore, 'applySelectedItems').mockImplementation(async () => {
      changeProposalsStore.applyingSelected = true
      try {
        return await applied.promise
      } finally {
        changeProposalsStore.applyingSelected = false
      }
    })

    await wrapper.get('.personalization-feedback').setValue('优化第一个正文')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()
    await wrapper.get('.personalization-apply').trigger('click')
    await wrapper.setProps({ blockTarget: secondTarget })
    await flushPromises()

    expect((wrapper.get('.personalization-generate').element as HTMLButtonElement).disabled).toBe(false)

    applied.resolve({
      proposal: { ...proposal, status: 'resolved' },
      receipt: { affected_block_ids: ['block-1'] },
      document: {
        course_id: 'course-1',
        document: { course_id: 'course-1', title: '课程', document_revision: 'cdr-2', sections: [], blocks: [] },
      },
      representation_sync: { status: 'synchronized', rebuilt: [] },
    })
    await flushPromises()
  })

  it('立即写回 apply 返回的课程 envelope，并在刷新失败后保留成功回执', async () => {
    const blockTarget = personalizationTarget()
    const proposal = personalizationProposal(blockTarget, 1)
    const wrapper = mountPanel([], '', blockTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const courseStore = useCourseStore()
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockResolvedValue(proposal)
    const document = {
      course_id: 'course-1',
      document: { course_id: 'course-1', title: '课程', document_revision: 'cdr-2', sections: [], blocks: [] },
    } as any
    vi.spyOn(changeProposalsStore, 'applySelectedItems').mockResolvedValue({
      proposal: { ...proposal, status: 'resolved' },
      receipt: { affected_block_ids: ['block-1'] },
      document,
      representation_sync: { status: 'synchronized', rebuilt: [] },
    })
    const applyEnvelope = vi.spyOn(courseStore, 'applyCourseDocumentEnvelope').mockImplementation(() => {
      courseStore.currentDocumentRevision = 'cdr-2'
    })
    vi.spyOn(courseStore, 'refreshCourseData').mockRejectedValue(new Error('refresh unavailable'))

    await wrapper.get('.personalization-feedback').setValue('请补充推导过程')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()
    await wrapper.get('.personalization-apply').trigger('click')
    await flushPromises()

    expect(applyEnvelope).toHaveBeenCalledWith(document)
    expect(wrapper.emitted('blockApplied')).toEqual([[blockTarget]])
    expect(wrapper.find('.personalization-apply-receipt').exists()).toBe(true)
    expect(wrapper.find('.personalization-error').exists()).toBe(false)
    expect((wrapper.vm as any).personalizationApplying).toBe(false)
  })

  it('不把旧课程的 apply 成功写入切换后的目标或课程状态', async () => {
    const applied = deferred<any>()
    const firstTarget = personalizationTarget('block-1', 'cbr-1')
    const secondTarget = personalizationTarget('block-2', 'cbr-2')
    const proposal = personalizationProposal(firstTarget, 1)
    const wrapper = mountPanel([], '', firstTarget, store => {
      store.currentDocumentRevision = 'cdr-1'
    })
    const courseStore = useCourseStore()
    const changeProposalsStore = useChangeProposalsStore()
    vi.spyOn(changeProposalsStore, 'createPersonalizationProposal').mockResolvedValue(proposal)
    vi.spyOn(changeProposalsStore, 'applySelectedItems').mockImplementation(() => applied.promise)
    const applyEnvelope = vi.spyOn(courseStore, 'applyCourseDocumentEnvelope').mockImplementation(() => {})

    await wrapper.get('.personalization-feedback').setValue('请补充推导过程')
    await wrapper.get('.personalization-generate').trigger('click')
    await flushPromises()
    await wrapper.get('.personalization-apply').trigger('click')
    courseStore.currentCourseId = 'course-2'
    courseStore.currentDocumentRevision = 'cdr-2'
    await wrapper.setProps({ blockTarget: secondTarget })

    applied.resolve({
      proposal: { ...proposal, status: 'resolved' },
      receipt: { affected_block_ids: ['block-1'] },
      document: {
        course_id: 'course-1',
        document: { course_id: 'course-1', title: '课程', document_revision: 'cdr-2', sections: [], blocks: [] },
      },
      representation_sync: { status: 'synchronized', rebuilt: [] },
    })
    await flushPromises()

    expect(applyEnvelope).not.toHaveBeenCalled()
    expect(wrapper.find('.personalization-apply-receipt').exists()).toBe(false)
    expect(wrapper.emitted('blockApplied')).toBeUndefined()
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
})
