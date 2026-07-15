import type { NextLearningAction } from '../stores/learningProgress'
import { t } from '../shared/i18n'

type Translate = (key: string, fallback?: string) => string

const ACTION_FALLBACKS: Record<string, string> = {
  confirm_version_change: '处理版本变化',
  resume_diagnostic: '继续辨别卡点',
  resume_remediation: '继续局部补救',
  resume_validation: '完成独立复验',
  resolve_diagnostic_support: '请老师进一步判断',
  resume_practice_attempt: '继续未完成练习',
  resolve_blocking_issue: '处理未解决问题',
  resolve_open_issue: '处理章节遗留问题',
  resolve_prerequisite_gap: '先处理前置目标',
  resume_reading: '继续阅读',
  start_objective: '开始当前目标',
  continue_objective: '继续当前目标',
  complete_reading: '标记本节已学完',
  start_mastery_check: '完成掌握检查',
  start_due_review: '开始到期复习',
  start_next_chapter: '进入下一章',
  view_chapter_result: '查看章节结果',
  repair_course_assets: '等待课程资产修复',
}

const TASK_KINDS = new Set(['practice', 'diagnostic', 'remediation', 'validation'])

export function learningActionLabel(actionType: string, translate: Translate = t): string {
  if (actionType === 'repair_course_assets') {
    return translate('courseAvailability.continuity.repairAssets', ACTION_FALLBACKS[actionType])
  }
  return translate(
    `courseWorkspace.continuity.actions.${actionType}`,
    ACTION_FALLBACKS[actionType] || '继续学习',
  )
}

export function learningActionReason(reasonCode: string, translate: Translate = t): string {
  if (reasonCode === 'required_practice_missing') {
    return translate('courseAvailability.continuity.requiredPracticeMissing', '标准课程缺少必需正式练习，已停止进入空的掌握检查。')
  }
  return translate(
    `courseWorkspace.continuity.reasons.${reasonCode}`,
    '根据当前学习状态继续',
  )
}

export function learningActionPresentation(action: NextLearningAction, translate: Translate = t) {
  return {
    label: learningActionLabel(action.action_type, translate),
    reason: learningActionReason(action.reason_code, translate),
  }
}

export function isWorkspaceTaskAction(action: NextLearningAction): boolean {
  return TASK_KINDS.has(action.task_ref?.kind || '')
}
