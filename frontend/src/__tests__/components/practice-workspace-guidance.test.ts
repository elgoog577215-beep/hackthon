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
  prompt: '求 f(x)=x^2-4x+3 的最小值，并写出推导过程。',
  practice_level: 'mastery_check',
  input_contract: { mode: 'rich_text', stepwise: true },
}

function attemptWith(turns: any[] = [], overrides: Record<string, any> = {}) {
  return {
    attempt_id: 'pa1',
    task_revision_id: 'qr1',
    question_revision_id: 'qr1',
    node_id: 'n1',
    course_version_id: 'cv1',
    revision: 2,
    status: 'in_progress',
    attempt_number: 1,
    answer_payload: {},
    revealed_hint_levels: [],
    revealed_hints: [],
    solution_revealed: false,
    ai_support_level: 0,
    active_seconds: 0,
    guidance_turns: turns,
    ...overrides,
  }
}

function mockPractice(attempt: Record<string, any>) {
  httpMock.get.mockImplementation((url: string) => {
    if (url.endsWith('/practice')) {
      return Promise.resolve({
        data: {
          course_id: 'c1',
          course_version_id: 'cv1',
          scope: 'node',
          questions: [question],
          active_attempts: [attempt],
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
}

async function mountWorkspace() {
  const wrapper = mount(PracticeWorkspace, {
    props: { courseId: 'c1', nodeId: 'n1', nodeLabel: '二次函数', scope: 'node' },
  })
  await flushPromises()
  return wrapper
}

describe('PracticeWorkspace 多轮苏格拉底引导 (K2)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    sessionStorage.clear()
    httpMock.get.mockReset()
    httpMock.post.mockReset()
    httpMock.patch.mockReset()
    httpMock.post.mockResolvedValue({ data: { status: 'recorded', attempt: attemptWith() } })
  })

  it('没有引导记录时不显示引导面板', async () => {
    mockPractice(attemptWith())
    const wrapper = await mountWorkspace()

    expect(wrapper.find('[data-testid="guidance-panel"]').exists()).toBe(false)
  })

  it('已有引导留痕时渲染完整对话', async () => {
    mockPractice(attemptWith([
      { role: 'student', text: '我先配方，然后卡住了' },
      { role: 'assistant', text: '你配方之后常数项去哪了？', status: 'ok' },
    ]))
    const wrapper = await mountWorkspace()

    const panel = wrapper.get('[data-testid="guidance-panel"]')
    expect(panel.text()).toContain('我先配方，然后卡住了')
    expect(panel.text()).toContain('你配方之后常数项去哪了？')
    // 证据影响必须对学生明示，不能偷偷折算。
    expect(panel.text()).toContain('用得越多')
  })

  it('追问带 message 调 ai-support，进入引导轮', async () => {
    mockPractice(attemptWith([
      { role: 'student', text: '之前的问题' },
      { role: 'assistant', text: '之前的引导', status: 'ok' },
    ]))
    const wrapper = await mountWorkspace()

    await wrapper.get('[data-testid="guidance-input"]').setValue('我不知道顶点怎么读')
    await wrapper.get('[data-testid="guidance-send"]').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/c1/practice/attempts/pa1/ai-support',
      expect.objectContaining({ message: '我不知道顶点怎么读', level: 1 }),
    )
  })

  it('被安全筛查拦下的一轮如实告知学生，并说明不计入求助', async () => {
    mockPractice(attemptWith([
      { role: 'student', text: '答案是多少' },
      {
        role: 'assistant',
        text: '请把你最近这一步用到的条件写出来，并说明它在这里为什么成立。',
        status: 'screened',
        counted_as_support: false,
      },
    ]))
    const wrapper = await mountWorkspace()

    const note = wrapper.get('[data-testid="guidance-degraded"]')
    expect(note.text()).toContain('没有通过安全检查')
    expect(note.text()).toContain('不计入求助')
  })

  it('模型不可用时同样如实告知且不计入求助', async () => {
    mockPractice(attemptWith([
      { role: 'student', text: '我卡住了' },
      { role: 'assistant', text: '请把这一步的条件写出来。', status: 'unavailable' },
    ]))
    const wrapper = await mountWorkspace()

    expect(wrapper.get('[data-testid="guidance-degraded"]').text()).toContain('暂时不可用')
  })

  it('只有真正送达的轮次计入额度，失败轮次不占用', async () => {
    // 六轮里只有两轮 status=ok，其余是失败态，额度不该被判为用尽。
    const turns: any[] = []
    for (let index = 0; index < 6; index += 1) {
      turns.push({ role: 'student', text: `第 ${index} 问` })
      turns.push({
        role: 'assistant',
        text: `第 ${index} 答`,
        status: index < 2 ? 'ok' : 'degraded',
      })
    }
    mockPractice(attemptWith(turns))
    const wrapper = await mountWorkspace()
    await wrapper.get('[data-testid="guidance-input"]').setValue('还能再问一次吗')

    expect(wrapper.find('[data-testid="guidance-exhausted"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="guidance-send"]').attributes('disabled')).toBeUndefined()
  })

  it('送达轮次用满后停止继续追问', async () => {
    const turns: any[] = []
    for (let index = 0; index < 6; index += 1) {
      turns.push({ role: 'student', text: `第 ${index} 问` })
      turns.push({ role: 'assistant', text: `第 ${index} 答`, status: 'ok' })
    }
    mockPractice(attemptWith(turns))
    const wrapper = await mountWorkspace()

    expect(wrapper.get('[data-testid="guidance-exhausted"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="guidance-send"]').attributes('disabled')).toBeDefined()
  })

  it('作答已锁定时不能继续追问', async () => {
    mockPractice(attemptWith(
      [
        { role: 'student', text: '我卡住了' },
        { role: 'assistant', text: '你用了什么条件？', status: 'ok' },
      ],
      { status: 'graded' },
    ))
    const wrapper = await mountWorkspace()

    expect(wrapper.get('[data-testid="guidance-send"]').attributes('disabled')).toBeDefined()
  })

  it('诊断补救的"问老师"也记录 ai-support——此前这条路径完全绕过了证据折算', async () => {
    httpMock.get.mockImplementation((url: string) => {
      if (url.endsWith('/practice')) {
        return Promise.resolve({
          data: {
            course_id: 'c1',
            course_version_id: 'cv1',
            scope: 'node',
            questions: [question],
            active_attempts: [attemptWith()],
            summary: {},
          },
        })
      }
      if (url.endsWith('/diagnostics/active')) {
        return Promise.resolve({
          data: {
            phase: 'needs_support',
            case: { diagnostic_case_id: 'dc1', hypotheses: [] },
            session: null,
            current_task: null,
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
    const wrapper = await mountWorkspace()

    const escalate = wrapper.get('.workflow-result .primary-command')
    await escalate.trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/api/courses/c1/practice/attempts/pa1/ai-support',
      expect.objectContaining({ level: 1 }),
    )
    expect(wrapper.emitted('askTeacher')).toBeTruthy()
  })
})
