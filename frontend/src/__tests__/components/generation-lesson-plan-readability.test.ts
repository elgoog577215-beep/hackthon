import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GenerationLessonPlan from '@/components/GenerationLessonPlan.vue'
import type { Node } from '@/stores/types'

describe('课程教案阅读尺度', () => {
  it('桌面端教案正文不再使用 8 至 10 像素的微缩字号', () => {
    const component = readFileSync(
      resolve(process.cwd(), 'src/components/GenerationLessonPlan.vue'),
      'utf8',
    )

    expect(component).not.toMatch(/font-size:\s*(?:8|9|10)px/)
    expect(component).toContain('width:min(1180px,100%)')
    expect(component).toContain('.generation-lesson-plan__section-title h3')
    expect(component).toContain('.generation-lesson-plan__knowledge-detail')
  })

  it('把教学流程、掌握证据、易错纠偏与知识衔接放在同一份小节教案中', async () => {
    const nodes: Node[] = [
      {
        node_id: 'chapter-1',
        node_name: '第一章',
        node_level: 1,
        parent_node_id: '',
        node_content: '',
        node_type: 'original',
        generation_status: 'completed',
        generated_chars: 0,
      },
      {
        node_id: 'section-1',
        node_name: '向量的线性组合',
        node_level: 2,
        parent_node_id: 'chapter-1',
        node_content: '',
        learning_objective: '能够用线性组合解释向量生成关系',
        node_type: 'original',
        generation_status: 'completed',
        generated_chars: 0,
      },
      {
        node_id: 'section-2',
        node_name: '张成空间',
        node_level: 2,
        parent_node_id: 'chapter-1',
        node_content: '',
        learning_objective: '能够判断给定向量组的张成范围',
        node_type: 'original',
        generation_status: 'completed',
        generated_chars: 0,
      },
    ]
    const plan = {
      schema_version: 'course_teaching_plan_projection_v1' as const,
      status: 'completed',
      revision_id: 'teaching-1',
      strategy: 'batched',
      section_count: 2,
      knowledge_point_count: 1,
      teaching_module_count: 1,
      sections: [{
        node_id: 'section-1',
        key_points: ['线性组合'],
        reused_knowledge_names: ['向量加法'],
        knowledge_relations: [{
          source_name: '向量加法',
          target_name: '线性组合',
          relation_type: 'prerequisite',
          reason: '线性组合建立在向量加法与数乘之上',
        }],
        teaching_modules: [{
          module_id: 'guided-example',
          teaching_purpose: '用几何例子建立线性组合直觉',
          teaching_guidance: '先让学生拖动系数，再归纳代数表达。',
          knowledge_names: ['线性组合'],
        }],
        knowledge_structure: [{
          concept_group: '核心机制',
          description: '从运算过程过渡到生成关系',
          knowledge_points: [{
            knowledge_id: 'k-1',
            name: '线性组合',
            statement: '向量按标量加权后相加。',
            knowledge_type: 'concept',
            conditions: ['向量属于同一向量空间'],
            boundaries: ['系数来自指定数域'],
            counterexamples: [],
            capability: '',
            capability_points: [{ observable_behavior: '能写出目标向量的系数组合' }],
            mastery_criteria: [{
              observable_performance: '独立完成两组分解',
              verification_method: '课堂出口题',
            }],
            misconceptions: [{
              observable_error_pattern: '把系数当作向量分量',
              repair_strategy: '用几何缩放重新辨析',
            }],
            aliases: [],
            prerequisite_names: ['向量加法'],
          }],
        }],
      }],
    }

    const wrapper = mount(GenerationLessonPlan, {
      props: {
        nodes,
        plan,
        activeNodeId: 'section-1',
      },
    })

    expect(wrapper.text()).toContain('这一节怎样展开')
    expect(wrapper.text()).toContain('用几何例子建立线性组合直觉')
    expect(wrapper.text()).toContain('独立完成两组分解')
    expect(wrapper.text()).toContain('把系数当作向量分量')
    expect(wrapper.text()).toContain('向量加法')
    expect(wrapper.text()).toContain('线性组合')

    await wrapper.get('.generation-lesson-plan__pager > button:last-child').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ node_id: 'section-2' })
  })
})
