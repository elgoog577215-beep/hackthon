import type { Task } from '@/stores/types'
import { t } from '@/shared/i18n'

export const COURSE_PRODUCTION_STAGE_KEYS = [
  'requirements',
  'outline',
  'teaching',
  'content',
  'release',
] as const

export type CourseProductionStageKey = typeof COURSE_PRODUCTION_STAGE_KEYS[number]
export type CourseProductionStageStatus = 'completed' | 'active' | 'pending' | 'review' | 'error' | 'paused' | 'blocked'

function phaseStageIndex(phase: string): number | null {
  if (/release|finaliz|publish|completed/.test(phase)) return 4
  if (/content|learning_assets|question_bank/.test(phase)) return 3
  if (/teaching|knowledge|graph/.test(phase)) return 2
  if (/requirement|material|pedagogy|outline|blueprint|queued/.test(phase)) return 1
  return null
}

export function courseProductionStageIndex(task?: Task): number {
  if (!task) return 1

  const reviewStep = task.guidedWorkflow?.review_step
  if (reviewStep === 'outline') return 1
  if (reviewStep === 'content') return 3
  if (reviewStep === 'release') return 4

  const phaseIndex = phaseStageIndex(String(task.currentPhase || '').toLowerCase())
  if (phaseIndex !== null) return phaseIndex

  const currentStep = task.guidedWorkflow?.current_step
  if (currentStep === 'requirements') return 0
  if (currentStep === 'outline') return 1
  if (currentStep === 'content') return 3
  if (currentStep === 'release') return 4
  return 1
}

export function courseProductionStageKey(task?: Task): CourseProductionStageKey {
  return COURSE_PRODUCTION_STAGE_KEYS[courseProductionStageIndex(task)] || 'outline'
}

export function courseProductionStageStatus(task: Task | undefined, index: number): CourseProductionStageStatus {
  const activeIndex = courseProductionStageIndex(task)
  if (task?.status === 'completed') return 'completed'
  if (task?.status === 'completed_with_warnings' && task.publicationAllowed === false) {
    if (index < 4) return 'completed'
    return index === 4 ? 'blocked' : 'pending'
  }
  if (task?.status === 'completed_with_warnings') return 'completed'
  if (index < activeIndex) return 'completed'
  if (index > activeIndex) return 'pending'
  if (task?.status === 'error') return 'error'
  if (task?.status === 'paused') return 'paused'
  if (task?.status === 'conflict') return 'blocked'
  if (task?.status === 'waiting_for_review') return 'review'
  return 'active'
}

export function canResumeCourseProduction(task?: Task): boolean {
  if (!task) return false
  if (task.recovery) return Boolean(task.recovery.can_resume)
  return task.status === 'paused' || task.status === 'error'
}

export function courseProductionTaskDetail(task?: Task): string {
  if (!task) return ''
  if (task.currentPhase === 'content_partial') {
    return t(
      'courseGeneration.production.contentPartial',
      '正文生成达到本轮总时限；已完成内容和草稿均已保存，可以从未完成小节继续。',
    )
  }
  return task.currentStep || ''
}

export function courseProductionRecoveryDetail(task?: Task): string {
  const checkpoint = task?.recovery?.checkpoint
  const stage = courseProductionStageKey(task)
  const completedNodes = Number(checkpoint?.completed_nodes || 0)
  const reasonCode = String(task?.recovery?.reason_code || '')

  if (reasonCode === 'quality_gate_failed') {
    return t('courseGeneration.production.recoveryQuality', '发布检查发现阻断项；修复后可从当前现场继续。')
  }
  if (reasonCode === 'version_conflict' || task?.status === 'conflict') {
    return t('courseGeneration.production.recoveryConflict', '当前产物需要与课程最新修订对账，完整检查点仍然保留。')
  }
  if (stage === 'outline') {
    return t('courseGeneration.production.recoveryOutline', '课程需求与资料处理结果已保留；继续后会重新生成课程目录。')
  }
  if (stage === 'teaching') {
    return t('courseGeneration.production.recoveryTeaching', '已完成的全局骨架与详细教案批次会被复用，只重做当前未完成批次。')
  }
  if (stage === 'content' && completedNodes > 0) {
    return t('courseGeneration.production.recoveryContent', '已保存 {count} 节正文；继续后从未完成小节恢复。')
      .replace('{count}', String(completedNodes))
  }
  if (stage === 'release') {
    return t('courseGeneration.production.recoveryRelease', '课程正文与正式引用已经保存；继续后只重新执行发布前检查。')
  }
  if (task?.status === 'paused') {
    return t('courseGeneration.production.recoveryPaused', '课程生产已停在完整检查点，继续时不会新建重复课程。')
  }
  return t('courseGeneration.production.recoveryDefault', '继续时复用已保存的检查点，不会新建重复课程。')
}

export function hasVisibleCourseDraft(task: Task | undefined, nodeContents: Array<string | undefined>): boolean {
  if (nodeContents.some(content => Boolean(content?.trim()))) return true
  return Boolean(task?.currentNodes?.length && /content/.test(String(task.currentPhase || '')))
}
