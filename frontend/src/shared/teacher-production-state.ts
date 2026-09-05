import { t } from './i18n'

export const COURSE_PRODUCTION_STAGE_KEYS = ['outline', 'lesson_plan', 'script', 'ppt'] as const

export type CourseProductionStageKey = typeof COURSE_PRODUCTION_STAGE_KEYS[number]
export type CourseProductionDisplayState = 'not_generated' | 'generating' | 'available' | 'failed'
export type CourseProductionTaskState =
  | 'idle'
  | 'queued'
  | 'running'
  | 'paused'
  | 'waiting_for_input'
  | 'waiting_for_review'
  | 'cancelled'
  | 'failed'
  | 'completed'
  | 'unknown'
export type CourseProductionAvailability = 'missing' | 'usable' | 'stale'
export type CourseProductionSourceState = 'missing' | 'current' | 'stale' | 'mixed'
export type CourseProductionAllowedAction =
  | 'generate'
  | 'pause_generation'
  | 'cancel_generation'
  | 'resume_generation'
  | 'provide_input'
  | 'review_generation'
  | 'retry_generation'
  | 'inspect_failure'
  | 'regenerate_from_latest_source'

export type CourseProductionActionTargets = Partial<
  Record<CourseProductionAllowedAction, string[]>
>

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
  task_ids: string[]
  action_targets: CourseProductionActionTargets
  issues: CourseProductionIssue[]
  allowed_actions: CourseProductionAllowedAction[]
}

export interface StageProductionState extends AssetProductionState {
  counts: CourseProductionCounts
  latest_attempt?: CourseProductionLatestAttempt
  has_unconfirmed_draft?: boolean
  blocking_issues?: CourseProductionIssue[]
  review_issues?: CourseProductionIssue[]
}

export type CourseProductionPrimaryAction =
  | 'none'
  | Exclude<CourseProductionAllowedAction, 'pause_generation' | 'cancel_generation'>

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
  recovery?: {
    state?: string
    can_resume?: boolean
    reason_code?: string
    reason?: string
    checkpoint?: Record<string, unknown>
  }
  publicationAllowed?: boolean
  qualityStatus?: string
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
const AVAILABILITY_STATES = new Set<CourseProductionAvailability>(['missing', 'usable', 'stale'])
const SOURCE_STATES = new Set<CourseProductionSourceState>(['missing', 'current', 'stale', 'mixed'])
const TASK_STATES = new Set<CourseProductionTaskState>([
  'idle',
  'queued',
  'running',
  'paused',
  'waiting_for_input',
  'waiting_for_review',
  'cancelled',
  'failed',
  'completed',
  'unknown',
])
const ALLOWED_ACTIONS = new Set<CourseProductionAllowedAction>([
  'generate',
  'pause_generation',
  'cancel_generation',
  'resume_generation',
  'provide_input',
  'review_generation',
  'retry_generation',
  'inspect_failure',
  'regenerate_from_latest_source',
])

export const TASK_BOUND_PRODUCTION_ACTIONS = new Set<CourseProductionAllowedAction>([
  'pause_generation',
  'cancel_generation',
  'resume_generation',
  'provide_input',
  'review_generation',
  'retry_generation',
])

function isActionTargets(value: unknown): value is CourseProductionActionTargets {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  return Object.entries(value).every(([action, taskIds]) => (
    ALLOWED_ACTIONS.has(action as CourseProductionAllowedAction)
    && Array.isArray(taskIds)
    && taskIds.every(taskId => typeof taskId === 'string')
  ))
}

