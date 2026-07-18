import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))
const rebuildMock = vi.hoisted(() => vi.fn())

vi.mock('@/utils/http', () => ({ default: httpMock }))
vi.mock('@/utils/question-bank-rebuild', () => ({
  runQuestionBankRebuild: rebuildMock,
}))

import PracticeWorkspace from '@/components/PracticeWorkspace.vue'

const legacyPractice = {
  course_id: 'legacy-course',
  course_version_id: 'legacy-version',
  scope: 'node',
  course_availability: {
    schema_version: 'course_learning_availability_v1',
    mode: 'compatibility',
    reason_code: 'legacy_course',
    capabilities: {},
  },
  practice_availability: {
    status: 'unavailable',
    reason_code: 'legacy_reading_compatible',
    scope: 'node',
    node_id: 'node-1',
  },
  questions: [],
  active_attempts: [],
  summary: {},
}

const rebuiltQuestion = {
  asset_id: 'question-1',
  revision_id: 'question-revision-1',
  task_revision_id: 'question-revision-1',
  node_id: 'node-1',
  prompt: 'Explain the rebuilt formal-practice contract.',
  practice_level: 'mastery_check',
  input_contract: { mode: 'rich_text' },
}

describe('PracticeWorkspace legacy question-bank repair', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    httpMock.get.mockReset()
    httpMock.post.mockReset()
    httpMock.patch.mockReset()
    rebuildMock.mockReset()
    rebuildMock.mockImplementation(async (
      _courseId: string,
      _request: unknown,
      options: { onUpdate?: (job: Record<string, unknown>) => void },
    ) => {
      options.onUpdate?.({
        status: 'running',
        progress: 55,
        current_stage: 'question_generation',
        message: '正在生成题目',
      })
      options.onUpdate?.({
        status: 'completed',
        progress: 100,
        current_stage: 'publication',
        message: '发布完成',
      })
      return { status: 'completed', progress: 100 }
    })

    let practiceLoads = 0
    httpMock.get.mockImplementation((url: string) => {
      if (url.endsWith('/practice')) {
        practiceLoads += 1
        return Promise.resolve({
          data: practiceLoads === 1
            ? legacyPractice
            : { ...legacyPractice, questions: [rebuiltQuestion] },
        })
      }
      if (url.endsWith('/diagnostics/active')) {
        return Promise.resolve({
          data: { phase: 'practice', case: null, session: null, current_task: null },
        })
      }
      return Promise.resolve({ data: {} })
    })
    httpMock.post.mockImplementation(() => {
      return Promise.resolve({
        data: {
          attempt: {
            attempt_id: 'attempt-1',
            task_revision_id: rebuiltQuestion.revision_id,
            question_revision_id: rebuiltQuestion.revision_id,
            revision: 1,
            status: 'in_progress',
            attempt_number: 1,
            answer_payload: {},
            revealed_hint_levels: [],
            solution_revealed: false,
            ai_support_level: 0,
            active_seconds: 0,
          },
        },
      })
    })
  })

  it('rebuilds an unusable legacy bank through the current question-bank pipeline', async () => {
    const wrapper = mount(PracticeWorkspace, {
      props: {
        courseId: 'legacy-course',
        nodeId: 'node-1',
        nodeLabel: 'Legacy section',
        scope: 'node',
      },
    })
    await flushPromises()

    const rebuildButton = wrapper.get('[data-testid="rebuild-question-bank"]')
    await rebuildButton.trigger('click')
    await flushPromises()

    expect(rebuildMock).toHaveBeenCalledWith(
      'legacy-course',
      {
        request_id: expect.any(String),
        scope: 'nodes',
        node_ids: ['node-1'],
        mode: 'incremental',
      },
      expect.objectContaining({ onUpdate: expect.any(Function) }),
    )
    expect(wrapper.text()).toContain(rebuiltQuestion.prompt)
    expect(wrapper.find('[data-testid="rebuild-question-bank"]').exists()).toBe(false)
  })
})
