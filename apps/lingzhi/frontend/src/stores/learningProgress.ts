import { defineStore } from 'pinia'
import http from '../utils/http'
import logger from '../utils/logger'
import type { LearnerModelSummary } from './learnerModel'
import { useCourseEvolutionStore } from './courseEvolution'

export type ReadingProgressStatus = 'not_started' | 'in_progress' | 'learned'
export type MasteryProgressStatus = 'not_checked' | 'evidence_insufficient' | 'partial' | 'mastered' | 'needs_review'

export interface LearningObjectiveProgress {
  objective_id: string
  objective_revision_id: string
  statement: string
  node_id: string
  node_name: string
  course_version_id: string
  reading_status: ReadingProgressStatus
  mastery_status: MasteryProgressStatus
  content_block_ids: string[]
  question_revision_ids: string[]
  criterion_revision_ids: string[]
  criterion_states: Array<{
    criterion_id: string
    criterion_revision_id: string
    observable_performance: string
    status: string
    latest_score?: number | null
    evidence_event_id?: string | null
  }>
  evidence_event_ids: string[]
  has_historical_evidence: boolean
}

export interface NextLearningAction {
  action_id: string
  action_type: string
  scope: string
  target_id: string
  target_revision_id: string
  node_id: string
  reason_code: string
  evidence_refs: string[]
  blocking: boolean
  requires_confirmation: boolean
  availability: 'available' | 'unavailable' | 'pending'
  task_ref?: LearningTaskRef
}

export interface LearningTaskRef {
  kind: 'reading' | 'practice' | 'diagnostic' | 'remediation' | 'validation' | 'record' | 'review'
  object_id: string
  task_revision_id: string
  status: string
  context: {
    course_id?: string
    course_version_id?: string
    chapter_id?: string
    node_id?: string
    objective_id?: string
    objective_revision_id?: string
    content_anchor?: Record<string, any> | null
  }
  return_node_id: string
}

export interface LearningContinuationProjection {
  schema_version: 'learning_continuation_v1'
  course_id: string
  course_version_id: string
  user_id: string
  projection_revision_id: string
  chapter: {
    chapter_id: string
    chapter_name: string
    chapter_index: number
    chapter_count: number
    objective_count: number
  }
  current_objective: LearningObjectiveProgress | null
  progress: {
    learning: 'not_started' | 'in_progress' | 'covered'
    mastery: 'not_checked' | 'evidence_insufficient' | 'partial' | 'verified' | 'needs_attention'
    task_continuity: 'none' | 'resumable' | 'stale' | 'blocked'
  }
  entry_mode: 'first_entry' | 'continue_learning' | 'resume_task' | 'version_change' | 'risk_handling' | 'awaiting_validation' | 'chapter_closeout'
  progression_contract: Record<string, any>
  risks: Array<Record<string, any>>
  chapter_result: {
    state: 'in_progress' | 'covered_unverified' | 'partially_verified' | 'verified' | 'needs_attention' | 'stale'
    chapter_id: string
    objectives: Array<Record<string, any>>
    residuals: Record<string, any>
  }
  primary_action: NextLearningAction
  secondary_notices: Array<Record<string, any>>
  version_conflicts: Array<Record<string, any>>
  version_transition?: VersionTransitionPlan | null
}

export interface VersionTransitionPlan {
  schema_version: 'learning_version_transition_v1'
  current_version_id: string
  source_version_ids: string[]
  snapshot: {
    snapshot_id: string
    source_version_id: string
    resolution_status: string
    content_changed?: boolean
    target_node_id: string
    previous_task_kind?: string
    previous_task_id?: string
    action: 'none' | 'migrate' | 'select_target'
    requires_target_node: boolean
  } | null
  attempts: Array<Record<string, any>>
  workflows: Array<Record<string, any>>
  records: {
    total: number
    by_migration_status: Record<string, number>
    needs_confirmation_ids: string[]
  }
  requires_target_node: boolean
  can_confirm: boolean
  summary: {
    migrated_snapshot: boolean
    invalidated_attempts: number
    stale_workflows: number
    preserved_records: number
  }
}

export interface LearningProgressProjection {
  schema_version: 'learning_progress_v1'
  course_id: string
  course_version_id: string
  user_id: string
  summary: {
    total_nodes: number
    not_started_nodes: number
    in_progress_nodes: number
    learned_nodes: number
    mastered_nodes: number
    needs_review_nodes: number
    completion_percentage: number
    mastery_percentage: number
  }
  nodes: LearningObjectiveProgress[]
}

export type AdaptiveBlockKind = 'explanation' | 'counterexample' | 'transition' | 'understanding_check' | 'animation'
export type AdaptiveBlockFeedback = 'unrated' | 'helpful' | 'not_helpful' | 'dismissed'
export type AdaptiveBlockInteraction = 'animation_played' | 'animation_answered' | 'validation_started'

