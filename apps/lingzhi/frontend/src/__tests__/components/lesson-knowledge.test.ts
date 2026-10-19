import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

const tree = (revision = 'base') => ({ revision_id: revision,
  categories: [{ id: 'c', name: '硬件', parent_id: null }],
  knowledge_points: [{ knowledge_id: 'cpu-k', name: 'CPU知识', statement: 'CPU执行指令', parent_id: 'c', section_refs: ['cpu'] },
    { knowledge_id: 'memory-k', name: '主存知识', statement: '主存保存数据', parent_id: 'c', section_refs: ['memory'] }], relations: [], misconceptions: [] })
const state = () => ({ enabled: true, source_mode: 'handouts', workflow: 'knowledge_first_generic_v1', can_edit: true,
  title: '计算机系统', document_revision: 'd', knowledge_revision: 'base', tree: tree(), history: [tree()], jobs: [], handouts: [],
  can_generate_tree: true, source_handouts: [{ lesson_id: 'cpu' }, { lesson_id: 'memory' }],
  lesson_options: [{ lesson_id: 'cpu', title: '处理器', can_generate: true }, { lesson_id: 'memory', title: '主存', can_generate: true }], candidates: [] })

it('explains that an adopted tree retains an older handout without starting generation', async () => {
  const v: any = state()
  v.source_handouts = [{ lesson_id: 'cpu', script_revision_id: 'handout-current' }]
  v.tree.source_handouts = [{ lesson_id: 'cpu', script_revision_id: 'handout-used' }]
  v.history = [v.tree]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  const notice = w.get('[data-testid="knowledge-source-version"]')
  expect((notice.element as HTMLDetailsElement).open).toBe(false)
  expect(notice.text()).toContain('讲义来源需要核对')
  expect(notice.text()).toContain('保留原讲义版本')
  expect(notice.text()).toContain('handout-used')
  expect(notice.text()).toContain('handout-current')
  expect(w.get('.mastery-tree').text()).toContain('CPU知识')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('prevents adopting a candidate after its handout source changes', async () => {
  const v: any = state()
  v.source_handouts = [{ lesson_id: 'cpu', script_revision_id: 'current' }]
  v.candidates = [{ job_id: 'candidate-job', lesson_id: 'cpu', tree: { ...tree('candidate-v1'), source_handouts: [{ lesson_id: 'cpu', script_revision_id: 'old' }] } }]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('[data-testid="knowledge-source-version"]').text()).toContain('暂不能采用')
  const adopt = w.findAll('button').find(b => b.text() === '采用这版知识树')!
  expect(adopt.attributes('disabled')).toBeDefined()
  await adopt.trigger('click'); await flushPromises()
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('compares only the selected lecture and treats a missing current source as unavailable', async () => {
  const v: any = state()
  v.source_handouts = [{ lesson_id: 'cpu', script_revision_id: 'cpu-same' }]
  v.tree.source_handouts = [{ lesson_id: 'cpu', script_revision_id: 'cpu-same' }, { lesson_id: 'memory', script_revision_id: 'memory-old' }]
  v.history = [v.tree]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('[data-testid="knowledge-source-version"]').classes()).not.toContain('needs-review')
  expect(w.get('[data-testid="knowledge-source-version"]').text()).not.toContain('memory-old')
  await w.get('select[aria-label="讲次"]').setValue('memory')
  expect(w.get('[data-testid="knowledge-source-version"]').classes()).toContain('needs-review')
  expect(w.get('[data-testid="knowledge-source-version"]').text()).toContain('未记录可用版本')
  expect(w.get('.mastery-tree').text()).toContain('主存知识')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('shows handout version differences in English', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => en })))
  await setLocale('en')
  const v: any = state()
  v.source_handouts = [{ lesson_id: 'cpu', script_revision_id: 'new-handout' }]
  v.tree.source_handouts = [{ lesson_id: 'cpu', script_revision_id: 'old-handout' }]
  v.history = [v.tree]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  const notice = w.get('[data-testid="knowledge-source-version"]')
  expect(notice.text()).toContain(en.knowledgeFirst.sourceNeedsReview)
  expect(notice.text()).toContain(en.knowledgeFirst.recordedHandoutVersion)
  expect(notice.text()).not.toContain('讲义来源')
  w.unmount()
})
afterEach(() => vi.useRealTimers())

it('allows another lecture while showing the selected lecture task', async () => {
  const v: any = state()
  v.jobs = [{ id: 'memory-tree', type: 'course_knowledge_tree_generation', knowledge_lesson_id: 'memory', status: 'running', progress: 20 }]
  v.active_jobs = v.jobs
  v.lesson_options[0].blocking_job_ids = []
  v.lesson_options[1].blocking_job_ids = ['memory-tree']
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  const generate = () => w.findAll('button').find(b => b.text().includes('生成本讲知识树'))!
  expect(generate().attributes('disabled')).toBeUndefined()
  await w.get('select[aria-label="讲次"]').setValue('memory')
  expect(generate().attributes('disabled')).toBeDefined()
  w.unmount()
})

