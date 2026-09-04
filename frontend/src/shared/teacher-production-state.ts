import { t } from './i18n'

export const COURSE_PRODUCTION_STAGE_KEYS = ['outline', 'lesson_plan', 'script', 'ppt'] as const

export type CourseProductionStageKey = typeof COURSE_PRODUCTION_STAGE_KEYS[number]
export type CourseProductionDisplayState = 'not_generated' | 'generating' | 'available' | 'failed'
export type CourseProductionTaskState = 'idle' | 'queued' | 'running' | 'paused' | 'failed' | 'completed'
export type CourseProductionAvailability = 'missing' | 'usable' | 'stale'
export type CourseProductionSourceState = 'missing' | 'current' | 'stale' | 'mixed'

export interface CourseProductionCounts {
  total: number
  available: number
  generating: number
  failed: number
  stale: number
}

export interface CourseProductionRecovery {
  action: string
  automatic: false
  requires_confirmation: true
}

export interface CourseProductionIssue {
  issue_id: string
  stage: CourseProductionStageKey
  lesson_unit_id: string
  block_id?: string
  task_id?: string
  source_id?: string
  blocking?: boolean
  category?: string
  code: string
  summary: string
  recovery: CourseProductionRecovery
}

export interface CourseProductionLatestAttempt {
  attempt_id: string
  task_ids: string[]
  task_state: CourseProductionTaskState
  target_count: number
  completed: number
  failed: number
  progress: number
  lesson_unit_ids: string[]
  message: string
  updated_at: string
}

export interface AssetProductionState {
  display_state: CourseProductionDisplayState
  task_state: CourseProductionTaskState
  availability: CourseProductionAvailability
  source_state: CourseProductionSourceState
  latest_attempt_failed: boolean
  update_required: boolean
  issues: CourseProductionIssue[]
}

export interface StageProductionState extends AssetProductionState {
  counts: CourseProductionCounts
  latest_attempt?: CourseProductionLatestAttempt
  blocking_issues?: CourseProductionIssue[]
  review_issues?: CourseProductionIssue[]
}

export interface CourseProductionSource {
  source_id: string
  label: string
  requirement: 'required' | 'optional'
  state: 'verified' | 'pending_review' | 'blocked'
  code: string
  summary: string
}

export interface CourseProductionSourceSummary {
  pending_review_count: number
  required_blocked_count: number
  sources: CourseProductionSource[]
}

export interface LessonProductionState {
  lesson_unit_id: string
  title: string
  stages: Partial<Record<Exclude<CourseProductionStageKey, 'outline'>, AssetProductionState>>
}

export interface CourseProductionState {
  schema_version: 'course_production_state_v1'
  course_id: string
  preparation_state: 'preparing' | 'prepared'
  stages: Record<CourseProductionStageKey, StageProductionState>
  lessons: LessonProductionState[]
  issues: CourseProductionIssue[]
  source_summary?: CourseProductionSourceSummary
}

type ProductionEnvelope = { course_production_state?: unknown }
type LegacyTask = {
  id?: string
  taskType?: string
  status?: string
  currentPhase?: string
  error?: string
  progress?: number
  phaseDetail?: Record<string, unknown>
  recovery?: { checkpoint?: Record<string, unknown> }
}
type LegacyCourse = {
  course_production_state?: unknown
  course_id?: string
  node_count?: number
  preparation_state?: 'preparing' | 'prepared'
  preparation_summary?: {
    planned_lessons?: number
    outline_ready?: boolean
    ready_lesson_plans?: number
    ready_handouts?: number
    ready_ppts?: number
    current_production?: {
      target?: CourseProductionStageKey | 'lesson_plan' | 'script' | 'ppt'
      status?: string
      completed?: number
      total?: number
      failed?: number
      progress?: number
      message?: string
      updated_at?: string
    }
  }
}

const DISPLAY_STATES = new Set<CourseProductionDisplayState>(['not_generated', 'generating', 'available', 'failed'])
const TASK_STATES = new Set<CourseProductionTaskState>(['idle', 'queued', 'running', 'paused', 'failed', 'completed'])

