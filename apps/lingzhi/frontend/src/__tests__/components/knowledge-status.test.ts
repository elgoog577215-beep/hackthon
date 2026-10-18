import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

function state() {
  const tree = { revision_id: 'base', source_mode: 'handouts', categories: [], knowledge_points: [], relations: [],
    gaps: ['需要补充边界条件'], uncovered_evidence_ids: ['source-missing'], source_handouts: [{ lesson_id: 'cpu' }] }
  const job = { id: 'tree-1', type: 'course_knowledge_tree_generation', knowledge_lesson_id: 'cpu',
    status: 'running', phase: 'model_streaming', progress: 10, received_chars: 120, elapsed_seconds: 23, activity_age_seconds: 1 }
  return { enabled: true, workflow: 'knowledge_first_generic_v1', source_mode: 'handouts', can_edit: true,
    document_revision: 'd', knowledge_revision: 'base', result_version: 'v1', title: '测试课程', tree,
    history: [tree], jobs: [job], active_jobs: [job], candidates: [], handouts: [], source_handouts: [],
    lesson_options: [{ lesson_id: 'cpu', title: '处理器', can_generate: true, blocking_job_ids: [job.id] },
      { lesson_id: 'memory', title: '主存', can_generate: true, blocking_job_ids: [] }] }
}
function status(v = state()) {
  return { jobs: v.jobs, active_jobs: v.active_jobs, result_version: v.result_version,
    blocking_job_ids: ['tree-1'], lesson_blocking_job_ids: { cpu: ['tree-1'], memory: [] } }
}
beforeEach(async () => {
  vi.useFakeTimers()
  vi.restoreAllMocks()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
  await setLocale('zh')
  vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

it('polls lightweight status and displays reported percentage without model diagnostics', async () => {
  const get = vi.spyOn(http, 'get').mockImplementation(async url => ({ data: String(url).endsWith('/status') ? status() : state() }))
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  const progress = w.get('[data-testid="knowledge-generation-progress"]')
  expect(progress.text()).toContain('10%')
  expect(progress.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('10')
  expect(progress.text()).not.toContain('120')
  expect(progress.text()).not.toContain('23')
  await vi.advanceTimersByTimeAsync(4000); await flushPromises()
  expect(get.mock.calls.filter(([url]) => String(url).endsWith('/status')).length).toBe(2)
  expect(get.mock.calls.filter(([url]) => !String(url).endsWith('/status')).length).toBe(1)
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('recovers status polling after an outage and loads the completed result once', async () => {
  const v = state()
  const finished = { ...v, result_version: 'v2', jobs: [{ ...v.jobs[0], status: 'completed', phase: 'completed' }], active_jobs: [] }
  let polls = 0
  const get = vi.spyOn(http, 'get').mockImplementation(async url => {
    if (!String(url).endsWith('/status')) return { data: polls > 1 ? finished : v }
    polls++
    if (polls === 1) throw new Error('offline')
    return { data: { ...status(), result_version: 'v2', jobs: finished.jobs, active_jobs: [], lesson_blocking_job_ids: { cpu: [], memory: [] } } }
  })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(w.get('[data-testid="knowledge-observation-notice"]').text()).toContain('重新连接')
  await vi.advanceTimersByTimeAsync(4000); await flushPromises()
  expect(polls).toBeGreaterThanOrEqual(2)
  expect(get.mock.calls.filter(([url]) => !String(url).endsWith('/status')).length).toBe(2)
  expect(w.find('[data-testid="knowledge-observation-notice"]').exists()).toBe(false)
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
  const calls = get.mock.calls.length
  await vi.advanceTimersByTimeAsync(30000)
  window.dispatchEvent(new Event('online'))
  expect(get).toHaveBeenCalledTimes(calls)
})

it('keeps other lecture tasks from cluttering or blocking the selected lecture', async () => {
  vi.spyOn(http, 'get').mockResolvedValue({ data: state() })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.find('[data-testid="knowledge-extraction-gaps"]').exists()).toBe(false)
  await w.get('select[aria-label="讲次"]').setValue('memory')
  expect(w.find('[data-testid="knowledge-other-jobs"]').exists()).toBe(false)
  expect(w.find('[data-testid="knowledge-generation-progress"]').exists()).toBe(false)
  expect(w.findAll('button').find(b => b.text().includes('生成本讲知识树'))!.attributes('disabled')).toBeUndefined()
  w.unmount()
})

it('renders waiting, streaming and reconnect states in English', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => en })))
  await setLocale('en')
  const v = state(); v.jobs[0]!.phase = 'model_wait'; v.jobs[0]!.received_chars = 0
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('[data-testid="knowledge-generation-progress"]').text()).toContain('Waiting for model output')
  expect(w.get('[role="progressbar"]').attributes('aria-label')).toBe('Generation progress')
  w.unmount()
})

