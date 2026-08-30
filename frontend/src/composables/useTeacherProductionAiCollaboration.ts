export type TeacherProductionAiDomain = 'outline' | 'lesson' | 'question-bank' | 'script' | 'ppt'

export type TeacherProductionAiPhase =
  | 'ready'
  | 'clarifying'
  | 'generating'
  | 'review'
  | 'accepting'
  | 'rejecting'
  | 'success'
  | 'error'

export type TeacherProductionAiEvent =
  | { type: 'OPEN'; candidatePending?: boolean }
  | { type: 'RESET' }
  | { type: 'ASK_CLARIFICATION' }
  | { type: 'GENERATE' }
  | { type: 'CANDIDATE_READY' }
  | { type: 'COURSE_PLAN_READY' }
  | { type: 'CANDIDATE_RESTORED' }
  | { type: 'ACCEPT' }
  | { type: 'REJECT' }
  | { type: 'RESOLVED' }
  | { type: 'FAIL' }

export interface TeacherProductionAiMessage {
  id: string
  role: 'assistant' | 'user'
  kind: 'text' | 'candidate' | 'course_plan' | 'receipt' | 'error'
  text: string
  planId?: string
  planStatus?: 'draft' | 'impact_ready' | 'needs_clarification' | 'candidate_ready' | 'blocked'
  impacts?: string[]
}

export type TeacherProductionAiCapability =
  | 'clarify_request'
  | 'edit_active_asset'
  | 'plan_course_change'

export interface TeacherProductionAiRoute {
  capability: TeacherProductionAiCapability
  domains: TeacherProductionAiDomain[]
  reason: 'unclear' | 'active_asset' | 'cross_asset' | 'batch_change' | 'structural_change'
}

export interface TeacherCoursePlanProjection {
  planId: string
  requestId: string
  status: NonNullable<TeacherProductionAiMessage['planStatus']>
  affectedUnitCount: number
  structuralOperationCount: number
  assetTypes: string[]
  blockingQuestionCount: number
}

interface TeacherCoursePlanSource {
  change_set_id?: unknown
  impact_summary?: {
    request_id?: unknown
    affected_units?: Array<{ asset_type?: unknown }>
  }
  teacher_change_planning?: {
    status?: unknown
    structural_operations?: unknown[]
    intent?: { blocking_questions?: unknown[] }
  } | null
}

const TEACHER_COURSE_PLAN_STATUSES = new Set<NonNullable<TeacherProductionAiMessage['planStatus']>>([
  'draft',
  'impact_ready',
  'needs_clarification',
  'candidate_ready',
  'blocked',
])

export interface TeacherProductionAiScope {
  domain: TeacherProductionAiDomain
  courseTitle: string
  primaryTitle: string
  secondaryTitle: string
  referenceCount: number
  selectionText?: string
  references?: Array<{
    id: string
    label: string
    role: 'primary' | 'reference' | 'question_source'
    origin?: 'material' | 'web_search'
  }>
}

const GENERATION_START_PHASES = new Set<TeacherProductionAiPhase>([
  'ready',
  'clarifying',
  'review',
  'success',
  'error',
])

export const TEACHER_LESSON_EDITABLE_FIELDS = [
  'learning_objective',
  'key_points',
  'key_difficulties',
  'pre_study',
  'key_analysis',
  'case_intro',
  'practice',
  'class_summary',
  'extension_learning',
  'teaching_modules',
  'in_class_checks',
  'homework',
  'teaching_notes',
] as const

