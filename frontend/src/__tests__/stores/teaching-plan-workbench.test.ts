import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({
  delete: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: httpMock, getTeacherIdentity: () => 'teacher-test' }))

import {
  useTeachingPlanWorkbenchStore,
  type TeachingPlanWorkbench,
} from '@/stores/teachingPlanWorkbench'

function workbench(overrides: Partial<TeachingPlanWorkbench> = {}): TeachingPlanWorkbench {
  return {
    course_id: 'course-1',
    enabled: true,
    available: false,
    can_initialize: true,
    read_only_reason: '当前课程可以从已发布目录建立可编辑教案基线。',
    current_plan_revision_id: '',
    course_document_revision: 'cdr-1',
    teaching_plan: {
      schema_version: 'course_teaching_plan_projection_v1',
      status: 'pending',
      revision_id: '',
      strategy: '',
      section_count: 0,
      knowledge_point_count: 0,
      teaching_module_count: 0,
      sections: [],
    },
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

describe('teaching plan workbench store', () => {
  it('clears transient review state when the active course changes', () => {
    const store = useTeachingPlanWorkbenchStore()
    store.applyWorkbench(workbench())
    store.review = {
      draft_id: 'draft-1',
      base_plan_revision_id: 'tpr-1',
      diff: { operations: [] },
      impact_report: {
        changed: [],
        needs_regeneration: [],
        stale: [],
        unchanged: [],
        blocked: [],
        blocking: false,
      },
      validation: { passed: true },
    }
    store.savingPaths = ['overall/positioning']

    store.applyWorkbench(workbench({ course_id: 'course-2' }))

    expect(store.review).toBeNull()
    expect(store.savingPaths).toEqual([])
  })

  it('explicitly initializes a missing plan against the current course revision', async () => {
    const store = useTeachingPlanWorkbenchStore()
    store.applyWorkbench(workbench())
    const initialized = workbench({
      available: true,
      can_initialize: false,
      current_plan_revision_id: 'tpr-1',
      read_only_reason: '',
    })
    httpMock.post.mockResolvedValue({ data: { workbench: initialized, receipt: { operation: 'initialize_teaching_plan_baseline' } } })

    const receipt = await store.initializeBaseline()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/teaching-plan/baseline',
      expect.objectContaining({
        base_course_document_revision: 'cdr-1',
        idempotency_key: expect.stringMatching(/^initialize_plan_/),
      }),
      expect.objectContaining({
        silentError: true,
        headers: { 'X-User-Id': 'teacher-test' },
      }),
    )
    expect(receipt).toEqual({ operation: 'initialize_teaching_plan_baseline' })
    expect(store.workbench?.available).toBe(true)
    expect(store.pendingAction).toBe('')
  })

  it('keeps the structured server error available for recovery', async () => {
    const store = useTeachingPlanWorkbenchStore()
    store.applyWorkbench(workbench())
    httpMock.post.mockRejectedValue({
      response: {
        status: 409,
        data: { detail: { code: 'course_document_base_conflict', message: '课程正文已更新，请重新载入。' } },
      },
    })

    await expect(store.initializeBaseline()).rejects.toBeTruthy()

    expect(store.errorCode).toBe('course_document_base_conflict')
    expect(store.errorMessage).toBe('课程正文已更新，请重新载入。')
    expect(store.workbench?.can_initialize).toBe(true)
    expect(store.pendingAction).toBe('')
  })

  it('sends a complete section-sized AI candidate request without writing the official plan', async () => {
    const store = useTeachingPlanWorkbenchStore()
    store.applyWorkbench(workbench({
      available: true,
      can_initialize: false,
      current_plan_revision_id: 'tpr-1',
      draft: {
        draft_id: 'draft-1',
        base_plan_revision_id: 'tpr-1',
        base_course_document_revision: 'cdr-1',
        changed_paths: [],
        operations: [],
      },
    }))
    const paths = Array.from({ length: 24 }, (_, index) => `sections/section-1/field-${index}`)
    const candidateWorkbench = workbench({
      available: true,
      can_initialize: false,
      current_plan_revision_id: 'tpr-1',
      draft: store.draft,
      ai_candidates: [{
        candidate_id: 'candidate-1',
        draft_id: 'draft-1',
        status: 'ready',
        rationale: '候选仍待教师确认',
        operations: [],
      }],
    })
    httpMock.post.mockResolvedValue({ data: { workbench: candidateWorkbench } })

    const candidate = await store.createAiCandidate(paths, '重新设计当前小节')

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/course-1/teaching-plan/drafts/draft-1/ai-candidates',
      expect.objectContaining({ paths, instruction: '重新设计当前小节' }),
      expect.objectContaining({
        silentError: true,
        headers: { 'X-User-Id': 'teacher-test' },
      }),
    )
    expect(candidate?.status).toBe('ready')
    expect(store.workbench?.current_plan_revision_id).toBe('tpr-1')
    expect(store.pendingAction).toBe('')
  })
})
