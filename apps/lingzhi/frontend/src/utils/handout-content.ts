export type HandoutContentGroup = 'explanation' | 'practice' | 'question'

// Classify explicit block metadata, never the wording of saved course content.
const groups: Record<string, HandoutContentGroup> = {
  background: 'explanation', introduction: 'explanation', definition: 'explanation',
  explanation: 'explanation', derivation: 'explanation', example: 'explanation',
  comparison: 'explanation', theorem: 'explanation', result: 'explanation',
  summary: 'explanation', misconception: 'explanation', warning: 'explanation',
  rule: 'explanation', diagram: 'explanation', flowchart: 'explanation',
  exercise: 'practice', case: 'practice',
  question: 'question', review_question: 'question', guiding_question: 'question',
}

const aliases: Record<string, string> = {
  背景: 'background', 引入: 'introduction', 定义: 'definition', 解释: 'explanation',
  讲解: 'explanation', 推导: 'derivation', 举例: 'example', 例题: 'example', 对比: 'comparison',
  定理: 'theorem', 结论: 'result', 总结: 'summary', 辨析: 'misconception', 易错点: 'warning',
  练习: 'exercise', 理论练习: 'exercise', 理论型练习: 'exercise', theoretical_exercise: 'exercise',
  实战案例: 'case', 实战型案例: 'case', practical_case: 'case',
  提问: 'question', 复习提问: 'review_question', 复习性提问: 'review_question', recall_question: 'review_question',
  启发提问: 'guiding_question', 启发性提问: 'guiding_question', heuristic_question: 'guiding_question',
  解答: 'answer',
}

export function handoutContentType(type: string): string {
  const value = type.trim()
  return aliases[value] || value
}

export function handoutContentGroup(type: string): HandoutContentGroup | undefined {
  return groups[handoutContentType(type)]
}
