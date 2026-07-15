import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: httpMock,
  withApiBase: (path: string) => path,
  learnerIdentityHeaders: (initial: HeadersInit = {}) => new Headers(initial),
}))

import { useChangeProposalsStore } from '@/stores/changeProposals'
import type { ChangeProposal } from '@/types/changeProposal'

const buildProposal = (): ChangeProposal => ({
  proposal_id: 'cp-1',
  course_id: 'course-1',
  scope: 'sections',
  target_block_ids: ['block-1', 'block-2'],
  items: [
    { item_id: 'item-1', block_id: 'block-1', before: '旧内容 A', after: '新内容 A', reason: '更准确', status: 'pending' },
    { item_id: 'item-2', block_id: 'block-2', before: '旧内容 B', after: '新内容 B', reason: '更清楚', status: 'pending' },
  ],
  source: 'evidence',
  status: 'pending',
  created_at: '2026-07-15T00:00:00Z',
})

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

describe('change proposals store', () => {
  it('fetches pending proposals for a course', async () => {
    httpMock.get.mockResolvedValue({ data: [buildProposal()] })
    const store = useChangeProposalsStore()
    await store.fetchChangeProposals('course-1')
    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/change_proposals')
    expect(store.proposals).toHaveLength(1)
    expect(store.pendingProposals).toHaveLength(1)
    expect(store.pendingItemsByBlockId['block-1']).toHaveLength(1)
    expect(store.scopeStats.sections).toBe(1)
  })

  it('applies one item without affecting sibling items in the same proposal', async () => {
    httpMock.get.mockResolvedValue({ data: [buildProposal()] })
    httpMock.post.mockResolvedValue({ data: {} })
    const store = useChangeProposalsStore()
    await store.fetchChangeProposals('course-1')

    await store.applyItem('cp-1', 'item-1')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/change_proposals/cp-1/items/item-1/apply',
    )
    const proposal = store.findProposal('cp-1')!
    expect(proposal.items.find(item => item.item_id === 'item-1')?.status).toBe('applied')
    expect(proposal.items.find(item => item.item_id === 'item-2')?.status).toBe('pending')
    // proposal 仍未 resolved，因为还有一个 pending item
    expect(proposal.status).toBe('pending')
  })

  it('rejects an item with an optional reason and marks proposal resolved once all items are settled', async () => {
    httpMock.get.mockResolvedValue({ data: [buildProposal()] })
    httpMock.post.mockResolvedValue({ data: {} })
    const store = useChangeProposalsStore()
    await store.fetchChangeProposals('course-1')

    await store.rejectItem('cp-1', 'item-1', '理由不充分')
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/change_proposals/cp-1/items/item-1/reject',
      { reason: '理由不充分' },
    )
    await store.applyItem('cp-1', 'item-2')

    const proposal = store.findProposal('cp-1')!
    expect(proposal.items.find(item => item.item_id === 'item-1')?.status).toBe('rejected')
    expect(proposal.items.find(item => item.item_id === 'item-2')?.status).toBe('applied')
    expect(proposal.status).toBe('resolved')
    expect(store.pendingProposals).toHaveLength(0)
  })

  it('regenerates an item and keeps it pending with updated content, without touching other items', async () => {
    httpMock.get.mockResolvedValue({ data: [buildProposal()] })
    httpMock.post.mockResolvedValue({ data: { after: '重新生成的内容 A' } })
    const store = useChangeProposalsStore()
    await store.fetchChangeProposals('course-1')

    await store.regenerateItem('cp-1', 'item-1', '再简洁一些')
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/change_proposals/cp-1/items/item-1/regenerate',
      { extra_instruction: '再简洁一些' },
    )
    const proposal = store.findProposal('cp-1')!
    const item1 = proposal.items.find(item => item.item_id === 'item-1')!
    expect(item1.status).toBe('pending')
    expect(item1.after).toBe('重新生成的内容 A')
    expect(proposal.items.find(item => item.item_id === 'item-2')?.after).toBe('新内容 B')
  })

  it('tolerates an unknown target_kind field on items without erroring', async () => {
    const proposalWithTargetKind = {
      ...buildProposal(),
      items: [
        { item_id: 'item-3', block_id: 'block-3', before: '', after: '知识库联动新增内容', reason: '', status: 'pending', target_kind: 'kg_node' },
      ],
    }
    httpMock.get.mockResolvedValue({ data: [proposalWithTargetKind] })
    const store = useChangeProposalsStore()
    await expect(store.fetchChangeProposals('course-1')).resolves.not.toThrow()
    expect(store.proposals[0].items[0].target_kind).toBe('kg_node')
  })
})