export function transitionTeacherProductionAiPhase(
  phase: TeacherProductionAiPhase,
  event: TeacherProductionAiEvent,
): TeacherProductionAiPhase {
  if (event.type === 'RESET') return 'ready'
  if (event.type === 'OPEN') return event.candidatePending ? 'review' : phase === 'review' ? 'ready' : phase
  if (event.type === 'CANDIDATE_RESTORED') return 'review'
  if (event.type === 'FAIL') return 'error'
  if (event.type === 'ASK_CLARIFICATION' && GENERATION_START_PHASES.has(phase)) return 'clarifying'
  if (event.type === 'GENERATE' && GENERATION_START_PHASES.has(phase)) return 'generating'
  if (event.type === 'CANDIDATE_READY' && phase === 'generating') return 'review'
  if (event.type === 'COURSE_PLAN_READY' && phase === 'generating') return 'review'
  if (event.type === 'ACCEPT' && phase === 'review') return 'accepting'
  if (event.type === 'REJECT' && phase === 'review') return 'rejecting'
  if (event.type === 'RESOLVED' && ['accepting', 'rejecting'].includes(phase)) return 'success'
  return phase
}

export function teacherProductionAiBusy(phase: TeacherProductionAiPhase): boolean {
  return ['generating', 'accepting', 'rejecting'].includes(phase)
}

const DOMAIN_TARGETS: Record<TeacherProductionAiDomain, RegExp> = {
  outline: /(章节|小节|目录|大纲|顺序|结构|学习路径|学习目标|前置|依赖|合并|拆分)/,
  lesson: /(目标|重点|难点|知识|概念|案例|互动|活动|检查|评价|提问|练习|节奏|时间|讲授|作业|备注|教师|学生|导入|总结|迁移)/,
  script: /(讲稿|口语|表达|讲解|案例|提问|过渡|开场|总结|节奏|时间|互动|课堂|学生|教师|重复|段落)/,
  'question-bank': /(题|题库|练习|选择|判断|填空|应用|难度|错因|能力|检查|测评|作答|答案|解析)/,
  ppt: /(PPT|课件|幻灯|页面|标题|副标题|结论|措辞|压缩|展示|表达|课堂)/i,
}

const EXPLICIT_ASSET_TARGETS: Record<TeacherProductionAiDomain, RegExp> = {
  outline: /(课程大纲|大纲|目录|章节|小节|课程结构|学习路径|前置依赖)/,
  lesson: /(教案|教学设计|教学目标|教学重点|教学难点|教学环节|师生活动)/,
  script: /(讲稿|讲解稿|逐字稿|教师用语|口语表达)/,
  'question-bank': /(题库|题目|试题|练习题|选择题|判断题|填空题|应用题|答案|解析)/,
  ppt: /(PPT|课件|幻灯片|页面文案)/i,
}

const STRUCTURAL_CHANGE = /(删除|删掉|移除|合并|拆分|交换|调换|前移|后移|调整顺序|重新排序|改成\s*\d+\s*(章|节|讲)|增加\s*\d*\s*(章|节|讲)|新增\s*\d*\s*(章|节|讲))/
const COURSE_WIDE_CHANGE = /(整门课|整门课程|全课程|全课|全文|全局|全部|所有|每一[章节讲页题]|统一|批量|一律|永远都)/
const BATCH_CHANGE = /(替换|改成|改为|删除|删掉|移除|合并|重写|统一|批量)/

/**
 * Pick one of the two existing mutation paths before any model call:
 * the active asset keeps its native candidate endpoint; changes that alter
 * identities, order, or several assets use the formal CourseEvolutionPlan.
 */
export function routeTeacherProductionRequest(
  domain: TeacherProductionAiDomain,
  value: string,
): TeacherProductionAiRoute {
  const request = value.replace(/\s+/g, ' ').trim()
  const domains = (Object.entries(EXPLICIT_ASSET_TARGETS) as Array<[TeacherProductionAiDomain, RegExp]>)
    .filter(([, pattern]) => pattern.test(request))
    .map(([targetDomain]) => targetDomain)

  if (assessTeacherProductionRequest(domain, request) === 'clarify') {
    return { capability: 'clarify_request', domains, reason: 'unclear' }
  }
  if (domains.length > 1) {
    return { capability: 'plan_course_change', domains, reason: 'cross_asset' }
  }
  if (STRUCTURAL_CHANGE.test(request) && (domain === 'outline' || domains.includes('outline'))) {
    return {
      capability: 'plan_course_change',
      domains: domains.length ? domains : ['outline'],
      reason: 'structural_change',
    }
  }
  if (COURSE_WIDE_CHANGE.test(request) && BATCH_CHANGE.test(request)) {
    return {
      capability: 'plan_course_change',
      domains: domains.length ? domains : [domain],
      reason: 'batch_change',
    }
  }
  if (domains.length === 1 && domains[0] !== domain) {
    return { capability: 'plan_course_change', domains, reason: 'cross_asset' }
  }
  return {
    capability: 'edit_active_asset',
    domains: domains.length ? domains : [domain],
    reason: 'active_asset',
  }
}

