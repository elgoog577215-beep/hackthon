export type CourseCoverPreset =
  | 'ai'
  | 'programming'
  | 'mathematics'
  | 'medicine'
  | 'engineering'
  | 'science'
  | 'humanities'
  | 'general'

const COURSE_COVER_RULES: Array<{ preset: CourseCoverPreset; pattern: RegExp }> = [
  {
    preset: 'ai',
    pattern: /机器学习|深度学习|人工智能|神经网络|大模型|计算机视觉|自然语言|数据科学|machine\s*learning|deep\s*learning|artificial\s*intelligence|\bai\b/i,
  },
  {
    preset: 'medicine',
    pattern: /医学|解剖|临床|生理|病理|护理|药理|诊断|人体|健康|medicine|medical|anatomy|clinical|nursing|health/i,
  },
  {
    preset: 'engineering',
    pattern: /控制学|控制论|自动化|工程|机械|电子|电路|信号|嵌入式|机器人|系统设计|control|engineering|automation|circuit|robotics/i,
  },
  {
    preset: 'programming',
    pattern: /unity|编程|程序设计|软件|算法|开发|计算机|前端|后端|数据库|python|java|javascript|typescript|c\+\+|software|programming|computer/i,
  },
  {
    preset: 'mathematics',
    pattern: /数学|代数|微积分|几何|概率|统计|矩阵|数论|方程|math|algebra|calculus|geometry|statistics|matrix/i,
  },
  {
    preset: 'science',
    pattern: /物理|化学|生物|科学|力学|热力学|电磁|天文|physics|chemistry|biology|science/i,
  },
  {
    preset: 'humanities',
    pattern: /语文|文学|写作|历史|哲学|政治|语言|英语|艺术|辩论|逻辑|演讲|法学|法律|社会|humanities|literature|history|philosophy|language|writing|debate|rhetoric|law/i,
  },
]

export function formatCourseTitle(title: string): string {
  const normalized = String(title || '')
    .trim()
    .replace(/^[《》\s]+/u, '')
    .replace(/[《》\s]+$/u, '')
    .trim()

  return normalized ? `《${normalized}》` : ''
}

export function courseCoverPreset(title: string): CourseCoverPreset {
  const normalized = String(title || '').trim()
  return COURSE_COVER_RULES.find(rule => rule.pattern.test(normalized))?.preset || 'general'
}
