/**
 * PendingChangeOverlay 组件测试
 * 覆盖：变更列表渲染、接受按钮触发 store action、
 * "变更作用域可控"——同一 change_set 中对不同 node 的 item 互不影响。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PendingChangeOverlay from '@/components/PendingChangeOverlay.vue'
import { usePendingChangesStore } from '@/stores/pendingChanges'
import httpMock from '@/utils/http'
import type { CourseChangeSet } from '@/types/adaptiveChange'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))


function multiNodeChangeSet(): CourseChangeSet {
  const now = Date.now()
  return {
    id: 'ccs-multi',
    course_id: 'course-1',
    scope: 'section',
    scope_node_ids: ['node-A', 'node-B'],
    change_items: [
      {
        target_node_id: 'node-A',
        operation: 'update',
        before: '旧内容 A',
        after: '新内容 A',
        reason: '理由 A',
      },
      {
        target_node_id: 'node-B',
        operation: 'insert',
        before: null,
        after: '新增内容 B',
        reason: '理由 B',
      },
    ],
    source_hypothesis_id: 'hyp-1',
    status: 'pending',
    created_at: now,
    resolved_at: null,
  }
}

describe('PendingChangeOverlay.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  async function seedStore(changeSet: CourseChangeSet) {
    const store = usePendingChangesStore()
    httpMock.get.mockResolvedValueOnce({
      data: {
        course_id: 'course-1',
        byNodeId: {
          'node-A': [changeSet],
          'node-B': [changeSet],
        },
      },
    })
    await store.fetchPendingChanges('course-1')
    return store
  }

  it('renders only the change items belonging to the given nodeId', async () => {
    const cs = multiNodeChangeSet()
    await seedStore(cs)

    const wrapper = mount(PendingChangeOverlay, { props: { nodeId: 'node-A' } })
    const items = wrapper.findAll('[data-testid="pending-change-item"]')
    expect(items.length).toBe(1)
    expect(wrapper.text()).toContain('理由 A')
    expect(wrapper.text()).not.toContain('理由 B')
  })

  it('shows before/after diff when before exists, and only "after" for insert with no before', async () => {
    const cs = multiNodeChangeSet()
    await seedStore(cs)

    const wrapperA = mount(PendingChangeOverlay, { props: { nodeId: 'node-A' } })
    expect(wrapperA.text()).toContain('修改前')
    expect(wrapperA.text()).toContain('修改后')
    expect(wrapperA.text()).toContain('旧内容 A')
    expect(wrapperA.text()).toContain('新内容 A')

    const wrapperB = mount(PendingChangeOverlay, { props: { nodeId: 'node-B' } })
    expect(wrapperB.text()).toContain('新增内容')
    expect(wrapperB.text()).not.toContain('修改前')
    expect(wrapperB.text()).toContain('新增内容 B')
  })

  it('clicking accept calls store.acceptChangeSet scoped to the current nodeId only', async () => {
    const cs = multiNodeChangeSet()
    const store = await seedStore(cs)
    const acceptSpy = vi.spyOn(store, 'acceptChangeSet').mockResolvedValue(undefined)

    const wrapper = mount(PendingChangeOverlay, { props: { nodeId: 'node-A' } })
    await wrapper.get('[data-testid="accept-btn"]').trigger('click')

    expect(acceptSpy).toHaveBeenCalledTimes(1)
    expect(acceptSpy).toHaveBeenCalledWith('ccs-multi', ['node-A'])
  })

  it('accepting node-A items does not affect node-B items in the same change set (scope control)', async () => {
    const cs = multiNodeChangeSet()
    httpMock.get.mockResolvedValueOnce({
      data: {
        course_id: 'course-1',
        byNodeId: { 'node-A': [cs], 'node-B': [cs] },
      },
    })
    const store = usePendingChangesStore()
    await store.fetchPendingChanges('course-1')

    // Simulate backend resolving only node-A's item, set stays pending with node-B item remaining
    const afterAccept: CourseChangeSet = {
      ...cs,
      change_items: cs.change_items.filter(ci => ci.target_node_id !== 'node-A'),
      status: 'pending',
    }
    httpMock.post.mockResolvedValueOnce({ data: afterAccept })

    const wrapperA = mount(PendingChangeOverlay, { props: { nodeId: 'node-A' } })
    await wrapperA.get('[data-testid="accept-btn"]').trigger('click')
    await wrapperA.vm.$nextTick()
    await Promise.resolve()
    await wrapperA.vm.$nextTick()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/change_sets/ccs-multi/accept',
      { node_ids: ['node-A'] }
    )

    // node-B's item should still be pending and rendered
    const wrapperB = mount(PendingChangeOverlay, { props: { nodeId: 'node-B' } })
    const itemsB = wrapperB.findAll('[data-testid="pending-change-item"]')
    expect(itemsB.length).toBe(1)
    expect(wrapperB.text()).toContain('理由 B')
  })

  it('reject flow opens a prompt textarea and calls store.rejectChangeSet with reason and nodeIds', async () => {
    const cs = multiNodeChangeSet()
    const store = await seedStore(cs)
    const rejectSpy = vi.spyOn(store, 'rejectChangeSet').mockResolvedValue(undefined)

    const wrapper = mount(PendingChangeOverlay, { props: { nodeId: 'node-A' } })
    await wrapper.get('[data-testid="reject-btn"]').trigger('click')
    const textarea = wrapper.get('[data-testid="prompt-textarea"]')
    await textarea.setValue('不需要这个改动')
    await wrapper.get('[data-testid="prompt-confirm-btn"]').trigger('click')

    expect(rejectSpy).toHaveBeenCalledWith('ccs-multi', '不需要这个改动', ['node-A'])
  })

  it('regenerate flow calls store.regenerateChangeSet with the extra instruction', async () => {
    const cs = multiNodeChangeSet()
    const store = await seedStore(cs)
    const regenSpy = vi.spyOn(store, 'regenerateChangeSet').mockResolvedValue(undefined)

    const wrapper = mount(PendingChangeOverlay, { props: { nodeId: 'node-A' } })
    await wrapper.get('[data-testid="regenerate-btn"]').trigger('click')
    await wrapper.get('[data-testid="prompt-textarea"]').setValue('补充更多例题')
    await wrapper.get('[data-testid="prompt-confirm-btn"]').trigger('click')

    expect(regenSpy).toHaveBeenCalledWith('ccs-multi', '补充更多例题')
  })

  it('with nodeKind="kg_node" uses the pendingForKgNode getter and renders matching items', async () => {
    const kgSet: CourseChangeSet = {
      id: 'ccs-kg',
      course_id: 'course-1',
      scope: 'block',
      scope_node_ids: [],
      change_items: [
        {
          target_node_id: 'kg-node-1',
          operation: 'update',
          before: '旧定义',
          after: '新定义',
          reason: '知识库联动理由',
          source: 'content_to_kb_link',
          target_kind: 'kg_node',
        },
      ],
      source_hypothesis_id: 'hyp-kg',
      status: 'pending',
      created_at: Date.now(),
      resolved_at: null,
    }
    const store = usePendingChangesStore()
    httpMock.get.mockResolvedValueOnce({
      data: { course_id: 'course-1', byNodeId: { 'kg-node-1': [kgSet] } },
    })
    await store.fetchPendingChanges('course-1')

    // default nodeKind ('course_node') must not match a kg_node-targeted item
    const wrapperDefault = mount(PendingChangeOverlay, { props: { nodeId: 'kg-node-1' } })
    expect(wrapperDefault.find('[data-testid="pending-change-overlay"]').exists()).toBe(false)

    const wrapperKg = mount(PendingChangeOverlay, { props: { nodeId: 'kg-node-1', nodeKind: 'kg_node' } })
    const items = wrapperKg.findAll('[data-testid="pending-change-item"]')
    expect(items.length).toBe(1)
    expect(wrapperKg.text()).toContain('知识库联动理由')
  })

  it('renders the source-specific badge for content_to_kb_link, kb_to_content_link, and default evidence_driven', async () => {
    const now = Date.now()
    const set: CourseChangeSet = {
      id: 'ccs-badges',
      course_id: 'course-1',
      scope: 'block',
      scope_node_ids: ['node-default'],
      change_items: [
        { target_node_id: 'node-default', operation: 'update', before: 'a', after: 'b', reason: '默认理由' },
      ],
      source_hypothesis_id: 'hyp-badges',
      status: 'pending',
      created_at: now,
      resolved_at: null,
    }
    const store = usePendingChangesStore()
    httpMock.get.mockResolvedValueOnce({
      data: { course_id: 'course-1', byNodeId: { 'node-default': [set] } },
    })
    await store.fetchPendingChanges('course-1')

    const wrapperDefault = mount(PendingChangeOverlay, { props: { nodeId: 'node-default' } })
    expect(wrapperDefault.text()).toContain('AI 生成')

    const fromKbSet: CourseChangeSet = {
      ...set,
      id: 'ccs-from-kb',
      change_items: [
        { target_node_id: 'node-a', operation: 'update', before: 'a', after: 'b', reason: '来自知识库理由', source: 'content_to_kb_link' },
      ],
      scope_node_ids: ['node-a'],
    }
    httpMock.get.mockResolvedValueOnce({
      data: { course_id: 'course-1', byNodeId: { 'node-a': [fromKbSet] } },
    })
    const store2 = usePendingChangesStore()
    await store2.fetchPendingChanges('course-1')
    const wrapperFromKb = mount(PendingChangeOverlay, { props: { nodeId: 'node-a' } })
    expect(wrapperFromKb.text()).toContain('来自知识库联动')

    const toKbSet: CourseChangeSet = {
      ...set,
      id: 'ccs-to-kb',
      change_items: [
        { target_node_id: 'node-b', operation: 'update', before: 'a', after: 'b', reason: '联动至知识库理由', source: 'kb_to_content_link' },
      ],
      scope_node_ids: ['node-b'],
    }
    httpMock.get.mockResolvedValueOnce({
      data: { course_id: 'course-1', byNodeId: { 'node-b': [toKbSet] } },
    })
    const store3 = usePendingChangesStore()
    await store3.fetchPendingChanges('course-1')
    const wrapperToKb = mount(PendingChangeOverlay, { props: { nodeId: 'node-b' } })
    expect(wrapperToKb.text()).toContain('联动至知识库')
  })

  it('renders nothing when there are no pending changes for the node', async () => {
    const store = usePendingChangesStore()
    httpMock.get.mockResolvedValueOnce({ data: { course_id: 'course-1', byNodeId: {} } })
    await store.fetchPendingChanges('course-1')

    const wrapper = mount(PendingChangeOverlay, { props: { nodeId: 'node-none' } })
    expect(wrapper.find('[data-testid="pending-change-overlay"]').exists()).toBe(false)
  })
})
