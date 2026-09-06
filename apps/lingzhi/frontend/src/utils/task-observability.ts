import { t } from '@/shared/i18n'
import type { Task } from '@/stores/types'

export const OBSERVABLE_TASK_STAGE_KEYS = [
  'receive',
  'parse',
  'retrieve',
  'generate',
  'validate',
  'export',
] as const

export type ObservableTaskStageKey = typeof OBSERVABLE_TASK_STAGE_KEYS[number]
export type ObservableTaskStageStatus = 'completed' | 'active' | 'pending' | 'error' | 'paused' | 'blocked'

export interface ObservableTaskStage {
  key: ObservableTaskStageKey
  label: string
  status: ObservableTaskStageStatus
}

const STAGE_PATTERNS: Array<[ObservableTaskStageKey, RegExp]> = [
  ['export', /export|release|publish|finaliz|completed/],
  ['validate', /quality|content_validation|question_analysis|quality_gate/],
  ['retrieve', /retriev|source_|question_bank|web_enrichment/],
  ['parse', /material|pars|classif|pedagogy|ingest|extract|ocr/],
  ['receive', /queued|receiv|upload|requirement|intake/],
  ['generate', /outline|blueprint|teaching|content|learning_asset|knowledge|relation|graph|generation|assembly|skeleton|ready|confirmed|resuming|validation/],
]

// 用户看得懂的四个里程碑。底下那六个阶段是系统内部划分，
// 用户不需要知道「检索证据」和「解析与分类」的区别，只需要知道
// 「现在完成了什么、还要多久、是否需要我操作」。
// 六阶段的机制原样保留，这里只做一层呈现映射——诊断面板仍然展开看六阶段。
export const COURSE_MILESTONE_KEYS = [
  'understand',
  'plan',
  'author',
  'verify',
] as const

export type CourseMilestoneKey = typeof COURSE_MILESTONE_KEYS[number]

export interface CourseMilestone {
  key: CourseMilestoneKey
  label: string
  status: ObservableTaskStageStatus
  stages: ObservableTaskStage[]
}

// generate 这一个阶段在系统内部同时承担「规划」和「撰写」，
// 但对用户来说这是两件事：规划失败要重来的是结构，撰写失败重来的是内容。
// 所以里程碑层按原始 phase 串把它拆开，不动 STAGE_PATTERNS。
const PLANNING_PHASE_PATTERN = /outline|blueprint|skeleton|knowledge|relation|graph|pedagogy/
const MILESTONE_STAGES: Record<CourseMilestoneKey, ObservableTaskStageKey[]> = {
  understand: ['receive', 'parse'],
  plan: ['retrieve'],
  author: ['generate'],
  verify: ['validate', 'export'],
}

function milestoneLabel(key: CourseMilestoneKey): string {
  const labels: Record<CourseMilestoneKey, string> = {
    understand: t('courseGeneration.milestone.understand', '理解需求与资料'),
    plan: t('courseGeneration.milestone.plan', '规划课程与知识结构'),
    author: t('courseGeneration.milestone.author', '生成教案和正文'),
    verify: t('courseGeneration.milestone.verify', '检查并准备发布'),
  }
  return labels[key]
}

// 一个里程碑的状态由它盖住的阶段合成：
// 任一阶段出错/阻塞就是出错（坏消息不许被好消息盖掉），
// 全部完成才算完成，否则只要有在跑的就是进行中。
function mergeStageStatus(stages: ObservableTaskStage[]): ObservableTaskStageStatus {
  if (!stages.length) return 'pending'
  const has = (status: ObservableTaskStageStatus) => stages.some(stage => stage.status === status)
  if (has('error')) return 'error'
  if (has('blocked')) return 'blocked'
  if (has('paused')) return 'paused'
  if (stages.every(stage => stage.status === 'completed')) return 'completed'
  if (has('active')) return 'active'
  if (has('completed')) return 'active'
  return 'pending'
}

