import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: httpMock }))

import { useCourseStore } from '@/stores/course'
import { useNoteStore } from '@/stores/notes'
import type { LearningRecord } from '@/stores/types'

const record = (overrides: Partial<LearningRecord> = {}): LearningRecord => ({
  record_id: 'lr-1',
  record_type: 'note',
  status: 'active',
  user_id: 'default_user',
  course_id: 'c1',
  course_version_id: 'cv1',
  node_id: 'n1',
  node_name: '向量',
  quote: '向量具有大小与方向。',
  title: '向量定义',
  content: '大小和方向缺一不可。',
  origin: 'user',
  priority: 'medium',
  tags: [],
  revision: 1,
  created_at: '2026-07-11T10:00:00Z',
  updated_at: '2026-07-11T10:00:00Z',
  migration_status: 'current',
  ...overrides,
})

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  httpMock.get.mockReset()
  httpMock.post.mockReset()
  httpMock.patch.mockReset()
  httpMock.get.mockResolvedValue({ data: {
    schema_version: 'learning_runtime_v1', course_id: 'c1', user_id: 'default_user',
    context: {}, revision_vector: {}, runtime_revision_id: 'lrr1', snapshot: {},
    progress: { schema_version: 'learning_progress_v1', course_id: 'c1', course_version_id: 'cv1', user_id: 'default_user', summary: {}, nodes: [] },
    records: { total: 0, by_type: {}, by_status: {}, open_issue_ids: [] },
    practice: { total: 0, active: [], pending_review_count: 0, needs_review_count: 0 },
    diagnostic: { phase: 'practice' }, active_task: null, continuation: null,
  } })
  const course = useCourseStore()
  course.currentCourseId = 'c1'
  course.nodes = [{
    node_id: 'n1', parent_node_id: 'root', node_name: '向量', node_level: 2,
    node_content: '向量', node_type: 'original', generation_status: 'completed', generated_chars: 2,
  }]
})

describe('learning records through notes store', () => {
  it('首次加载迁移旧注释，之后只读取服务端记录', async () => {
    httpMock.post.mockResolvedValue({ data: { created: 0, records: [] } })
    httpMock.get.mockResolvedValue({ data: { records: [record()] } })
    const store = useNoteStore()

    await store.loadCourseRecords('c1')
    await store.loadCourseRecords('c1')

    expect(httpMock.post).toHaveBeenCalledTimes(1)
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/c1/learning-records/migrate-legacy-annotations',
      { include_unowned: false },
    )
    expect(store.notes[0]?.recordType).toBe('note')
    expect(store.notes[0]?.revision).toBe(1)
  })

  it('稍后处理会创建明确的问题记录', async () => {
    httpMock.post.mockResolvedValue({ data: record({
      record_id: 'lr-issue', record_type: 'issue', status: 'open', title: '未解决问题',
    }) })
    const store = useNoteStore()
    store.courseId = 'c1'

    await store.createLater('issue', { nodeId: 'n1', quote: '为什么需要方向？' })

    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/c1/learning-records', expect.objectContaining({
      record_type: 'issue', status: 'open', node_id: 'n1',
    }))
    expect(store.notes[0]?.recordType).toBe('issue')
  })

  it('状态更新携带期望修订号并使用服务端返回值', async () => {
    httpMock.patch.mockResolvedValue({ data: record({
      record_id: 'lr-issue', record_type: 'issue', status: 'resolved', revision: 2,
    }) })
    const store = useNoteStore()
    store.courseId = 'c1'
    store.notes = [{
      id: 'lr-issue', nodeId: 'n1', highlightId: '', quote: '问题', content: '问题', color: 'red',
      createdAt: Date.now(), sourceType: 'user', recordType: 'issue', status: 'open', revision: 1,
    }]

    await store.updateRecordStatus('lr-issue', 'resolved')

    expect(httpMock.patch).toHaveBeenCalledWith('/api/courses/c1/learning-records/lr-issue', {
      expected_revision: 1, status: 'resolved',
    })
    expect(store.notes[0]?.status).toBe('resolved')
    expect(store.notes[0]?.revision).toBe(2)
  })

  it('格式高亮只保留在本地，不写入正式记录', async () => {
    const store = useNoteStore()
    await store.createNote({
      id: 'format-1', nodeId: 'n1', highlightId: 'hl-1', quote: '向量', content: '', color: 'yellow',
      createdAt: Date.now(), sourceType: 'format',
    })

    expect(httpMock.post).not.toHaveBeenCalled()
    expect(store.notes).toHaveLength(1)
  })

  it('保存失败时保留本地笔记草稿，并可使用同一记录 ID 重试', async () => {
    httpMock.post
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ data: record({ record_id: 'local-note' }) })
    const store = useNoteStore()
    store.courseId = 'c1'
    const note = {
      id: 'local-note', nodeId: 'n1', highlightId: 'hl-local-note', quote: '向量', content: '本地理解',
      color: 'amber', createdAt: Date.now(), sourceType: 'user' as const, recordType: 'note' as const,
      status: 'active', anchor: { text_quote: '向量', text_position: { start: 0, end: 2, prefix: '', suffix: '', occurrence: 0 } },
    }

    await store.createNote(note)

    expect(store.notes[0]?.syncState).toBe('local_only')
    expect(localStorage.getItem('learning_record_draft_v1:c1:local-note')).toContain('本地理解')

    await store.retryNote('local-note')

    expect(httpMock.post).toHaveBeenLastCalledWith('/api/courses/c1/learning-records', expect.objectContaining({ record_id: 'local-note' }))
    expect(store.notes[0]?.syncState).toBe('saved')
    expect(localStorage.getItem('learning_record_draft_v1:c1:local-note')).toBeNull()
  })

  it('同一原文锚点的 AI 连续追问更新同一条行内记录', async () => {
    httpMock.post.mockImplementationOnce((_url, payload) => Promise.resolve({ data: record({
      record_id: payload.record_id, origin: 'assistant_inline_qa', revision: 1,
      content: '第一次解释', metadata: { ai_message_ids: ['m1'], record_subtype: 'anchored_ai_qa' },
    }) }))
    const store = useNoteStore()
    store.courseId = 'c1'
    const payload = {
      nodeId: 'n1', quote: '向量',
      anchor: { text_quote: '向量', text_position: { start: 0, end: 2, prefix: '', suffix: '', occurrence: 0 } },
      conversationId: 'conv-1',
    }

    const first = await store.upsertAnchoredAiNote({ ...payload, content: '第一次解释', messageId: 'm1' })
    expect(first?.sourceType).toBe('ai')
    const recordId = first?.id || ''
    httpMock.patch.mockResolvedValueOnce({ data: record({
      record_id: recordId, origin: 'assistant_inline_qa', revision: 2,
      content: '追问后的解释', metadata: { ai_message_ids: ['m1', 'm2'], record_subtype: 'anchored_ai_qa' },
    }) })

    await store.upsertAnchoredAiNote({ ...payload, content: '追问后的解释', messageId: 'm2' })

    expect(store.notes).toHaveLength(1)
    expect(store.notes[0]?.content).toBe('追问后的解释')
    expect(httpMock.patch).toHaveBeenCalledWith(`/api/courses/c1/learning-records/${recordId}`, expect.objectContaining({
      expected_revision: 1,
      metadata: expect.objectContaining({ ai_message_ids: ['m1', 'm2'] }),
    }))
  })
})

