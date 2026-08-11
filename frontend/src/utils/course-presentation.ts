export type CourseCoverPreset = 'ai' | 'programming' | 'mathematics' | 'science' | 'humanities' | 'general'

const COURSE_COVER_RULES: Array<{ preset: CourseCoverPreset; pattern: RegExp }> = [
  {
    preset: 'ai',
    pattern: /机器学习|深度学习|人工智能|神经网络|大模型|计算机视觉|自然语言|数据科学|machine\s*learning|deep\s*learning|artificial\s*intelligence|\bai\b/i,
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
    pattern: /语文|文学|写作|历史|哲学|政治|语言|英语|艺术|humanities|literature|history|philosophy|language|writing/i,
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
