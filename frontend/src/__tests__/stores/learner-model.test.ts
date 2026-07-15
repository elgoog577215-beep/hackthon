import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMock }))

import { useLearnerModelStore, type LearnerModelProjection } from '@/stores/learnerModel'

const model = (): LearnerModelProjection => ({
  schema_version: 'learner_model_v1',
  model_revision_id: 'lmr_1',
  user_id: 'u1',
  course_id: 'course-1',
  course_version_id: 'cv1',
  source_revision_vector: { events_revision: 'levr_1' },
  observed_at: '2026-07-14T00:00:00Z',
  data_sufficiency: {
    level: 'limited', formal_evidence_count: 1, total_evidence_count: 1,
    covered_objective_count: 1, reason_code: 'insufficient_for_stable_inference',
  },
  summary: {
    total_objectives: 1, started_objectives: 1, learned_objectives: 0,
    mastered_objectives: 0, needs_attention_objectives: 0,
    formal_evidence_count: 1, active_record_count: 0,
  },
  objectives: [],
  strengths: [],
  needs_attention: [],
  self_reports: [],
  evidence_catalog: [],
  model_policy: {
    deterministic: true, ai_writable: false, reading_is_mastery: false,
    legacy_profile_included: false, learning_os_included: false,
  },
})

beforeEach(() => {
  setActivePinia(createPinia())
  httpMock.get.mockReset()
})

describe('learner model store', () => {
  it('只从正式只读接口加载模型修订', async () => {
    httpMock.get.mockResolvedValue({ data: model() })
    const store = useLearnerModelStore()

    await store.load('course-1')

    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/learner-model')
    expect(store.model?.model_revision_id).toBe('lmr_1')
    expect(store.model?.model_policy.ai_writable).toBe(false)
  })

  it('较慢的旧课程响应不能覆盖较新的模型', async () => {
    let resolveFirst!: (value: unknown) => void
    let resolveSecond!: (value: unknown) => void
    httpMock.get
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))
    const store = useLearnerModelStore()

    const first = store.load('course-old')
    const second = store.load('course-new')
    resolveSecond({ data: { ...model(), course_id: 'course-new', model_revision_id: 'lmr_new' } })
    await second
    resolveFirst({ data: { ...model(), course_id: 'course-old', model_revision_id: 'lmr_old' } })
    await first

    expect(store.courseId).toBe('course-new')
    expect(store.model?.model_revision_id).toBe('lmr_new')
  })
})
