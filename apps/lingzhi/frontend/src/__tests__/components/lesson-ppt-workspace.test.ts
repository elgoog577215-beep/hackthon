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
})
