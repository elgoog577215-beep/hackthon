import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({
  delete: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: httpMock }))

import GenerationLessonPlan from '@/components/GenerationLessonPlan.vue'
import {
  useTeachingPlanWorkbenchStore,
  type TeachingPlanWorkbench,
} from '@/stores/teachingPlanWorkbench'
import type { CourseTeachingPlanProjection, Node } from '@/stores/types'

const nodes: Node[] = [{
  node_id: 'section-1',
  node_name: '一次函数斜率',
  node_level: 2,
  parent_node_id: 'chapter-1',
  node_content: '',
  learning_objective: '理解斜率表示的变化关系',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 0,
}]

const emptyPlan: CourseTeachingPlanProjection = {
  schema_version: 'course_teaching_plan_projection_v1',
  status: 'pending',
  revision_id: '',
  strategy: '',
  section_count: 0,
  knowledge_point_count: 0,
  teaching_module_count: 0,
  sections: [],
}

const editablePlan: CourseTeachingPlanProjection = {
  ...emptyPlan,
  status: 'completed',
  revision_id: 'tpr-1',
  strategy: 'deterministic_baseline',
  section_count: 1,
  teaching_module_count: 1,
  overall: {
    course_title: '一次函数',
    positioning: '从变化率理解函数',
    target_audience: '初中二年级',
    learning_objectives: ['解释斜率的意义'],
    prerequisites: ['平面直角坐标系'],
    teaching_strategy: { primary_mode: '', secondary_mode: '', rationale: '从情境进入表达。' },
    assessment_methods: ['出口题'],
    chapters: [],
    knowledge_tags: [],
  },
  sections: [{
    node_id: 'section-1',
    key_points: ['斜率'],
    reused_knowledge_names: [],
    knowledge_relations: [],
    teaching_modules: [{
      module_id: 'guided-example',
      teaching_purpose: '建立变化率直觉',
      teaching_guidance: '先比较，再归纳。',
      knowledge_names: ['斜率'],
    }],
    knowledge_structure: [],
  }],
}

function workbench(overrides: Partial<TeachingPlanWorkbench> = {}): TeachingPlanWorkbench {
  return {
    course_id: 'course-1',
    enabled: true,
    available: false,
    can_initialize: true,
    read_only_reason: '当前课程可以从已发布目录建立可编辑教案基线。',
    current_plan_revision_id: '',
    course_document_revision: 'cdr-1',
    teaching_plan: emptyPlan,
    draft: null,
    revisions: [],
    change_sets: [],
    ai_candidates: [],
    editable_fields: [],
    downstream: {},
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  for (const mock of Object.values(httpMock)) mock.mockReset()
})

describe('课程教案工作台', () => {
  it('由教师显式建立旧课程基线后直接进入可自动保存的编辑态', async () => {
    const store = useTeachingPlanWorkbenchStore()
    store.applyWorkbench(workbench())
    const initialized = workbench({
      available: true,
      can_initialize: false,
      read_only_reason: '',
      current_plan_revision_id: 'tpr-1',
      teaching_plan: editablePlan,
      revisions: [{ revision_id: 'tpr-1', revision_number: 1, created_by: 'migration' }],
      editable_fields: [{ path: 'overall/positioning', state: 'requires_impact_review', reason: '影响正式教案' }],
    })
    const editing = workbench({
      ...initialized,
      draft: {
        draft_id: 'draft-1',
        base_plan_revision_id: 'tpr-1',
        base_course_document_revision: 'cdr-1',
        changed_paths: [],
        operations: [],
      },
    })
    httpMock.post
      .mockResolvedValueOnce({ data: { workbench: initialized, receipt: { operation: 'initialize_teaching_plan_baseline' } } })
      .mockResolvedValueOnce({ data: { workbench: editing } })

    const wrapper = mount(GenerationLessonPlan, {
      props: { courseId: 'course-1', nodes, activeNodeId: 'section-1' },
    })

    expect(wrapper.text()).toContain('建立可编辑教案')
    await wrapper.get('.generation-lesson-plan__workbench-notice button').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenNthCalledWith(
      1,
      '/api/courses/course-1/teaching-plan/baseline',
      expect.objectContaining({ base_course_document_revision: 'cdr-1' }),
      { silentError: true },
    )
    expect(httpMock.post).toHaveBeenNthCalledWith(
      2,
      '/api/courses/course-1/teaching-plan/drafts',
      expect.objectContaining({ base_plan_revision_id: 'tpr-1' }),
      { silentError: true },
    )
    expect(wrapper.text()).toContain('正式修订 #1')
    expect(wrapper.text()).toContain('草稿已保存')
    expect(wrapper.find('.generation-lesson-plan__inline-editor').exists()).toBe(true)
  })

  it('切换 AI 调整范围时同步默认指令且保留教师自定义内容', async () => {
    const store = useTeachingPlanWorkbenchStore()
    store.applyWorkbench(workbench({
      available: true,
      can_initialize: false,
      current_plan_revision_id: 'tpr-1',
      teaching_plan: editablePlan,
      draft: {
        draft_id: 'draft-1',
        base_plan_revision_id: 'tpr-1',
        base_course_document_revision: 'cdr-1',
        changed_paths: [],
        operations: [],
      },
      revisions: [{ revision_id: 'tpr-1', revision_number: 1 }],
      editable_fields: [
        { path: 'overall/positioning', state: 'requires_impact_review', reason: '影响正式教案' },
        { path: 'sections/section-1/learning_objective', state: 'requires_impact_review', reason: '影响小节正文' },
      ],
    }))

    const wrapper = mount(GenerationLessonPlan, {
      props: {
        courseId: 'course-1',
        plan: editablePlan,
        nodes,
        activeNodeId: 'section-1',
      },
    })

    await wrapper.get('button[aria-label="生成 AI 建议"]').trigger('click')
    await flushPromises()
    const instruction = wrapper.get('.generation-lesson-plan__ai-request textarea')
    expect((instruction.element as HTMLTextAreaElement).value).toContain('系统优化全课定位')

    const sectionScope = wrapper.findAll('.generation-lesson-plan__scope-control button')[1]!
    await sectionScope.trigger('click')
    expect((instruction.element as HTMLTextAreaElement).value).toContain('重新设计本小节')

    await instruction.setValue('只调整课堂提问节奏')
    await wrapper.findAll('.generation-lesson-plan__scope-control button')[0]!.trigger('click')
    expect((instruction.element as HTMLTextAreaElement).value).toBe('只调整课堂提问节奏')
  })
})
