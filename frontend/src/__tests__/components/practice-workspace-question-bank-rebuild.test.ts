import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: httpMock }))

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
    httpMock.post.mockImplementation((url: string) => {
      if (url.endsWith('/question-bank/rebuild')) {
        return Promise.resolve({
          data: {
            bundle_revision_id: 'question-bank-revision-1',
            learning_asset_bundle_revision_id: 'asset-bundle-revision-1',
          },
        })
      }
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

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/legacy-course/question-bank/rebuild',
      { request_id: expect.any(String) },
    )
    expect(wrapper.text()).toContain(rebuiltQuestion.prompt)
    expect(wrapper.find('[data-testid="rebuild-question-bank"]').exists()).toBe(false)
  })
})