it('shows a blocking handout and refreshes when that job completes without restarting it', async () => {
  vi.useFakeTimers()
  const v: any = state()
  v.active_jobs = [{ id: 'cpu-handout', type: 'teacher_lesson_script_generation', lesson_unit_id: 'cpu', status: 'running', progress: 35 }]
  v.lesson_options[0].blocking_job_ids = ['cpu-handout']
  const get = vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  const generate = () => w.findAll('button').find(b => b.text().includes('生成本讲知识树'))!
  expect(generate().attributes('disabled')).toBeDefined()
  expect(w.get('[data-testid="knowledge-source-blocker"]').text()).toContain('讲义')
  expect(w.text()).not.toContain('本讲还没有知识树，点击“生成本讲知识树”开始。')
  get.mockResolvedValue({ data: { ...v, active_jobs: [], lesson_options: state().lesson_options } })
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(generate().attributes('disabled')).toBeUndefined()
  expect(w.find('[data-testid="knowledge-source-blocker"]').exists()).toBe(false)
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('reconciles a conflicting start response with the accepted background task', async () => {
  const v: any = state()
  const get = vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  const job = { id: 'cpu-tree', type: 'course_knowledge_tree_generation', knowledge_lesson_id: 'cpu', status: 'running', progress: 15, message: '正在生成' }
  get.mockResolvedValue({ data: { ...v, jobs: [job], active_jobs: [job], lesson_options: [{ ...v.lesson_options[0], blocking_job_ids: [job.id] }, v.lesson_options[1]] } })
  vi.mocked(http.post).mockRejectedValue({ response: { status: 409, data: { detail: '已有生成任务' } } })
  await w.findAll('button').find(b => b.text().includes('生成本讲知识树'))!.trigger('click'); await flushPromises()
  expect(w.find('[role="alert"]').exists()).toBe(false)
  expect(w.get('[role="status"]').text()).toContain(zh.knowledgeFirst.phase_model)
  expect(w.text()).not.toContain('本讲还没有知识树，点击“生成本讲知识树”开始。')
  expect(http.post).toHaveBeenCalledTimes(1)
  w.unmount()
})

it('explains a blocked source task in English and stops observing after unmount', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => en })))
  await setLocale('en')
  const v: any = state()
  v.active_jobs = [{ id: 'plan', type: 'teacher_lesson_plan_generation', lesson_unit_id: 'cpu', status: 'pending', progress: 0 }]
  v.lesson_options[0].blocking_job_ids = ['plan']
  const get = vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('[data-testid="knowledge-source-blocker"]').text()).toContain('Lesson plan generation in progress')
  expect(w.get('[data-testid="knowledge-source-blocker"]').text()).toContain('source task finishes')
  w.unmount()
  const calls = get.mock.calls.length
  await vi.advanceTimersByTimeAsync(4000)
  expect(get).toHaveBeenCalledTimes(calls)
})
beforeEach(async () => {
  vi.restoreAllMocks()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
  await setLocale('zh')
  vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
})

it('switches lecture trees and sends only the selected lecture when generating', async () => {
  vi.spyOn(http, 'get').mockResolvedValue({ data: state() })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('.mastery-tree').text()).toContain('CPU知识')
  expect(w.get('.mastery-tree').text()).not.toContain('主存知识')
  await w.get('select[aria-label="讲次"]').setValue('memory')
  expect(w.get('.mastery-tree').text()).toContain('主存知识')
  expect(w.get('.mastery-tree').text()).not.toContain('CPU知识')
  await w.findAll('button').find(b => b.text().includes('生成本讲知识树'))!.trigger('click'); await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree', expect.objectContaining({ lesson_id: 'memory', source_mode: 'handouts' }))
  w.unmount()
})

it('keeps candidate selection tied to its lecture and disables generation for missing handouts', async () => {
  const v: any = state()
  v.candidates = [{ job_id: 'cpu-job', lesson_id: 'cpu', source_knowledge_revision: 'base', tree: tree('cpu-candidate') }]
  v.lesson_options[1].can_generate = false
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.findAll('button').find(b => b.text() === '采用这版知识树')!.trigger('click'); await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/adopt/cpu-job', expect.anything())
  await w.get('select[aria-label="讲次"]').setValue('memory')
  expect(w.findAll('button').some(b => b.text() === '采用这版知识树')).toBe(false)
  expect(w.findAll('button').find(b => b.text().includes('生成本讲知识树'))!.attributes('disabled')).toBeDefined()
  w.unmount()
})

