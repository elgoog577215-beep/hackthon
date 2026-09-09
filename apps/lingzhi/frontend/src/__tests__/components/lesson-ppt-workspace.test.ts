import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LessonPptWorkspace from '@/components/LessonPptWorkspace.vue'
import { setLocale } from '@/shared/i18n'
import messages from '../../../public/locales/zh/translation.json'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))

vi.mock('@/utils/http', () => ({
  default: http,
  identityRequestConfig: () => ({}),
  teacherIdentityHeaders: () => ({}),
  withApiBase: (path: string) => path,
}))

describe('LessonPptWorkspace', () => {
  beforeEach(async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, json: async () => messages } as Response)
    await setLocale('zh')
    http.get.mockReset()
    http.post.mockReset()
    http.patch.mockReset()
  })

  it('没有内容稿时显示可见的空状态和生成入口', async () => {
    http.get.mockResolvedValue({
      data: {
        ppt_manuscript_state: {
          manuscript: null,
          source_script_revision_id: 'script-1',
          page_errors: [],
        },
      },
    })

    const wrapper = mount(LessonPptWorkspace, {
      props: {
        courseId: 'course-1',
        initialLessonId: 'L1-1',
        title: '第一讲',
      },
    })
    await flushPromises()

    expect(wrapper.find('section.lesson-ppt-workspace > template').exists()).toBe(false)
    expect(wrapper.get('.lesson-ppt-empty').text()).toContain('本讲尚无 PPT 内容稿')
    expect(wrapper.get('.lesson-ppt-empty button').text()).toContain('生成页面内容稿')
    expect(wrapper.get('.lesson-ppt-empty button').attributes('disabled')).toBeUndefined()

    wrapper.unmount()
  })

  it('生成内容稿时显示整体百分比和当前具体步骤', async () => {
    http.get.mockImplementation(async (url: string) => ({
      data: url.includes('/lesson-jobs/')
        ? {
            job: {
              id: 'ppt-task-1',
              status: 'running',
              phase: 'ppt_page_generation',
              progress: 42,
              message: '正在生成第 2/4 个小节的页面内容',
              attempt_number: 2,
              updated_at: new Date(Date.now() - 70_000).toISOString(),
            },
          }
        : {
            ppt_manuscript_state: {
              manuscript: null,
              source_script_revision_id: 'script-1',
              task_id: 'ppt-task-1',
              page_errors: [],
            },
          },
    }))

    const wrapper = mount(LessonPptWorkspace, {
      props: { courseId: 'course-1', initialLessonId: 'L1-1', title: '第一讲' },
    })
    await flushPromises()

    const progress = wrapper.get('[data-testid="ppt-manuscript-progress"]')
    expect(progress.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('42')
    expect(progress.text()).toContain('正在生成第 2/4 个小节的页面内容')
    expect(progress.findAll('[data-step]').map(step => step.text())).toEqual([
      expect.stringContaining('核对讲义来源'),
      expect.stringContaining('生成逐页内容'),
      expect.stringContaining('校验页面与引用'),
      expect.stringContaining('保存内容稿'),
    ])
    expect(progress.get('[data-step="pages"]').attributes('data-state')).toBe('current')
    expect(progress.text()).toContain('第 2 次尝试')
    expect(progress.text()).toContain('已等待 70 秒')
    expect(progress.attributes('aria-live')).toBe('polite')

    wrapper.unmount()
  })

  it('来源校验失败时指出失败步骤和讲义块并保留技术详情', async () => {
    http.get.mockImplementation(async (url: string) => ({
      data: url.includes('/lesson-jobs/')
        ? {
            job: {
              id: 'ppt-task-1',
              status: 'failed',
              phase: 'ppt_page_validation_failed',
              progress: 68,
              error: {
                code: 'lesson_ppt_source_grounding_failed',
                message: '页面引用未能匹配讲义原文。',
                failed_step: 'sources',
                failed_block_id: 'tsb-fb9d8c62c7fd',
                technical_detail: 'source_excerpt_mismatch:tsb-fb9d8c62c7fd',
              },
            },
          }
        : {
            ppt_manuscript_state: {
              manuscript: null,
              source_script_revision_id: 'script-1',
              task_id: 'ppt-task-1',
              page_errors: [],
            },
          },
    }))

    const wrapper = mount(LessonPptWorkspace, {
      props: { courseId: 'course-1', initialLessonId: 'L1-1', title: '第一讲' },
    })
    await flushPromises()

    const error = wrapper.get('.lesson-ppt-error')
    expect(error.text()).toContain('校验页面与引用')
    expect(error.text()).toContain('tsb-fb9d8c62c7fd')
    expect(error.get('details').text()).toContain('source_excerpt_mismatch:tsb-fb9d8c62c7fd')
    expect(wrapper.get('[data-step="sources"]').attributes('data-state')).toBe('failed')

    wrapper.unmount()
  })

  it('点击生成后不等待接口返回就立即进入启动进度', async () => {
    let resolveStart!: (value: any) => void
    const pendingStart = new Promise(resolve => { resolveStart = resolve })
    http.get.mockResolvedValue({ data: { ppt_manuscript_state: {
      manuscript: null, source_script_revision_id: 'script-1', page_errors: [],
    } } })
    http.post.mockReturnValue(pendingStart)

    const wrapper = mount(LessonPptWorkspace, {
      props: { courseId: 'course-1', initialLessonId: 'L1-1', title: '第一讲' },
    })
    await flushPromises()
    await wrapper.get('.lesson-ppt-empty button').trigger('click')

    const progress = wrapper.get('[data-testid="ppt-manuscript-progress"]')
    expect(progress.text()).toContain('正在启动 PPT 内容稿生成')
    expect(progress.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('0')
    expect(wrapper.find('.lesson-ppt-empty').exists()).toBe(false)

    resolveStart({ data: { job: { id: 'ppt-task-2', status: 'running', phase: 'ppt_source_validation', progress: 8 } } })
    await flushPromises()
    wrapper.unmount()
  })

  it('服务端报告原任务运行时自动接管该任务而不是停在错误页', async () => {
    let jobReads = 0
    http.get.mockImplementation(async (url: string) => {
      if (url.includes('/lesson-jobs/')) {
        jobReads += 1
        return { data: { job: jobReads === 1
          ? { id: 'ppt-task-1', status: 'failed', phase: 'ppt_page_validation_failed', progress: 92,
              error: { message: '上次失败', failed_step: 'sources' } }
          : { id: 'ppt-task-1', status: 'running', phase: 'ppt_page_generation', progress: 16,
              message: '正在继续原任务' } } }
      }
      return { data: { ppt_manuscript_state: {
        manuscript: null, source_script_revision_id: 'script-1', task_id: 'ppt-task-1', page_errors: [],
      } } }
    })
    http.post.mockRejectedValue({ response: { data: { detail: {
      code: 'lesson_ppt_job_running', message: '原任务仍在运行。',
    } } } })

    const wrapper = mount(LessonPptWorkspace, {
      props: { courseId: 'course-1', initialLessonId: 'L1-1', title: '第一讲' },
    })
    await flushPromises()
    await wrapper.get('.lesson-ppt-error button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.lesson-ppt-error').exists()).toBe(false)
    expect(wrapper.get('[data-testid="ppt-manuscript-progress"]').text()).toContain('正在继续原任务')
    expect(jobReads).toBeGreaterThanOrEqual(2)
    wrapper.unmount()
  })
})
