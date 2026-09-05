import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: httpMock }))

import {
  unresolvedMistakeAttempts,
  useCourseWorkspaceStore,
  type PracticeAttempt,
} from '@/stores/courseWorkspace'

const runtimeResponse = {
  schema_version: 'learning_runtime_v1', course_id: 'c1', user_id: 'default_user',
  context: { course_id: 'c1', course_version_id: 'cv1', node_id: 'n1' },
  revision_vector: {}, runtime_revision_id: 'lrr1', snapshot: { current: null, resolution: null },
  progress: { schema_version: 'learning_progress_v1', course_id: 'c1', course_version_id: 'cv1', user_id: 'default_user', summary: {}, nodes: [] },
  records: { total: 0, by_type: {}, by_status: {}, open_issue_ids: [] },
  practice: { total: 0, active: [], pending_review_count: 0, needs_review_count: 0 },
  diagnostic: { phase: 'practice' }, active_task: null,
  continuation: { primary_action: {}, chapter_result: {}, chapter: {}, progress: {}, risks: [], secondary_notices: [], version_conflicts: [] },
}

const question = {
  asset_id: 'q1',
  revision_id: 'qr1',
  node_id: 'n1',
  prompt: '解释向量。',
  practice_level: 'mastery_check',
  input_contract: { mode: 'rich_text' },
}

const attempt = (overrides: Record<string, any> = {}): PracticeAttempt => ({
  attempt_id: 'pa1',
  task_revision_id: 'qr1',
  question_revision_id: 'qr1',
  revision: 1,
  status: 'in_progress',
  attempt_number: 1,
  answer_payload: {},
  revealed_hint_levels: [],
  solution_revealed: false,
  ai_support_level: 0,
  active_seconds: 0,
  ...overrides,
})

describe('mistake book projection', () => {
  it('只保留每条针对再练链上最新且仍未解决的作答', () => {
    const original = attempt({
      attempt_id: 'pa-original',
      status: 'graded',
      result: { passed: false, mastery_eligible: false },
    })
    const failedRetry = attempt({
      attempt_id: 'pa-retry-failed',
      status: 'graded',
      origin_attempt_id: 'pa-original',
      practice_intent: 'targeted_retry',
      result: { passed: false, mastery_eligible: false },
    })

    expect(unresolvedMistakeAttempts([original, failedRetry]).map(item => item.attempt_id))
      .toEqual(['pa-retry-failed'])

    const passedRetry = attempt({
      attempt_id: 'pa-retry-passed',
      status: 'graded',
      origin_attempt_id: 'pa-retry-failed',
      practice_intent: 'targeted_retry',
      result: { passed: true, mastery_eligible: true },
    })

    expect(unresolvedMistakeAttempts([original, failedRetry, passedRetry])).toEqual([])
  })
})

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  sessionStorage.clear()
  httpMock.get.mockReset()
  httpMock.post.mockReset()
  httpMock.patch.mockReset()
  httpMock.get.mockResolvedValue({ data: runtimeResponse })
})