it('opens a cross-lecture knowledge link in the matching lecture without leaving the workspace', async () => {
  Element.prototype.scrollIntoView = vi.fn()
  const v: any = state()
  v.tree.knowledge_points[0].statement = 'CPU执行指令'
  v.tree.knowledge_points[1].statement = '主存保存数据'
  v.tree.relations = [{ id: 'cross', source_id: 'cpu-k', target_id: 'memory-k', type: 'applies_to', cross_lesson: true, reason: '取指使用主存' }]
  v.history = [v.tree]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.get('[data-knowledge-id="cpu-k"]').trigger('click')
  expect(w.text()).toContain('跨讲关联')
  await w.findAll('button').find(b => b.text().includes('第2讲') && b.text().includes('主存知识'))!.trigger('click'); await flushPromises()
  expect((w.get('select[aria-label="讲次"]').element as HTMLSelectElement).value).toBe('memory')
  expect(w.get('.point-card').text()).toContain('主存保存数据')
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('shows related definitions and provenance in the right pane without switching to the handout', async () => {
  const v: any = state()
  v.lesson_options[0].title = '第1讲 处理器'
  v.tree.knowledge_points[0] = { ...v.tree.knowledge_points[0], statement: 'CPU执行指令', conditions: ['通电'],
    meta_question: '指令由谁执行？', meta_answer: 'CPU执行', revision_id: 'point-v1',
    source_quotes: [{ evidence_id: 's1', quote: '本讲讲义中的CPU原文', handout_ref: { lesson_id: 'cpu', script_revision_id: 'script-v1', block_id: 'b1' } }] }
  v.tree.knowledge_points.push({ knowledge_id: 'alu', name: '运算器', statement: '运算器执行运算', parent_id: 'c', section_refs: ['cpu'] })
  v.tree.relations = [{ id: 'local', source_id: 'cpu-k', target_id: 'alu', type: 'applies_to', reason: '执行依赖运算', conditions: ['算术指令'] }]
  v.history = [v.tree]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('.tree-course').text()).not.toContain('第1讲 · 第1讲')
  await w.get('[data-knowledge-id="cpu-k"]').trigger('click')
  const pane = w.get('.point-card')
  for (const content of ['CPU执行指令', '通电', '指令由谁执行', 'CPU执行', '运算器执行运算', '执行依赖运算', '算术指令', '本讲讲义中的CPU原文', 'point-v1']) expect(pane.text()).toContain(content)
  expect(pane.text()).not.toContain('applies_to')
  expect(pane.findAll('button').some(b => b.text().includes('定位讲义'))).toBe(false)
  await pane.findAll('button').find(b => b.text().includes('运算器'))!.trigger('click'); await flushPromises()
  expect(w.get('.point-card h2').text()).toBe('运算器')
  expect(w.find('.handout-reader').exists()).toBe(false)
  expect(http.post).not.toHaveBeenCalled()
  w.unmount()
})

it('keeps a pending candidate open when navigating a relation within that lecture', async () => {
  const v: any = state()
  const candidate: any = tree('candidate')
  candidate.base_knowledge_revision = 'base'
  candidate.knowledge_points.push({ knowledge_id: 'new-point', name: '候选新增点', statement: '新增点的定义', parent_id: 'c', section_refs: ['cpu'] })
  candidate.relations = [{ id: 'new-edge', source_id: 'cpu-k', target_id: 'new-point', type: 'derives' }]
  v.candidates = [{ job_id: 'job', lesson_id: 'cpu', tree: candidate }]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  await w.get('[data-knowledge-id="cpu-k"]').trigger('click')
  await w.get('.point-card').findAll('button').find(b => b.text() === '候选新增点')!.trigger('click'); await flushPromises()
  expect(w.get('.point-card h2').text()).toBe('候选新增点')
  expect((w.get('.tree-version select').element as HTMLSelectElement).value).toBe('candidate')
  w.unmount()
})

it('renders the detail panel and relation type labels in English', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => en })))
  await setLocale('en')
  const v: any = state()
  v.lesson_options[0].title = 'Lecture 1: Processor'
  v.tree.relations = [{ id: 'cross', source_id: 'cpu-k', target_id: 'memory-k', type: 'applies_to', cross_lesson: true }]
  v.history = [v.tree]
  vi.spyOn(http, 'get').mockResolvedValue({ data: v })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('.tree-search input').attributes('placeholder')).toBe(en.knowledgeProfile.search)
  expect(w.get('.tree-course').text()).not.toContain('Lecture 1:')
  await w.get('[data-knowledge-id="cpu-k"]').trigger('click')
  expect(w.get('.relation').text()).toContain(en.knowledgeFirst.relationTypes.applies_to)
  expect(w.get('.knowledge-detail-pane').attributes('aria-label')).toBe('Knowledge point details')
  w.unmount()
})

it('keeps the adopted lecture tree visible after a regeneration fails before the model call',async()=>{
  const v:any=state()
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  vi.mocked(http.get).mockResolvedValue({data:{...v,jobs:[{id:'failed',status:'failed',knowledge_lesson_id:'cpu',error:{message:'输入容量超限'}}]}})
  await w.findAll('button').find(b=>b.text().includes('生成本讲知识树'))!.trigger('click');await flushPromises()
  expect(w.get('[role="alert"]').text()).toContain('输入容量超限')
  expect(w.get('.mastery-tree').text()).toContain('CPU知识')
  expect((w.get('.tree-version select').element as HTMLSelectElement).value).toBe('base')
  w.unmount()
})
