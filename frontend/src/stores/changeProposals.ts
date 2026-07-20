import { defineStore } from 'pinia'
import http from '../utils/http'
import type {
  ApplySelectedChangeProposalResult,
  ChangeProposal,
  ChangeProposalItem,
  ChangeProposalScope,
  CreatePersonalizationProposalInput,
  RepresentationSyncResult,
} from '../types/changeProposal'
import logger from '../utils/logger'

interface ChangeProposalsState {
  courseId: string
  courseRequestToken: number
  proposals: ChangeProposal[]
  loading: boolean
  fetchRequestToken: number
  personalizationLoading: boolean
  personalizationRequestToken: number
  applyingSelected: boolean
  applySelectedRequestToken: number
  actingItemIds: Set<string>
  lastRepresentationSync: RepresentationSyncResult | null
}

export const useChangeProposalsStore = defineStore('changeProposals', {
  state: (): ChangeProposalsState => ({
    courseId: '',
    courseRequestToken: 0,
    proposals: [],
    loading: false,
    fetchRequestToken: 0,
    personalizationLoading: false,
    personalizationRequestToken: 0,
    applyingSelected: false,
    applySelectedRequestToken: 0,
    actingItemIds: new Set<string>(),
    lastRepresentationSync: null,
  }),

  getters: {
    // 仅返回仍有 pending item 的 proposal（proposal.status 可能已被后端标记 resolved，
    // 但为了防御性展示，同时以 item.status 过滤）。
    pendingProposals(state): ChangeProposal[] {
      return state.proposals.filter(proposal => (
        proposal.source !== 'personalization'
        &&
        proposal.status === 'pending' && proposal.items.some(item => item.status === 'pending')
      ))
    },

    // 按 block_id 分组的待处理 items，便于在课程正文对应位置展示。
    pendingItemsByBlockId(): Record<string, Array<{ proposal: ChangeProposal; item: ChangeProposalItem }>> {
      const grouped: Record<string, Array<{ proposal: ChangeProposal; item: ChangeProposalItem }>> = {}
      for (const proposal of this.pendingProposals as ChangeProposal[]) {
        for (const item of proposal.items) {
          if (item.status !== 'pending') continue
          const bucket = grouped[item.block_id] ?? (grouped[item.block_id] = [])
          bucket.push({ proposal, item })
        }
      }
      return grouped
    },

    // 按 scope 分类的统计（仅统计 pending 的 proposal）。
    scopeStats(): Record<ChangeProposalScope, number> {
      const stats: Record<ChangeProposalScope, number> = {
        block: 0, section: 0, sections: 0, chapters: 0, book: 0,
      }
      for (const proposal of this.pendingProposals as ChangeProposal[]) {
        stats[proposal.scope] = (stats[proposal.scope] || 0) + 1
      }
      return stats
    },

    isItemActing(state) {
      return (itemId: string) => state.actingItemIds.has(itemId)
    },
  },

  actions: {
    switchCourse(courseId: string) {
      if (this.courseId === courseId) return
      this.courseId = courseId
      this.courseRequestToken += 1
      this.proposals = []
      this.loading = false
      this.personalizationLoading = false
      this.applyingSelected = false
      this.actingItemIds.clear()
      this.lastRepresentationSync = null
    },

    isCurrentCourseRequest(courseId: string, courseRequestToken: number) {
      return this.courseId === courseId && this.courseRequestToken === courseRequestToken
    },

    async fetchChangeProposals(courseId: string) {
      if (!courseId) return
      this.switchCourse(courseId)
      const courseRequestToken = this.courseRequestToken
      const requestToken = ++this.fetchRequestToken
      this.loading = true
      try {
        const response = await http.get(`/api/courses/${courseId}/authoring-changes`)
        const data = response.data
        if (this.isCurrentCourseRequest(courseId, courseRequestToken) && this.fetchRequestToken === requestToken) {
          this.proposals = Array.isArray(data) ? data : (data?.proposals || [])
        }
      } catch (error) {
        if (this.isCurrentCourseRequest(courseId, courseRequestToken) && this.fetchRequestToken === requestToken) {
          logger.warn('Failed to fetch change proposals', error)
        }
      } finally {
        if (this.isCurrentCourseRequest(courseId, courseRequestToken) && this.fetchRequestToken === requestToken) {
          this.loading = false
        }
      }
    },

    findProposal(proposalId: string): ChangeProposal | undefined {
      return this.proposals.find(proposal => proposal.proposal_id === proposalId)
    },

    upsertProposal(proposal: ChangeProposal) {
      const index = this.proposals.findIndex(candidate => candidate.proposal_id === proposal.proposal_id)
      if (index >= 0) this.proposals.splice(index, 1, proposal)
      else this.proposals.unshift(proposal)
    },

    async createPersonalizationProposal(input: CreatePersonalizationProposalInput): Promise<ChangeProposal> {
      this.switchCourse(input.courseId)
      const courseRequestToken = this.courseRequestToken
      const requestToken = ++this.personalizationRequestToken
      this.personalizationLoading = true
      try {
        const response = await http.post(
          `/api/courses/${input.courseId}/blocks/${input.blockId}/personalization-proposals`,
          {
            request_id: input.requestId,
            expected_document_revision: input.expectedDocumentRevision,
            expected_block_revision: input.expectedBlockRevision,
            direction: input.direction,
            feedback: input.feedback,
            scope_selection: input.scopeSelection || 'current_block',
          },
        )
        const proposal = response.data as ChangeProposal
        if (
          this.isCurrentCourseRequest(input.courseId, courseRequestToken)
          && this.personalizationRequestToken === requestToken
        ) {
          this.upsertProposal(proposal)
        }
        return proposal
      } finally {
        if (
          this.isCurrentCourseRequest(input.courseId, courseRequestToken)
          && this.personalizationRequestToken === requestToken
        ) {
          this.personalizationLoading = false
        }
      }
    },

    async applySelectedItems(
      proposalId: string,
      itemIds: string[],
      expectedDocumentRevision: string,
    ): Promise<ApplySelectedChangeProposalResult> {
      if (!this.courseId) throw new Error('Missing current course')
      if (!itemIds.length) throw new Error('At least one change item must be selected')
      const courseId = this.courseId
      const courseRequestToken = this.courseRequestToken
      const requestToken = ++this.applySelectedRequestToken
      this.applyingSelected = true
      itemIds.forEach(itemId => this.actingItemIds.add(itemId))
      try {
        const response = await http.post(
          `/api/courses/${courseId}/authoring-changes/${proposalId}/apply-selected`,
          {
            item_ids: itemIds,
            expected_document_revision: expectedDocumentRevision,
          },
        )
        const result = response.data as ApplySelectedChangeProposalResult
        if (
          this.isCurrentCourseRequest(courseId, courseRequestToken)
          && this.applySelectedRequestToken === requestToken
        ) {
          this.upsertProposal(result.proposal)
          this.lastRepresentationSync = result.representation_sync || null
        }
        return result
      } finally {
        if (
          this.isCurrentCourseRequest(courseId, courseRequestToken)
          && this.applySelectedRequestToken === requestToken
        ) {
          this.applyingSelected = false
          itemIds.forEach(itemId => this.actingItemIds.delete(itemId))
        }
      }
    },

    // 硬性要求：处理某个 item（apply/reject/regenerate）只更新该 item 自身的状态，
    // 不得影响同一 proposal 内其它 item 的状态。
    patchItem(proposalId: string, itemId: string, patch: Partial<ChangeProposalItem>) {
      const proposal = this.findProposal(proposalId)
      if (!proposal) return
      const item = proposal.items.find(candidate => candidate.item_id === itemId)
      if (!item) return
      Object.assign(item, patch)
      if (proposal.items.every(candidate => candidate.status !== 'pending')) {
        proposal.status = 'resolved'
      }
    },

    async applyItem(proposalId: string, itemId: string) {
      if (!this.courseId) throw new Error('Missing current course')
      this.actingItemIds.add(itemId)
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/authoring-changes/${proposalId}/items/${itemId}/apply`,
        )
        this.lastRepresentationSync = response.data?.representation_sync || null
        this.patchItem(proposalId, itemId, { status: 'applied' })
        return response.data
      } finally {
        this.actingItemIds.delete(itemId)
      }
    },

    async rejectItem(proposalId: string, itemId: string, reason?: string) {
      if (!this.courseId) throw new Error('Missing current course')
      this.actingItemIds.add(itemId)
      try {
        await http.post(
          `/api/courses/${this.courseId}/authoring-changes/${proposalId}/items/${itemId}/reject`,
          reason ? { reason } : {},
        )
        this.patchItem(proposalId, itemId, { status: 'rejected' })
      } finally {
        this.actingItemIds.delete(itemId)
      }
    },

    async regenerateItem(proposalId: string, itemId: string, extraInstruction?: string) {
      if (!this.courseId) throw new Error('Missing current course')
      this.actingItemIds.add(itemId)
      try {
        const response = await http.post(
          `/api/courses/${this.courseId}/authoring-changes/${proposalId}/items/${itemId}/regenerate`,
          extraInstruction ? { extra_instruction: extraInstruction } : {},
        )
        const updated = response.data as ChangeProposal | Partial<ChangeProposalItem> | undefined
        if (updated && 'proposal_id' in updated && Array.isArray(updated.items)) {
          const proposalIndex = this.proposals.findIndex(
            proposal => proposal.proposal_id === proposalId,
          )
          if (proposalIndex >= 0) this.proposals.splice(proposalIndex, 1, updated)
        } else {
          // Backward compatibility for older servers that returned only an item patch.
          const itemPatch = updated as Partial<ChangeProposalItem> | undefined
          this.patchItem(proposalId, itemId, {
            status: 'pending',
            ...(itemPatch || {}),
          })
        }
      } finally {
        this.actingItemIds.delete(itemId)
      }
    },
  },
})
