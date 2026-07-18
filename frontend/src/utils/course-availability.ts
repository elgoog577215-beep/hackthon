type Translate = (key: string, fallback?: string) => string

const PRACTICE_COPY: Record<string, { title: string; body: string }> = {
  declared_reading_only: {
    title: '这门课程按设计只提供阅读学习',
    body: '当前课程没有生成正式题目。阅读进度可以继续，但不会据此确认掌握。',
  },
  legacy_reading_compatible: {
    title: '这是一门旧版兼容课程',
    body: '正文仍可继续学习，但旧课程没有可追踪的正式练习与掌握证据。',
  },
  required_practice_missing: {
    title: '课程练习资产需要修复',
    body: '这门标准课程应当提供正式题目，系统不会把资产缺失当成纯阅读模式。',
  },
  question_generation_in_progress: {
    title: '正在生成正式练习',
    body: '系统正在整理来源、生成题目并独立验证，完成后会自动刷新当前范围。',
  },
  question_review_pending: {
    title: '题目正在等待教师审核',
    body: '候选题已经生成，但风险项尚未确认，因此不会提前展示给学生。',
  },
  question_validation_failed: {
    title: '题目没有通过质量验证',
    body: '生成结果与独立求解或验证器不一致，当前节点不会用宽泛题目凑数。',
  },
  question_source_insufficient: {
    title: '课程资料不足以生成可靠题目',
    body: '当前来源无法支撑可解、可评分的题目，请补充资料或由教师确认候选题。',
  },
  node_assessment_not_enabled: {
    title: '当前节点未启用测评',
    body: '该节点尚未编译测评目标，可以继续阅读或由教师为该节点重建题库。',
  },
  question_generation_failed: {
    title: '题目生成失败',
    body: '当前正式版本没有被覆盖，可以稍后重试或查看失败原因。',
  },
  no_questions_in_scope: {
    title: '当前范围没有正式练习',
    body: '课程其他范围可能仍有题目，可以切换章节或返回课程继续学习。',
  },
}

const DEFAULT_PRACTICE_COPY = {
  title: '当前范围没有正式练习',
  body: '课程其他范围可能仍有题目，可以切换章节或返回课程继续学习。',
}

const QUESTION_BANK_REPAIR_REASONS = new Set([
  'legacy_reading_compatible',
  'required_practice_missing',
  'question_validation_failed',
  'question_source_insufficient',
  'node_assessment_not_enabled',
  'question_generation_failed',
])

export function isQuestionBankRepairReason(reasonCode: string | null | undefined): boolean {
  return QUESTION_BANK_REPAIR_REASONS.has(String(reasonCode || ''))
}

export function practiceAvailabilityCopy(reasonCode: string, translate: Translate) {
  const fallback = PRACTICE_COPY[reasonCode] || DEFAULT_PRACTICE_COPY
  return {
    title: translate(`courseAvailability.practice.${reasonCode}.title`, fallback.title),
    body: translate(`courseAvailability.practice.${reasonCode}.body`, fallback.body),
  }
}

export function masteryAvailabilityCopy(
  availability: Record<string, any> | null | undefined,
  translate: Translate,
) {
  const mode = availability?.mode || 'standard'
  const masteryStatus = availability?.capabilities?.mastery_evidence?.status || 'available'
  if (mode === 'reading_only') {
    return {
      tone: 'notice',
      title: translate('courseAvailability.mastery.readingOnlyTitle', '当前课程只提供阅读与自检'),
      body: translate('courseAvailability.mastery.readingOnlyBody', '自我确认可以帮助回顾，但不等于系统已经验证掌握。'),
    }
  }
  if (mode === 'compatibility') {
    return {
      tone: 'notice',
      title: translate('courseAvailability.mastery.compatibilityTitle', '旧课程没有正式掌握验证'),
      body: translate('courseAvailability.mastery.compatibilityBody', '系统保留阅读能力，但不会根据旧数据推断你已经掌握。'),
    }
  }
  if (masteryStatus === 'blocked') {
    return {
      tone: 'warning',
      title: translate('courseAvailability.mastery.blockedTitle', '课程掌握资产需要修复'),
      body: translate('courseAvailability.mastery.blockedBody', '正式掌握检查不完整，系统不会用自检结果替代正式证据。'),
    }
  }
  return null
}
