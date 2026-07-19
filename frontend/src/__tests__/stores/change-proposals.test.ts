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
  change_kind: 'course_authoring_change',
  write_target: 'base_course',
  source: 'manual',
  status: 'pending',
  created_at: '2026-07-15T00:00:00Z',
})

const buildPersonalizationProposal = (): ChangeProposal => ({
  ...buildProposal(),
  proposal_id: 'personalization-1',
  scope: 'section',
  source: 'personalization',
  generation_meta: { base_document_revision: 'cdr-1', direction: 'expand' },
  items: buildProposal().items.map((item, index) => ({
    ...item,
    selected: true,
    expected_block_revision: `cbr-${index + 1}`,
  })),
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

describe('change proposals store', () => {
  it('creates a personalization proposal with the selected direction and canonical revisions', async () => {
    const proposal = buildPersonalizationProposal()
    httpMock.post.mockResolvedValue({ data: proposal })
    const store = useChangeProposalsStore()

    const result = await store.createPersonalizationProposal({
      courseId: 'course-1',
      blockId: 'block-1',
      requestId: 'request-1',
      expectedDocumentRevision: 'cdr-1',
      expectedBlockRevision: 'cbr-1',
      direction: 'expand',
      feedback: '请补充推导过程',
    })

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/blocks/block-1/personalization-proposals',
      {
        request_id: 'request-1',
        expected_document_revision: 'cdr-1',
        expected_block_revision: 'cbr-1',
        direction: 'expand',
        feedback: '请补充推导过程',
        scope_selection: 'current_block',
      },
    )
    expect(result).toEqual(proposal)
    expect(store.findProposal('personalization-1')).toEqual(proposal)
  })

  it('keeps personalization loading active until the latest generation request settles', async () => {
    const first = deferred<{ data: ChangeProposal }>()
    const second = deferred<{ data: ChangeProposal }>()
    const staleProposal = { ...buildPersonalizationProposal(), proposal_id: 'personalization-stale' }
    const currentProposal = { ...buildPersonalizationProposal(), proposal_id: 'personalization-current' }
    httpMock.post.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const store = useChangeProposalsStore()
    const input = {
      courseId: 'course-1',
      blockId: 'block-1',
      expectedDocumentRevision: 'cdr-1',
      expectedBlockRevision: 'cbr-1',
      direction: 'expand' as const,
      feedback: '补充推导过程',
    }

    const firstRequest = store.createPersonalizationProposal({ ...input, requestId: 'request-1' })
    const secondRequest = store.createPersonalizationProposal({ ...input, requestId: 'request-2' })
    expect(store.personalizationLoading).toBe(true)

    first.resolve({ data: staleProposal })
    await expect(firstRequest).resolves.toEqual(staleProposal)
    expect(store.personalizationLoading).toBe(true)
    expect(store.proposals).toEqual([])

    second.resolve({ data: currentProposal })
    await expect(secondRequest).resolves.toEqual(currentProposal)
    expect(store.personalizationLoading).toBe(false)
    expect(store.proposals).toEqual([currentProposal])
  })

  it('does not let an in-flight personalization request from course A write course B proposals', async () => {
    const generation = deferred<{ data: ChangeProposal }>()
    const courseBProposal = { ...buildProposal(), proposal_id: 'course-b-proposal', course_id: 'course-b' }
    httpMock.post.mockReturnValueOnce(generation.promise)
    httpMock.get.mockResolvedValue({ data: [courseBProposal] })
    const store = useChangeProposalsStore()

    const courseARequest = store.createPersonalizationProposal({
      courseId: 'course-a', blockId: 'block-a', requestId: 'request-a',
      expectedDocumentRevision: 'cdr-a', expectedBlockRevision: 'cbr-a',
      direction: 'expand', feedback: '补充推导过程',
    })
    await store.fetchChangeProposals('course-b')

    const courseAProposal = { ...buildPersonalizationProposal(), course_id: 'course-a' }
    generation.resolve({ data: courseAProposal })

    await expect(courseARequest).resolves.toEqual(courseAProposal)
    expect(store.courseId).toBe('course-b')
    expect(store.proposals).toEqual([courseBProposal])
  })

  it('keeps the latest course fetch loading and proposals when an older fetch succeeds', async () => {
    const courseA = deferred<{ data: ChangeProposal[] }>()
    const courseB = deferred<{ data: ChangeProposal[] }>()
    const courseBProposal = { ...buildProposal(), proposal_id: 'course-b-proposal', course_id: 'course-b' }
    httpMock.get.mockReturnValueOnce(courseA.promise).mockReturnValueOnce(courseB.promise)
    const store = useChangeProposalsStore()

    const courseARequest = store.fetchChangeProposals('course-a')
    const courseBRequest = store.fetchChangeProposals('course-b')
    courseA.resolve({ data: [buildProposal()] })
    await courseARequest

    expect(store.courseId).toBe('course-b')
    expect(store.proposals).toEqual([])
    expect(store.loading).toBe(true)

    courseB.resolve({ data: [courseBProposal] })
    await courseBRequest
    expect(store.proposals).toEqual([courseBProposal])
    expect(store.loading).toBe(false)
  })

  it('keeps the latest course fetch loading when an older fetch rejects', async () => {
    const courseA = deferred<{ data: ChangeProposal[] }>()
    const courseB = deferred<{ data: ChangeProposal[] }>()
    httpMock.get.mockReturnValueOnce(courseA.promise).mockReturnValueOnce(courseB.promise)
    const store = useChangeProposalsStore()

    const courseARequest = store.fetchChangeProposals('course-a')
    const courseBRequest = store.fetchChangeProposals('course-b')
    courseA.reject(new Error('course A unavailable'))
    await courseARequest

    expect(store.courseId).toBe('course-b')
    expect(store.loading).toBe(true)

    courseB.resolve({ data: [] })
    await courseBRequest
    expect(store.loading).toBe(false)
  })

  it('does not let an in-flight apply from course A change course B state', async () => {
    const applyA = deferred<{ data: any }>()
    const applyB = deferred<{ data: any }>()
    const courseBProposal = { ...buildPersonalizationProposal(), proposal_id: 'personalization-b', course_id: 'course-b' }
    httpMock.post.mockReturnValueOnce(applyA.promise).mockReturnValueOnce(applyB.promise)
    httpMock.get.mockResolvedValue({ data: [courseBProposal] })
    const store = useChangeProposalsStore()
    const courseAProposal = { ...buildPersonalizationProposal(), proposal_id: 'personalization-a', course_id: 'course-a' }
    store.courseId = 'course-a'
    store.proposals = [courseAProposal]

    const courseARequest = store.applySelectedItems('personalization-a', ['item-1'], 'cdr-a')
    await store.fetchChangeProposals('course-b')
    const courseBRequest = store.applySelectedItems('personalization-b', ['item-2'], 'cdr-b')
    const resultA = {
      proposal: { ...courseAProposal, status: 'resolved' as const },
      receipt: { affected_block_ids: ['block-1'] },
      document: { course_id: 'course-a', document: { document_revision: 'cdr-a2' } },
      representation_sync: { status: 'synchronized', rebuilt: [] },
    }
    applyA.resolve({ data: resultA })

    await expect(courseARequest).resolves.toEqual(resultA)
    expect(store.proposals).toEqual([courseBProposal])
    expect(store.lastRepresentationSync).toBeNull()
    expect(store.applyingSelected).toBe(true)
    expect(store.actingItemIds).toEqual(new Set(['item-2']))

    applyB.resolve({ data: {
      ...resultA,
      proposal: { ...courseBProposal, status: 'resolved' },
      document: { course_id: 'course-b', document: { document_revision: 'cdr-b2' } },
    } })
    await courseBRequest
  })

  it('applies selected personalization items in one request and uses the server proposal as truth', async () => {
    const store = useChangeProposalsStore()
    const pending = buildPersonalizationProposal()
    store.courseId = 'course-1'
    store.proposals = [pending]
    const applied = {
      ...pending,
      items: pending.items.map((item, index) => ({
        ...item,
        status: index === 0 ? 'applied' as const : item.status,
      })),
    }
    httpMock.post.mockResolvedValue({ data: {
      proposal: applied,
      receipt: { affected_block_ids: ['block-1'] },
      document: { document: { document_revision: 'cdr-2' } },
      representation_sync: { status: 'synchronized', rebuilt: [] },
    } })

    const result = await store.applySelectedItems('personalization-1', ['item-1'], 'cdr-1')

    expect(httpMock.post).toHaveBeenCalledTimes(1)
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/authoring-changes/personalization-1/apply-selected',
      { item_ids: ['item-1'], expected_document_revision: 'cdr-1' },
    )
    expect(result.receipt.affected_block_ids).toEqual(['block-1'])
    expect(store.findProposal('personalization-1')?.items[0]?.status).toBe('applied')
    expect(store.lastRepresentationSync?.status).toBe('synchronized')
  })

  it('keeps every item pending when apply-selected returns a 409 conflict', async () => {
    const store = useChangeProposalsStore()
    store.courseId = 'course-1'
    store.proposals = [buildPersonalizationProposal()]
    httpMock.post.mockRejectedValue({
      response: { status: 409, data: { detail: { code: 'change_proposal_conflict' } } },
    })

    await expect(
      store.applySelectedItems('personalization-1', ['item-1', 'item-2'], 'cdr-1'),
    ).rejects.toMatchObject({ response: { status: 409 } })

    expect(store.findProposal('personalization-1')?.items.map(item => item.status)).toEqual([
      'pending',
      'pending',
    ])
    expect(store.lastRepresentationSync).toBeNull()
  })

  it('fetches pending proposals for a course', async () => {
    httpMock.get.mockResolvedValue({ data: [buildProposal()] })
    const store = useChangeProposalsStore()
    await store.fetchChangeProposals('course-1')
    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/authoring-changes')
    expect(store.proposals).toHaveLength(1)
    expect(store.pendingProposals).toHaveLength(1)
    expect(store.pendingItemsByBlockId['block-1']).toHaveLength(1)
    expect(store.scopeStats.sections).toBe(1)
  })

  it('keeps personalization proposals addressable while excluding them from generic pending views', async () => {
    const personalization = buildPersonalizationProposal()
    httpMock.get.mockResolvedValue({ data: [buildProposal(), personalization] })
    const store = useChangeProposalsStore()

    await store.fetchChangeProposals('course-1')

    expect(store.proposals).toHaveLength(2)
    expect(store.findProposal(personalization.proposal_id)).toEqual(personalization)
    expect(store.pendingProposals.map(proposal => proposal.proposal_id)).toEqual(['cp-1'])
    expect(store.pendingItemsByBlockId['block-1']).toHaveLength(1)
    expect(store.scopeStats.section).toBe(0)
    expect(store.scopeStats.sections).toBe(1)
  })

  it('applies one item without affecting sibling items in the same proposal', async () => {
    httpMock.get.mockResolvedValue({ data: [buildProposal()] })
    httpMock.post.mockResolvedValue({ data: {
      representation_sync: {
        status: 'synchronized',
        rebuilt: [{ representation_type: 'slide_deck', rebuilt_unit_ids: ['slide-1'] }],
      },
    } })
    const store = useChangeProposalsStore()
    await store.fetchChangeProposals('course-1')

    await store.applyItem('cp-1', 'item-1')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/authoring-changes/cp-1/items/item-1/apply',
    )
    const proposal = store.findProposal('cp-1')!
    expect(proposal.items.find(item => item.item_id === 'item-1')?.status).toBe('applied')
    expect(proposal.items.find(item => item.item_id === 'item-2')?.status).toBe('pending')
    expect(store.lastRepresentationSync?.status).toBe('synchronized')
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
      '/api/courses/course-1/authoring-changes/cp-1/items/item-1/reject',
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
      '/api/courses/course-1/authoring-changes/cp-1/items/item-1/regenerate',
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
    expect(store.proposals[0]?.items[0]?.target_kind).toBe('kg_node')
  })

  it('replaces the full proposal after verified regeneration', async () => {
    httpMock.get.mockResolvedValue({ data: [buildProposal()] })
    const original = buildProposal()
    const regeneratedProposal: ChangeProposal = {
      ...original,
      items: [
        { ...original.items[0]!, status: 'rejected' },
        original.items[1]!,
        {
          item_id: 'item-3',
          block_id: 'block-1',
          before: 'old content A',
          after: 'verified regenerated content A',
          reason: 'more precise',
          status: 'pending',
        },
      ],
    }
    httpMock.post.mockResolvedValue({ data: regeneratedProposal })
    const store = useChangeProposalsStore()
    await store.fetchChangeProposals('course-1')

    await store.regenerateItem('cp-1', 'item-1', 'make it concise')

    const proposal = store.findProposal('cp-1')!
    expect(proposal.items.find(item => item.item_id === 'item-1')?.status).toBe('rejected')
    expect(proposal.items.find(item => item.item_id === 'item-3')?.after).toBe('verified regenerated content A')
    expect(proposal.items.find(item => item.item_id === 'item-2')?.after).toBe(original.items[1]?.after)
  })
})
