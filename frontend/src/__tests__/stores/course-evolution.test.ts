import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMock }))

import { useCourseEvolutionStore } from '@/stores/courseEvolution'

const payload = (status: 'pending' | 'applied' = 'pending') => ({
  evidence_items: [{
    evidence_id: 'evidence-1', source_type: 'practice_attempt', evidence_kind: 'formal_failure',
    summary: '正式练习暴露前置缺口', strength: 0.9,
    anchor: { section_id: 'section-1', block_id: 'block-1', resolution_status: 'unresolved' },
  }],
  hypotheses: [],
  course_evolution_plans: [{
    plan_id: 'plan-1', plan_kind: 'course_evolution_plan', write_target: 'course_document', change_set_id: 'plan-1',
    hypothesis_id: 'hypothesis-1', evidence_ids: ['evidence-1'], operations: [],
    allowed_scopes: ['current'], impact_summary: {}, expected_effect: '补充课程解释',
    status, effect_evaluation: {},
  }],
  permissions: {
    write_target: 'course_document', can_modify_current_course: true, can_modify_other_courses: false,
    can_modify_course_knowledge_base: false,
  },
  summary: {},
})

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

describe('course evolution store', () => {
  it('loads plans and explicit current-course permissions from the canonical API', async () => {
    httpMock.get.mockResolvedValue({ data: payload() })
    const store = useCourseEvolutionStore()

    await store.load('course-1')

    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/evolution')
    expect(store.pendingPlans).toHaveLength(1)
    expect(store.permissions?.can_modify_current_course).toBe(true)
    expect(store.permissions?.can_modify_other_courses).toBe(false)
  })

  it('accepts a reviewed plan through the canonical course-evolution endpoint', async () => {
    httpMock.get.mockResolvedValue({ data: payload() })
    httpMock.post.mockResolvedValue({ data: payload('applied') })
    const store = useCourseEvolutionStore()
    await store.load('course-1')

    await store.accept('plan-1', 'current')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/evolution/change-sets/plan-1/accept',
      { selected_scope: 'current' },
    )
    expect(store.appliedPlans).toHaveLength(1)
    expect(store.plans[0]?.write_target).toBe('course_document')
  })

  it('submits only the operation ids included in a multi-node review', async () => {
    httpMock.get.mockResolvedValue({ data: payload() })
    httpMock.post.mockResolvedValue({ data: payload('applied') })
    const store = useCourseEvolutionStore()
    await store.load('course-1')

    await store.accept('plan-1', 'current', ['operation-1', 'operation-3'])

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/evolution/change-sets/plan-1/accept',
      {
        selected_scope: 'current',
        selected_operation_ids: ['operation-1', 'operation-3'],
      },
    )
  })

  it('requests a reviewable replacement after an ineffective adaptation', async () => {
    httpMock.get.mockResolvedValue({ data: payload('applied') })
    httpMock.post.mockResolvedValue({ data: payload() })
    const store = useCourseEvolutionStore()
    await store.load('course-1')

    await store.adjust('plan-1')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/evolution/change-sets/plan-1/adjust',
    )
    expect(store.pendingPlans).toHaveLength(1)
  })

  it('generates a section plan through the same canonical evolution store', async () => {
    httpMock.post.mockResolvedValue({ data: payload() })
    const store = useCourseEvolutionStore()
    store.courseId = 'course-1'

    await store.createSectionPlan('section-1', '强化理论推导与实战讲解')

    expect(httpMock.post).toHaveBeenCalledTimes(1)
    expect(httpMock.post.mock.calls[0]?.[0]).toBe(
      '/api/courses/course-1/evolution/sections/section-1/plans',
    )
    expect(httpMock.post.mock.calls[0]?.[1]).toMatchObject({
      instruction: '强化理论推导与实战讲解',
      scope_selection: 'current_section',
    })
    expect(store.pendingPlans).toHaveLength(1)
  })

  it('sends the user-selected whole-course boundary beside the natural-language request', async () => {
    httpMock.post.mockResolvedValue({ data: payload() })
    const store = useCourseEvolutionStore()
    store.courseId = 'course-1'

    await store.createSectionPlan(
      'section-1',
      '以后所有例子都讲得详细一点',
      'whole_course',
      'example',
    )

    expect(httpMock.post.mock.calls[0]?.[1]).toMatchObject({
      instruction: '以后所有例子都讲得详细一点',
      scope_selection: 'whole_course',
      anchor_role: 'example',
    })
  })

  it('turns an evidence suggestion into candidates through the same plan endpoint', async () => {
    httpMock.post.mockResolvedValue({ data: payload() })
    const store = useCourseEvolutionStore()
    store.courseId = 'course-1'

    await store.generateSuggested('plan-1')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/evolution/change-sets/plan-1/generate',
    )
  })
})
