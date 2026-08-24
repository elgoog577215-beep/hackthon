import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QuestionBankImportWorkspace from '@/components/QuestionBankImportWorkspace.vue'
import { setLocale } from '@/shared/i18n'
import zhMessages from '@/../public/locales/zh/translation.json'

const { get, post, patch } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))
vi.mock('@/utils/http', () => ({
  default: { get, post, patch },
  teacherRequestConfig: (config = {}) => config,
}))

const session = {
  import_id: 'qimp-1',
  filename: 'HTTP 测试题.docx',
  extension: '.docx',
  size_bytes: 1024,
  status: 'needs_review',
  step: 'review',
  question_count: 1,
  pending_count: 1,
  updated_at: '2026-08-24T00:00:00Z',
  source_pages: [{ page: 1, text: '1. HTTP 默认端口是？\nA. 21\nB. 80' }],
  questions: [{
    draft_id: 'qid-1',
    prompt: 'HTTP 默认端口是？',
    question_type: 'single_choice',
    options: [{ id: 'A', text: '21' }, { id: 'B', text: '80' }],
    answer: '',
    explanation: '',
    score: null,
    node_id: 'node-http',
    source_page: 1,
    warnings: ['answer_missing'],
    confirmed: false,
  }],
}

describe('QuestionBankImportWorkspace', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    await setLocale('zh')
    get.mockReset()
    post.mockReset()
    patch.mockReset()
  })

  it('以文件导入作为默认入口，AI 生成是次要选择', async () => {
    get
      .mockResolvedValueOnce({ data: { session: null } })
      .mockResolvedValueOnce({ data: { imports: [] } })
    const wrapper = mount(QuestionBankImportWorkspace, {
      props: { courseId: 'course-http' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('上传 PDF 或 Word 试题')
    expect(wrapper.get('[data-testid="choose-question-file"]')).toBeTruthy()
    await wrapper.get('.quiet-button--ai').trigger('click')
    expect(wrapper.emitted('show-ai')).toHaveLength(1)
  })

  it('对照原文校对待确认题目并解锁入库', async () => {
    get
      .mockResolvedValueOnce({ data: { session } })
      .mockResolvedValueOnce({ data: { imports: [] } })
    patch.mockResolvedValue({
      data: {
        ...session,
        status: 'ready',
        pending_count: 0,
        questions: [{ ...session.questions[0], answer: 'B', confirmed: true }],
      },
    })
    post.mockResolvedValue({ data: { bundle_revision_id: 'qbb-imported' } })
    const wrapper = mount(QuestionBankImportWorkspace, {
      props: { courseId: 'course-http' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('原文')
    expect(wrapper.text()).toContain('未识别到答案')
    await wrapper.get('input[type="radio"][value="B"]').setValue(true)
    await wrapper.get('[data-testid="confirm-import-question"]').trigger('click')
    await flushPromises()

    expect(patch).toHaveBeenCalledWith(
      '/api/courses/course-http/question-bank/imports/qimp-1/items/qid-1',
      expect.objectContaining({ answer: 'B', confirmed: true }),
      expect.any(Object),
    )
    expect(wrapper.get('[data-testid="commit-question-import"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="commit-question-import"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('imported')).toEqual([['qbb-imported']])
    expect(wrapper.emitted('show-bank')).toHaveLength(1)
  })
})