function isStage(value: unknown): value is StageProductionState {
  if (!value || typeof value !== 'object') return false
  const stage = value as StageProductionState
  return DISPLAY_STATES.has(stage.display_state)
    && TASK_STATES.has(stage.task_state)
    && Boolean(stage.counts && Number.isFinite(stage.counts.total))
}

export function readCourseProductionState(source?: ProductionEnvelope | CourseProductionState | null): CourseProductionState | null {
  const value = source && 'schema_version' in source
    ? source
    : source?.course_production_state
  if (!value || typeof value !== 'object') return null
  const state = value as CourseProductionState
  if (state.schema_version !== 'course_production_state_v1' || !state.course_id) return null
  if (!COURSE_PRODUCTION_STAGE_KEYS.every(key => isStage(state.stages?.[key]))) return null
  return state
}

function taskStage(task?: LegacyTask): CourseProductionStageKey {
  if (task?.taskType === 'teacher_outline_generation') return 'outline'
  const phase = String(task?.currentPhase || '').toLowerCase()
  if (/script|handout|content/.test(phase)) return 'script'
  if (/ppt|slide/.test(phase)) return 'ppt'
  if (/lesson|teaching/.test(phase)) return 'lesson_plan'
  return 'outline'
}

function legacyTaskState(status = ''): CourseProductionTaskState {
  if (status === 'running') return 'running'
  if (['pending', 'queued'].includes(status)) return 'queued'
  if (['paused', 'waiting_for_input', 'waiting_for_review', 'conflict'].includes(status)) return 'paused'
  if (['failed', 'error', 'cancelled'].includes(status)) return 'failed'
  if (['completed', 'completed_with_warnings'].includes(status)) return 'completed'
  return 'idle'
}

function emptyStage(total: number, available: number): StageProductionState {
  return {
    display_state: total > 0 && available > 0 ? 'available' : 'not_generated',
    task_state: 'idle',
    availability: total > 0 && available >= total ? 'usable' : available > 0 ? 'stale' : 'missing',
    source_state: available > 0 ? 'current' : 'missing',
    latest_attempt_failed: false,
    update_required: false,
    counts: { total, available, generating: 0, failed: 0, stale: 0 },
    issues: [],
  }
}

// Temporary compatibility compiler. It is deliberately pure and lives beside the
// only reader so old response fields cannot become a second page-owned state model.
export function readCourseProductionStateWithLegacy(
  course: LegacyCourse,
  task?: LegacyTask,
): CourseProductionState {
  const current = readCourseProductionState(course)
  if (current) return current
  const summary = course.preparation_summary || {}
  const total = Math.max(0, Number(summary.planned_lessons || course.node_count || 0))
  const stages: CourseProductionState['stages'] = {
    outline: emptyStage(1, summary.outline_ready ? 1 : 0),
    lesson_plan: emptyStage(total, Math.max(0, Number(summary.ready_lesson_plans || 0))),
    script: emptyStage(total, Math.max(0, Number(summary.ready_handouts || 0))),
    ppt: emptyStage(total, Math.max(0, Number(summary.ready_ppts || 0))),
  }
  const legacyCurrent = summary.current_production
  const stageKey = legacyCurrent?.target || taskStage(task)
  const status = String(legacyCurrent?.status || task?.status || '')
  const taskState = legacyTaskState(status)
  if (status) {
    const stage = stages[stageKey]
    const completed = Math.max(0, Number(legacyCurrent?.completed ?? stage.counts.available))
    const targetTotal = Math.max(0, Number(legacyCurrent?.total || stage.counts.total))
    const failed = Math.max(0, Number(legacyCurrent?.failed || (taskState === 'failed' ? 1 : 0)))
    stage.task_state = taskState
    stage.counts = {
      ...stage.counts,
      generating: ['queued', 'running', 'paused'].includes(taskState) ? Math.max(1, targetTotal - completed) : 0,
      failed,
    }
    stage.display_state = stage.counts.available > 0
      ? 'available'
      : ['queued', 'running', 'paused'].includes(taskState)
        ? 'generating'
        : taskState === 'failed' || failed > 0 ? 'failed' : stage.display_state
    stage.latest_attempt_failed = taskState === 'failed' || failed > 0
    stage.latest_attempt = {
      attempt_id: String(task?.id || ''),
      task_ids: task?.id ? [task.id] : [],
      task_state: taskState,
      target_count: targetTotal,
      completed,
      failed,
      progress: Math.max(0, Math.min(100, Number(legacyCurrent?.progress ?? task?.progress ?? 0))),
      lesson_unit_ids: [],
      message: String(legacyCurrent?.message || task?.error || ''),
      updated_at: String(legacyCurrent?.updated_at || ''),
    }
    if (stage.latest_attempt_failed) {
      stage.issues = [{
        issue_id: `legacy-${stageKey}-${task?.id || 'current'}`,
        stage: stageKey,
        lesson_unit_id: '',
        task_id: task?.id,
        code: 'legacy_generation_failed',
        summary: stage.latest_attempt.message || t('teacherProductionState.auxiliary.recentFailure'),
        recovery: { action: 'retry_generation', automatic: false, requires_confirmation: true },
      }]
    }
  }
  const prepared = course.preparation_state === 'prepared' || (
    stages.outline.availability === 'usable'
    && total > 0
    && ['lesson_plan', 'script', 'ppt'].every(key => stages[key as CourseProductionStageKey].counts.available >= total)
  )
  const issues = COURSE_PRODUCTION_STAGE_KEYS.flatMap(key => stages[key].issues)
  return {
    schema_version: 'course_production_state_v1',
    course_id: String(course.course_id || ''),
    preparation_state: prepared ? 'prepared' : 'preparing',
    stages,
    lessons: [],
    issues,
  }
}

