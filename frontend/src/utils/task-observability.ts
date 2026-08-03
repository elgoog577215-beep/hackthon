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
  ['validate', /quality|validation|check|gate/],
  ['retrieve', /retriev|source_|question_bank|web_enrichment|knowledge_(mapping|index|graph)|course_(knowledge|relation|graph)/],
  ['parse', /material|pars|classif|pedagogy|ingest|extract|ocr/],
  ['receive', /queued|receiv|upload|requirement|intake/],
  ['generate', /outline|blueprint|teaching|content|learning_asset|generation|assembly|skeleton|ready|confirmed|resuming/],
]

export function observableStageIndex(phase?: string): number {
  const normalized = String(phase || '').toLowerCase()
  const match = STAGE_PATTERNS.find(([, pattern]) => pattern.test(normalized))
  return Math.max(0, OBSERVABLE_TASK_STAGE_KEYS.indexOf(match?.[0] || 'receive'))
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
  const activeIndex = observableStageIndex(task.currentPhase)
  const historyIndexes = new Set(
    (task.phaseHistory || [])
      .filter(entry => entry.status === 'completed')
      .map(entry => observableStageIndex(entry.phase)),
  )
  return OBSERVABLE_TASK_STAGE_KEYS.map((key, index) => {
    let status: ObservableTaskStageStatus = 'pending'
    if (task.status === 'completed') status = 'completed'
    else if (index < activeIndex || historyIndexes.has(index)) status = 'completed'
    else if (index === activeIndex) {
      status = task.status === 'error' ? 'error'
        : task.status === 'paused' ? 'paused'
          : task.status === 'conflict' ? 'blocked'
            : 'active'
    }
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

export function taskUserError(task: Pick<Task, 'error' | 'errorCode' | 'errorUserMessage'>): {
  message: string
  technicalDetail: string
} {
  const code = String(task.errorCode || '')
  const technicalDetail = String(task.error || code || '')
  if (task.errorUserMessage) return { message: task.errorUserMessage, technicalDetail }
  if (!technicalDetail) return { message: '', technicalDetail: '' }
  const known: Array<[RegExp, string]> = [
    [/slide_deck_variant_quality_gate_failed|quality_gate_failed/, t('taskObservability.errors.quality', '生成结果质量检查未通过，请查看问题后重试当前阶段。')],
    [/rate.?limit|too_many_requests|429/, t('taskObservability.errors.rateLimit', '服务请求过于频繁，系统已保留当前进度，请稍后重试。')],
    [/authentication|not_configured/, t('taskObservability.errors.providerAuth', 'AI 服务暂时无法完成身份校验，请检查服务配置后重试。')],
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
