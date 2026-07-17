import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: httpMock }))

import {
  useLearningProgressStore,
  type LearningContinuationProjection,
  type LearningProgressProjection,
} from '@/stores/learningProgress'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'

const projection = (reading_status: 'not_started' | 'in_progress' | 'learned' = 'not_started'): LearningProgressProjection => ({
  schema_version: 'learning_progress_v1',
  course_id: 'c1',
  course_version_id: 'cv1',
  user_id: 'default_user',
  summary: {
    total_nodes: 1,
    not_started_nodes: reading_status === 'not_started' ? 1 : 0,
    in_progress_nodes: reading_status === 'in_progress' ? 1 : 0,
    learned_nodes: reading_status === 'learned' ? 1 : 0,
    mastered_nodes: 0,
    needs_review_nodes: 0,
    completion_percentage: reading_status === 'learned' ? 100 : 0,
    mastery_percentage: 0,
  },
  nodes: [{
    objective_id: 'lo_1',
    objective_revision_id: 'lor_1',
    statement: '能够解释向量',
    node_id: 'n1',
    node_name: '向量',
    course_version_id: 'cv1',
    reading_status,
    mastery_status: reading_status === 'learned' ? 'evidence_insufficient' : 'not_checked',
    content_block_ids: ['b1'],
    question_revision_ids: ['qr_1'],
    criterion_revision_ids: ['mcr_1'],
    criterion_states: [],
    evidence_event_ids: [],
    has_historical_evidence: false,
  }],
})

const continuation = (actionType = 'start_objective'): LearningContinuationProjection => ({
  schema_version: 'learning_continuation_v1',
  course_id: 'c1', course_version_id: 'cv1', user_id: 'default_user', projection_revision_id: 'lcr1',
  chapter: { chapter_id: 'chapter-1', chapter_name: '第一章', chapter_index: 0, chapter_count: 1, objective_count: 1 },
  current_objective: projection().nodes[0]!,
  progress: { learning: 'not_started', mastery: 'not_checked', task_continuity: 'none' },
  entry_mode: 'first_entry', progression_contract: {}, risks: [],
  chapter_result: { state: 'in_progress', chapter_id: 'chapter-1', objectives: [], residuals: {} },
  primary_action: {
    action_id: 'a1', action_type: actionType, scope: 'learning_objective', target_id: 'lor_1',
    target_revision_id: 'lor_1', node_id: 'n1', reason_code: 'reading_not_started', evidence_refs: [],
    blocking: false, requires_confirmation: false, availability: 'available',
  },
  secondary_notices: [], version_conflicts: [],
})

const runtime = (progress = projection(), next = continuation()) => ({
  schema_version: 'learning_runtime_v1',
  course_id: 'c1',
  user_id: 'default_user',
  context: { course_id: 'c1', course_version_id: 'cv1', node_id: 'n1' },
  revision_vector: { course_version_id: 'cv1' },
  runtime_revision_id: 'lrr1',
  snapshot: { current: null, resolution: null },
  progress,
  records: { total: 0, by_type: {}, by_status: {}, open_issue_ids: [] },
  practice: { total: 0, active: [], pending_review_count: 0, needs_review_count: 0 },
  diagnostic: { phase: 'practice' },
  course_evolution: undefined as Record<string, unknown> | undefined,
  active_task: null,
  continuation: next,
})

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