function isAsset(value: unknown): value is AssetProductionState {
  if (!value || typeof value !== 'object') return false
  const asset = value as AssetProductionState
  const actionTargets = asset.action_targets ?? {}
  if (!(DISPLAY_STATES.has(asset.display_state)
    && TASK_STATES.has(asset.task_state)
    && AVAILABILITY_STATES.has(asset.availability)
    && SOURCE_STATES.has(asset.source_state)
    && typeof asset.latest_attempt_failed === 'boolean'
    && typeof asset.update_required === 'boolean'
    && Array.isArray(asset.task_ids)
    && asset.task_ids.every(taskId => typeof taskId === 'string' && Boolean(taskId))
    && isActionTargets(actionTargets)
    && Array.isArray(asset.issues)
    && Array.isArray(asset.allowed_actions)
    && asset.allowed_actions.every(action => ALLOWED_ACTIONS.has(action)))) return false
  const allowed = new Set(asset.allowed_actions)
  const taskIds = new Set(asset.task_ids)
  if (asset.task_state === 'waiting_for_input'
    && (allowed.size !== 1 || !allowed.has('provide_input'))) return false
  if (asset.task_state === 'waiting_for_review'
    && (allowed.size !== 1 || !allowed.has('review_generation'))) return false
  if (asset.task_state === 'unknown'
    && (allowed.size !== 1 || !allowed.has('inspect_failure'))) return false
  if (Object.keys(actionTargets).some(action => !allowed.has(action as CourseProductionAllowedAction))) return false
  if (Object.values(actionTargets).some(targets => targets?.some(taskId => !taskIds.has(taskId)))) return false
  return asset.allowed_actions.every(action => (
    !TASK_BOUND_PRODUCTION_ACTIONS.has(action)
    || (actionTargets[action] || []).some(Boolean)
  ))
}

function isStage(value: unknown): value is StageProductionState {
  if (!isAsset(value)) return false
  const stage = value as StageProductionState
  return Boolean((stage.has_unconfirmed_draft === undefined || typeof stage.has_unconfirmed_draft === 'boolean')
    && !(stage.has_unconfirmed_draft === true
      && stage.allowed_actions.includes('regenerate_from_latest_source')
      && !(stage.action_targets.regenerate_from_latest_source || []).some(Boolean))
    && stage.counts && [
    stage.counts.total,
    stage.counts.available,
    stage.counts.generating,
    stage.counts.failed,
    stage.counts.stale,
  ].every(Number.isFinite))
}

// The v1 projection originally exposed an explicit recovery action on each
// issue before action_targets became a required top-level authorization map.
// During a rolling/local frontend update the old backend can therefore return
// enough authority to retry, but not the newer transport fields. Promote only
// that explicit issue-level authority; never infer a write action from a task
// state, display state, checkpoint, or local job.
function upgradeLegacyV1AssetActions(
  value: unknown,
  stage: CourseProductionStageKey,
  lessonUnitId?: string,
): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value
  const asset = value as Record<string, unknown>
  if (
    Object.prototype.hasOwnProperty.call(asset, 'task_ids')
    || Object.prototype.hasOwnProperty.call(asset, 'action_targets')
    || Object.prototype.hasOwnProperty.call(asset, 'allowed_actions')
  ) return value

  const issues = Array.isArray(asset.issues) ? asset.issues : []
  const actionTargets: CourseProductionActionTargets = {}
  const allowedActions: CourseProductionAllowedAction[] = []
  const taskIds = new Set<string>()
  const latestAttempt = asset.latest_attempt
  if (latestAttempt && typeof latestAttempt === 'object' && !Array.isArray(latestAttempt)) {
    const attemptTaskIds = (latestAttempt as Record<string, unknown>).task_ids
    if (Array.isArray(attemptTaskIds)) {
      attemptTaskIds.forEach(taskId => {
        if (typeof taskId === 'string' && taskId) taskIds.add(taskId)
      })
    }
  }

  for (const rawIssue of issues) {
    if (!rawIssue || typeof rawIssue !== 'object' || Array.isArray(rawIssue)) continue
    const issue = rawIssue as Record<string, unknown>
    if (issue.stage !== stage) continue
    if (lessonUnitId !== undefined && issue.lesson_unit_id !== lessonUnitId) continue
    const recovery = issue.recovery
    if (!recovery || typeof recovery !== 'object' || Array.isArray(recovery)) continue
    const recoveryRecord = recovery as Record<string, unknown>
    if (recoveryRecord.automatic !== false || recoveryRecord.requires_confirmation !== true) continue
    const action = recoveryRecord.action
    if (action === 'inspect_failure') {
      if (!allowedActions.includes(action)) allowedActions.push(action)
      continue
    }
    if (action !== 'retry_generation') continue
    const taskId = typeof issue.task_id === 'string' ? issue.task_id : ''
    if (!taskId) continue
    taskIds.add(taskId)
    if (!allowedActions.includes(action)) allowedActions.push(action)
    actionTargets[action] = [...new Set([...(actionTargets[action] || []), taskId])]
  }

  if (!allowedActions.length && ['failed', 'unknown'].includes(String(asset.task_state || ''))) {
    allowedActions.push('inspect_failure')
  }
  return {
    ...asset,
    task_ids: [...taskIds],
    action_targets: actionTargets,
    allowed_actions: allowedActions,
  }
}

