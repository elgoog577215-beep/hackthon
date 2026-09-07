import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import PptProjectWorkspace from '@/components/PptProjectWorkspace.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import messages from '../../../public/locales/zh/translation.json'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, identityRequestConfig: (_s: any, c: any) => c, withApiBase: (url: string) => url, teacherIdentityHeaders: () => ({}) }))
vi.mock('@/utils/slide-deck-v6-adapter', () => ({ adaptSlideDeckV6ForWeb: () => [{ title: '导数的定义' }, { title: '切线的斜率与变化率的关系' }] }))

beforeEach(async () => {
  vi.clearAllMocks()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, json: async () => messages } as Response)
  await setLocale('zh')
})

it('keeps the result page, page rail and shared pagination aligned without regenerating', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
  await router.push('/')
  const project = { project_id: 'p', title: '导数与切线', status: 'ready', lesson_ids: ['l1'], asset_ids: [], manuscript: { manuscript_revision: 'm1' }, confirmed_revision: 'm1', last_good_render: { manuscript_revision: 'm1', deck: {} } }
  vi.mocked(http.get).mockImplementation(async url => ({ data: String(url).endsWith('/ppt-projects') ? { lectures: [], uploads: [], projects: [project] } : project }))
  const wrapper = mount(PptProjectWorkspace, { props: { courseId: 'c', embedded: true }, global: { plugins: [router], stubs: { SlideCanvas: { props: ['slide', 'pageNumber'], template: '<div data-testid="result-canvas">{{pageNumber}} {{slide.title}}</div>' }, PptManuscriptWorkflow: true } } })
  await flushPromises()
  await wrapper.get('.existing-projects button').trigger('click')
  await flushPromises()
  expect(wrapper.get('.project-render h1').text()).toBe('导数与切线')
  expect(wrapper.get('[data-testid="result-canvas"]').text()).toContain('1 导数的定义')
  expect(wrapper.get('[data-testid="ppt-result-page-prev"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-testid="ppt-result-page-next"]').trigger('click')
  expect(wrapper.get('[data-testid="result-canvas"]').text()).toContain('2 切线的斜率')
  expect(wrapper.get('.project-deck [aria-current="page"]').text()).toContain('切线的斜率')
  expect(wrapper.get('[data-testid="ppt-result-page-next"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-testid="ppt-result-page-select"]').setValue('1')
  expect(wrapper.get('.project-deck [aria-current="page"]').text()).toContain('导数的定义')
  expect(http.post).not.toHaveBeenCalled()
  wrapper.unmount()
})