describe('inline record writes under slow transport', () => {
  it('连续创建、修改等待前次修订，并在保存完成后归档', async () => {
    const { createInlineRecordPersistence } = await import('@/composables/inline-record-persistence')
    const store = useNoteStore()
    store.courseId = 'c1'
    const note = { id: 'lr-1', nodeId: 'n1', highlightId: '', quote: '', content: '', color: 'amber', createdAt: 1 }
    store.addNote(note)
    let finishCreate!: (value: unknown) => void
    httpMock.post.mockImplementationOnce(() => new Promise(resolve => { finishCreate = resolve }))
    httpMock.post.mockResolvedValue({ data: {} })
    httpMock.patch.mockResolvedValue({ data: record({ content: '第二次输入', revision: 2 }) })
    const writes = createInlineRecordPersistence(store)
    const first = writes.save(note, '第一次输入')
    const second = writes.save(note, '第二次输入')
    const removal = writes.remove(note)
    expect(httpMock.patch).not.toHaveBeenCalled()
    expect(httpMock.post).toHaveBeenCalledTimes(1)
    finishCreate({ data: record({ content: '第一次输入', revision: 1 }) })
    await Promise.all([first, second, removal])
    expect(httpMock.patch).toHaveBeenCalledWith('/api/courses/c1/learning-records/lr-1', { expected_revision: 1, content: '第二次输入' })
    expect(httpMock.post).toHaveBeenLastCalledWith('/api/courses/c1/learning-records/lr-1/archive', { expected_revision: 2 })
    expect(store.notes).toHaveLength(0)
    expect(writes.isPending(note.id)).toBe(false)
    expect(localStorage.getItem('learning_record_draft_v1:c1:lr-1')).toBeNull()
  })

  it('归档失败保留记录和本地草稿，成功后清除草稿避免刷新复活', async () => {
    const store = useNoteStore()
    store.courseId = 'c1'
    const note = { id: 'lr-1', nodeId: 'n1', highlightId: '', quote: '', content: '草稿', color: 'amber', createdAt: 1, revision: 1 }
    store.addNote(note)
    localStorage.setItem('learning_record_draft_v1:c1:lr-1', JSON.stringify({ note }))
    httpMock.post.mockRejectedValueOnce(new Error('offline'))
    expect(await store.deleteNote(note.id)).toBe(false)
    expect(store.notes).toHaveLength(1)
    expect(localStorage.getItem('learning_record_draft_v1:c1:lr-1')).not.toBeNull()
    httpMock.post.mockResolvedValueOnce({ data: {} })
    expect(await store.deleteNote(note.id)).toBe(true)
    expect(store.notes).toHaveLength(0)
    expect(localStorage.getItem('learning_record_draft_v1:c1:lr-1')).toBeNull()
  })
})
