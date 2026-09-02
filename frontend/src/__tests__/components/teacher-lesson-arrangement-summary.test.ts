import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TeacherLessonArrangementSummary from '@/components/TeacherLessonArrangementSummary.vue'
import type { TeacherLessonArrangement } from '@/stores/teacherLessonAuthoring'

const arrangement: TeacherLessonArrangement = {
  schema_version: 'teacher_lesson_arrangement_v1',
  revision_id: 'arrangement-1',
  lesson_unit_id: 'lesson-1',
  source_outline_revision_id: 'outline-1',
  lesson_type: 'theory_practice',
  lesson_type_label: '讲练结合',
  lesson_type_recommendation_reason: '本讲需要把原理讲解、示范和练习组织为连续学习任务。',
  blocks: [{
    block_id: 'block-1',
    module_id: 'math_formalization',
    section_node_id: 'section-1',
    section_title: '导数的定义',
    name: '建立正式定义',
    role: 'concept',
    purpose: '从变化过程建立导数定义。',
    content_summary: '连接图像、语言与极限表达。',
    planned_minutes: 20,
    teacher_activity: '显化对象、条件和极限过程。',
    student_activity: '补全定义并解释每个符号。',
    expected_output: '条件完整的导数定义。',
    check_method: '检查符号、条件和图像是否一致。',
    feedback_strategy: '先定位用直觉替代定义的问题，再安排修正。',
    adaptation_options: ['达到：进入变式', '部分达到：补充表征', '未达到：回到极限前置'],
    resource_refs: ['教材第 3 章'],
    tools: ['函数图像工具'],
    safety_boundary: '不得伪造定理、证明或计算结果。',
    required: true,
  }],
  status: 'confirmed',
  confirmed: true,
  source_state: 'current',
}

describe('本讲教学结构摘要', () => {
  it('先显示课型与推荐依据，再展开师生行动、证据和调整预案', async () => {
    const wrapper = mount(TeacherLessonArrangementSummary, {
      props: {
        arrangement,
        impactLabels: ['当前教案需要重新核对', 'PPT 需要更新'],
      },
    })

    expect(wrapper.text()).toContain('讲练结合')
    expect(wrapper.text()).toContain('本讲需要把原理讲解、示范和练习组织为连续学习任务')
    expect(wrapper.text()).toContain('最后可用版本会保留，不会被静默覆盖')
    expect(wrapper.text()).not.toContain('显化对象、条件和极限过程')

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('教师动作')
    expect(wrapper.text()).toContain('显化对象、条件和极限过程')
    expect(wrapper.text()).toContain('学生行动')
    expect(wrapper.text()).toContain('条件完整的导数定义')
    expect(wrapper.text()).toContain('教材第 3 章；函数图像工具')
    expect(wrapper.text()).toContain('三档处理')
    expect(wrapper.text()).toContain('不得伪造定理、证明或计算结果')
  })
})
