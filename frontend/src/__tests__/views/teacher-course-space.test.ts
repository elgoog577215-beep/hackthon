import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMock }))

import TeacherCourseSpaceView from '@/views/TeacherCourseSpaceView.vue'
import { setLocale } from '@/shared/i18n'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/courses', component: { template: '<div />' } },
    { path: '/teacher-course-space', component: TeacherCourseSpaceView },
  ],
})

const mountView = () => mount(TeacherCourseSpaceView, {
  global: {
    plugins: [router],
    stubs: { ElDialog: true, ElTree: true },
  },
})

describe('TeacherCourseSpaceView', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    httpMock.get.mockReset().mockResolvedValue({ data: [] })
    httpMock.post.mockReset()
    await setLocale('zh')
    await router.push('/teacher-course-space')
    await router.isReady()
  })

  it('首次进入时直接显示创建主体，不渲染空的双栏工作台', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('.knowledge-space').classes()).toContain('knowledge-space--first-run')
    expect(wrapper.find('.knowledge-sidebar').exists()).toBe(false)
    expect(wrapper.get('.workspace-create').text()).toContain('新建课程文件库')
    expect(wrapper.find('label.create-field--course').text()).toContain('课程名称')
    expect(wrapper.findAll('.create-template button')).toHaveLength(2)

    await setLocale('en')
    await flushPromises()
    expect(wrapper.get('.workspace-create').text()).toContain('Create a course file library')
    expect(wrapper.get('.library-header').text()).toContain('Course file library')
  })

  it('创建方式使用单选语义，并允许清楚切换', async () => {
    const wrapper = mountView()
    await flushPromises()
    const options = wrapper.findAll('.create-template button')

    expect(options[1]!.attributes('aria-pressed')).toBe('true')
    await options[0]!.trigger('click')
    expect(options[0]!.attributes('aria-pressed')).toBe('true')
    expect(options[1]!.attributes('aria-pressed')).toBe('false')
  })
})