it('recovers an initial read failure without starting a generation task', async () => {
  const get = vi.spyOn(http, 'get').mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ data: state() })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('[data-testid="knowledge-observation-notice"]').text()).toContain('重新连接')
  await vi.advanceTimersByTimeAsync(4000); await flushPromises()
  expect(get).toHaveBeenCalledTimes(2)
  expect(w.find('[data-testid="knowledge-generation-progress"]').exists()).toBe(true)
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('stops automatic observation after access is revoked and permits a manual status check', async () => {
  const get = vi.spyOn(http, 'get').mockImplementation(async url => ({ data: String(url).endsWith('/status')
    ? { can_edit: false, jobs: [], active_jobs: [] } : state() }))
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(w.get('[data-testid="knowledge-observation-notice"]').text()).toContain('访问权限')
  const calls = get.mock.calls.length
  window.dispatchEvent(new Event('online'))
  await vi.advanceTimersByTimeAsync(30000)
  expect(get).toHaveBeenCalledTimes(calls)
  get.mockResolvedValue({ data: { ...status(), can_edit: true } })
  await w.get('[data-testid="knowledge-observation-notice"] button').trigger('click'); await flushPromises()
  expect(w.find('[data-testid="knowledge-observation-notice"]').exists()).toBe(false)
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('stops polling and editing on a forbidden status response', async () => {
  const get = vi.spyOn(http, 'get').mockImplementation(async url => {
    if (String(url).endsWith('/status')) throw { response: { status: 403 } }
    return { data: state() }
  })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(w.get('[data-testid="knowledge-observation-notice"]').text()).toContain('访问权限')
  expect(w.findAll('button').some(b => b.text().includes('生成本讲知识树'))).toBe(false)
  const calls = get.mock.calls.length
  await vi.advanceTimersByTimeAsync(30000)
  expect(get).toHaveBeenCalledTimes(calls)
  w.unmount()
})

it('does not attribute another lecture gap report to the selected lecture', async () => {
  const v: any = state()
  v.tree.scope_lesson_id = 'memory'
  v.tree.lesson_revisions = { cpu: 'cpu-v1', memory: 'memory-v1' }
  v.tree.gaps = ['主存讲独有的缺口']
  v.history = [v.tree]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.text()).not.toContain('主存讲独有的缺口')
  expect(w.find('[data-testid="knowledge-extraction-gaps"]').exists()).toBe(false)
  w.unmount()
})

it('retries loading a completed result if the first full read fails', async () => {
  const v = state()
  let fullReads = 0
  const get = vi.spyOn(http, 'get').mockImplementation(async url => {
    if (String(url).endsWith('/status')) return { data: { ...status(), result_version: 'v2' } }
    fullReads++
    if (fullReads === 2) throw new Error('result read interrupted')
    return { data: fullReads === 1 ? v : { ...v, result_version: 'v2', jobs: [], active_jobs: [] } }
  })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(w.find('[data-testid="knowledge-generation-progress"]').exists()).toBe(true)
  await vi.advanceTimersByTimeAsync(4000); await flushPromises()
  expect(fullReads).toBe(3)
  expect(w.find('[data-testid="knowledge-observation-notice"]').exists()).toBe(false)
  const calls = get.mock.calls.length
  w.unmount()
  await vi.advanceTimersByTimeAsync(20000)
  expect(get).toHaveBeenCalledTimes(calls)
  expect(http.post).not.toHaveBeenCalled()
})
