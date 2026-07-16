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
  adaptation_plans: [{
    plan_id: 'plan-1', plan_kind: 'personal_adaptation_plan', write_target: 'personal_overlay', change_set_id: 'plan-1',
    hypothesis_id: 'hypothesis-1', evidence_ids: ['evidence-1'], operations: [],
    allowed_scopes: ['current'], impact_summary: {}, expected_effect: '补充个人解释',
    status, effect_evaluation: {},
  }],
  personal_course_overlay: {
    schema_version: 'personal_course_overlay_v1', overlay_id: 'overlay-1',
    active_plan_ids: status === 'applied' ? ['plan-1'] : [], operations: [],
  },
  permissions: {
    write_target: 'personal_overlay', can_modify_base_course: false,
    can_modify_other_learners: false, can_modify_course_knowledge_base: false,
  },
  summary: {},
})

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
  httpMock.post.mockReset()
})

describe('personal adaptation store', () => {
  it('loads plans and explicit personal-overlay permissions from the canonical API', async () => {
    httpMock.get.mockResolvedValue({ data: payload() })
    const store = useCourseEvolutionStore()

    await store.load('course-1')

    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/personal-adaptation')
    expect(store.pendingPlans).toHaveLength(1)
    expect(store.permissions?.can_modify_base_course).toBe(false)
    expect(store.personalCourseOverlay?.overlay_id).toBe('overlay-1')
  })

  it('accepts a plan through the personal endpoint instead of a course write endpoint', async () => {
    httpMock.get.mockResolvedValue({ data: payload() })
    httpMock.post.mockResolvedValue({ data: payload('applied') })
    const store = useCourseEvolutionStore()
    await store.load('course-1')

    await store.accept('plan-1', 'current')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/personal-adaptation/plans/plan-1/accept',
      { selected_scope: 'current' },
    )
    expect(store.appliedPlans).toHaveLength(1)
    expect(store.personalCourseOverlay?.active_plan_ids).toEqual(['plan-1'])
  })

  it('requests a reviewable replacement after an ineffective adaptation', async () => {
    httpMock.get.mockResolvedValue({ data: payload('applied') })
    httpMock.post.mockResolvedValue({ data: payload() })
    const store = useCourseEvolutionStore()
    await store.load('course-1')

    await store.adjust('plan-1')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/personal-adaptation/plans/plan-1/adjust',
    )
    expect(store.pendingPlans).toHaveLength(1)
  })
})