function upgradeLegacyV1Projection(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value
  const state = value as Record<string, unknown>
  if (state.schema_version !== 'course_production_state_v1') return value
  const rawStages = state.stages
  if (!rawStages || typeof rawStages !== 'object' || Array.isArray(rawStages)) return value
  const stages = rawStages as Record<string, unknown>
  const lessons = Array.isArray(state.lessons) ? state.lessons.map(rawLesson => {
    if (!rawLesson || typeof rawLesson !== 'object' || Array.isArray(rawLesson)) return rawLesson
    const lesson = rawLesson as Record<string, unknown>
    const lessonStages = lesson.stages
    if (!lessonStages || typeof lessonStages !== 'object' || Array.isArray(lessonStages)) return rawLesson
    const lessonUnitId = typeof lesson.lesson_unit_id === 'string' ? lesson.lesson_unit_id : ''
    return {
      ...lesson,
      stages: Object.fromEntries(Object.entries(lessonStages).map(([key, asset]) => [
        key,
        COURSE_PRODUCTION_STAGE_KEYS.includes(key as CourseProductionStageKey)
          ? upgradeLegacyV1AssetActions(asset, key as CourseProductionStageKey, lessonUnitId)
          : asset,
      ])),
    }
  }) : state.lessons
  return {
    ...state,
    stages: Object.fromEntries(Object.entries(stages).map(([key, asset]) => [
      key,
      COURSE_PRODUCTION_STAGE_KEYS.includes(key as CourseProductionStageKey)
        ? upgradeLegacyV1AssetActions(asset, key as CourseProductionStageKey)
        : asset,
    ])),
    lessons,
  }
}

export function readCourseProductionState(source?: unknown): CourseProductionState | null {
  if (!source || typeof source !== 'object') return null
  const rawValue = 'schema_version' in source
    ? source
    : (source as ProductionEnvelope).course_production_state
  const value = upgradeLegacyV1Projection(rawValue)
  if (!value || typeof value !== 'object') return null
  const state = value as CourseProductionState
  if (state.schema_version !== 'course_production_state_v1' || !state.course_id) return null
  if (!COURSE_PRODUCTION_STAGE_KEYS.every(key => isStage(state.stages?.[key]))) return null
  if (!Array.isArray(state.lessons) || state.lessons.some(lesson => (
    !lesson || typeof lesson !== 'object'
    || Object.values(lesson.stages || {}).some(asset => !isAsset(asset))
  ))) return null
  return state
}

export function productionStagePrimaryAction(
  stage?: StageProductionState | null,
): CourseProductionPrimaryAction {
  return primaryAction(stage?.allowed_actions)
}

export function productionAssetPrimaryAction(
  asset?: AssetProductionState | null,
): CourseProductionPrimaryAction {
  return primaryAction(asset?.allowed_actions)
}

export function productionActionTaskIds(
  asset: AssetProductionState | StageProductionState | null | undefined,
  action: CourseProductionAllowedAction,
): string[] {
  if (!asset?.allowed_actions.includes(action)) return []
  return [...new Set((asset.action_targets?.[action] || []).filter(Boolean))]
}

export function productionAllowsTaskAction(
  asset: AssetProductionState | StageProductionState | null | undefined,
  action: CourseProductionAllowedAction,
): boolean {
  return TASK_BOUND_PRODUCTION_ACTIONS.has(action)
    && productionActionTaskIds(asset, action).length > 0
}

