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

const question = {
  asset_id: 'q1',
  revision_id: 'qr1',
  task_revision_id: 'qr1',
  node_id: 'n1',
  prompt: '说明向量的大小与方向。',
  practice_level: 'mastery_check',
  input_contract: { mode: 'rich_text' },
}

const activeAttempt = {
  attempt_id: 'pa1',
  task_revision_id: 'qr1',
  question_revision_id: 'qr1',
  node_id: 'n1',
  course_version_id: 'cv1',
  revision: 2,
  status: 'in_progress',
  attempt_number: 1,
  answer_payload: {},
  revealed_hint_levels: [1],
  revealed_hints: [
    { level: 1, kind: 'orientation', content: '先区分大小与方向。' },
  ],
  solution_revealed: false,
  ai_support_level: 1,
  active_seconds: 0,
}

describe('PracticeWorkspace resumed hints', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    sessionStorage.clear()
    httpMock.get.mockReset()
    httpMock.post.mockReset()
    httpMock.patch.mockReset()
    httpMock.get.mockImplementation((url: string) => {
      if (url.endsWith('/practice')) {
        return Promise.resolve({
          data: {
            course_id: 'c1',
            course_version_id: 'cv1',
            scope: 'node',
            questions: [question],
            active_attempts: [activeAttempt],
            summary: {},
          },
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
      if (url.endsWith('/hints/1')) {
        return Promise.resolve({
          data: {
            status: 'revealed',
            attempt: activeAttempt,
            hint: activeAttempt.revealed_hints[0],
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
  })

  it('刷新恢复后显示已看提示，并允许再次展开同一级提示', async () => {
    const wrapper = mount(PracticeWorkspace, {
      props: {
        courseId: 'c1',
        nodeId: 'n1',
        nodeLabel: '向量',
        scope: 'node',
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('先区分大小与方向。')
    const hintButtons = wrapper.findAll('.icon-command')
    expect(hintButtons).toHaveLength(3)
    const [firstHintButton, secondHintButton, thirdHintButton] = hintButtons
    if (!firstHintButton || !secondHintButton || !thirdHintButton) {
      throw new Error('expected three hint buttons')
    }
    expect(firstHintButton.attributes('disabled')).toBeUndefined()
    expect(secondHintButton.attributes('disabled')).toBeUndefined()
    expect(thirdHintButton.attributes('disabled')).toBeDefined()

    await firstHintButton.trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/c1/practice/attempts/pa1/hints/1',
      { expected_revision: 2 },
    )
    expect(wrapper.text()).toContain('先区分大小与方向。')
  })

  it('提示请求等待期间立即显示生成占位，完成后原位替换为正式提示', async () => {
    const freshAttempt = {
      ...activeAttempt,
      revision: 1,
      revealed_hint_levels: [],
      revealed_hints: [],
      ai_support_level: 0,
    }
    httpMock.get.mockImplementation((url: string) => {
      if (url.endsWith('/practice')) {
        return Promise.resolve({
          data: {
            course_id: 'c1',
            course_version_id: 'cv1',
            scope: 'node',
            questions: [question],
            active_attempts: [freshAttempt],
            summary: {},
          },
        })
      }
      if (url.endsWith('/diagnostics/active')) {
        return Promise.resolve({
          data: { phase: 'practice', case: null, session: null, current_task: null },
        })
      }
      return Promise.resolve({ data: {} })
    })
    let resolveHintRequest: ((value: unknown) => void) | undefined
    const pendingHintRequest = new Promise(resolve => {
      resolveHintRequest = resolve
    })
    httpMock.post.mockImplementation((url: string) => {
      if (url.endsWith('/hints/1')) return pendingHintRequest
      return Promise.resolve({ data: {} })
    })
    const wrapper = mount(PracticeWorkspace, {
      props: {
        courseId: 'c1',
        nodeId: 'n1',
        nodeLabel: '向量',
        scope: 'node',
      },
    })
    await flushPromises()

    const firstHintButton = wrapper.findAll('.icon-command')[0]
    if (!firstHintButton) throw new Error('expected first hint button')
    await firstHintButton.trigger('click')

    const loadingPlaceholder = wrapper.get('[data-testid="hint-loading-placeholder"]')
    expect(loadingPlaceholder.text()).toContain('正在生成提示，请稍候')
    expect(loadingPlaceholder.attributes('aria-live')).toBe('polite')
    expect(loadingPlaceholder.attributes('aria-busy')).toBe('true')
    expect(firstHintButton.attributes('disabled')).toBeDefined()

    resolveHintRequest?.({
      data: {
        status: 'revealed',
        attempt: {
          ...freshAttempt,
          revision: 2,
          revealed_hint_levels: [1],
          revealed_hints: [
            { level: 1, kind: 'orientation', content: '先区分大小与方向。' },
          ],
        },
        hint: { level: 1, kind: 'orientation', content: '先区分大小与方向。' },
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="hint-loading-placeholder"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('先区分大小与方向。')
  })
})
