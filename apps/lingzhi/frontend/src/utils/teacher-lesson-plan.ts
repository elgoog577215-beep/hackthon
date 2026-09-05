export interface TeacherLessonSectionView {
  learningObjective: string
  keyDifficulties: string[]
  teacherActivities: string[]
  studentActivities: string[]
  homework: string[]
}

export interface TeacherLessonSectionDiff {
  key: keyof TeacherLessonSectionView
  label: string
  before: string
  after: string
  changed: boolean
}

const MODULE_LABELS: Record<string, string> = {
  lesson_goal: '本节目标',
  core_explanation: '核心讲解',
  math_problem_strategy: '策略选择',
  math_worked_example: '例题推演',
  math_intuition: '直觉导入',
  math_representation: '多重表征',
  math_formalization: '正式定义',
  math_variation: '变式练习',
  learner_action: '学习者行动',
  feedback_check: '检查与反馈',
}

const asTextList = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.flatMap(item => typeof item === 'string' ? [item.trim()] : []).filter(Boolean)
  }
  if (typeof value === 'string') {
    return value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  }
  return []
}

const unique = (values: string[]): string[] => [...new Set(values.map(item => item.trim()).filter(Boolean))]

const knowledgePoints = (section: Record<string, any>): Array<Record<string, any>> => (
  (section.knowledge_structure || [])
    .flatMap((group: Record<string, any>) => group?.knowledge_points || [])
    .filter((item: unknown) => item && typeof item === 'object')
)

const moduleLine = (module: Record<string, any>): string => {
  const moduleId = String(module.module_id || '')
  const label = String(module.label || MODULE_LABELS[moduleId] || '教学活动')
  const knowledge = asTextList(module.knowledge_names)
  const guidance = String(module.teaching_guidance || '').trim()
  const concreteGuidance = /^按模板完成/.test(guidance) ? '' : guidance
  const suffix = [
    knowledge.length ? `围绕${knowledge.join('、')}` : '',
    concreteGuidance,
  ].filter(Boolean).join('；')
  return suffix ? `${label}：${suffix}` : label
}

export function teacherLessonSectionView(section: Record<string, any> | null | undefined): TeacherLessonSectionView {
  if (!section) {
    return { learningObjective: '', keyDifficulties: [], teacherActivities: [], studentActivities: [], homework: [] }
  }

  const points = knowledgePoints(section)
  const modules = (section.teaching_modules || []).filter((item: unknown) => item && typeof item === 'object')
  const capabilityObjectives = points.flatMap(point => (
    (point.capability_points || []).map((item: Record<string, any>) => String(item?.observable_behavior || item?.name || '').trim())
  )).filter(Boolean)
  const pointStatements = points.map(point => String(point.statement || point.description || '').trim()).filter(Boolean)
  const boundaries = points.flatMap(point => asTextList(point.boundaries))
  const misconceptions = points.flatMap(point => (
    (point.misconceptions || []).map((item: Record<string, any>) => String(item?.discrimination || item?.name || '').trim())
  )).filter(Boolean)

  const explicitObjective = String(section.learning_objective || section.objective || '').trim()
  const learningObjective = explicitObjective
    || capabilityObjectives.join('；')
    || pointStatements.join('；')
    || asTextList(section.key_points).join('；')

  const explicitDifficulties = asTextList(section.key_difficulties)
  const keyDifficulties = unique(explicitDifficulties.length
    ? explicitDifficulties
    : [...asTextList(section.key_points), ...boundaries, ...misconceptions])

  const explicitTeacher = asTextList(section.teacher_activities)
  const teacherActivities = unique(explicitTeacher.length
    ? explicitTeacher
    : modules
      .filter((module: Record<string, any>) => !['learner_action', 'math_variation', 'feedback_check'].includes(String(module.module_id || '')))
      .map(moduleLine))

  const explicitStudent = asTextList(section.student_activities)
  const studentActivities = unique(explicitStudent.length
    ? explicitStudent
    : modules
      .filter((module: Record<string, any>) => ['learner_action', 'math_variation'].includes(String(module.module_id || '')))
      .map(moduleLine))

  const explicitHomework = asTextList(section.homework)
  const homework = unique(explicitHomework.length
    ? explicitHomework
    : modules
      .filter((module: Record<string, any>) => String(module.module_id || '') === 'feedback_check')
      .map(moduleLine))

  return { learningObjective, keyDifficulties, teacherActivities, studentActivities, homework }
}

export function teacherLessonSectionMarkdown(section: Record<string, any>, index: number): string {
  const view = teacherLessonSectionView(section)
  const title = String(section.title || section.node_name || `第 ${index + 1} 小节`)
  const list = (label: string, values: string[]) => values.length
    ? `**${label}：**\n${values.map(item => `- ${item}`).join('\n')}`
    : ''
  return [
    `### ${index + 1}. ${title}`,
    view.learningObjective ? `**学习目标：** ${view.learningObjective}` : '',
    list('重点与难点', view.keyDifficulties),
    list('教师活动', view.teacherActivities),
    list('学生活动', view.studentActivities),
    list('课后作业', view.homework),
  ].filter(Boolean).join('\n\n')
}

export function teacherLessonSectionDiff(
  beforeSection: Record<string, any> | null | undefined,
  afterSection: Record<string, any> | null | undefined,
): TeacherLessonSectionDiff[] {
  const before = teacherLessonSectionView(beforeSection)
  const after = teacherLessonSectionView(afterSection)
  const rows: Array<[keyof TeacherLessonSectionView, string]> = [
    ['learningObjective', '学习目标'],
    ['keyDifficulties', '重点与难点'],
    ['teacherActivities', '教师活动'],
    ['studentActivities', '学生活动'],
    ['homework', '课后作业'],
  ]
  const text = (value: string | string[]) => Array.isArray(value) ? value.join('\n') : value
  return rows.map(([key, label]) => {
    const beforeText = text(before[key])
    const afterText = text(after[key])
    return { key, label, before: beforeText, after: afterText, changed: beforeText !== afterText }
  })
}