export function assessTeacherProductionRequest(
  domain: TeacherProductionAiDomain,
  value: string,
): 'clarify' | 'generate' {
  const request = value.replace(/\s+/g, ' ').trim()
  if (!request) return 'clarify'

  const target = DOMAIN_TARGETS[domain]
  const concreteAction = /(增加|减少|删除|压缩|延长|改成|改为|突出|补充|替换|重写|调整|优化|细化|合并|拆分|保留|对齐|强化|弱化|前移|后移)/
  const vagueRequest = /(改好一点|优化一下|调整一下|完善一下|帮我改|不太好|重新弄|重新写|再优化|更好一些)/
  const asksForAdvice = /(怎么改|如何改|你觉得|给.*建议|先问|不知道.*改)/

  if (asksForAdvice.test(request)) return 'clarify'
  if (vagueRequest.test(request) && !target.test(request)) return 'clarify'
  if (request.length < 6 && !(target.test(request) && concreteAction.test(request))) return 'clarify'
  return 'generate'
}

function compactTeacherTurns(messages: TeacherProductionAiMessage[], budget = 1080): string[] {
  const selected: string[] = []
  let remaining = budget
  const turns = messages
    .filter(message => message.role === 'user')
    .map(message => message.text.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .slice(-8)
    .reverse()

  for (const turn of turns) {
    const clipped = turn.slice(0, 360)
    if (!selected.length || clipped.length + 8 <= remaining) {
      selected.push(clipped)
      remaining -= clipped.length + 8
    }
  }
  return selected.reverse()
}

export function buildTeacherCourseChangeInstruction(
  messages: TeacherProductionAiMessage[],
  scope: TeacherProductionAiScope,
): string {
  const requirements = compactTeacherTurns(messages)
    .map((turn, index) => `${index + 1}. ${turn}`)
    .join('\n')
  return [
    `课程：${scope.courseTitle}。`,
    `发起位置：${scope.primaryTitle} / ${scope.secondaryTitle}。`,
    scope.selectionText ? `教师选中内容：\n“${scope.selectionText.slice(0, 1200)}”` : '',
    `教师连续要求（越靠后优先级越高）：\n${requirements}`,
    '请先形成可审阅的整课修改方案，识别内容修改与结构修改及其下游影响；此时不要写入正式课程。',
  ].filter(Boolean).join('\n')
}

export function projectTeacherCoursePlan(plan: TeacherCoursePlanSource): TeacherCoursePlanProjection | null {
  const planning = plan?.teacher_change_planning
  const planId = String(plan?.change_set_id || '')
  const status = String(planning?.status || '') as NonNullable<TeacherProductionAiMessage['planStatus']>
  if (!planId || !planning || !TEACHER_COURSE_PLAN_STATUSES.has(status)) return null
  const affectedUnits = Array.isArray(plan?.impact_summary?.affected_units)
    ? plan.impact_summary.affected_units
    : []
  return {
    planId,
    requestId: String(plan?.impact_summary?.request_id || ''),
    status,
    affectedUnitCount: affectedUnits.length,
    structuralOperationCount: Array.isArray(planning.structural_operations)
      ? planning.structural_operations.length
      : 0,
    assetTypes: [...new Set(affectedUnits.map(item => String(item?.asset_type || '')).filter(Boolean))],
    blockingQuestionCount: Array.isArray(planning?.intent?.blocking_questions)
      ? planning.intent.blocking_questions.length
      : 0,
  }
}

export function buildTeacherProductionAiInstruction(
  messages: TeacherProductionAiMessage[],
  scope: TeacherProductionAiScope,
): string {
  const turns = compactTeacherTurns(messages)
  const requirements = turns.map((turn, index) => `${index + 1}. ${turn}`).join('\n')
  const sourceList = (scope.references || [])
    .map((item, index) => `${index + 1}. [${item.role}] ${item.label} (${item.id})`)
    .join('\n')
  const scopeLine = `范围：课程“${scope.courseTitle}”；当前对象“${scope.primaryTitle}”；局部范围“${scope.secondaryTitle}”。`
  const common = [
    scopeLine,
    scope.selectionText
      ? `教师当前选中内容（本轮只围绕此内容修改）：\n“${scope.selectionText.slice(0, 1200)}”`
      : '教师当前未限定具体文字选区。',
    `资料范围（只能使用下列精确资料）：\n${sourceList || '无额外资料'}`,
    `教师对话（越靠后优先级越高）：\n${requirements}`,
    '输出边界：只生成候选，不确认、不发布，也不自动改写下游正式内容。',
  ]

  if (scope.domain === 'outline') {
    return [
      '任务：依据教师对话，为当前课程大纲生成一份可审阅的结构调整候选。',
      ...common,
      '修改原则：保持已稳定节点 ID 和课程方向；只处理章节增删、顺序、学习目标与前置依赖；未涉及内容保持原样。',
    ].join('\n')
  }

  if (scope.domain === 'script') {
    return [
      '任务：依据教师对话，为当前讲稿小节生成一份可审阅的表达修改候选。',
      ...common,
      '修改原则：保持已确认教案的教学目标、模块身份、知识事实与时间约束；只调整教师明确提出的讲解表达。',
    ].join('\n')
  }

  if (scope.domain === 'question-bank') {
    return [
      '任务：依据教师对话，为整门课程题库生成一份可确认的重建任务候选。',
      ...common,
      '修改原则：保持已确认的课程范围、精确资料和题库版本；教师指令不得改变学习目标、题型合同、答案事实、验证器和质量门。',
    ].join('\n')
  }

  if (scope.domain === 'ppt') {
    return [
      '任务：依据教师对话，为当前 V6 PPT 页面生成一份可审阅的表达修改候选。',
      ...common,
      '修改原则：只调整标题、副标题和关键结论；保持页面身份、顺序、来源绑定、教学语义和其他页面不变。',
    ].join('\n')
  }

  return [
    '任务：依据教师对话，为当前教案小节生成一份可审阅的结构化修改候选。',
    ...common,
    '修改原则：只修改实现教师要求所必需的字段，未涉及内容保持原样；不得改写知识事实、稳定 ID、小节数量、教学环节身份和顺序。',
    '教学原则：目标应可观察；活动和课堂检查应与目标对应；除非教师明确要求调整节奏，否则保持原有总时长。',
  ].join('\n')
}

export function changedTeacherLessonFields(
  basePlan: Record<string, any> | undefined,
  candidatePlan: Record<string, any> | undefined,
  sectionId: string,
): string[] {
  const baseSections = Array.isArray(basePlan?.sections) ? basePlan!.sections : []
  const candidateSections = Array.isArray(candidatePlan?.sections) ? candidatePlan!.sections : []
  const base = baseSections.find((section: any) => String(section?.node_id || '') === sectionId)
  const candidate = candidateSections.find((section: any) => String(section?.node_id || '') === sectionId)
  if (!base || !candidate) return []
  return TEACHER_LESSON_EDITABLE_FIELDS.filter(
    field => JSON.stringify(base[field] ?? null) !== JSON.stringify(candidate[field] ?? null),
  )
}
