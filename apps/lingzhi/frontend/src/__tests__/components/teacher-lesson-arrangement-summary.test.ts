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
  ready: true,
  source_state: 'current',
}

describe('本讲教学结构摘要', () => {
  it('已生成结构直接展示教师需要使用的课堂流程', () => {
    const wrapper = mount(TeacherLessonArrangementSummary, {
      props: {
        arrangement,
        impactLabels: ['当前教案需要重新核对', 'PPT 需要更新'],
      },
    })

    expect(wrapper.text()).not.toContain('讲练结合')
    expect(wrapper.find('select').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('本讲需要把原理讲解、示范和练习组织为连续学习任务')
    expect(wrapper.text()).not.toContain('个内容主题')
    expect(wrapper.text()).not.toContain('个教学块')
    expect(wrapper.text()).toContain('最后可用版本会保留，不会被静默覆盖')
    expect(wrapper.text()).toContain('环节目标')
    expect(wrapper.text()).toContain('课堂活动')
    expect(wrapper.text()).toContain('显化对象、条件和极限过程')
    expect(wrapper.text()).toContain('补全定义并解释每个符号')
    expect(wrapper.text()).toContain('达成判断')
    expect(wrapper.text()).toContain('条件完整的导数定义')
    expect(wrapper.text()).not.toContain('教师动作')
    expect(wrapper.text()).not.toContain('学生行动')
    expect(wrapper.text()).not.toContain('教材第 3 章')
    expect(wrapper.text()).not.toContain('三档处理')
    expect(wrapper.text()).not.toContain('进入支持')
    expect(wrapper.text()).not.toContain('分组方式')
    expect(wrapper.text()).not.toContain('前后衔接')
    expect(wrapper.text()).not.toContain('专业边界')
    expect(wrapper.find('.arrangement-disclosure').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('教学结构确认')
    expect(wrapper.text()).not.toContain('生成依据')
  })

  it('教学结构摘要中的公式通过 KaTeX 显示', () => {
    const formulaArrangement = structuredClone(arrangement)
    formulaArrangement.blocks[0]!.content_summary = String.raw`比较 $\nabla^2 f$ 与 $\varphi(0)=1$。`

    const wrapper = mount(TeacherLessonArrangementSummary, {
      props: { arrangement: formulaArrangement },
    })

    expect(wrapper.findAll('.katex')).toHaveLength(2)
    expect(wrapper.text()).not.toContain('\\nabla')
    expect(wrapper.text()).not.toContain('\\varphi')
  })

  it('不再用解释性标题或展开按钮重复说明区域用途', () => {
    const wrapper = mount(TeacherLessonArrangementSummary, {
      props: { arrangement },
    })

    expect(wrapper.find('.arrangement-disclosure').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('教学结构确认')
    expect(wrapper.text()).not.toContain('生成依据')
    expect(wrapper.text()).toContain('环节目标')
  })

  it('上游变更后直接展示需更新的课堂流程', () => {
    const wrapper = mount(TeacherLessonArrangementSummary, {
      props: {
        arrangement: { ...arrangement, source_state: 'stale' },
      },
    })

    expect(wrapper.text()).toContain('环节目标')
    expect(wrapper.text()).toContain('教学结构需更新')
    expect(wrapper.find('.arrangement-confirm').exists()).toBe(false)
  })

  it('把生成操作放在置顶操作栏内，不再另设统计条和生成范围标题', () => {
    const wrapper = mount(TeacherLessonArrangementSummary, {
      props: { arrangement, stickyActions: true },
      slots: {
        'generation-actions': '<div data-testid="generation-slot"><button>只生成本讲</button><button>生成全部教案</button></div>',
      },
    })

    const toolbar = wrapper.get('.arrangement-toolbar')
    expect(toolbar.get('.arrangement-context').text()).toContain('教学结构已生成')
    expect(toolbar.find('select').exists()).toBe(false)
    expect(toolbar.get('.arrangement-state').text()).toContain('教学结构已生成')
    expect(toolbar.get('[data-testid="generation-slot"]').text()).toContain('只生成本讲')
    expect(toolbar.text()).toContain('生成全部教案')
    expect(wrapper.get('[data-testid="lesson-arrangement-summary"]').classes()).toContain('has-sticky-actions')
    expect(wrapper.find('.arrangement-heading').exists()).toBe(false)
    expect(wrapper.find('.arrangement-disclosure').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('生成范围')
  })
})
