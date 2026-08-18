import { describe, expect, it } from 'vitest'
import {
  teacherLessonSectionDiff,
  teacherLessonSectionMarkdown,
  teacherLessonSectionView,
} from '../../utils/teacher-lesson-plan'

const section = {
  node_id: 'L2-1-1',
  title: '1.1 数制转换',
  key_points: ['二进制转换'],
  knowledge_structure: [{
    knowledge_points: [{
      name: '二进制转换',
      statement: '完成二进制与十进制之间的相互转换。',
      boundaries: ['仅处理无符号整数'],
      capability_points: [{ observable_behavior: '能够独立完成一次进制转换并核对结果。' }],
    }],
  }],
  teaching_modules: [
    {
      module_id: 'core_explanation',
      teaching_purpose: '按模板完成「核心讲解」',
      teaching_guidance: '使用位权展开演示转换过程',
      knowledge_names: ['二进制转换'],
    },
    {
      module_id: 'learner_action',
      teaching_guidance: '学生独立完成一道转换题',
      knowledge_names: ['二进制转换'],
    },
  ],
}

describe('teacher lesson plan projection', () => {
  it('projects real plan-v3 fields into populated editor values', () => {
    const view = teacherLessonSectionView(section)
    expect(view.learningObjective).toBe('能够独立完成一次进制转换并核对结果。')
    expect(view.keyDifficulties).toContain('仅处理无符号整数')
    expect(view.teacherActivities[0]).toContain('位权展开演示转换过程')
    expect(view.studentActivities[0]).toContain('学生独立完成一道转换题')
  })

  it('renders human-readable preview without raw module JSON', () => {
    const markdown = teacherLessonSectionMarkdown(section, 0)
    expect(markdown).toContain('**学习目标：**')
    expect(markdown).toContain('**教师活动：**')
    expect(markdown).not.toContain('"module_id"')
    expect(markdown).not.toContain('按模板完成')
  })

  it('builds field-level candidate comparisons', () => {
    const changed = {
      ...section,
      learning_objective: '学生能够解释位权并完成两种进制转换。',
      teacher_activities: ['先演示，再让学生解释每一步依据。'],
    }
    const diff = teacherLessonSectionDiff(section, changed)
    expect(diff.find(item => item.key === 'learningObjective')?.changed).toBe(true)
    expect(diff.find(item => item.key === 'teacherActivities')?.after).toContain('学生解释')
    expect(diff.some(item => item.changed)).toBe(true)
  })
})
