import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MistakeNotebookPanel from '@/components/MistakeNotebookPanel.vue'
import { useCourseWorkspaceStore, type PracticeAttempt } from '@/stores/courseWorkspace'

const failedAttempt: PracticeAttempt = {
  attempt_id: 'pa-failed',
  task_revision_id: 'qr1',
  question_revision_id: 'qr1',
  revision: 2,
  status: 'graded',
  attempt_number: 1,
  answer_payload: { text: '错误答案' },
  revealed_hint_levels: [],
  solution_revealed: false,
  ai_support_level: 0,
  active_seconds: 45,
  node_id: 'n1',
  node_name: '向量空间',
  result: {
    passed: false,
    feedback: '还没有区分向量空间与向量集合。',
  },
}

describe('MistakeNotebookPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('以错题本形式展示当前仍需巩固的正式练习', async () => {
    const workspace = useCourseWorkspaceStore()
    workspace.mistakeBookAttempts = [failedAttempt]
    workspace.assets = {
      course_id: 'c1',
      plan: {},
      quality_report: {},
      course_availability: {
        schema_version: 'course_learning_availability_v1',
        mode: 'standard',
        reason_code: 'ready',
        capabilities: {},
      },
      assets: {
        questions: [{ asset_id: 'q1', revision_id: 'qr1', node_id: 'n1', prompt: '什么是向量空间？' }],
      },
    }
    vi.spyOn(workspace, 'loadMistakeBook').mockResolvedValue({ attempts: [failedAttempt] } as any)

    const wrapper = mount(MistakeNotebookPanel, { props: { courseId: 'c1' } })
    await flushPromises()

    expect(wrapper.text()).toContain('错题本')
    expect(wrapper.text()).toContain('共 1 道待巩固题目')
    expect(wrapper.text()).toContain('什么是向量空间？')
    expect(wrapper.text()).toContain('还没有区分向量空间与向量集合。')
    expect(wrapper.text()).toContain('针对再练')
  })

  it('针对再练后把当前正式题目交回课程练习工作区', async () => {
    const workspace = useCourseWorkspaceStore()
    workspace.mistakeBookAttempts = [failedAttempt]
    workspace.practice = {
      course_id: 'c1',
      scope: 'node',
      questions: [{ asset_id: 'q2', revision_id: 'qr2', node_id: 'n1', prompt: '判断一个集合是否为向量空间。' }],
      active_attempts: [],
      summary: {},
    } as any
    vi.spyOn(workspace, 'loadMistakeBook').mockResolvedValue({ attempts: [failedAttempt] } as any)
    vi.spyOn(workspace, 'startTargetedRetry').mockResolvedValue({
      ...failedAttempt,
      attempt_id: 'pa-retry',
      task_revision_id: 'qr2',
      question_revision_id: 'qr2',
      status: 'in_progress',
      origin_attempt_id: failedAttempt.attempt_id,
      practice_intent: 'targeted_retry',
    })

    const wrapper = mount(MistakeNotebookPanel, { props: { courseId: 'c1' } })
    await flushPromises()
    await wrapper.get('.mistake-notebook__retry').trigger('click')
    await flushPromises()

    expect(workspace.startTargetedRetry).toHaveBeenCalledWith('c1', failedAttempt)
    expect(wrapper.emitted('retry')).toEqual([[{ nodeId: 'n1', taskRevisionId: 'qr2' }]])
  })
})
