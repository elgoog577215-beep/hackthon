import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import http from '@/utils/http'
import GenerationLessonPlan from '@/components/GenerationLessonPlan.vue'
import { useTeachingPlanWorkbenchStore } from '@/stores/teachingPlanWorkbench'
import type { Node } from '@/stores/types'

// 教学环节增删的 UI 入口。后端 2.3 早就能改了，但页面上一直没有入口，
// 教师只能改环节里的文字、不能增删环节本身。这里钉住入口存在且真的发命令。
const nodes: Node[] = [{
  node_id: 'section-1',
  node_name: '1.1 向量',
  node_level: 2,
  parent_node_id: 'chapter-1',
  node_content: '',
  learning_objective: '理解向量',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 0,
}]

const plan: any = {
  schema_version: 'course_teaching_plan_projection_v1',
  status: 'completed',
  revision_id: 'r1',
  strategy: 'batched',
  section_count: 1,
  knowledge_point_count: 1,
  teaching_module_count: 1,
  sections: [{
    node_id: 'section-1',
    key_points: ['向量'],
    reused_knowledge_names: [],
    knowledge_relations: [],
    knowledge_structure: [],
    teaching_modules: [{
      module_id: 'core',
      teaching_purpose: '建立向量直觉',
      teaching_guidance: '先看几何再看代数。',
      knowledge_names: ['向量'],
    }],
  }],
}

function workbench(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 'teaching_plan_workbench_v1',
    course_id: 'course-1',
    enabled: true,
    available: true,
    read_only_reason: '',
    course_document_revision: 'doc-1',
    current_plan_revision_id: 'tpr_1',
    course_revision_vector: {},
    teaching_plan: plan,
    draft: {
      draft_id: 'tpd_1',
      base_plan_revision_id: 'tpr_1',
      base_course_document_revision: 'doc-1',
      changed_paths: [],
      operations: [],
    },
    revisions: [],
    change_sets: [],
    ai_candidates: [],
    editable_fields: [
      { path: 'sections/section-1/teaching_modules', state: 'requires_impact_review' as const, reason: '' },
    ],
    section_module_options: {
      'section-1': [
        { module_id: 'core', label: '核心讲解', required: true, selected: true, output_contract: '解释向量' },
        { module_id: 'practice', label: '随堂练习', required: false, selected: false, output_contract: '当堂检验' },
        { module_id: 'warmup', label: '情境导入', required: false, selected: true, output_contract: '引入情境' },
      ],
    },
    downstream: {},
    ...overrides,
  }
}

async function mountEditing() {
  vi.mocked(http.get).mockResolvedValue({ data: { workbench: workbench() } } as any)
  vi.mocked(http.post).mockResolvedValue({ data: { workbench: workbench() } } as any)
  vi.mocked(http.patch).mockResolvedValue({ data: { workbench: workbench() } } as any)

  const store = useTeachingPlanWorkbenchStore()
  await store.load('course-1')

  const wrapper = mount(GenerationLessonPlan, {
    props: { nodes, plan, activeNodeId: 'section-1', courseId: 'course-1' },
  })
  // editing 由 store.draft 推导，fixture 已带草稿即为编辑态；只需切到分小节视图
  const tabs = wrapper.findAll('.generation-lesson-plan__view-switch button')
  await tabs[1]!.trigger('click')
  return wrapper
}

