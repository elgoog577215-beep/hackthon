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
