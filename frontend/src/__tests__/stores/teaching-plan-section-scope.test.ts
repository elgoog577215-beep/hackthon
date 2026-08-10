import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import http from '@/utils/http'
import { useTeachingPlanWorkbenchStore } from '@/stores/teachingPlanWorkbench'

// 需求 5：分小节优化。前端把「当前小节」的全部可编辑路径一次性发给
// AI 候选接口——最小课程的一个小节已有 17 条，模块或知识点多几个更高。
// 这里钉住的是：作用域筛选正确（不混进别的小节、不混进总体），
// 并且请求体真的把整节路径都带上了。
function workbenchPayload() {
  const sectionOne = [
    'learning_objective', 'key_points', 'planned_minutes', 'homework',
    'in_class_checks', 'key_difficulties', 'resource_refs',
    'student_activities', 'teacher_activities', 'teaching_notes',
  ].map(field => ({
    path: `sections/section-1/${field}`,
    state: 'requires_impact_review' as const,
    reason: '',
  }))
  const modules = [
    'teaching_purpose', 'teaching_guidance', 'planned_minutes',
    'teacher_activity', 'student_activity',
  ].map(field => ({
    path: `sections/section-1/teaching_modules/core/${field}`,
    state: 'requires_impact_review' as const,
    reason: '',
  }))
  const knowledge = ['statement', 'capability'].map(field => ({
    path: `sections/section-1/knowledge/斜率/${field}`,
    state: 'requires_impact_review' as const,
    reason: '',
  }))
  return {
    schema_version: 'teaching_plan_workbench_v1',
    course_id: 'course-1',
    enabled: true,
    available: true,
    read_only_reason: '',
    course_document_revision: 'doc-1',
    current_plan_revision_id: 'tpr_1',
    course_revision_vector: {},
    teaching_plan: {},
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
      { path: 'overall/positioning', state: 'editable' as const, reason: '' },
      { path: 'overall/learning_objectives', state: 'editable' as const, reason: '' },
      ...sectionOne,
      ...modules,
      ...knowledge,
      // 只读字段与别的小节：都不该进入本节的优化范围。
      { path: 'sections/section-1/node_id', state: 'readonly' as const, reason: '由课程维护' },
      { path: 'sections/section-2/learning_objective', state: 'requires_impact_review' as const, reason: '' },
    ],
    downstream: {},
  }
}

describe('分小节优化的 AI 候选作用域', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('把当前小节的全部可编辑路径发出，且不混入其他小节或只读字段', async () => {
    const payload = workbenchPayload()
    vi.mocked(http.get).mockResolvedValue({ data: { workbench: payload } } as any)
    vi.mocked(http.post).mockResolvedValue({ data: { workbench: payload } } as any)

    const store = useTeachingPlanWorkbenchStore()
    await store.load('course-1')

    const prefix = 'sections/section-1/'
    const sectionPaths = store.workbench!.editable_fields
      .filter(field => field.state !== 'readonly' && field.path.startsWith(prefix))
      .map(field => field.path)

    // 这正是旧的 12 条上限会 422 掉的规模。
    expect(sectionPaths.length).toBeGreaterThan(12)
    expect(sectionPaths).not.toContain('sections/section-1/node_id')
    expect(sectionPaths.some(path => path.startsWith('sections/section-2/'))).toBe(false)
    expect(sectionPaths.some(path => path.startsWith('overall/'))).toBe(false)

    await store.createAiCandidate(sectionPaths, '把这一节讲得更具体')

    const [url, body] = vi.mocked(http.post).mock.calls.at(-1)!
    expect(url).toContain('/teaching-plan/drafts/tpd_1/ai-candidates')
    expect((body as any).paths).toEqual(sectionPaths)
    expect((body as any).instruction).toBe('把这一节讲得更具体')
    expect((body as any).idempotency_key).toBeTruthy()
  })

  it('总体范围只发总体字段，不把小节字段一起重生成', async () => {
    const payload = workbenchPayload()
    vi.mocked(http.get).mockResolvedValue({ data: { workbench: payload } } as any)
    vi.mocked(http.post).mockResolvedValue({ data: { workbench: payload } } as any)

    const store = useTeachingPlanWorkbenchStore()
    await store.load('course-1')

    const overallPaths = store.workbench!.editable_fields
      .filter(field => field.state !== 'readonly' && field.path.startsWith('overall/'))
      .map(field => field.path)

    await store.createAiCandidate(overallPaths, '让全课定位更清楚')

    const [, body] = vi.mocked(http.post).mock.calls.at(-1)!
    expect((body as any).paths).toEqual(overallPaths)
    expect((body as any).paths.some((path: string) => path.startsWith('sections/'))).toBe(false)
  })
})
