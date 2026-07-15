/**
 * pendingChanges store 测试
 * 覆盖 accept/reject/regenerate 的真实 API 调用行为，以及按 node_id 分组的 getter。
 * http 模块被 mock，返回值模拟后端契约：
 *   GET  /api/courses/{courseId}/pending_changes                          -> PendingChangeOverlay
 *   POST /api/courses/{courseId}/change_sets/{changeSetId}/accept         -> CourseChangeSet
 *   POST /api/courses/{courseId}/change_sets/{changeSetId}/reject         -> CourseChangeSet
 *   POST /api/courses/{courseId}/change_sets/{changeSetId}/regenerate     -> CourseChangeSet
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { CourseChangeSet } from '@/types/adaptiveChange'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import { usePendingChangesStore } from '@/stores/pendingChanges'
import httpMock from '@/utils/http'

function makeChangeSet(overrides: Partial<CourseChangeSet> = {}): CourseChangeSet {
  const now = Date.now()
  return {
    id: 'ccs-mock-1',
    course_id: 'course-1',
    scope: 'block',
    scope_node_ids: ['node-1-2'],
    change_items: [
      {
        target_node_id: 'node-1-2',
        operation: 'update',
        before: '牛顿第二定律：F = ma。',
        after: '牛顿第二定律：F = ma。补充生活化类比。',
        reason: '检测到你在该节点多次追问相关概念。',
      },
    ],
    source_hypothesis_id: 'hyp-mock-1',
    status: 'pending',
    created_at: now - 3600_000,
    resolved_at: null,
    ...overrides,
  }
}

function makeMultiItemChangeSet(): CourseChangeSet {
  const now = Date.now()
  return {
    id: 'ccs-mock-2',
    course_id: 'course-1',
    scope: 'section',
    scope_node_ids: ['node-2', 'node-2-1', 'node-2-2'],
    change_items: [
      {
        target_node_id: 'node-2-1',
        operation: 'update',
        before: '（原有例题）',
        after: '（新增例题）',
        reason: '综合本小节多个节点的错题分布。',
      },
      {
        target_node_id: 'node-2-2',
        operation: 'insert',
        before: null,
        after: '新增小节：加速度的图像法求解',
        reason: '同一假设联动影响到相邻小节。',
      },
    ],
    source_hypothesis_id: 'hyp-mock-2',
    status: 'pending',
    created_at: now - 1800_000,
    resolved_at: null,
  }
}

function makeOverlayResponse(changeSets: CourseChangeSet[]) {
  const byNodeId: Record<string, CourseChangeSet[]> = {}
  changeSets.forEach(cs => {
    const nodeIds = new Set<string>([...cs.scope_node_ids, ...cs.change_items.map(ci => ci.target_node_id)])
    nodeIds.forEach(nodeId => {
      if (!byNodeId[nodeId]) byNodeId[nodeId] = []
      byNodeId[nodeId].push(cs)
    })
  })
  return { data: { course_id: 'course-1', byNodeId } }
}

describe('usePendingChangesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('fetchPendingChanges loads change sets from GET /pending_changes', async () => {
    const set1 = makeChangeSet()
    const set2 = makeMultiItemChangeSet()
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([set1, set2]))

    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/pending_changes')
    expect(store.changeSets.length).toBe(2)
    expect(store.pendingChangeSets.length).toBe(2)
    expect(store.pendingCount).toBe(2)
    store.changeSets.forEach(cs => {
      expect(cs.status).toBe('pending')
      expect(cs.course_id).toBe('course-1')
    })
  })

  it('fetchPendingChanges falls back to mock data on request failure', async () => {
    httpMock.get.mockRejectedValueOnce(new Error('network error'))

    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    expect(store.changeSets.length).toBeGreaterThanOrEqual(2)
    store.changeSets.forEach(cs => expect(cs.course_id).toBe('course-1'))
  })

  it('acceptChangeSet calls POST /accept and marks the whole set as accepted', async () => {
    const set1 = makeChangeSet()
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([set1]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    const accepted = { ...set1, status: 'accepted' as const, resolved_at: Date.now() }
    httpMock.post.mockResolvedValueOnce({ data: accepted })

    await store.acceptChangeSet(set1.id)

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/change_sets/ccs-mock-1/accept',
      { node_ids: undefined }
    )
    const target = store.changeSets.find(c => c.id === set1.id)!
    expect(target.status).toBe('accepted')
    expect(target.resolved_at).not.toBeNull()
    expect(store.pendingChangeSets.find(cs => cs.id === set1.id)).toBeUndefined()
  })

  it('acceptChangeSet with nodeIds only resolves matching items — other nodes in the same set stay pending', async () => {
    const multiItemSet = makeMultiItemChangeSet()
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([multiItemSet]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    // Backend response after accepting only node-2-1: set stays pending, item removed
    const partiallyResolved: CourseChangeSet = {
      ...multiItemSet,
      change_items: multiItemSet.change_items.filter(ci => ci.target_node_id !== 'node-2-1'),
      status: 'pending',
    }
    httpMock.post.mockResolvedValueOnce({ data: partiallyResolved })

    await store.acceptChangeSet(multiItemSet.id, ['node-2-1'])

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/change_sets/ccs-mock-2/accept',
      { node_ids: ['node-2-1'] }
    )
    const target = store.changeSets.find(c => c.id === multiItemSet.id)!
    expect(target.status).toBe('pending')
    expect(target.change_items.length).toBe(1)
    expect(target.change_items[0]!.target_node_id).toBe('node-2-2')

    // Accepting the remaining node-2-2 fully resolves the set
    const fullyResolved: CourseChangeSet = {
      ...multiItemSet,
      change_items: [],
      status: 'accepted',
      resolved_at: Date.now(),
    }
    httpMock.post.mockResolvedValueOnce({ data: fullyResolved })
    await store.acceptChangeSet(multiItemSet.id, ['node-2-2'])

    const finalTarget = store.changeSets.find(c => c.id === multiItemSet.id)!
    expect(finalTarget.status).toBe('accepted')
    expect(finalTarget.resolved_at).not.toBeNull()
  })

  it('rejectChangeSet calls POST /reject with reason and marks the set rejected', async () => {
    const set1 = makeChangeSet()
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([set1]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    const rejected = { ...set1, status: 'rejected' as const, resolved_at: Date.now() }
    httpMock.post.mockResolvedValueOnce({ data: rejected })

    await store.rejectChangeSet(set1.id, '不需要这个类比')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/change_sets/ccs-mock-1/reject',
      { reason: '不需要这个类比', node_ids: undefined }
    )
    const target = store.changeSets.find(c => c.id === set1.id)!
    expect(target.status).toBe('rejected')
    expect(target.resolved_at).not.toBeNull()
    expect(store.pendingChangeSets.find(cs => cs.id === set1.id)).toBeUndefined()
  })

  it('regenerateChangeSet calls POST /regenerate and pushes the new change set', async () => {
    const set1 = makeChangeSet()
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([set1]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    const newSet = makeChangeSet({ id: 'ccs-regenerated-1' })
    httpMock.post.mockResolvedValueOnce({ data: newSet })

    await store.regenerateChangeSet(set1.id, '请补充更多例题')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/change_sets/ccs-mock-1/regenerate',
      { extra_instruction: '请补充更多例题' }
    )
    const target = store.changeSets.find(c => c.id === set1.id)!
    expect(target.status).toBe('regenerated')
    expect(target.resolved_at).not.toBeNull()
    expect(store.changeSets.find(cs => cs.id === 'ccs-regenerated-1')).toBeTruthy()
  })

  it('accept/reject/regenerate on a non-pending or unknown set is a no-op (no HTTP call)', async () => {
    const set1 = makeChangeSet()
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([set1]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    const accepted = { ...set1, status: 'accepted' as const, resolved_at: Date.now() }
    httpMock.post.mockResolvedValueOnce({ data: accepted })
    await store.acceptChangeSet(set1.id)
    httpMock.post.mockClear()

    // already accepted -> further calls should not hit the network or change status
    await store.rejectChangeSet(set1.id)
    expect(httpMock.post).not.toHaveBeenCalled()
    const target = store.changeSets.find(c => c.id === set1.id)!
    expect(target.status).toBe('accepted')

    // unknown id -> should not throw and should not call http
    await expect(store.acceptChangeSet('does-not-exist')).resolves.not.toThrow()
    expect(httpMock.post).not.toHaveBeenCalled()
  })

  it('pendingByNodeId groups pending change sets by affected node_id', async () => {
    const set1 = makeChangeSet()
    const set2 = makeMultiItemChangeSet()
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([set1, set2]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    const byNode = store.pendingByNodeId
    expect(byNode['node-1-2']?.some(cs => cs.id === 'ccs-mock-1')).toBe(true)
    expect(byNode['node-2-1']?.some(cs => cs.id === 'ccs-mock-2')).toBe(true)
    expect(byNode['node-2-2']?.some(cs => cs.id === 'ccs-mock-2')).toBe(true)

    const accepted = { ...set1, status: 'accepted' as const, resolved_at: Date.now() }
    httpMock.post.mockResolvedValueOnce({ data: accepted })
    await store.acceptChangeSet('ccs-mock-1')
    expect(store.pendingByNodeId['node-1-2']).toBeUndefined()
  })

  it('pendingForNode returns only pending sets touching the given node', async () => {
    const set1 = makeChangeSet()
    const nodeThreeSet = makeChangeSet({
      id: 'ccs-mock-3',
      scope_node_ids: ['node-3-1'],
      change_items: [
        {
          target_node_id: 'node-3-1',
          operation: 'update',
          before: '（原有公式推导）',
          after: '（补充展开的中间推导步骤）',
          reason: '笔记中标记"看不懂这一步"。',
        },
      ],
    })
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([set1, nodeThreeSet]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    const forNode = store.pendingForNode('node-3-1')
    expect(forNode.length).toBe(1)
    expect(forNode[0]!.id).toBe('ccs-mock-3')

    expect(store.pendingForNode('node-does-not-exist').length).toBe(0)
  })

  it('pendingForKgNode returns only pending sets whose change_items target a kg_node with the given id, and pendingForNode excludes them', async () => {
    const kgLinkedSet = makeChangeSet({
      id: 'ccs-kg-1',
      scope_node_ids: [],
      change_items: [
        {
          target_node_id: 'kg-node-1',
          operation: 'update',
          before: '（原有定义）',
          after: '（联动自内容的新定义）',
          reason: '内容变更联动至知识库节点。',
          source: 'content_to_kb_link',
          target_kind: 'kg_node',
        },
      ],
    })
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([kgLinkedSet]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    const forKg = store.pendingForKgNode('kg-node-1')
    expect(forKg.length).toBe(1)
    expect(forKg[0]!.id).toBe('ccs-kg-1')

    // pendingForNode must not pick up kg_node-targeted items even if the id matched
    expect(store.pendingForNode('kg-node-1').length).toBe(0)
    expect(store.pendingForKgNode('node-does-not-exist').length).toBe(0)
  })

  it('preserves before/after/reason on change_items for diff-style rendering', async () => {
    const set1 = makeChangeSet()
    httpMock.get.mockResolvedValueOnce(makeOverlayResponse([set1]))
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    const cs = store.changeSets.find(c => c.id === 'ccs-mock-1')!
    const item = cs.change_items[0]!
    expect(item.before).toBeTruthy()
    expect(item.after).toBeTruthy()
    expect(item.reason).toBeTruthy()
    expect(item.before).not.toBe(item.after)
  })
})