describe('formal practice attempt store', () => {
  it('加载练习后恢复服务端活动 Attempt', async () => {
    httpMock.get
      .mockResolvedValueOnce({ data: {
        course_id: 'c1', course_version_id: 'cv1', scope: 'node', questions: [question], active_attempts: [attempt({ node_id: 'n1', course_version_id: 'cv1' })], summary: {},
      } })
      .mockResolvedValueOnce({ data: { phase: 'practice', case: null, session: null, current_task: null } })
      .mockResolvedValue({ data: runtimeResponse })
    const store = useCourseWorkspaceStore()

    await store.loadPractice('c1', 'n1')

    expect(store.currentAttempt?.attempt_id).toBe('pa1')
    expect(store.practiceSaveState).toBe('saved')
  })

  it('恢复活动 Attempt 时同步恢复已经查看的提示正文', async () => {
    httpMock.get
      .mockResolvedValueOnce({ data: {
        course_id: 'c1',
        course_version_id: 'cv1',
        scope: 'node',
        questions: [question],
        active_attempts: [attempt({
          node_id: 'n1',
          course_version_id: 'cv1',
          revealed_hint_levels: [1],
          revealed_hints: [
            { level: 1, kind: 'orientation', content: '先区分大小与方向。' },
          ],
        })],
        summary: {},
      } })
      .mockResolvedValueOnce({ data: { phase: 'practice', case: null, session: null, current_task: null } })
      .mockResolvedValue({ data: runtimeResponse })
    const store = useCourseWorkspaceStore()

    await store.loadPractice('c1', 'n1')

    expect(store.revealedHints).toEqual([
      { level: 1, kind: 'orientation', content: '先区分大小与方向。' },
    ])
  })

  it('加载新题修订时清除仍指向旧题的活动 Attempt', async () => {
    httpMock.get
      .mockResolvedValueOnce({ data: {
        course_id: 'c1',
        course_version_id: 'cv2',
        scope: 'node',
        questions: [question],
        active_attempts: [],
        summary: {},
      } })
      .mockResolvedValueOnce({ data: { phase: 'practice', case: null, session: null, current_task: null } })
      .mockResolvedValue({ data: runtimeResponse })
    const store = useCourseWorkspaceStore()
    store.currentAttempt = attempt({
      task_revision_id: 'qr-retired',
      question_revision_id: 'qr-retired',
      revealed_hint_levels: [1, 2, 3],
    }) as any
    store.revealedHints = [
      { level: 1, content: '旧题提示' },
    ]

    await store.loadPractice('c1', 'n1')

    expect(store.currentAttempt).toBeNull()
    expect(store.revealedHints).toEqual([])
  })

  it('草稿先写本地，再用期望修订同步服务端', async () => {
    httpMock.patch.mockResolvedValue({ data: { attempt: attempt({ revision: 2, answer_payload: { text: '大小和方向' } }) } })
    const store = useCourseWorkspaceStore()
    store.currentAttempt = attempt() as any
    store.currentDraft = { text: '大小和方向' }
    store.practiceStartedAt = Date.now()

    await store.savePracticeDraft('c1')

    expect(httpMock.patch).toHaveBeenCalledWith('/api/courses/c1/practice/attempts/pa1/draft', expect.objectContaining({
      expected_revision: 1,
      answer_payload: { text: '大小和方向' },
    }))
    expect(store.currentAttempt?.revision).toBe(2)
    expect(store.practiceSaveState).toBe('saved')
    expect(localStorage.getItem('practice_attempt_draft_v1:c1:pa1')).toContain('大小和方向')
  })

  it('冲突时保留本地草稿并切换到冲突状态', async () => {
    httpMock.patch.mockRejectedValue({ response: { status: 409, data: { detail: { current: attempt({ revision: 3 }) } } } })
    const store = useCourseWorkspaceStore()
    store.currentAttempt = attempt() as any
    store.currentDraft = { text: '本地版本' }

    await expect(store.savePracticeDraft('c1')).rejects.toBeTruthy()

    expect(store.practiceSaveState).toBe('conflict')
    expect(store.currentAttempt?.revision).toBe(3)
    expect(localStorage.getItem('practice_attempt_draft_v1:c1:pa1')).toContain('本地版本')
  })

  it('提交使用当前 Attempt 并清理已同步本地草稿', async () => {
    localStorage.setItem('practice_attempt_draft_v1:c1:pa1', JSON.stringify({ answer_payload: { text: '答案' } }))
    httpMock.post.mockResolvedValue({ data: {
      status: 'graded',
      attempt: attempt({ revision: 2, status: 'graded' }),
      result: { status: 'graded', score: 100, passed: true, evidence_strength: 'independent' },
    } })
    const store = useCourseWorkspaceStore()
    store.currentAttempt = attempt() as any
    store.currentDraft = { text: '答案' }
    store.practiceStartedAt = Date.now()

    await store.submitCurrentPractice('c1')

    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/c1/practice/attempts/pa1/submit', expect.objectContaining({
      expected_revision: 1,
      answer_payload: { text: '答案' },
    }))
    expect(store.practiceResult?.passed).toBe(true)
    expect(localStorage.getItem('practice_attempt_draft_v1:c1:pa1')).toBeNull()
  })

  it('提交后沿同一工作区切换到诊断任务', async () => {
    const diagnosticTask = {
      asset_id: 'diagnostic-1',
      revision_id: 'diagnostic-1',
      task_revision_id: 'diagnostic-1',
      task_purpose: 'diagnostic_probe',
      prompt: '辨别当前卡点',
    }
    httpMock.post.mockResolvedValue({ data: {
      status: 'graded',
      attempt: attempt({ revision: 2, status: 'graded', result: { passed: false } }),
      result: { status: 'graded', passed: false },
      workflow: {
        phase: 'diagnostic',
        case: { diagnostic_case_id: 'dc1' },
        session: null,
        current_task: diagnosticTask,
      },
    } })
    const store = useCourseWorkspaceStore()
    store.practice = { course_id: 'c1', scope: 'node', questions: [question], active_attempts: [], summary: {} } as any
    store.currentAttempt = attempt() as any
    store.currentDraft = { text: '错误答案' }

    await store.submitCurrentPractice('c1')

    expect(store.diagnosticWorkflow?.phase).toBe('diagnostic')
    expect(store.currentPracticeQuestion?.task_revision_id).toBe('diagnostic-1')
  })

  it('提交超时后沿用同一个请求 ID', async () => {
    httpMock.post
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce({ data: {
        status: 'graded',
        attempt: attempt({ revision: 2, status: 'graded' }),
        result: { status: 'graded', passed: true },
      } })
    const store = useCourseWorkspaceStore()
    store.currentAttempt = attempt() as any
    store.currentDraft = { text: '答案' }

    await expect(store.submitCurrentPractice('c1')).rejects.toThrow('timeout')
    const firstRequest = httpMock.post.mock.calls[0]?.[1]?.request_id
    await store.submitCurrentPractice('c1')
    const secondRequest = httpMock.post.mock.calls[1]?.[1]?.request_id

    expect(firstRequest).toBeTruthy()
    expect(secondRequest).toBe(firstRequest)
  })

  it('自动保存进行中时拒绝并行提交', async () => {
    const store = useCourseWorkspaceStore()
    store.currentAttempt = attempt() as any
    store.currentDraft = { text: '答案' }
    store.practiceSaveState = 'saving'

    await expect(store.submitCurrentPractice('c1')).rejects.toThrow('practice_draft_is_saving')
    expect(httpMock.post).not.toHaveBeenCalled()
  })

  it('针对未通过记录优先选择同易错点的另一道版本化练习并保留来源', async () => {
    const sourceQuestion = {
      ...question,
      mistake_point_ids: ['mistake-1'],
      skill_unit_ids: ['skill-1'],
    }
    const targetedQuestion = {
      ...question,
      asset_id: 'q2',
      revision_id: 'qr2',
      task_revision_id: 'qr2',
      prompt: '换一种情境解释向量。',
      mistake_point_ids: ['mistake-1'],
      skill_unit_ids: ['skill-1'],
    }
    const unrelatedQuestion = {
      ...question,
      asset_id: 'q3',
      revision_id: 'qr3',
      task_revision_id: 'qr3',
      node_id: 'n2',
      mistake_point_ids: ['mistake-2'],
      skill_unit_ids: ['skill-2'],
    }
    const failedAttempt = attempt({
      status: 'graded',
      result: { passed: false },
      mistake_point_ids: ['mistake-1'],
      skill_unit_ids: ['skill-1'],
    })
    httpMock.post.mockResolvedValueOnce({
      data: {
        status: 'created',
        attempt: attempt({
          attempt_id: 'pa2',
          task_revision_id: 'qr2',
          question_revision_id: 'qr2',
          origin_attempt_id: 'pa1',
          practice_intent: 'targeted_retry',
        }),
      },
    })
    const store = useCourseWorkspaceStore()
    store.practice = {
      course_id: 'c1',
      course_version_id: 'cv1',
      scope: 'node',
      questions: [sourceQuestion, targetedQuestion, unrelatedQuestion],
      active_attempts: [],
      summary: {},
    } as any

    const result = await store.startTargetedRetry('c1', failedAttempt as any)

    expect(result?.task_revision_id).toBe('qr2')
    expect(store.currentQuestionIndex).toBe(1)
    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/c1/practice/attempts', expect.objectContaining({
      task_revision_id: 'qr2',
      resume: false,
      origin_attempt_id: 'pa1',
      practice_intent: 'targeted_retry',
    }))
  })

  it('针对再练优先使用本次答案诊断，而不是沿用题目上全部候选标签', async () => {
    const sourceQuestion = {
      ...question,
      mistake_point_ids: ['mistake-old'],
      skill_unit_ids: ['skill-old'],
    }
    const oldSignalQuestion = {
      ...question,
      asset_id: 'q-old',
      revision_id: 'qr-old',
      task_revision_id: 'qr-old',
      mistake_point_ids: ['mistake-old'],
      skill_unit_ids: ['skill-old'],
    }
    const diagnosedQuestion = {
      ...question,
      asset_id: 'q-diagnosed',
      revision_id: 'qr-diagnosed',
      task_revision_id: 'qr-diagnosed',
      mistake_point_ids: ['mistake-real'],
      skill_unit_ids: ['skill-real'],
    }
    const failedAttempt = attempt({
      status: 'graded',
      result: {
        passed: false,
        answer_diagnosis: {
          status: 'completed',
          diagnosis: {
            knowledge_ids: [],
            skill_ids: ['skill-real'],
            misconception_ids: ['mistake-real'],
          },
        },
      },
    })
    httpMock.post.mockResolvedValueOnce({
      data: {
        status: 'created',
        attempt: attempt({
          task_revision_id: 'qr-diagnosed',
          question_revision_id: 'qr-diagnosed',
        }),
      },
    })
    const store = useCourseWorkspaceStore()
    store.practice = {
      course_id: 'c1',
      scope: 'node',
      questions: [sourceQuestion, oldSignalQuestion, diagnosedQuestion],
      active_attempts: [],
      summary: {},
    } as any

    await store.startTargetedRetry('c1', failedAttempt as any)

    expect(store.currentQuestionIndex).toBe(2)
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/c1/practice/attempts',
      expect.objectContaining({ task_revision_id: 'qr-diagnosed' }),
    )
  })

  it('从错题本首次发起针对再练时先加载错题所在节点的正式题目', async () => {
    const failedAttempt = attempt({
      node_id: 'n1',
      status: 'graded',
      result: { passed: false, mastery_eligible: false },
    })
    httpMock.get
      .mockResolvedValueOnce({
        data: {
          course_id: 'c1',
          course_version_id: 'cv1',
          scope: 'node',
          questions: [question],
          active_attempts: [],
          summary: {},
        },
      })
      .mockResolvedValueOnce({
        data: { phase: 'practice', case: null, session: null, current_task: null },
      })
      .mockResolvedValue({ data: runtimeResponse })
    httpMock.post.mockResolvedValueOnce({
      data: {
        status: 'created',
        attempt: attempt({
          attempt_id: 'pa-retry',
          status: 'in_progress',
          origin_attempt_id: 'pa1',
          practice_intent: 'targeted_retry',
        }),
      },
    })
    const store = useCourseWorkspaceStore()

    const result = await store.startTargetedRetry('c1', failedAttempt)

    expect(httpMock.get).toHaveBeenNthCalledWith(1, '/api/courses/c1/practice', {
      params: { scope: 'node', node_id: 'n1' },
    })
    expect(result?.origin_attempt_id).toBe('pa1')
    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/c1/practice/attempts',
      expect.objectContaining({
        task_revision_id: 'qr1',
        origin_attempt_id: 'pa1',
        practice_intent: 'targeted_retry',
      }),
    )
  })

  it('查看完整解析后同步 Attempt 证据状态', async () => {
    httpMock.post.mockResolvedValue({ data: {
      attempt: attempt({ revision: 3, status: 'graded', solution_revealed: true }),
      solution: { guidance: '逐项检查', criteria: ['条件完整'] },
    } })
    const store = useCourseWorkspaceStore()
    store.currentAttempt = attempt({ revision: 2, status: 'graded' }) as any

    await store.revealPracticeSolution('c1')

    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/c1/practice/attempts/pa1/solution', { expected_revision: 2 })
    expect(store.currentAttempt?.solution_revealed).toBe(true)
    expect(store.revealedSolution?.criteria).toEqual(['条件完整'])
    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/c1/learning-runtime', { params: undefined })
  })

  it('恢复已揭示解析的 Attempt 时保留结构化答案', async () => {
    httpMock.post.mockResolvedValueOnce({ data: {
      attempt: attempt({ revision: 4, status: 'graded', solution_revealed: true }),
      solution: {
        schema_version: 'solution_spec_v1',
        steps: ['先定位首次失衡节点'],
        final_answer: { preorder: [30, 20, 10, 25, 40, 50] },
        checks: ['中序严格递增'],
      },
    } })
    const store = useCourseWorkspaceStore()

    await store.startPracticeAttempt('c1', 'qr1')

    expect(store.revealedSolution?.steps).toEqual(['先定位首次失衡节点'])
    expect(store.revealedSolution?.final_answer.preorder).toEqual([30, 20, 10, 25, 40, 50])
  })

  it('连续性动作精确恢复第二道题的活动 Attempt', async () => {
    const secondQuestion = { ...question, asset_id: 'q2', revision_id: 'qr2', task_revision_id: 'qr2', prompt: '解释矩阵。' }
    const secondAttempt = attempt({
      attempt_id: 'pa2', task_revision_id: 'qr2', question_revision_id: 'qr2', node_id: 'n1', course_version_id: 'cv1',
      answer_payload: { text: '未提交草稿' },
    })
    httpMock.get
      .mockResolvedValueOnce({ data: {
        course_id: 'c1', course_version_id: 'cv1', scope: 'node', questions: [question, secondQuestion], active_attempts: [secondAttempt], summary: {},
      } })
      .mockResolvedValueOnce({ data: { phase: 'practice', case: null, session: null, current_task: null } })
      .mockResolvedValue({ data: runtimeResponse })
    const store = useCourseWorkspaceStore()
    store.prepareLearningAction({
      action_id: 'a2', action_type: 'resume_practice_attempt', scope: 'practice_attempt', target_id: 'pa2',
      target_revision_id: '', node_id: 'n1', reason_code: 'unfinished_practice_attempt', evidence_refs: ['pa2'],
      blocking: false, requires_confirmation: false, availability: 'available',
      task_ref: {
        kind: 'practice', object_id: 'pa2', task_revision_id: 'qr2', status: 'in_progress',
        context: { course_id: 'c1', course_version_id: 'cv1', node_id: 'n1' }, return_node_id: 'n1',
      },
    })

    await store.loadPractice('c1', 'n1')

    expect(store.currentQuestionIndex).toBe(1)
    expect(store.currentAttempt?.attempt_id).toBe('pa2')
    expect(store.currentDraft.text).toBe('未提交草稿')
    expect(httpMock.post).not.toHaveBeenCalled()
  })

  it('掌握检查动作只定位指定题目，不提前创建 Attempt', async () => {
    const conceptQuestion = { ...question, practice_level: 'concept_check' }
    const masteryQuestion = {
      ...question,
      asset_id: 'q-mastery',
      revision_id: 'qr-mastery',
      task_revision_id: 'qr-mastery',
      practice_level: 'mastery_check',
      prompt: '完成掌握检查。',
    }
    httpMock.get
      .mockResolvedValueOnce({ data: {
        course_id: 'c1', course_version_id: 'cv1', scope: 'node',
        questions: [conceptQuestion, masteryQuestion], active_attempts: [], summary: {},
      } })
      .mockResolvedValueOnce({ data: { phase: 'practice', case: null, session: null, current_task: null } })
      .mockResolvedValue({ data: runtimeResponse })
    const store = useCourseWorkspaceStore()
    store.prepareLearningAction({
      action_id: 'mastery-a1', action_type: 'start_mastery_check', scope: 'learning_objective',
      target_id: 'lor-n1', target_revision_id: 'lor-n1', node_id: 'n1',
      reason_code: 'mastery_evidence_insufficient', evidence_refs: [], blocking: false,
      requires_confirmation: false, availability: 'available',
      task_ref: {
        kind: 'practice', object_id: '', task_revision_id: 'qr-mastery', status: 'active',
        context: { course_id: 'c1', course_version_id: 'cv1', node_id: 'n1', objective_revision_id: 'lor-n1' },
        return_node_id: 'n1',
      },
    })

    await store.loadPractice('c1', 'n1')

    expect(store.currentQuestionIndex).toBe(1)
    expect(store.currentPracticeQuestion?.task_revision_id).toBe('qr-mastery')
    expect(store.currentAttempt).toBeNull()
    expect(store.taskResumeError).toBe('')
    expect(httpMock.post).not.toHaveBeenCalled()
  })

  it('课程生长插入的针对性练习按后端题目修订精确定位', async () => {
    const alternateQuestion = {
      ...question,
      asset_id: 'q-targeted',
      revision_id: 'qr-targeted',
      task_revision_id: 'qr-targeted',
      prompt: '解释复合顺序。',
    }
    httpMock.get
      .mockResolvedValueOnce({ data: {
        course_id: 'c1', course_version_id: 'cv1', scope: 'node',
        questions: [question, alternateQuestion], active_attempts: [], summary: {},
      } })
      .mockResolvedValueOnce({ data: { phase: 'practice', case: null, session: null, current_task: null } })
      .mockResolvedValue({ data: runtimeResponse })
    const store = useCourseWorkspaceStore()
    store.preparePracticeTask('c1', 'n1', 'qr-targeted')

    await store.loadPractice('c1', 'n1')

    expect(store.currentQuestionIndex).toBe(1)
    expect(store.currentPracticeQuestion?.task_revision_id).toBe('qr-targeted')
    expect(store.currentAttempt).toBeNull()
    expect(store.taskResumeError).toBe('')
    expect(httpMock.get).toHaveBeenNthCalledWith(
      1,
      '/api/courses/c1/practice',
      {
        params: {
          scope: 'node',
          node_id: 'n1',
          task_revision_id: 'qr-targeted',
        },
      },
    )
  })

  it('目标 Attempt 与题目修订不一致时不打开其他活动题目', async () => {
    const otherAttempt = attempt({ attempt_id: 'pa-other', task_revision_id: 'qr1', question_revision_id: 'qr1' })
    httpMock.get
      .mockResolvedValueOnce({ data: {
        course_id: 'c1', course_version_id: 'cv1', scope: 'node', questions: [question], active_attempts: [otherAttempt], summary: {},
      } })
      .mockResolvedValueOnce({ data: { phase: 'practice', case: null, session: null, current_task: null } })
      .mockResolvedValue({ data: runtimeResponse })
    const store = useCourseWorkspaceStore()
    store.prepareLearningAction({
      action_id: 'stale-a1', action_type: 'resume_practice_attempt', scope: 'practice_attempt',
      target_id: 'pa-stale', target_revision_id: '', node_id: 'n1', reason_code: 'unfinished_practice_attempt',
      evidence_refs: ['pa-stale'], blocking: false, requires_confirmation: false, availability: 'available',
      task_ref: {
        kind: 'practice', object_id: 'pa-stale', task_revision_id: 'qr-stale', status: 'in_progress',
        context: { course_id: 'c1', course_version_id: 'cv1', node_id: 'n1' }, return_node_id: 'n1',
      },
    })

    await store.loadPractice('c1', 'n1')

    expect(store.currentAttempt).toBeNull()
    expect(store.taskResumeError).toBe('target_not_active')
    expect(store.currentQuestionIndex).toBe(0)
  })

  it('连续性动作按任务修订精确恢复诊断链当前阶段', async () => {
    const diagnosticTask = {
      asset_id: 'remediation-1', revision_id: 'remediation-r1', task_revision_id: 'remediation-r1',
      task_purpose: 'remediation_guided', prompt: '完成局部补救', practice_level: 'remediation_guided',
      input_contract: { mode: 'rich_text' },
    }
    httpMock.get
      .mockResolvedValueOnce({ data: {
        course_id: 'c1', course_version_id: 'cv1', scope: 'node', questions: [question], active_attempts: [], summary: {},
      } })
      .mockResolvedValueOnce({ data: {
        phase: 'remediation', case: { diagnostic_case_id: 'dc1' },
        session: { unit: { remediation_objective: '修复向量方向判断', micro_explanation: '先区分方向与模长' } },
        current_task: diagnosticTask,
      } })
      .mockResolvedValue({ data: runtimeResponse })
    const store = useCourseWorkspaceStore()
    store.prepareLearningAction({
      action_id: 'remediation-a1', action_type: 'resume_remediation', scope: 'diagnostic_session',
      target_id: 'dc1', target_revision_id: '', node_id: 'n1', reason_code: 'active_remediation',
      evidence_refs: ['dc1'], blocking: true, requires_confirmation: false, availability: 'available',
      task_ref: {
        kind: 'remediation', object_id: 'dc1', task_revision_id: 'remediation-r1', status: 'active',
        context: { course_id: 'c1', course_version_id: 'cv1', node_id: 'n1' }, return_node_id: 'n1',
      },
    })

    await store.loadPractice('c1', 'n1')

    expect(store.diagnosticWorkflow?.phase).toBe('remediation')
    expect(store.currentPracticeQuestion?.task_revision_id).toBe('remediation-r1')
    expect(store.taskResumeError).toBe('')
    expect(store.requestedTaskRef).toBeNull()
  })

  it('手动换题会保留旧记录并切换到服务端选择的冻结题目', async () => {
    const alternateQuestion = {
      ...question,
      asset_id: 'q2',
      revision_id: 'qr2',
      task_revision_id: 'qr2',
      prompt: '同目标的另一道题。',
    }
    httpMock.post
      .mockResolvedValueOnce({
        data: { status: 'abandoned', attempt: attempt({ status: 'abandoned', revision: 2 }) },
      })
      .mockResolvedValueOnce({
        data: {
          question: alternateQuestion,
          has_alternative: true,
          selection_policy: 'frozen_course_question',
        },
      })
    const store = useCourseWorkspaceStore()
    store.practice = {
      course_id: 'c1',
      course_version_id: 'cv1',
      scope: 'node',
      questions: [question, alternateQuestion],
      active_attempts: [],
      summary: {},
    } as any
    store.currentAttempt = attempt() as any
    store.currentDraft = { text: '未提交草稿' }

    const refreshed = await store.refreshPracticeQuestion('c1', 'n1', 'node')

    expect(httpMock.post).toHaveBeenNthCalledWith(
      1,
      '/api/courses/c1/practice/attempts/pa1/abandon',
      { expected_revision: 1 },
    )
    expect(httpMock.post).toHaveBeenNthCalledWith(
      2,
      '/api/courses/c1/practice/refresh',
      {
        current_task_revision_id: 'qr1',
        node_id: 'n1',
        scope: 'node',
      },
    )
    expect(refreshed?.task_revision_id).toBe('qr2')
    expect(store.currentQuestionIndex).toBe(1)
    expect(store.currentAttempt).toBeNull()
    expect(store.currentDraft).toEqual({})
  })

  it('换到批次外题目时替换当前位置并保持三题上限', async () => {
    const second = {
      ...question,
      asset_id: 'q2',
      revision_id: 'qr2',
      task_revision_id: 'qr2',
      prompt: '第二题。',
    }
    const third = {
      ...question,
      asset_id: 'q3',
      revision_id: 'qr3',
      task_revision_id: 'qr3',
      prompt: '第三题。',
    }
    const replacement = {
      ...question,
      asset_id: 'q4',
      revision_id: 'qr4',
      task_revision_id: 'qr4',
      prompt: '替换题。',
    }
    httpMock.post.mockResolvedValueOnce({
      data: {
        question: replacement,
        has_alternative: true,
        selection_policy: 'frozen_course_question',
      },
    })
    const store = useCourseWorkspaceStore()
    store.practice = {
      course_id: 'c1',
      course_version_id: 'cv1',
      scope: 'node',
      batch_size: 3,
      questions: [question, second, third],
      active_attempts: [],
      summary: {},
    } as any
    store.currentQuestionIndex = 1

    const refreshed = await store.refreshPracticeQuestion('c1', 'n1', 'node')

    expect(refreshed?.task_revision_id).toBe('qr4')
    expect(store.practice?.questions).toHaveLength(3)
    expect(store.practice?.questions.map(
      item => item.task_revision_id || item.revision_id,
    )).toEqual([
      'qr1',
      'qr4',
      'qr3',
    ])
    expect(store.currentQuestionIndex).toBe(1)
  })
})
