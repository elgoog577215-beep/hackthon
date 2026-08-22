import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ExamPaperComposer from '@/components/ExamPaperComposer.vue'
import { setLocale } from '@/shared/i18n'
import zhMessages from '@/../public/locales/zh/translation.json'

const post = vi.hoisted(() => vi.fn())
vi.mock('@/utils/http', () => ({ default: { post } }))

describe('ExamPaperComposer', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    await setLocale('zh')
    post.mockReset().mockResolvedValue({
      data: { paper: { paper_id: 'paper-1', title: '期中测试卷' } },
    })
  })

  it('saves a paper from pinned question revisions', async () => {
    const wrapper = mount(ExamPaperComposer, {
      attachTo: document.body,
      props: {
        courseId: 'course-1',
        bundleRevisionId: 'bundle-1',
        questions: [{
          revision_id: 'question-rev-1',
          prompt: '解释设计思维中的共情。',
          question_type: 'short_answer',
        }],
      },
    })
    await flushPromises()

    const inputs = document.body.querySelectorAll('input')
    ;(inputs[0] as HTMLInputElement).value = '期中测试卷'
    inputs[0]?.dispatchEvent(new Event('input', { bubbles: true }))
    document.body.querySelector('form')?.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    )
    await flushPromises()

    expect(post).toHaveBeenCalledWith(
      '/api/courses/course-1/question-bank/exam-papers',
      {
        title: '期中测试卷',
        duration_minutes: 120,
        total_score: 100,
        question_revision_ids: ['question-rev-1'],
        expected_bundle_revision_id: 'bundle-1',
      },
    )
    expect(wrapper.emitted('created')?.[0]?.[0]).toMatchObject({
      paper_id: 'paper-1',
    })
    wrapper.unmount()
  })
})
