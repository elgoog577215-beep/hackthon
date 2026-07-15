import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { isReactive } from 'vue'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  withApiBase: (path: string) => path,
  learnerIdentityHeaders: (initial: HeadersInit = {}) => new Headers(initial),
}))

import { useAITeacherStore, type AIMessage } from '@/stores/aiTeacher'

const emptyConversation = {
  conversation_id: 'aic-1',
  course_id: 'course-1',
  course_version_id: 'cv-1',
  title: '新对话',
  revision: 1,
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
          sources: [{ source_id: 'block-rev-1', title: '变量定义' }],
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
      'event: sources\ndata: {"sources":[{"source_id":"block-rev-1","title":"变量定义"}]}\n\n',
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
    })

    const requestBody = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)
    expect(requestBody).toMatchObject({
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
    expect(observedAssistantMessage?.status).toBe('complete')
    expect(store.messages.at(-1)?.content).toBe('变量用于保存可变化的值。')
    expect(store.messages.at(-1)?.sources?.[0]?.source_id).toBe('block-rev-1')
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
})