export interface AdaptiveLearningBlock {
  adaptive_block_id: string
  change_set_id?: string
  anchor: {
    node_id: string
    content_block_id: string
    placement: 'after_block' | 'after_node'
  }
  kind: AdaptiveBlockKind
  role: 'low_risk_support' | 'accepted_personal_course_growth' | 'course_evolution_block'
  payload: {
    body: string
    contrast: string
    prompt: string
    objective: string
    knowledge_refs?: string[]
    ability_refs?: string[]
    expected_effect?: string
    steps?: Array<{ index: number; label: string }>
    animation_spec?: {
      schema_version: 'animation_spec_v1'
      animation_id: string
      title: string
      scene: Record<string, string>
      object_bindings: Array<Record<string, unknown>>
      knowledge_refs: string[]
      keyframes: Array<{
        index: number
        label: string
        state: Record<string, string>
        transformations: string[]
        duration_ms: number
        pause_after: boolean
      }>
      fallback_frames: Array<{ index: number; label: string; description?: string }>
      accessibility_text: string
    }
  }
  reason_code: string
  evidence_refs: string[]
  status: 'active' | 'expired'
  expires_at: string
  feedback: {
    value: AdaptiveBlockFeedback
    options: AdaptiveBlockFeedback[]
  }
}

export interface LearningRuntimeProjection {
  schema_version: 'learning_runtime_v1'
  course_id: string
  user_id: string
  context: Record<string, string>
  revision_vector: Record<string, string | number>
  runtime_revision_id: string
  course_availability: {
    schema_version: 'course_learning_availability_v1'
    mode: 'standard' | 'reading_only' | 'compatibility'
    reason_code: string
    capabilities: Record<string, { status: string; reason_code: string }>
  }
  snapshot: Record<string, any>
  progress: LearningProgressProjection
  records: {
    total: number
    by_type: Record<string, number>
    by_status: Record<string, number>
    open_issue_ids: string[]
  }
  practice: {
    total: number
    active: Array<Record<string, any>>
    pending_review_count: number
    needs_review_count: number
  }
  diagnostic: Record<string, any>
  learner_model: LearnerModelSummary
  course_evolution?: Record<string, any>
  adaptive_blocks: AdaptiveLearningBlock[]
  active_task: LearningTaskRef | null
  continuation: LearningContinuationProjection
}

const migrationKey = (courseId: string) => `learning_progress_legacy_migrated_v1:${courseId}`

const legacyCompletedNodeIds = (): string[] => {
  try {
    const stats = JSON.parse(localStorage.getItem('learning_stats') || '{}')
    return Array.isArray(stats.completedNodes)
      ? stats.completedNodes.map((item: unknown) => String(item)).filter(Boolean)
      : []
  } catch {
    return []
  }
}