export function courseMilestones(task?: Task): CourseMilestone[] {
  const stages = task
    ? observableTaskStages(task)
    : OBSERVABLE_TASK_STAGE_KEYS.map(key => ({
      key,
      label: key,
      status: 'pending' as ObservableTaskStageStatus,
    }))
  const stageByKey = new Map(stages.map(stage => [stage.key, stage]))
  const phase = task ? String(observableTaskPhase(task) || '').toLowerCase() : ''
  const generateStage = stageByKey.get('generate')
  const planningNow = Boolean(generateStage) && PLANNING_PHASE_PATTERN.test(phase)

  return COURSE_MILESTONE_KEYS.map(key => {
    const owned = MILESTONE_STAGES[key]
      .map(stageKey => stageByKey.get(stageKey))
      .filter((stage): stage is ObservableTaskStage => Boolean(stage))

    // generate 正处在规划语义时，把它算进「规划」而不是「撰写」，
    // 否则用户会在还没开始写正文时就看到「生成教案和正文」在转。
    if (key === 'plan' && planningNow && generateStage) {
      return { key, label: milestoneLabel(key), status: mergeStageStatus([...owned, generateStage]), stages: [...owned, generateStage] }
    }
    if (key === 'author' && planningNow && generateStage) {
      const pending: ObservableTaskStage = { ...generateStage, status: 'pending' }
      return { key, label: milestoneLabel(key), status: 'pending', stages: [pending] }
    }
    return { key, label: milestoneLabel(key), status: mergeStageStatus(owned), stages: owned }
  })
}

export function observableStageIndex(phase?: string): number {
  const normalized = String(phase || '').toLowerCase()
  const match = STAGE_PATTERNS.find(([, pattern]) => pattern.test(normalized))
  return Math.max(0, OBSERVABLE_TASK_STAGE_KEYS.indexOf(match?.[0] || 'receive'))
}

function workflowStepStatus(task: Task, key: string): string {
  return String(task.guidedWorkflow?.steps.find(step => step.key === key)?.status || '')
}

function qualityIsBlocked(task: Task): boolean {
  return task.recovery?.state === 'quality_blocked'
    || (task.status === 'completed_with_warnings' && task.publicationAllowed === false)
}

export function observableTaskPhase(task: Task): string {
  if (qualityIsBlocked(task)) return 'quality_failed'
  if (task.status === 'completed') return 'completed'

  const phase = String(task.currentPhase || '').toLowerCase()
  const workflowStep = task.guidedWorkflow?.review_step || task.guidedWorkflow?.current_step
  if (workflowStep === 'release') {
    const releaseStatus = workflowStepStatus(task, 'release')
    if (releaseStatus === 'needs_regeneration' || releaseStatus === 'failed') return 'quality_failed'
    if (task.status === 'waiting_for_review') return 'release_ready'
    if (releaseStatus === 'confirmed' || /release_confirmed|publish|export|completed/.test(phase)) {
      return phase || 'release_confirmed'
    }
    return 'publication_quality_check'
  }

  if (phase && !/_confirmed$/.test(phase)) return phase
  const inferredPhase = {
    requirements: 'requirement_analysis',
    outline: 'outline_generation',
    teaching: 'course_teaching_plan',
    content: 'content_generation',
  }[String(workflowStep || '')]
  if (inferredPhase) return inferredPhase
  if (phase) return phase

  const latestHistory = [...(task.phaseHistory || [])]
    .reverse()
    .find(entry => Boolean(entry.phase))
  return String(latestHistory?.phase || '')
}

function stageLabel(key: ObservableTaskStageKey): string {
  return {
    receive: t('taskObservability.receive', '资料接收'),
    parse: t('taskObservability.parse', '解析与分类'),
    retrieve: t('taskObservability.retrieve', '检索证据'),
    generate: t('taskObservability.generate', '内容生成'),
    validate: t('taskObservability.validate', '质量检查'),
    export: t('taskObservability.export', '导出与发布'),
  }[key]
}

export function observableTaskStages(task: Task): ObservableTaskStage[] {
  const activeIndex = observableStageIndex(observableTaskPhase(task))
  if (qualityIsBlocked(task)) {
    const validateIndex = OBSERVABLE_TASK_STAGE_KEYS.indexOf('validate')
    return OBSERVABLE_TASK_STAGE_KEYS.map((key, index) => ({
      key,
      label: stageLabel(key),
      status: index < validateIndex ? 'completed' : index === validateIndex ? 'blocked' : 'pending',
    }))
  }
  return OBSERVABLE_TASK_STAGE_KEYS.map((key, index) => {
    let status: ObservableTaskStageStatus = 'pending'
    if (task.status === 'completed') status = 'completed'
    else if (index === activeIndex) {
      status = task.status === 'error' ? 'error'
        : task.status === 'paused' ? 'paused'
          : task.status === 'conflict' ? 'blocked'
            : 'active'
    }
    else if (index < activeIndex) status = 'completed'
    return { key, label: stageLabel(key), status }
  })
}

