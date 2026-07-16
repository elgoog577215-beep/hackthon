import { defineStore } from 'pinia'
import http from '../utils/http'
import type { ChangeProposal, ChangeProposalItem, ChangeProposalScope } from '../types/changeProposal'
import logger from '../utils/logger'

interface ChangeProposalsState {
  courseId: string
  proposals: ChangeProposal[]
  loading: boolean
  actingItemIds: Set<string>
}

export const useChangeProposalsStore = defineStore('changeProposals', {
  state: (): ChangeProposalsState => ({
    courseId: '',
    proposals: [],
    loading: false,
    actingItemIds: new Set<string>(),
  }),

  getters: {
    // 仅返回仍有 pending item 的 proposal（proposal.status 可能已被后端标记 resolved，
    // 但为了防御性展示，同时以 item.status 过滤）。
    pendingProposals(state): ChangeProposal[] {
      return state.proposals.filter(proposal => (
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
    async fetchChangeProposals(courseId: string) {
      if (!courseId) return
      this.courseId = courseId
      this.loading = true
      try {
        const response = await http.get(`/api/courses/${courseId}/authoring-changes`)
        const data = response.data
        this.proposals = Array.isArray(data) ? data : (data?.proposals || [])
      } catch (error) {
        logger.warn('Failed to fetch change proposals', error)
      } finally {
        this.loading = false
      }
    },

    findProposal(proposalId: string): ChangeProposal | undefined {
      return this.proposals.find(proposal => proposal.proposal_id === proposalId)
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
        await http.post(
          `/api/courses/${this.courseId}/authoring-changes/${proposalId}/items/${itemId}/apply`,
        )
        this.patchItem(proposalId, itemId, { status: 'applied' })
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