describe('learning progress store', () => {
  it('加载服务端投影并以它作为完成状态真源', async () => {
    httpMock.get.mockResolvedValue({ data: runtime(projection('learned'), continuation('start_next_chapter')) })
    const store = useLearningProgressStore()

    await store.load('c1')

    expect(store.learnedNodeIds).toEqual(['n1'])
    expect(store.projection?.summary.completion_percentage).toBe(100)
    expect(store.continuation?.primary_action.action_type).toBe('start_next_chapter')
  })

  it('打开未开始节点只写开始动作，不写学完', async () => {
    const store = useLearningProgressStore()
    store.courseId = 'c1'
    store.projection = projection('not_started')
    httpMock.post.mockResolvedValue({ data: { projection: projection('in_progress') } })
    httpMock.get.mockResolvedValue({ data: runtime(projection('in_progress'), continuation('complete_reading')) })

    await store.startNode('c1', 'n1')

    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/c1/learning-progress/nodes/n1', { action: 'start' })
    expect(store.nodeProgress('n1')?.reading_status).toBe('in_progress')
  })

  it('打开已学习节点不重复写事件，但必须刷新该节点运行态', async () => {
    const store = useLearningProgressStore()
    store.courseId = 'c1'
    store.projection = projection('learned')
    httpMock.get.mockResolvedValue({ data: runtime(projection('learned'), continuation('start_mastery_check')) })

    await store.startNode('c1', 'n1')

    expect(httpMock.post).not.toHaveBeenCalled()
    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/c1/learning-runtime', { params: { node_id: 'n1' } })
    expect(store.continuation?.primary_action.action_type).toBe('start_mastery_check')
  })

  it('只有明确动作才将阅读状态改为已学完', async () => {
    const store = useLearningProgressStore()
    store.courseId = 'c1'
    store.projection = projection('in_progress')
    httpMock.post.mockResolvedValue({ data: { projection: projection('learned') } })
    httpMock.get.mockResolvedValue({ data: runtime(projection('learned'), continuation('start_next_chapter')) })

    await store.completeReading('c1', 'n1')

    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/c1/learning-progress/nodes/n1', { action: 'complete_reading' })
    expect(store.nodeProgress('n1')?.reading_status).toBe('learned')
    expect(store.nodeProgress('n1')?.mastery_status).toBe('evidence_insufficient')
  })

  it('旧完成数组只迁移一次', async () => {
    localStorage.setItem('learning_stats', JSON.stringify({ completedNodes: ['n1'] }))
    httpMock.get.mockResolvedValue({ data: runtime() })
    httpMock.post.mockResolvedValue({ data: { projection: projection('in_progress') } })
    const store = useLearningProgressStore()

    await store.load('c1')
    await store.load('c1')

    expect(httpMock.post).toHaveBeenCalledTimes(1)
    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/c1/learning-progress/migrate-legacy', { node_ids: ['n1'] })
  })

  it('较慢的旧节点响应不能覆盖较新的运行时', async () => {
    let resolveFirst!: (value: any) => void
    let resolveSecond!: (value: any) => void
    httpMock.get
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))
    const store = useLearningProgressStore()

    const first = store.loadRuntime('c1', 'n1')
    const second = store.loadRuntime('c1', 'n2')
    resolveSecond({ data: runtime(projection('learned'), continuation('start_next_chapter')) })
    await second
    resolveFirst({ data: runtime(projection('not_started'), continuation('start_objective')) })
    await first

    expect(store.projection?.summary.completion_percentage).toBe(100)
    expect(store.continuation?.primary_action.action_type).toBe('start_next_chapter')
  })

  it('运行时刷新同步更新课程生长建议和目录所读的同一状态', async () => {
    const nextRuntime = runtime()
    nextRuntime.course_evolution = {
      evidence_items: [{ evidence_id: 'e1', source_type: 'learning_event' }],
      hypotheses: [],
      course_evolution_plans: [{
        change_set_id: 'plan-1',
        hypothesis_id: 'hypothesis-1',
        evidence_ids: ['e1'],
        operations: [],
        allowed_scopes: ['current'],
        impact_summary: { affected_section_ids: ['n1'] },
        expected_effect: '补充当前理解',
        status: 'pending',
        effect_evaluation: {},
      }],
    }
    httpMock.get.mockResolvedValue({ data: nextRuntime })

    await useLearningProgressStore().loadRuntime('c1', 'n1')

    const evolution = useCourseEvolutionStore()
    expect(evolution.courseId).toBe('c1')
    expect(evolution.evidenceItems.map(item => item.evidence_id)).toEqual(['e1'])
    expect(evolution.pendingPlans.map(item => item.change_set_id)).toEqual(['plan-1'])
  })

  it('确认版本变化时携带投影修订并采用服务端新运行时', async () => {
    const store = useLearningProgressStore()
    const versionContinuation = continuation('confirm_version_change')
    versionContinuation.projection_revision_id = 'version-projection-1'
    versionContinuation.entry_mode = 'version_change'
    versionContinuation.version_transition = {
      schema_version: 'learning_version_transition_v1', current_version_id: 'cv2', source_version_ids: ['cv1'],
      snapshot: null, attempts: [], workflows: [],
      records: { total: 0, by_migration_status: {}, needs_confirmation_ids: [] },
      requires_target_node: false, can_confirm: true,
      summary: { migrated_snapshot: true, invalidated_attempts: 1, stale_workflows: 0, preserved_records: 0 },
    }
    store.continuation = versionContinuation
    const updated = runtime(projection('in_progress'), continuation('complete_reading'))
    updated.context.course_version_id = 'cv2'
    httpMock.post.mockResolvedValue({ data: { status: 'confirmed', runtime: updated } })

    await store.confirmVersionTransition('c1', { requestId: 'request-1', nodeId: 'n1' })

    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/c1/learning-continuation/version-change/confirm', {
      expected_projection_revision_id: 'version-projection-1',
      request_id: 'request-1',
      node_id: 'n1',
      target_node_id: undefined,
    })
    expect(store.continuation?.primary_action.action_type).toBe('complete_reading')
    expect(store.runtime?.context.course_version_id).toBe('cv2')
  })
})
