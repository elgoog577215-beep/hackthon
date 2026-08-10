import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import FormalLessonPlanDocument from '@/components/FormalLessonPlanDocument.vue'
import type { CourseTeachingPlanProjection, Node } from '@/stores/types'

const nodes: Node[] = [{
  node_id: 'section-1',
  node_name: '第一课 识别生成式 AI 的教学边界',
  node_level: 2,
  parent_node_id: 'chapter-1',
  node_content: '',
  learning_objective: '能够判断适用边界',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 0,
}]

const plan: CourseTeachingPlanProjection = {
  schema_version: 'course_teaching_plan_projection_v1',
  status: 'completed',
  revision_id: 'teaching-plan-7',
  strategy: 'bounded_batches',
  section_count: 1,
  knowledge_point_count: 1,
  teaching_module_count: 1,
  overall: {
    course_title: '生成式人工智能教学应用设计',
    positioning: '面向师范生的课堂应用设计课程',
    target_audience: '本科师范生',
    learning_objectives: ['能够依据教学目标判断生成式 AI 的适用边界'],
    prerequisites: ['具备基础教学设计知识'],
    teaching_strategy: {
      primary_mode: 'case_based',
      secondary_mode: 'discussion',
      rationale: '以真实案例辨析和小组设计任务组织学习。',
    },
    assessment_methods: ['课堂辨析任务', '教学设计作品'],
    classroom: {
      total_class_hours: 12,
      lesson_duration_minutes: 45,
      teaching_context: 'classroom',
      class_profile: '学生具备教学法基础，但 AI 使用经验差异较大。',
      teaching_preparation: ['准备正反案例'],
      course_assessment_plan: ['过程任务 40%，课程作品 60%'],
    },
    chapters: [],
    knowledge_tags: [],
  },
  sections: [{
    node_id: 'section-1',
    knowledge_structure: [],
    key_points: ['适用边界判断'],
    key_difficulties: ['区分效率提升与教学责任转移'],
    reused_knowledge_names: [],
    knowledge_relations: [],
    planned_minutes: 45,
    resource_refs: ['教师提供的课堂案例包'],
    in_class_checks: ['用新案例解释采用或不采用 AI 的理由'],
    homework: ['完成一页教学应用设计说明'],
    teaching_notes: ['避免上传学生隐私数据'],
    teaching_modules: [{
      module_id: 'case-analysis',
      teaching_purpose: '辨析适用边界',
      knowledge_names: ['适用边界判断'],
      planned_minutes: 20,
      teacher_activity: '展示正反案例并追问判断依据',
      student_activity: '小组比较案例并形成判断规则',
    }],
  }],
}

describe('正式教案文档', () => {
  it('把结构化教案编译为连续、可交付的教师文档', () => {
    const wrapper = mount(FormalLessonPlanDocument, { props: { plan, nodes } })
    const text = wrapper.text()

    expect(text).toContain('正式课程教案')
    expect(text).toContain('生成式人工智能教学应用设计')
    expect(text).toContain('教学目标')
    expect(text).toContain('教学重点与难点')
    expect(text).toContain('教学策略、准备与评价')
    expect(text).toContain('教学过程')
    expect(text).toContain('第一课 识别生成式 AI 的教学边界')
    expect(text).toContain('展示正反案例并追问判断依据')
    expect(text).toContain('小组比较案例并形成判断规则')
    expect(text).toContain('完成一页教学应用设计说明')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.find('.formal-lesson-plan__footer').text()).toContain('teaching-plan-7')
  })
})