export const useLearningProgressStore = defineStore('learningProgress', {
  state: () => ({
    courseId: '',
    projection: null as LearningProgressProjection | null,
    continuation: null as LearningContinuationProjection | null,
    runtime: null as LearningRuntimeProjection | null,
    loading: false,
    runtimeLoading: false,
    runtimeRequestSeq: 0,
    pendingNodeId: '',
  }),
  getters: {
    learnedNodeIds: state => (state.projection?.nodes || [])
      .filter(item => item.reading_status === 'learned')
      .map(item => item.node_id),
    masteredNodeIds: state => (state.projection?.nodes || [])
      .filter(item => item.mastery_status === 'mastered')
      .map(item => item.node_id),
  },
  actions: {
    nodeProgress(nodeId: string): LearningObjectiveProgress | null {
      return this.projection?.nodes?.find(item => item.node_id === nodeId) || null
    },

    async load(courseId: string, nodeId?: string) {
      if (!courseId) return null
      this.loading = true
      if (this.courseId !== courseId) this.pendingNodeId = ''
      this.courseId = courseId
      try {
        await this.loadRuntime(courseId, nodeId)
        try {
          const migration = await this.migrateLegacy(courseId)
          if (migration?.created) await this.loadRuntime(courseId, nodeId)
        } catch (error) {
          logger.warn('Legacy learning progress migration deferred', error)
        }
        return this.projection
      } finally {
        this.loading = false
      }
    },

    async startNode(courseId: string, nodeId: string) {
      if (!courseId || !nodeId || this.pendingNodeId === nodeId) return this.nodeProgress(nodeId)
      const current = this.nodeProgress(nodeId)
      if (current && current.reading_status !== 'not_started') {
        await this.loadRuntime(courseId, nodeId)
        return this.nodeProgress(nodeId)
      }
      this.pendingNodeId = nodeId
      try {
        const res = await http.post(`/api/courses/${courseId}/learning-progress/nodes/${nodeId}`, { action: 'start' })
        this.projection = res.data.projection
        await this.loadRuntime(courseId, nodeId)
        return this.nodeProgress(nodeId)
      } finally {
        this.pendingNodeId = ''
      }
    },

    async completeReading(courseId: string, nodeId: string) {
      if (!courseId || !nodeId) return null
      const res = await http.post(`/api/courses/${courseId}/learning-progress/nodes/${nodeId}`, { action: 'complete_reading' })
      this.projection = res.data.projection
      await this.loadRuntime(courseId, nodeId)
      return this.nodeProgress(nodeId)
    },

    async loadRuntime(courseId: string, nodeId?: string) {
      if (!courseId) return null
      const requestSeq = ++this.runtimeRequestSeq
      this.runtimeLoading = true
      try {
        const res = await http.get(`/api/courses/${courseId}/learning-runtime`, {
          params: nodeId ? { node_id: nodeId } : undefined,
        })
        if (requestSeq !== this.runtimeRequestSeq) return this.runtime
        this.courseId = courseId
        this.runtime = res.data
        this.projection = res.data.progress
        this.continuation = res.data.continuation
        if (res.data.course_evolution) {
          useCourseEvolutionStore().applyPayload(courseId, res.data.course_evolution)
        }
        return this.runtime
      } finally {
        if (requestSeq === this.runtimeRequestSeq) this.runtimeLoading = false
      }
    },

    async feedbackAdaptiveBlock(
      courseId: string,
      block: AdaptiveLearningBlock,
      feedback: Exclude<AdaptiveBlockFeedback, 'unrated'>,
    ) {
      const storageKey = `adaptive_block_feedback_v1:${courseId}:${block.adaptive_block_id}`
      localStorage.setItem(storageKey, feedback)
      if (this.runtime) {
        this.runtime.adaptive_blocks = feedback === 'dismissed'
          ? this.runtime.adaptive_blocks.filter(item => item.adaptive_block_id !== block.adaptive_block_id)
          : this.runtime.adaptive_blocks.map(item => item.adaptive_block_id === block.adaptive_block_id
              ? { ...item, feedback: { ...item.feedback, value: feedback } }
              : item)
      }
      try {
        await http.post(`/api/courses/${courseId}/learning-runtime/adaptive-blocks/feedback`, {
          adaptive_block_id: block.adaptive_block_id,
          node_id: block.anchor.node_id,
          feedback,
        })
        return true
      } catch (error) {
        logger.warn('Adaptive block feedback deferred', error)
        return false
      }
    },

    async recordAdaptiveBlockInteraction(
      courseId: string,
      block: AdaptiveLearningBlock,
      interaction: AdaptiveBlockInteraction,
      details: {
        answer?: 'right_then_left' | 'left_then_right'
        correct?: boolean
        frame_index?: number
      } = {},
    ) {
      try {
        await http.post(`/api/courses/${courseId}/learning-runtime/adaptive-blocks/interactions`, {
          adaptive_block_id: block.adaptive_block_id,
          node_id: block.anchor.node_id,
          interaction,
          ...details,
        })
        return true
      } catch (error) {
        logger.warn('Adaptive block interaction deferred', error)
        return false
      }
    },

    async deferRisk(courseId: string, riskId: string, nodeId?: string) {
      if (!this.continuation) return null
      const res = await http.post(`/api/courses/${courseId}/learning-continuation/risks/${riskId}/defer`, {
        expected_projection_revision_id: this.continuation.projection_revision_id,
        defer_hours: 24,
        node_id: nodeId || this.continuation.current_objective?.node_id || undefined,
      })
      this.continuation = res.data.projection
      await this.loadRuntime(courseId, nodeId)
      return this.continuation
    },

    async confirmVersionTransition(
      courseId: string,
      options: { requestId: string; nodeId?: string; targetNodeId?: string },
    ) {
      if (!this.continuation?.projection_revision_id) return null
      const res = await http.post(`/api/courses/${courseId}/learning-continuation/version-change/confirm`, {
        expected_projection_revision_id: this.continuation.projection_revision_id,
        request_id: options.requestId,
        node_id: options.nodeId || undefined,
        target_node_id: options.targetNodeId || undefined,
      })
      const runtime = res.data.runtime as LearningRuntimeProjection
      this.courseId = courseId
      this.runtime = runtime
      this.projection = runtime.progress
      this.continuation = runtime.continuation
      if (runtime.course_evolution) {
        useCourseEvolutionStore().applyPayload(courseId, runtime.course_evolution)
      }
      return res.data
    },

    async migrateLegacy(courseId: string) {
      if (localStorage.getItem(migrationKey(courseId))) return
      const nodeIds = legacyCompletedNodeIds()
      if (nodeIds.length) {
        const res = await http.post(`/api/courses/${courseId}/learning-progress/migrate-legacy`, { node_ids: nodeIds })
        this.projection = res.data.projection
        localStorage.setItem(migrationKey(courseId), new Date().toISOString())
        return res.data
      }
      localStorage.setItem(migrationKey(courseId), new Date().toISOString())
      return { created: 0 }
    },
  },
})
