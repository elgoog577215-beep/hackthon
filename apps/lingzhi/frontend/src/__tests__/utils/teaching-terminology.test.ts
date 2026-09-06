import { describe, expect, it } from 'vitest'
import { teacherFacingTeachingLabel } from '../../utils/teaching-terminology'

describe('teacher-facing teaching terminology', () => {
  it('shows formal educational terms for historical module labels', () => {
    expect(teacherFacingTeachingLabel('本节任务', 'lesson_goal')).toBe('本讲目标')
    expect(teacherFacingTeachingLabel('核心教学', 'core_explanation')).toBe('重点讲解')
    expect(teacherFacingTeachingLabel('学习者行动', 'learner_action')).toBe('学生活动')
    expect(teacherFacingTeachingLabel('检查与反馈', 'feedback_check')).toBe('课堂评价与反馈')
    expect(teacherFacingTeachingLabel('项目实战（20 分钟）')).toBe('项目实践（20 分钟）')
  })

  it('uses the module id when historical content only stores an internal identifier', () => {
    expect(teacherFacingTeachingLabel('core_explanation', 'core_explanation')).toBe('重点讲解')
    expect(teacherFacingTeachingLabel('', 'engineering_testing')).toBe('测试与结果分析')
  })

  it('preserves a teacher-written concrete title', () => {
    expect(teacherFacingTeachingLabel('比较两种排序算法')).toBe('比较两种排序算法')
  })
})