export function workbenchStageForProduction(stage: CourseProductionStageKey): 'foundation' | 'lesson' | 'script' | 'ppt' {
  return stage === 'outline' ? 'foundation' : stage === 'lesson_plan' ? 'lesson' : stage
}

export function productionStageLabel(stage: CourseProductionStageKey): string {
  const fallback: Record<CourseProductionStageKey, string> = {
    outline: '大纲',
    lesson_plan: '教案',
    script: '讲义',
    ppt: 'PPT',
  }
  return t(`teacherProductionState.stages.${stage}`, fallback[stage])
}

export function productionDisplayStateLabel(state: CourseProductionDisplayState): string {
  const fallback: Record<CourseProductionDisplayState, string> = {
    not_generated: '未生成',
    generating: '生成中',
    available: '可使用',
    failed: '生成失败',
  }
  return t(`teacherProductionState.states.${state}`, fallback[state])
}

export function productionTaskStateLabel(state: CourseProductionTaskState): string {
  const fallback: Record<CourseProductionTaskState, string> = {
    idle: '尚未开始',
    queued: '等待生成',
    running: '生成中',
    paused: '已暂停',
    failed: '生成失败',
    completed: '已完成',
  }
  return t(`teacherProductionState.auxiliary.${state}`, fallback[state])
}

export function productionStageProgress(stage: StageProductionState): number {
  if (stage.counts.total <= 0) return stage.display_state === 'available' ? 100 : 0
  return Math.max(0, Math.min(100, Math.round((stage.counts.available / stage.counts.total) * 100)))
}

export function lessonProductionState(
  state: CourseProductionState | null,
  lessonUnitId: string,
  stage: Exclude<CourseProductionStageKey, 'outline'>,
): AssetProductionState | null {
  return state?.lessons.find(item => item.lesson_unit_id === lessonUnitId)?.stages[stage] || null
}

export function issueNavigationQuery(issue: CourseProductionIssue): Record<string, string> {
  return {
    stage: workbenchStageForProduction(issue.stage),
    issue: issue.issue_id,
    expandIssue: '1',
    ...(issue.lesson_unit_id ? { lesson: issue.lesson_unit_id } : {}),
    ...(issue.block_id ? { block: issue.block_id } : {}),
    ...(issue.task_id ? { task: issue.task_id } : {}),
  }
}
