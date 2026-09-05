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

function summary(value: Record<string, any> = session) {
  const { questions: _questions, source_pages: _pages, ...result } = value
  return result
}

describe('QuestionBankImportWorkspace', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    window.sessionStorage.clear()
    await setLocale('zh')
    get.mockReset()
    post.mockReset()
    patch.mockReset()
  })

  it('中间保持题目审阅，右侧只承载导入文件队列', async () => {
    get.mockResolvedValueOnce({ data: { imports: [] } })
    const wrapper = mount(QuestionBankImportWorkspace, {
      props: { courseId: 'course-http' },
    })
    await flushPromises()

    expect(wrapper.get('.question-import__main').text()).toContain('题目审阅')
    expect(wrapper.get('.question-import__empty-review').text()).toBe('题目审阅')
    expect(wrapper.text()).toContain('题库文件')
    expect(wrapper.text()).toContain('还没有导入文档')
    expect(wrapper.get('.question-import__sources [data-testid="add-question-files"]').text()).toContain('选择多份文件')
    expect(wrapper.get('.question-import__sources').text()).toContain('导入文件')
    expect(wrapper.get('.question-import__sources').text()).not.toContain('联网来源')
    expect(wrapper.get('[data-testid="question-import-file"]').attributes('multiple')).toBeDefined()
  })

  it('一次选择多份文件并逐份建立可恢复导入记录', async () => {
    const secondSession = {
      ...session,
      import_id: 'qimp-2',
      filename: '第二套试题.pdf',
      status: 'ready',
      pending_count: 0,
      questions: [{ ...session.questions[0], confirmed: true, warnings: [], answer: 'B' }],
    }
    get
      .mockResolvedValueOnce({ data: { imports: [] } })
      .mockResolvedValueOnce({ data: { imports: [summary(secondSession), summary(session)] } })
    post
      .mockResolvedValueOnce({ data: session })
      .mockResolvedValueOnce({ data: secondSession })

    const wrapper = mount(QuestionBankImportWorkspace, {
      props: { courseId: 'course-http' },
    })
    await flushPromises()

    const input = wrapper.get('[data-testid="question-import-file"]').element as HTMLInputElement
    Object.defineProperty(input, 'files', {
      configurable: true,
      value: [
        new File(['docx'], 'HTTP 测试题.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }),
        new File(['pdf'], '第二套试题.pdf', { type: 'application/pdf' }),
      ],
    })
    await wrapper.get('[data-testid="question-import-file"]').trigger('change')
    await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    await flushPromises()

    expect(wrapper.text()).toContain('HTTP 测试题.docx')
    expect(wrapper.text()).toContain('第二套试题.pdf')
    const documentRows = wrapper.findAll('.question-import__documents nav button')
    expect(documentRows).toHaveLength(2)
    expect(documentRows.find(row => row.text().includes('HTTP 测试题.docx'))?.text()).toBe('HTTP 测试题.docx正在处理')
    expect(documentRows.find(row => row.text().includes('第二套试题.pdf'))?.text()).toBe('第二套试题.pdf已完成')
    expect(window.sessionStorage.getItem('lingzhi:question-import:course-http')).toBe('qimp-1')
  })

  it('批量处理中单份失败不会清除已经识别的文档', async () => {
    get
      .mockResolvedValueOnce({ data: { imports: [] } })
      .mockResolvedValueOnce({ data: { imports: [summary(session)] } })
    post
      .mockResolvedValueOnce({ data: session })
      .mockRejectedValueOnce({ response: { data: { detail: '文件无法解析' } } })

    const wrapper = mount(QuestionBankImportWorkspace, {
      props: { courseId: 'course-http' },
    })
    await flushPromises()

    const input = wrapper.get('[data-testid="question-import-file"]').element as HTMLInputElement
    Object.defineProperty(input, 'files', {
      configurable: true,
      value: [
        new File(['docx'], 'HTTP 测试题.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }),
        new File(['pdf'], '损坏试题.pdf', { type: 'application/pdf' }),
      ],
    })
    await wrapper.get('[data-testid="question-import-file"]').trigger('change')
    await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    await flushPromises()

    expect(wrapper.text()).toContain('HTTP 测试题.docx')
    expect(wrapper.text()).toContain('损坏试题.pdf：文件无法解析')
    expect(wrapper.findAll('.question-import__documents nav button')).toHaveLength(1)
  })

  it('从右侧选择文档校对，入库后仍停留在文档工作区', async () => {
    const confirmed = {
      ...session,
      status: 'ready',
      pending_count: 0,
      questions: [{ ...session.questions[0], answer: 'B', confirmed: true, warnings: [] }],
    }
    const committed = { ...confirmed, status: 'committed', step: 'complete' }
    get
      .mockResolvedValueOnce({ data: { imports: [summary(session)] } })
      .mockResolvedValueOnce({ data: session })
      .mockResolvedValueOnce({ data: { imports: [summary(committed)] } })
    patch.mockResolvedValue({ data: confirmed })
    post.mockResolvedValue({ data: { session: committed, bundle_revision_id: 'qbb-imported' } })

    const wrapper = mount(QuestionBankImportWorkspace, {
      props: { courseId: 'course-http' },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="confirm-import-question"]').exists()).toBe(false)
    expect(wrapper.get('.question-import__documents nav button').text()).toBe('HTTP 测试题.docx未处理')

    await wrapper.get('.question-import__documents nav button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.question-import__documents nav button').text()).toBe('HTTP 测试题.docx正在处理')
    expect(wrapper.text()).toContain('原文')
    expect(wrapper.text()).toContain('未识别到答案')
    expect(wrapper.find('input[type="radio"]').exists()).toBe(false)

    await wrapper.get('[data-testid="edit-import-question"]').trigger('click')
    await wrapper.get('input[type="radio"][value="B"]').setValue(true)
    await wrapper.get('[data-testid="confirm-import-question"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="commit-question-import"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="commit-question-import"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('imported')).toEqual([['qbb-imported']])
    expect(wrapper.emitted('show-bank')).toBeUndefined()
    expect(wrapper.text()).toContain('原文与题目来源已经保留')
    expect(wrapper.find('[data-testid="commit-question-import"]').exists()).toBe(false)

    const viewBank = wrapper.findAll('button').find(button => button.text().includes('查看题库'))
    expect(viewBank).toBeTruthy()
    await viewBank!.trigger('click')
    expect(wrapper.emitted('show-bank')).toHaveLength(1)
  })
})
