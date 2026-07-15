/**
 * 待确认 AI 变更 Store（PendingChangeOverlay）
 * 覆盖规格文档中"AI 变更 MUST 以待确认形式呈现"与"变更作用域 MUST 可控且显式"的前端状态管理。
 *
 * Phase 2：已接入真实后端接口（见 backend 契约）：
 *   GET  /api/courses/{courseId}/pending_changes
 *   POST /api/courses/{courseId}/change_sets/{changeSetId}/accept      { node_ids? }
 *   POST /api/courses/{courseId}/change_sets/{changeSetId}/reject      { reason?, node_ids? }
 *   POST /api/courses/{courseId}/change_sets/{changeSetId}/regenerate  { extra_instruction? }
 */
import { defineStore } from 'pinia'
import http from '../utils/http'
import { ElMessage } from 'element-plus'
import logger from '../utils/logger'
import type { CourseChangeSet, ChangeItem, PendingChangeOverlay } from '../types/adaptiveChange'

/** 保留 mock 生成器供测试/离线演示复用 */
function mockChangeSets(courseId: string): CourseChangeSet[] {
  const now = Date.now()
  return [
    {
      id: 'ccs-mock-1',
      course_id: courseId,
      scope: 'block',
      scope_node_ids: ['node-1-2'],
      change_items: [
        {
          target_node_id: 'node-1-2',
          operation: 'update',
          before: '牛顿第二定律：F = ma。',
          after: '牛顿第二定律：F = ma。结合你在上一次测验中对"惯性"概念的反复追问，补充一个生活化类比：推购物车时越用力，加速度越大；购物车越重，同样力下加速度越小。',
          reason: '检测到你在该节点多次追问相关概念，且错题中存在对惯性理解的偏差，建议补充类比说明。',
        },
      ],
      source_hypothesis_id: 'hyp-mock-1',
      status: 'pending',
      created_at: now - 3600_000,
      resolved_at: null,
    },
    {
      id: 'ccs-mock-2',
      course_id: courseId,
      scope: 'section',
      scope_node_ids: ['node-2', 'node-2-1', 'node-2-2'],
      change_items: [
        {
          target_node_id: 'node-2-1',
          operation: 'update',
          before: '（原有例题：匀速直线运动）',
          after: '（新增例题：变速直线运动，含分步推导）',
          reason: '综合本小节多个节点的错题分布，判断你对匀变速运动的例题练习不足。',
        },
        {
          target_node_id: 'node-2-2',
          operation: 'insert',
          before: null,
          after: '新增小节：加速度的图像法求解',
          reason: '同一假设联动影响到相邻小节，建议一并补充图像法讲解。',
        },
      ],
      source_hypothesis_id: 'hyp-mock-2',
      status: 'pending',
      created_at: now - 1800_000,
      resolved_at: null,
    },
    {
      id: 'ccs-mock-3',
      course_id: courseId,
      scope: 'block',
      scope_node_ids: ['node-3-1'],
      change_items: [
        {
          target_node_id: 'node-3-1',
          operation: 'update',
          before: '（原有公式推导，未展开中间步骤）',
          after: '（补充展开的中间推导步骤，并标注每一步依据）',
          reason: '笔记中标记"看不懂这一步怎么来的"，AI 判断需要补充推导细节。',
        },
      ],
      source_hypothesis_id: 'hyp-mock-3',
      status: 'pending',
      created_at: now - 600_000,
      resolved_at: null,
    },
  ]
}