const PRIMARY_ACTION_PRIORITY: Exclude<
  CourseProductionAllowedAction,
  'pause_generation' | 'cancel_generation'
>[] = [
  'provide_input',
  'review_generation',
  'resume_generation',
  'retry_generation',
  'regenerate_from_latest_source',
  'inspect_failure',
  'generate',
]

function primaryAction(
  actions?: CourseProductionAllowedAction[],
): CourseProductionPrimaryAction {
  if (!actions?.length) return 'none'
  const allowed = new Set(actions)
  return PRIMARY_ACTION_PRIORITY.find(action => allowed.has(action)) || 'none'
}

const PRODUCTION_ISSUE_ACTION_PRIORITY = new Map([
  ['resume_generation', 0],
  ['retry_generation', 1],
  ['regenerate_from_latest_source', 2],
  ['inspect_failure', 3],
])

export function productionPrimaryIssue(
  issues: CourseProductionIssue[],
): CourseProductionIssue | undefined {
  return [...issues].sort((left, right) => {
    const leftPriority = PRODUCTION_ISSUE_ACTION_PRIORITY.get(left.recovery.action)
      ?? (left.blocking ? 4 : 5)
    const rightPriority = PRODUCTION_ISSUE_ACTION_PRIORITY.get(right.recovery.action)
      ?? (right.blocking ? 4 : 5)
    return leftPriority - rightPriority
      || left.stage.localeCompare(right.stage)
      || left.lesson_unit_id.localeCompare(right.lesson_unit_id)
      || left.issue_id.localeCompare(right.issue_id)
  })[0]
}

export function productionStagePrimaryIssue(
  stage?: AssetProductionState | StageProductionState | null,
): CourseProductionIssue | undefined {
  if (!stage || ['queued', 'running'].includes(stage.task_state)) return undefined
  return productionPrimaryIssue(stage.issues)
}

export function courseProductionPrimaryIssue(
  state: CourseProductionState,
): CourseProductionIssue | undefined {
  if (COURSE_PRODUCTION_STAGE_KEYS.some(key => (
    ['queued', 'running'].includes(state.stages[key].task_state)
  ))) return undefined
  return productionPrimaryIssue(state.issues)
}

function taskStage(task?: LegacyTask): CourseProductionStageKey {
  const taskTypeStages: Record<string, CourseProductionStageKey> = {
    teacher_outline_generation: 'outline',
    teacher_lesson_plan_generation: 'lesson_plan',
    teacher_lesson_script_generation: 'script',
    teacher_lesson_ppt_manuscript_generation: 'ppt',
    teacher_lesson_ppt_generation: 'ppt',
    teaching_representation_build: 'ppt',
    slide_deck_variant_build: 'ppt',
  }
  const taskTypeStage = taskTypeStages[String(task?.taskType || '')]
  if (taskTypeStage) return taskTypeStage
  const phase = String(task?.currentPhase || '').toLowerCase()
  if (/script|handout|content/.test(phase)) return 'script'
  if (/ppt|slide/.test(phase)) return 'ppt'
  if (/lesson|teaching/.test(phase)) return 'lesson_plan'
  return 'outline'
}

function legacyTaskState(status = ''): CourseProductionTaskState {
  if (['running', 'active'].includes(status)) return 'running'
  if (['pending', 'queued'].includes(status)) return 'queued'
  if (status === 'paused') return 'paused'
  if (status === 'waiting_for_input') return 'waiting_for_input'
  if (status === 'waiting_for_review') return 'waiting_for_review'
  if (['cancelled', 'canceled'].includes(status)) return 'cancelled'
  if (['failed', 'error', 'conflict'].includes(status)) return 'failed'
  if (status === 'completed') return 'completed'
  if (status === 'idle' || !status) return 'idle'
  return 'unknown'
}

function legacyWarningIsPublished(status: string, task?: LegacyTask): boolean {
  return status === 'completed_with_warnings'
    && (task?.publicationAllowed === true || task?.recovery?.state === 'completed')
}

