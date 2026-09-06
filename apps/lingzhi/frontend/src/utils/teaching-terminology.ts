/**
 * 教师端正式教学用语。
 *
 * 后端的 module_id、历史课程标题和兼容接口可以继续保留旧值；所有面向
 * 教师的标题都应经过这里，避免把内部建模语言直接显示在备课界面。
 */

export const TEACHER_MODULE_LABELS: Record<string, string> = {
  integrated_transfer: '综合应用',
  lesson_goal: '本讲目标',
  core_explanation: '重点讲解',
  learner_action: '学生活动',
  feedback_check: '课堂评价与反馈',
  composition_deep_reasoning: '深入讲解与推理',
  composition_real_application: '情境应用',
  composition_project_task: '项目实践',
  composition_boundary: '适用条件与反例',
  difficulty_guided_practice: '分步练习',
  difficulty_transfer_challenge: '拓展应用',
  general_concept_map: '概念关系',
  general_explained_example: '例子讲解',
  general_transfer: '综合应用',
  math_intuition: '直观理解',
  math_worked_example: '例题讲解',
  math_representation: '多种表示',
  engineering_artifact_path: '项目成果与进度',
  engineering_minimal_run: '基础示例与运行',
  engineering_output: '运行结果与核对',
  engineering_mechanism: '实现原理',
  engineering_modification: '改进练习',
  engineering_debugging: '调试与修正',
  engineering_testing: '测试与结果分析',
  engineering_design: '需求分析与方案设计',
  science_phenomenon_path: '从现象到模型',
  life_mechanism: '过程与机制',
  life_case: '案例分析',
  language_scenario_path: '交际能力发展',
  language_controlled_practice: '基础练习',
  language_output: '表达与运用',
  language_interaction: '互动交流',
  language_mediation: '转述与沟通',
  business_deliverable_path: '成果形成过程',
  business_case: '案例分析',
  business_task: '实践任务',
  business_reflection: '成果评价与反思',
}

const LEGACY_LABELS: Array<[string, string]> = [
  ['最小可运行示例', '基础示例与运行'],
  ['工程成果路径', '项目成果与进度'],
  ['需求与设计', '需求分析与方案设计'],
  ['检查与反馈', '课堂评价与反馈'],
  ['学习者行动', '学生活动'],
  ['本节任务', '本讲目标'],
  ['本节目标', '本讲目标'],
  ['核心教学', '重点讲解'],
  ['核心讲解', '重点讲解'],
  ['深入推演', '深入讲解与推理'],
  ['真实场景', '情境应用'],
  ['项目实战', '项目实践'],
  ['边界与反例', '适用条件与反例'],
  ['带支架练习', '分步练习'],
  ['迁移挑战', '拓展应用'],
  ['综合迁移', '综合应用'],
  ['概念地图', '概念关系'],
  ['解释性例子', '例子讲解'],
  ['直觉入口', '直观理解'],
  ['例题推演', '例题讲解'],
  ['多重表征', '多种表示'],
  ['运行结果', '运行结果与核对'],
  ['机制拆解', '实现原理'],
  ['修改任务', '改进练习'],
  ['调试案例', '调试与修正'],
  ['测试与质量', '测试与结果分析'],
  ['现象到模型路径', '从现象到模型'],
  ['机制过程', '过程与机制'],
  ['机制案例', '案例分析'],
  ['交际场景路径', '交际能力发展'],
  ['控制练习', '基础练习'],
  ['真实输出', '表达与运用'],
  ['互动协商', '互动交流'],
  ['调解转述', '转述与沟通'],
  ['工作成果路径', '成果形成过程'],
  ['案例拆解', '案例分析'],
  ['实战任务', '实践任务'],
  ['成果复盘', '成果评价与反思'],
]

const escaped = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

export function teacherFacingTeachingLabel(value: unknown, moduleId = ''): string {
  const raw = String(value || '').trim()
  const canonical = TEACHER_MODULE_LABELS[String(moduleId || '').trim()]
  if (!raw || raw === moduleId) return canonical || raw

  for (const [legacy, current] of LEGACY_LABELS) {
    const match = raw.match(new RegExp(`^${escaped(legacy)}(?=$|[：:\\s（(]|\\d)`))
    if (match) return `${current}${raw.slice(match[0].length)}`
  }
  return raw
}