export const usePendingChangesStore = defineStore('pendingChanges', {
  state: () => ({
    /** 当前课程的所有变更集（含 pending/accepted/rejected/regenerated，便于展示历史） */
    changeSets: [] as CourseChangeSet[],
    loading: false,
    currentCourseId: '' as string,
  }),

  getters: {
    /** 仅待处理的变更集 */
    pendingChangeSets(state): CourseChangeSet[] {
      return state.changeSets.filter(cs => cs.status === 'pending')
    },

    /**
     * 按 node_id 分组的待处理变更集（PendingChangeOverlay.byNodeId）。
     * 一个变更集可能通过 scope_node_ids / change_items 影响多个节点，因此会出现在多个分组中。
     */
    pendingByNodeId(state): Record<string, CourseChangeSet[]> {
      const map: Record<string, CourseChangeSet[]> = {}
      for (const cs of state.changeSets) {
        if (cs.status !== 'pending') continue
        const nodeIds = new Set<string>([
          ...cs.scope_node_ids,
          ...cs.change_items.map(ci => ci.target_node_id),
        ])
        for (const nodeId of nodeIds) {
          if (!map[nodeId]) map[nodeId] = []
          map[nodeId].push(cs)
        }
      }
      return map
    },

    /** 当前课程待处理变更总数，用于 UI 角标 */
    pendingCount(): number {
      return this.pendingChangeSets.length
    },

    /** 指定课程节点上的待处理变更集（不含作用目标为知识图谱节点的变更） */
    pendingForNode(state) {
      return (nodeId: string): CourseChangeSet[] => {
        return state.changeSets.filter(
          cs =>
            cs.status === 'pending' &&
            (cs.scope_node_ids.includes(nodeId) ||
              cs.change_items.some(
                ci =>
                  ci.target_node_id === nodeId &&
                  (ci.target_kind === undefined || ci.target_kind === 'course_node')
              ))
        )
      }
    },

    /** 指定知识图谱节点上的待处理变更集 */
    pendingForKgNode(state) {
      return (kgNodeId: string): CourseChangeSet[] => {
        return state.changeSets.filter(
          cs =>
            cs.status === 'pending' &&
            cs.change_items.some(ci => ci.target_node_id === kgNodeId && ci.target_kind === 'kg_node')
        )
      }
    },
  },

  actions: {
    /**
     * 拉取指定课程的待确认变更集。
     * 优先使用真实接口 GET /api/courses/{courseId}/pending_changes（返回 PendingChangeOverlay.byNodeId）；
     * 请求失败时回退到本地 mock 数据，保证组件在后端未就绪时仍可演示/开发。
     */
    async fetchPendingChanges(courseId: string) {
      this.loading = true
      this.currentCourseId = courseId
      try {
        const res = await http.get<PendingChangeOverlay>(`/api/courses/${courseId}/pending_changes`)
        const byNodeId = res.data?.byNodeId || {}
        const merged = new Map<string, CourseChangeSet>()
        Object.values(byNodeId).forEach(list => {
          list.forEach(cs => merged.set(cs.id, cs))
        })
        this.changeSets = Array.from(merged.values())
      } catch (error) {
        logger.error('Failed to fetch pending changes, falling back to mock data', error)
        this.changeSets = mockChangeSets(courseId)
      } finally {
        this.loading = false
      }
    },

    /**
     * 接受一个变更集。
     * 若传入 nodeIds，则仅接受变更集中命中这些节点的 change_items（支持"对不同节点分别接受/拒绝"）；
     * 当变更集内所有 change_items 均被处理后，整个变更集状态才会变为 accepted。
     * 调用 POST /api/courses/{courseId}/change_sets/{changeSetId}/accept { node_ids? }，
     * 并用后端返回的最新 change_set 覆盖本地状态。
     */
    async acceptChangeSet(changeSetId: string, nodeIds?: string[]) {
      const cs = this.changeSets.find(c => c.id === changeSetId)
      if (!cs || cs.status !== 'pending') return

      try {
        const res = await http.post<CourseChangeSet>(
          `/api/courses/${this.currentCourseId}/change_sets/${changeSetId}/accept`,
          { node_ids: nodeIds && nodeIds.length > 0 ? nodeIds : undefined }
        )
        this.applyChangeSetResult(res.data)
      } catch (error) {
        logger.error('Failed to accept change set', error)
        ElMessage.error('接受变更失败，请稍后重试')
      }
    },

    /**
     * 拒绝一个变更集（或其中部分节点）。
     * 调用 POST /api/courses/{courseId}/change_sets/{changeSetId}/reject { reason?, node_ids? }。
     */
    async rejectChangeSet(changeSetId: string, reason?: string, nodeIds?: string[]) {
      const cs = this.changeSets.find(c => c.id === changeSetId)
      if (!cs || cs.status !== 'pending') return

      try {
        const res = await http.post<CourseChangeSet>(
          `/api/courses/${this.currentCourseId}/change_sets/${changeSetId}/reject`,
          { reason, node_ids: nodeIds && nodeIds.length > 0 ? nodeIds : undefined }
        )
        this.applyChangeSetResult(res.data)
      } catch (error) {
        logger.error('Failed to reject change set', error)
        ElMessage.error('拒绝变更失败，请稍后重试')
      }
    },

    /**
     * 请求重新生成一个变更集（例如学生不满意当前建议，附加额外指令）。
     * 调用 POST /api/courses/{courseId}/change_sets/{changeSetId}/regenerate { extra_instruction? }，
     * 原变更集标记为 regenerated，后端返回的新 CourseChangeSet 被 push 进 changeSets。
     */
    async regenerateChangeSet(changeSetId: string, extraInstruction?: string) {
      const cs = this.changeSets.find(c => c.id === changeSetId)
      if (!cs || cs.status !== 'pending') return

      try {
        const res = await http.post<CourseChangeSet>(
          `/api/courses/${this.currentCourseId}/change_sets/${changeSetId}/regenerate`,
          { extra_instruction: extraInstruction }
        )
        cs.status = 'regenerated'
        cs.resolved_at = Date.now()
        if (res.data) {
          this.changeSets.push(res.data)
        }
      } catch (error) {
        logger.error('Failed to regenerate change set', error)
        ElMessage.error('重新生成失败，请稍后重试')
      }
    },

    /** 将后端返回的最新 change_set 结果写回本地状态（accept/reject 共用） */
    applyChangeSetResult(updated: CourseChangeSet | undefined) {
      if (!updated) return
      const idx = this.changeSets.findIndex(c => c.id === updated.id)
      if (idx >= 0) {
        this.changeSets.splice(idx, 1, updated)
      } else {
        this.changeSets.push(updated)
      }
    },

    reset() {
      this.changeSets = []
      this.currentCourseId = ''
    },
  },
})

export type { ChangeItem }