describe('教学环节增删入口', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('编辑态下列出模板提供的候选环节，必需环节不可取消', async () => {
    const wrapper = await mountEditing()
    const composer = wrapper.find('.generation-lesson-plan__module-composer')
    expect(composer.exists()).toBe(true)

    const boxes = composer.findAll('input[type="checkbox"]')
    expect(boxes).toHaveLength(3)
    // core 必需且已选 -> 勾上且禁用
    expect((boxes[0]!.element as HTMLInputElement).checked).toBe(true)
    expect((boxes[0]!.element as HTMLInputElement).disabled).toBe(true)
    // practice 可选未选 -> 未勾、可点
    expect((boxes[1]!.element as HTMLInputElement).checked).toBe(false)
    expect((boxes[1]!.element as HTMLInputElement).disabled).toBe(false)
    expect(composer.text()).toContain('必需')
  })

  it('勾选新增环节时按模板顺序发出整组 module_id', async () => {
    const wrapper = await mountEditing()
    const boxes = wrapper.findAll('.generation-lesson-plan__module-composer input[type="checkbox"]')
    await boxes[1]!.setValue(true)   // 勾上 practice
    await new Promise(resolve => setTimeout(resolve, 0))

    const call = vi.mocked(http.patch).mock.calls.at(-1)!
    expect(call[0]).toContain('/teaching-plan/drafts/tpd_1')
    const body = call[1] as any
    expect(body.path).toBe('sections/section-1/teaching_modules')
    // 保持模板顺序 core -> practice -> warmup，不是把新增的追加到末尾
    expect(body.value).toEqual(['core', 'practice', 'warmup'])
  })

  it('取消可选环节时把它从列表里去掉', async () => {
    const wrapper = await mountEditing()
    const boxes = wrapper.findAll('.generation-lesson-plan__module-composer input[type="checkbox"]')
    await boxes[2]!.setValue(false)  // 取消 warmup（已选、非必需）
    await new Promise(resolve => setTimeout(resolve, 0))

    const body = vi.mocked(http.patch).mock.calls.at(-1)![1] as any
    expect(body.value).toEqual(['core'])
  })

  it('非编辑态（无草稿）不显示增删入口', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { workbench: workbench({ draft: null }) } } as any)
    const store = useTeachingPlanWorkbenchStore()
    await store.load('course-1')
    const wrapper = mount(GenerationLessonPlan, {
      props: { nodes, plan, activeNodeId: 'section-1', courseId: 'course-1' },
    })
    const tabs = wrapper.findAll('.generation-lesson-plan__view-switch button')
    await tabs[1]!.trigger('click')
    expect(wrapper.find('.generation-lesson-plan__module-composer').exists()).toBe(false)
  })
})

describe('目录重定向的跳转入口', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('后端返回 redirect_to_outline_edit 时给出可点的跳转按钮并带上 endpoint', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { workbench: workbench() } } as any)
    const store = useTeachingPlanWorkbenchStore()
    await store.load('course-1')

    // 模拟后端 409 + details.outline_editor
    vi.mocked(http.patch).mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: {
            code: 'redirect_to_outline_edit',
            message: '章节增删与排序请在目录编辑器中完成。',
            course_id: 'course-1',
            outline_revision_id: 'cdr_x',
            outline_editor: {
              endpoint: '/api/courses/course-1/blueprint',
              revision_field: 'current_blueprint_revision_id',
            },
          },
        },
      },
    })

    const wrapper = mount(GenerationLessonPlan, {
      props: { nodes, plan, activeNodeId: 'section-1', courseId: 'course-1' },
    })
    await store.patchDraft('course_plan/chapters', 'x').catch(() => {})
    await wrapper.vm.$nextTick()

    // store 必须留下 details，否则前端拿不到 endpoint
    expect(store.errorCode).toBe('redirect_to_outline_edit')
    expect((store.errorDetail as any).outline_editor.endpoint)
      .toBe('/api/courses/course-1/blueprint')

    const action = wrapper.find('.generation-lesson-plan__error-action')
    expect(action.exists()).toBe(true)
    await action.trigger('click')
    const emitted = wrapper.emitted('open-outline-editor')
    expect(emitted).toBeTruthy()
    expect(emitted![0]![0]).toEqual({
      endpoint: '/api/courses/course-1/blueprint',
      revisionField: 'current_blueprint_revision_id',
    })
  })

  it('普通错误不显示跳转按钮', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { workbench: workbench() } } as any)
    const store = useTeachingPlanWorkbenchStore()
    await store.load('course-1')
    vi.mocked(http.patch).mockRejectedValue({
      response: { status: 409, data: { detail: { code: 'teaching_plan_base_conflict' } } },
    })
    const wrapper = mount(GenerationLessonPlan, {
      props: { nodes, plan, activeNodeId: 'section-1', courseId: 'course-1' },
    })
    await store.patchDraft('overall/positioning', 'x').catch(() => {})
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.generation-lesson-plan__error-action').exists()).toBe(false)
  })
})
