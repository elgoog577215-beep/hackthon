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
})
