import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  getTeacherIdentity: () => 'teacher-test',
}))

import http from '@/utils/http'
import GenerationLessonPlan from '@/components/GenerationLessonPlan.vue'
import { useTeachingPlanWorkbenchStore } from '@/stores/teachingPlanWorkbench'
import type { Node } from '@/stores/types'

// 5.5/5.6：差异要按新增/删除/替换分组并定位到教师看得懂的位置；
// 影响要五组分开，尤其「保持不变」必须显示——教师要能区分「确认没事」与「漏了」。
const nodes: Node[] = [{
  node_id: 'L2-1-1', node_name: '1.1 向量', node_level: 2, parent_node_id: 'c1',
  node_content: '', learning_objective: '理解向量', node_type: 'original',
  generation_status: 'completed', generated_chars: 0,
}]

const plan: any = {
  schema_version: 'course_teaching_plan_projection_v1', status: 'completed',
  revision_id: 'r1', strategy: 'batched', section_count: 1,
  knowledge_point_count: 1, teaching_module_count: 1,
  sections: [{ node_id: 'L2-1-1', key_points: [], reused_knowledge_names: [],
    knowledge_relations: [], knowledge_structure: [], teaching_modules: [] }],
}

const review = {
  draft_id: 'tpd_1',
  base_plan_revision_id: 'tpr_1',
  diff: { operations: [
    { operation_id: 'o1', path: 'sections/L2-1-1/homework', before: [], after: ['作业一'] },
    { operation_id: 'o2', path: 'overall/positioning', before: '旧定位', after: '' },
    { operation_id: 'o3', path: 'sections/L2-1-1/teaching_modules/core/teaching_guidance',
      before: '旧指导', after: '新指导', source: 'ai' },
  ] },
  impact_report: {
    changed: [{ type: 'teaching_plan_section', id: 'L2-1-1', reason: '小节教案已更新' }],
    needs_regeneration: [{ type: 'section_content', id: 'L2-1-1', reason: '正文需重建' }],
    stale: [],
    unchanged: [{ type: 'practice', id: 'p9', reason: '未引用该目标' }],
    blocked: [],
    blocking: false,
  },
  validation: { passed: true },
}

function workbench() {
  return {
    schema_version: 'teaching_plan_workbench_v1', course_id: 'course-1',
    enabled: true, available: true, read_only_reason: '',
    course_document_revision: 'doc-1', current_plan_revision_id: 'tpr_1',
    course_revision_vector: {}, teaching_plan: plan,
    draft: { draft_id: 'tpd_1', base_plan_revision_id: 'tpr_1',
      base_course_document_revision: 'doc-1', changed_paths: ['x'], operations: [] },
    revisions: [], change_sets: [], ai_candidates: [],
    editable_fields: [], downstream: {},
  }
}

async function mountWithReview() {
  vi.mocked(http.get).mockResolvedValue({ data: { workbench: workbench() } } as any)
  vi.mocked(http.post).mockResolvedValue({ data: { review } } as any)
  const store = useTeachingPlanWorkbenchStore()
  await store.load('course-1')
  const wrapper = mount(GenerationLessonPlan, {
    props: { nodes, plan, activeNodeId: 'L2-1-1', courseId: 'course-1' },
  })
  await wrapper.get('[aria-label="审阅变更"]').trigger('click')
  await new Promise(r => setTimeout(r, 0))
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('差异与影响审阅面板', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('差异按新增/删除/替换分组', async () => {
    const wrapper = await mountWithReview()
    const kinds = wrapper.findAll('.generation-lesson-plan__diff-kind').map(n => n.text())
    expect(kinds).toContain('新增')
    expect(kinds).toContain('删除')
    expect(kinds).toContain('替换')
    // 新增排在最前，删除排在最后
    expect(kinds[0]).toBe('新增')
    expect(kinds[kinds.length - 1]).toBe('删除')
  })

  it('字段路径定位到教师看得懂的位置而不是只有裸路径', async () => {
    const wrapper = await mountWithReview()
    const text = wrapper.find('.generation-lesson-plan__review-grid').text()
    expect(text).toContain('1.1 向量')            // 小节名，不是 L2-1-1
    expect(text).toContain('教学环节')             // 模块路径被翻译
    expect(text).toContain('教学大纲')             // overall 归到教学大纲
    expect(text).toContain('AI 建议')              // 来源标注
  })

  it('影响按五组分开展示，保持不变也要显示', async () => {
    const wrapper = await mountWithReview()
    const headings = wrapper.findAll('.generation-lesson-plan__impact-heading').map(n => n.text())
    expect(headings.some(h => h.includes('待重建'))).toBe(true)
    expect(headings.some(h => h.includes('已更新'))).toBe(true)
    expect(headings.some(h => h.includes('保持不变'))).toBe(true)
    // 对象类型翻成中文，不是 section_content
    const text = wrapper.find('.generation-lesson-plan__review-grid').text()
    expect(text).toContain('正文')
    expect(text).toContain('练习')
  })
})