function legacyWarningIsQualityBlocked(status: string, task?: LegacyTask): boolean {
  return status === 'completed_with_warnings'
    && (
      task?.publicationAllowed === false
      || task?.recovery?.state === 'quality_blocked'
      || task?.qualityStatus === 'quality_failed'
      || task?.currentPhase === 'quality_failed'
    )
}

function legacyAllowedActions(
  taskState: CourseProductionTaskState,
  task?: LegacyTask,
): CourseProductionAllowedAction[] {
  if (taskState === 'idle' || taskState === 'cancelled') return ['generate']
  if (!task?.id) return ['inspect_failure']
  if (taskState === 'queued' || taskState === 'running') {
    return ['pause_generation', 'cancel_generation']
  }
  if (taskState === 'waiting_for_input') return ['provide_input']
  if (taskState === 'waiting_for_review') return ['review_generation']
  if (taskState === 'paused') {
    const isTeacherAssetJob = [
      'teacher_lesson_plan_generation',
      'teacher_lesson_script_generation',
      'teacher_lesson_ppt_manuscript_generation',
      'teacher_lesson_ppt_generation',
    ].includes(String(task.taskType || ''))
    return task.recovery?.can_resume === true || (!task.recovery && isTeacherAssetJob)
      ? ['resume_generation', 'cancel_generation']
      : ['inspect_failure']
  }
  if (taskState === 'failed') {
    return task.recovery?.can_resume === true
      && ['manual_resume', 'quality_blocked'].includes(String(task.recovery.state || ''))
      ? ['retry_generation']
      : ['inspect_failure']
  }
  if (taskState === 'unknown') return ['inspect_failure']
  return []
}

function legacyActionTargets(
  allowedActions: CourseProductionAllowedAction[],
  task?: LegacyTask,
): CourseProductionActionTargets {
  const taskId = String(task?.id || '')
  return Object.fromEntries(allowedActions.map(action => [
    action,
    TASK_BOUND_PRODUCTION_ACTIONS.has(action) && taskId ? [taskId] : [],
  ]))
}

function emptyStage(total: number, available: number): StageProductionState {
  const allowedActions: CourseProductionAllowedAction[] = total > available ? ['generate'] : []
  return {
    display_state: total > 0 && available > 0 ? 'available' : 'not_generated',
    task_state: 'idle',
    availability: total > 0 && available >= total ? 'usable' : available > 0 ? 'stale' : 'missing',
    source_state: available > 0 ? 'current' : 'missing',
    latest_attempt_failed: false,
    update_required: false,
    task_ids: [],
    action_targets: legacyActionTargets(allowedActions),
    counts: { total, available, generating: 0, failed: 0, stale: 0 },
    has_unconfirmed_draft: false,
    issues: [],
    allowed_actions: allowedActions,
  }
}