export function taskDisplayProgress(task: Pick<Task, 'status' | 'progress'>): number {
  const progress = Math.max(0, Math.min(100, Math.round(Number(task.progress || 0))))
  return task.status === 'error' && progress >= 100 ? 99 : progress
}

export function taskHeartbeatState(
  task: Pick<Task, 'status' | 'heartbeatAt' | 'updatedAt'>,
  now = Date.now(),
): { state: 'fresh' | 'stalled' | 'unknown' | 'terminal'; ageSeconds: number | null } {
  if (['completed', 'completed_with_warnings', 'error', 'conflict'].includes(task.status)) {
    return { state: 'terminal', ageSeconds: null }
  }
  const value = task.heartbeatAt || task.updatedAt
  if (!value) return { state: 'unknown', ageSeconds: null }
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return { state: 'unknown', ageSeconds: null }
  const ageSeconds = Math.max(0, Math.floor((now - timestamp) / 1000))
  return { state: ageSeconds > 120 ? 'stalled' : 'fresh', ageSeconds }
}

const GENERATION_ERROR_CODES = new Set([
  'provider_rate_limited',
  'provider_quota_exhausted',
  'provider_auth_failed',
  'provider_unavailable',
  'provider_timeout',
  'generation_budget_exceeded',
  'generation_deadline_exceeded',
  'response_truncated',
  'workspace_missing',
  'revision_conflict',
  'course_missing',
  'generation_failed',
])

export function taskUserError(task: Pick<Task, 'error' | 'errorCode' | 'errorUserMessage'>): {
  message: string
  technicalDetail: string
} {
  const code = String(task.errorCode || '')
  const technicalDetail = String(task.error || code || '')
  if (task.errorUserMessage) return { message: task.errorUserMessage, technicalDetail }
  // A classified backend failure resolves straight from its code: that mapping
  // is exact, so it must win over the string heuristics below. Fall back to the
  // generic sentence rather than an empty box if a key is ever missing.
  if (GENERATION_ERROR_CODES.has(code)) {
    const generic = t('taskObservability.errors.generic', '任务在当前阶段中断，已完成内容不会丢失。')
    return { message: t(`taskObservability.errors.${code}`, generic), technicalDetail }
  }
  if (!technicalDetail) return { message: '', technicalDetail: '' }
  const known: Array<[RegExp, string]> = [
    [/slide_deck_variant_quality_gate_failed|quality_gate_failed/, t('taskObservability.errors.quality', '生成结果质量检查未通过，请查看问题后重试当前阶段。')],
    [/rate.?limit|too_many_requests|429/, t('taskObservability.errors.rateLimit', '服务请求过于频繁，系统已保留当前进度，请稍后重试。')],
    [/authentication|credential|api[_ -]?key|not_configured/, t('taskObservability.errors.providerAuth', 'AI 服务暂时无法完成身份校验，请检查服务配置后重试。')],
    [/timeout|timed out/, t('taskObservability.errors.timeout', 'AI 服务响应超时，当前阶段尚未完成；已保存的内容不会重做。')],
    [/unavailable|connection|network/, t('taskObservability.errors.unavailable', 'AI 服务暂时不可用，当前阶段尚未完成；可在服务恢复后从保存点继续。')],
    [/markdown_heading_missing/, t('taskObservability.errors.heading', '没有识别到课程标题，请补充 Markdown 标题后重新导入。')],
    [/markdown_encoding_unsupported/, t('taskObservability.errors.encoding', '文件编码无法解析，请转为 UTF-8 后重新导入。')],
    [/markdown_teachable_body_missing/, t('taskObservability.errors.body', '文件只有标题或层级，请补充可讲授正文后重新导入。')],
    [/import_persistence_failed/, t('taskObservability.errors.persistence', '课程保存暂时失败，解析结果已保留，可以从保存点重试。')],
  ]
  const source = `${code} ${technicalDetail}`
  const matched = known.find(([pattern]) => pattern.test(source))
  return {
    message: matched?.[1] || t('taskObservability.errors.generic', '任务在当前阶段中断，已完成内容不会丢失。'),
    technicalDetail,
  }
}
