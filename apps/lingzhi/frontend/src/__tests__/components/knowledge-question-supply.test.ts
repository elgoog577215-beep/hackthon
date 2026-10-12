import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../../components/KnowledgeQuestionSupply.vue'
import { setLocale } from '../../shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../../utils/http', () => ({ default: http, teacherRequestConfig: () => ({ identityScope: 'teacher' }) }))
const point = { knowledge_id: 'k', revision_id: 'v', node_id: 'n', available_count: 0, pending_count: 0, sources: {}, can_generate: true }
const response = (patch = {}) => ({ data: { knowledge_baseline_revision: 'kb', points: [{ ...point, ...patch }], job: null } })
const mountView = () => mount(View, { props: { courseId: 'c', knowledgeId: 'k', baselineRevision: 'kb' } })
beforeEach(async () => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh })))
  await setLocale('zh')
  http.get.mockResolvedValue(response()); http.post.mockResolvedValue({ data: {} })
})
afterEach(() => vi.unstubAllGlobals())
describe('knowledge question supply', () => {
  it('generates only the selected point against its adopted revision', async () => {
    const view = mountView(); await flushPromises()
    expect(view.text()).toContain('暂无可用题目')
    await view.get('button').trigger('click'); await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/api/courses/c/question-bank/rebuild', expect.objectContaining({ scope: 'nodes', node_ids: ['n'], knowledge_ids: ['k'], knowledge_baseline_revision: 'kb', mode: 'incremental', retrieval_enabled: false }), { identityScope: 'teacher' })
    view.unmount()
  })
  it('reuses existing supply instead of generating when questions are available', async () => {
    http.get.mockResolvedValue(response({ available_count: 2, sources: { generated: 2 } }))
    const view = mountView(); await flushPromises()
    expect(view.text()).toContain('AI 题 2'); expect(view.find('button').exists()).toBe(false)
    expect(http.post).not.toHaveBeenCalled(); view.unmount()
  })
  it('leaves pending questions for review and blocks a stale baseline', async () => {
    http.get.mockResolvedValue(response({ pending_count: 1 }))
    const view = mountView(); await flushPromises()
    expect(view.text()).toContain('已有待审核题'); expect(view.find('button').exists()).toBe(false)
    http.get.mockResolvedValue({ data: { ...response().data, knowledge_baseline_revision: 'new' } })
    await view.setProps({ knowledgeId: 'k2' }); await flushPromises()
    await view.setProps({ knowledgeId: 'k' }); await flushPromises()
    expect(view.get('button').attributes('disabled')).toBeDefined(); view.unmount()
  })
  it('renders English labels', async () => {
    await setLocale('en')
    const view = mountView(); await flushPromises()
    expect(view.get('button').text()).toBe('Generate one foundational question'); view.unmount()
  })
})