function failClosedExistingProjection(
  course: LegacyCourse,
): CourseProductionState {
  const raw = course.course_production_state
  const value = raw && typeof raw === 'object'
    ? raw as Partial<CourseProductionState>
    : {}
  const projectedStages: Partial<Record<CourseProductionStageKey, StageProductionState>> = (
    value.stages && typeof value.stages === 'object'
      ? value.stages
      : {}
  )
  const stages = Object.fromEntries(COURSE_PRODUCTION_STAGE_KEYS.map(key => {
    const projected = projectedStages[key]
    if (projected && typeof projected === 'object') {
      const fallback = emptyStage(0, 0)
      return [key, {
        ...fallback,
        display_state: DISPLAY_STATES.has(projected.display_state) ? projected.display_state : 'failed',
        task_state: 'unknown',
        availability: AVAILABILITY_STATES.has(projected.availability) ? projected.availability : 'missing',
        source_state: SOURCE_STATES.has(projected.source_state) ? projected.source_state : 'missing',
        latest_attempt_failed: projected.latest_attempt_failed === true,
        update_required: projected.update_required === true,
        task_ids: Array.isArray(projected.task_ids)
          ? projected.task_ids.filter(taskId => typeof taskId === 'string' && Boolean(taskId))
          : [],
        counts: projected.counts && [
          projected.counts.total,
          projected.counts.available,
          projected.counts.generating,
          projected.counts.failed,
          projected.counts.stale,
        ].every(Number.isFinite) ? projected.counts : fallback.counts,
        has_unconfirmed_draft: projected.has_unconfirmed_draft === true,
        issues: Array.isArray(projected.issues) ? projected.issues : [],
        action_targets: {},
        allowed_actions: ['inspect_failure'],
      }]
    }
    return [key, {
      ...emptyStage(0, 0),
      display_state: 'failed',
      task_state: 'unknown',
      action_targets: {},
      allowed_actions: ['inspect_failure'],
    }]
  })) as unknown as CourseProductionState['stages']

  return {
    schema_version: 'course_production_state_v1',
    course_id: String(value.course_id || course.course_id || ''),
    preparation_state: value.preparation_state === 'prepared' ? 'prepared' : 'preparing',
    stages,
    lessons: [],
    issues: Array.isArray(value.issues) ? value.issues : [],
    ...(value.source_summary ? { source_summary: value.source_summary } : {}),
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
  // A present-but-invalid v1 projection is a contract failure, not permission
  // to revive page-owned action inference from legacy task fields.
  if (course.course_production_state != null) {
    return failClosedExistingProjection(course)
  }
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
  const warningPublished = legacyWarningIsPublished(status, task)
  const warningQualityBlocked = legacyWarningIsQualityBlocked(status, task)
  const taskState = status === 'completed_with_warnings'
    ? warningPublished ? 'completed' : 'failed'
    : legacyTaskState(status)
  if (status) {
    const stage = stages[stageKey]
    const completed = Math.max(0, Number(legacyCurrent?.completed ?? stage.counts.available))
    const targetTotal = Math.max(0, Number(legacyCurrent?.total || stage.counts.total))
    const failed = Math.max(0, Number(legacyCurrent?.failed || (taskState === 'failed' ? 1 : 0)))
    stage.task_state = taskState
    stage.counts = {
      ...stage.counts,
      generating: ['queued', 'running', 'paused', 'waiting_for_input', 'waiting_for_review'].includes(taskState)
        ? Math.max(1, targetTotal - completed)
        : 0,
      failed,
    }
    stage.allowed_actions = legacyAllowedActions(taskState, task)
    stage.task_ids = task?.id ? [task.id] : []
    stage.action_targets = legacyActionTargets(stage.allowed_actions, task)
    stage.display_state = stage.counts.available > 0
      ? 'available'
      : ['queued', 'running', 'paused', 'waiting_for_input', 'waiting_for_review'].includes(taskState)
        ? 'generating'
        : ['failed', 'unknown'].includes(taskState) || failed > 0 ? 'failed' : stage.display_state
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
    if (stage.latest_attempt_failed || taskState === 'unknown') {
      const recoveryAction = productionStagePrimaryAction(stage) === 'none'
        ? 'inspect_failure'
        : productionStagePrimaryAction(stage)
      stage.issues = [{
        issue_id: `legacy-${stageKey}-${task?.id || 'current'}`,
        stage: stageKey,
        lesson_unit_id: '',
        task_id: task?.id,
        code: taskState === 'unknown'
          ? 'legacy_unknown_task_state'
          : warningQualityBlocked
            ? 'legacy_quality_blocked'
            : 'legacy_generation_failed',
        summary: stage.latest_attempt.message || t('teacherProductionState.auxiliary.recentFailure'),
        blocking: taskState === 'unknown' || warningQualityBlocked,
        recovery: { action: recoveryAction, automatic: false, requires_confirmation: true },
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
    waiting_for_input: '等待补充信息',
    waiting_for_review: '等待审阅',
    cancelled: '已取消',
    failed: '生成失败',
    completed: '已完成',
    unknown: '状态异常',
  }
  const keys: Record<CourseProductionTaskState, string> = {
    idle: 'idle',
    queued: 'queued',
    running: 'running',
    paused: 'paused',
    waiting_for_input: 'waitingForInput',
    waiting_for_review: 'waitingForReview',
    cancelled: 'cancelled',
    failed: 'failed',
    completed: 'completed',
    unknown: 'unknown',
  }
  return t(`teacherProductionState.auxiliary.${keys[state]}`, fallback[state])
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
