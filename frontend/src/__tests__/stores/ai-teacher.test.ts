import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { isReactive } from 'vue'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  withApiBase: (path: string) => path,
  learnerIdentityHeaders: (initial: HeadersInit = {}) => new Headers(initial),
}))

import { useAITeacherStore, type AIMessage } from '@/stores/aiTeacher'
import { useLearningProgressStore } from '@/stores/learningProgress'

const emptyConversation = {
  conversation_id: 'aic-1',
  course_id: 'course-1',
  course_version_id: 'cv-1',
  title: '新对话',
  revision: 1,
  retrieval_enabled: false,
  messages: [],
  created_at: '2026-07-12T00:00:00Z',
  updated_at: '2026-07-12T00:00:00Z',
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.restoreAllMocks()
  httpMock.get.mockReset()
  httpMock.post.mockReset()
  httpMock.patch.mockReset()
  httpMock.delete.mockReset()
})

describe('AI teacher store', () => {
  it('只发送引用和当前问题，并消费结构化 SSE', async () => {
    const serverConversation = {
      ...emptyConversation,
      revision: 3,
      messages: [
        { message_id: 'user-1', role: 'user', content: '变量是什么？', status: 'complete' },
        {
          message_id: 'assistant-1', role: 'assistant', content: '变量用于保存可变化的值。', status: 'complete',
          retrieval_status: 'completed',
          retrieval_receipt: { status: 'completed', source_count: 1 },
          sources: [{ source_id: 'src-web-1', title: '变量定义', url: 'https://example.edu/variables' }],
        },
      ],
    }
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/ai-teacher/conversations') return Promise.resolve({ data: { conversations: [] } })
      if (url === '/api/ai-teacher/trigger') return Promise.resolve({ data: { candidate: null } })
      return Promise.resolve({ data: serverConversation })
    })
    httpMock.post.mockResolvedValue({ data: { ...emptyConversation } })
    const sse = [
      'event: context\ndata: {"conversation_id":"aic-1","user_message_id":"user-1","assistant_message_id":"assistant-1"}\n\n',
      'event: retrieval\ndata: {"status":"started"}\n\n',
      'event: retrieval\ndata: {"status":"completed","receipt":{"status":"completed","source_count":1}}\n\n',
      'event: sources\ndata: {"sources":[{"source_id":"src-web-1","title":"变量定义","url":"https://example.edu/variables"}]}\n\n',
      'event: answer\ndata: {"chunk":"变量用于保存"}\n\n',
      'event: final_answer\ndata: {"answer":"变量用于保存可变化的值。","message_id":"assistant-1"}\n\n',
      'event: done\ndata: {"conversation_id":"aic-1"}\n\n',
    ].join('')
    const fetchMock = vi.fn().mockResolvedValue(new Response(sse, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useAITeacherStore()
    let observedAssistantMessage: AIMessage | undefined
    let contentWhenQuestionRecorded = 'not-called'
    const onQuestionRecorded = vi.fn(() => {
      contentWhenQuestionRecorded = observedAssistantMessage?.content || ''
    })
    await store.load('course-1', 'node-1')
    await store.sendMessage({
      courseId: 'course-1',
      courseVersionId: 'cv-1',
      nodeId: 'node-1',
      nodeName: '变量',
      question: '变量是什么？',
      entrypoint: 'selection',
      selection: '变量用于保存可以变化的值',
      contextRef: { course_id: 'course-1', course_version_id: 'cv-1', node_id: 'node-1' },
      onAssistantMessage: message => { observedAssistantMessage = message },
      onQuestionRecorded,
    })

    const requestBody = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)
    expect(requestBody).toMatchObject({
      request_id: expect.stringMatching(/^local-user-/),
      course_id: 'course-1',
      conversation_id: 'aic-1',
      node_id: 'node-1',
      question: '变量是什么？',
      entrypoint: 'selection',
    })
    expect(requestBody).not.toHaveProperty('node_content')
    expect(requestBody).not.toHaveProperty('history')
    expect(requestBody).not.toHaveProperty('user_notes')
    expect(isReactive(observedAssistantMessage)).toBe(true)
    expect(onQuestionRecorded).toHaveBeenCalledTimes(1)
    expect(contentWhenQuestionRecorded).toBe('')
    expect(observedAssistantMessage?.status).toBe('complete')
    expect(store.messages.at(-1)?.content).toBe('变量用于保存可变化的值。')
    expect(store.messages.at(-1)?.sources?.[0]?.source_id).toBe('src-web-1')
    expect(store.messages.at(-1)?.retrieval_status).toBe('completed')
    expect(store.messages.at(-1)?.retrieval_receipt).toMatchObject({ source_count: 1 })
  })

  it('persists retrieval per conversation with optimistic revision control', async () => {
    const updated = { ...emptyConversation, revision: 2, retrieval_enabled: true }
    httpMock.patch.mockResolvedValue({ data: updated })
    const store = useAITeacherStore()
    store.courseId = 'course-1'
    store.conversations = [{ ...emptyConversation }]
    store.currentConversationId = 'aic-1'

    await store.updateRetrievalEnabled(true)

    expect(httpMock.patch).toHaveBeenCalledWith(
      '/api/ai-teacher/conversations/aic-1/settings',
      {
        course_id: 'course-1',
        retrieval_enabled: true,
        expected_revision: 1,
      },
    )
    expect(store.currentConversation?.retrieval_enabled).toBe(true)
    expect(store.currentConversation?.revision).toBe(2)
  })

  it('reloads the conversation when retrieval settings hit a revision conflict', async () => {
    const current = { ...emptyConversation, revision: 2, retrieval_enabled: false }
    httpMock.patch.mockRejectedValue({ response: { status: 409 } })
    httpMock.get.mockResolvedValue({ data: current })
    const store = useAITeacherStore()
    store.courseId = 'course-1'
    store.conversations = [{ ...emptyConversation }]
    store.currentConversationId = 'aic-1'

    await store.updateRetrievalEnabled(true)

    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/ai-teacher/conversations/aic-1',
      { params: { course_id: 'course-1' } },
    )
    expect(store.currentConversation?.retrieval_enabled).toBe(false)
    expect(store.currentConversation?.revision).toBe(2)
    expect(store.error).toBe('conversation_revision_conflict')
  })

  it('把块级回答效果反馈提交到所属会话消息', async () => {
    httpMock.post.mockResolvedValue({ data: { status: 'recorded', event_id: 'evt-1', feedback: 'resolved' } })
    const store = useAITeacherStore()
    store.courseId = 'course-1'
    store.currentConversationId = 'aic-1'

    await store.submitAnswerFeedback(
      { message_id: 'assistant-1', role: 'assistant', content: '解释内容', status: 'complete' },
      'resolved',
      {
        nodeId: 'node-1',
        nodeName: '变量',
        action: 'explain',
        contentAnchor: { block_id: 'block-1', block_revision_id: 'rev-1' },
      },
    )

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/ai-teacher/conversations/aic-1/messages/assistant-1/feedback',
      {
        course_id: 'course-1',
        feedback: 'resolved',
        node_id: 'node-1',
        node_name: '变量',
        action: 'explain',
        content_anchor: { block_id: 'block-1', block_revision_id: 'rev-1' },
      },
    )
  })

  it('保留分类后的模型失败代码与已经读到的半截回答', async () => {
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/ai-teacher/conversations') return Promise.resolve({ data: { conversations: [] } })
      return Promise.resolve({ data: { ...emptyConversation } })
    })
    httpMock.post.mockResolvedValue({ data: { ...emptyConversation } })
    const sse = [
      'event: context\ndata: {"conversation_id":"aic-1","user_message_id":"user-1","assistant_message_id":"assistant-1"}\n\n',
      'event: answer\ndata: {"chunk":"线性相关的意思是"}\n\n',
      'event: error\ndata: {"code":"model_rate_limited","message":"AI 模型当前繁忙，请稍后重试。","retryable":true}\n\n',
      'event: done\ndata: {"conversation_id":"aic-1"}\n\n',
    ].join('')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(sse, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })))

    const store = useAITeacherStore()
    let observed: AIMessage | undefined
    await store.sendMessage({
      courseId: 'course-1',
      question: '什么是线性相关？',
      onAssistantMessage: message => { observed = message },
    })

    expect(observed?.status).toBe('failed')
    expect(observed?.failure_code).toBe('model_rate_limited')
    expect(observed?.failure_retryable).toBe(true)
    // The partial answer must survive — the error copy does not overwrite it.
    expect(observed?.content).toBe('线性相关的意思是')
  })

  it('把不可重试的模型失败标记为不可重试', async () => {
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/ai-teacher/conversations') return Promise.resolve({ data: { conversations: [] } })
      return Promise.resolve({ data: { ...emptyConversation } })
    })
    httpMock.post.mockResolvedValue({ data: { ...emptyConversation } })
    const sse = [
      'event: context\ndata: {"conversation_id":"aic-1","assistant_message_id":"assistant-1"}\n\n',
      'event: error\ndata: {"code":"model_auth_failed","message":"AI 模型认证失败，请联系管理员检查密钥。","retryable":false}\n\n',
      'event: done\ndata: {"conversation_id":"aic-1"}\n\n',
    ].join('')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(sse, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })))

    const store = useAITeacherStore()
    let observed: AIMessage | undefined
    await store.sendMessage({
      courseId: 'course-1',
      question: '什么是线性相关？',
      onAssistantMessage: message => { observed = message },
    })

    expect(observed?.failure_code).toBe('model_auth_failed')
    expect(observed?.failure_retryable).toBe(false)
  })

  it('把被拒绝的确认当作真实回执，而不是成功动作', async () => {
    // The backend now answers every terminal confirm outcome with a receipt.
    // A `stale` receipt means nothing was written, so the proposal must not be
    // left looking succeeded and the runtime must not be reloaded.
    const runtimeStore = useLearningProgressStore()
    const runtimeSpy = vi.spyOn(runtimeStore, 'loadRuntime').mockResolvedValue(undefined as never)
    httpMock.post.mockResolvedValue({
      data: {
        receipt_id: 'air-1',
        proposal_id: 'aip-1',
        status: 'stale',
        result_code: 'runtime_changed',
        action_type: 'create_note',
        affected_refs: [],
        summary: '学习状态已经变化，请重新计算建议。',
        failure_reason: '学习状态已经变化，请重新计算建议。',
        undo_capability: 'none',
      },
    })
    const store = useAITeacherStore()
    store.courseId = 'course-1'
    const message: AIMessage = {
      message_id: 'assistant-1',
      role: 'assistant',
      content: '解释内容',
      status: 'complete',
      proposal: {
        proposal_id: 'aip-1',
        action_type: 'create_note',
        target_ref: { node_id: 'node-1' },
        payload_preview: {},
        reason: '',
        expected_effect: '创建一条学习笔记',
        confirmation_mode: 'explicit',
        runtime_revision_id: 'runtime-1',
        status: 'presented',
      },
    }

    const receipt = await store.confirmProposal(message)

    expect(receipt?.status).toBe('stale')
    expect(receipt?.result_code).toBe('runtime_changed')
    expect(message.proposal?.status).toBe('stale')
    expect(message.receipt_id).toBe('air-1')
    expect(runtimeSpy).not.toHaveBeenCalled()
  })

  it('拒绝的撤销保留原回执状态且不重载运行时', async () => {    const runtimeStore = useLearningProgressStore()
    const runtimeSpy = vi.spyOn(runtimeStore, 'loadRuntime').mockResolvedValue(undefined as never)
    httpMock.post.mockResolvedValue({
      data: {
        receipt_id: 'air-undo-1',
        proposal_id: 'aip-1',
        status: 'stale',
        result_code: 'undo_target_changed',
        action_type: 'undo_create_record',
        affected_refs: [],
        summary: '这条记录在创建之后被改动过，已保留你的修改。',
        failure_reason: '这条记录在创建之后被改动过，已保留你的修改。',
        undo_capability: 'none',
        undo_of_receipt_id: 'air-1',
      },
    })
    const store = useAITeacherStore()
    store.courseId = 'course-1'
    const message: AIMessage = {
      message_id: 'assistant-1',
      role: 'assistant',
      content: '解释内容',
      status: 'complete',
      receipt: {
        receipt_id: 'air-1',
        proposal_id: 'aip-1',
        status: 'succeeded',
        result_code: 'note_created',
        action_type: 'create_note',
        affected_refs: [{ kind: 'learning_record', record_id: 'rec-1', revision: 1 }],
        summary: '已保存为笔记。',
        undo_capability: 'archive_record',
      },
    }

    const receipt = await store.undoReceipt(message)

    expect(receipt?.status).toBe('stale')
    expect(receipt?.result_code).toBe('undo_target_changed')
    expect(message.receipt?.receipt_id).toBe('air-undo-1')
    expect(message.receipt?.undo_capability).toBe('none')
    expect(runtimeSpy).not.toHaveBeenCalled()
  })

  describe('主动建议', () => {
    const candidate = {
      trigger_id: 'ait-1',
      trigger_type: 'runtime_support',
      moment: 'section_completed',
      node_id: 'node-1',
      scope_ref: { node_id: 'node-1' },
      severity: 'high',
      eligible_action: 'explain_runtime_action',
      runtime_action: { action_type: 'resume_diagnostic' },
      dedupe_key: 'dk-1',
      runtime_revision_id: 'runtime-1',
    }

    it('只在自然停顿点向服务端询问，并带上会话标识', async () => {
      httpMock.get.mockResolvedValue({ data: { candidate } })
      const store = useAITeacherStore()
      store.courseId = 'course-1'

      const result = await store.checkSuggestion('section_completed', 'node-1')

      expect(result?.trigger_id).toBe('ait-1')
      expect(store.suggestion?.trigger_id).toBe('ait-1')
      const params = httpMock.get.mock.calls.at(-1)![1].params
      expect(params.moment).toBe('section_completed')
      expect(params.course_id).toBe('course-1')
      // The interruption budget is counted per learning session, so the
      // session key has to reach the server or "2 per session" is unenforceable.
      expect(params.session_id).toBeTruthy()
    })

    it('把三种停顿点原样传给服务端，由服务端决定是否放行', async () => {
      httpMock.get.mockResolvedValue({ data: { candidate: null } })
      const store = useAITeacherStore()
      store.courseId = 'course-1'

      for (const moment of ['section_completed', 'practice_submitted', 'course_entered'] as const) {
        await store.checkSuggestion(moment, 'node-1')
        expect(httpMock.get.mock.calls.at(-1)![1].params.moment).toBe(moment)
      }
    })

    it('展示后才消费打扰预算，只是询问不消费', async () => {
      httpMock.get.mockResolvedValue({ data: { candidate } })
      httpMock.post.mockResolvedValue({ data: { status: 'recorded' } })
      const store = useAITeacherStore()
      store.courseId = 'course-1'

      await store.checkSuggestion('section_completed', 'node-1')
      expect(httpMock.post).not.toHaveBeenCalled()

      await store.markSuggestionShown(store.suggestion!)
      expect(httpMock.post).toHaveBeenCalledWith(
        '/api/ai-teacher/trigger/shown',
        expect.objectContaining({
          course_id: 'course-1',
          trigger_id: 'ait-1',
          dedupe_key: 'dk-1',
          node_id: 'node-1',
          moment: 'section_completed',
          session_id: expect.any(String),
        }),
      )
    })

    it('服务端判定不该打扰时不留下建议', async () => {
      httpMock.get.mockResolvedValue({ data: { candidate: null } })
      const store = useAITeacherStore()
      store.courseId = 'course-1'

      expect(await store.checkSuggestion('section_completed', 'node-1')).toBeNull()
      expect(store.suggestion).toBeNull()
    })

    it('建议查询失败不影响学习现场，也不抛错', async () => {
      httpMock.get.mockRejectedValue(new Error('network down'))
      const store = useAITeacherStore()
      store.courseId = 'course-1'

      await expect(store.checkSuggestion('course_entered', 'node-1')).resolves.toBeNull()
      expect(store.error).toBeNull()
    })
  })
})
