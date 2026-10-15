import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import View from '../../components/TeacherKnowledgeManager.vue'
import { setLocale } from '../../shared/i18n'
import zh from '../../../public/locales/zh/translation.json'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../../utils/http', () => ({ default: api }))
beforeEach(async () => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
  await setLocale('zh')
  api.post.mockResolvedValue({ data: {} })
})
const state = () => ({ enabled: true, workflow: 'knowledge_first_generic_v1', source_mode: 'handouts',
  can_edit: true, title: '计算机系统', document_revision: 'd', knowledge_revision: '',
  can_generate_tree: true, source_handouts: [{ lesson_id: 'cpu', title: 'CPU', script_revision_id: 'r' }],
  jobs: [], history: [], handouts: [], inputs: { material_asset_ids: [] } })

it('uses handouts without an upload prerequisite or another course setup form', async () => {
  api.get.mockResolvedValue({ data: state() })
  const w = mount(View, { props: { courseId: 'c' } }); await flushPromises()
  expect(w.find('input[type=file]').exists()).toBe(false)
  expect(w.find('textarea').exists()).toBe(false)
  const generate = w.findAll('button').find(b => b.text() === '根据讲义生成知识树')!
  expect(generate.exists()).toBe(true)
  expect(generate.attributes('disabled')).toBeUndefined()
  await generate.trigger('click'); await flushPromises()
  expect(api.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree', expect.objectContaining({ source_mode: 'handouts' }))
  w.unmount()
})

it('guides an empty course back to the normal handout workflow', async () => {
  api.get.mockResolvedValue({ data: { ...state(), can_generate_tree: false, source_handouts: [] } })
  const w = mount(View, { props: { courseId: 'c' } }); await flushPromises()
  await w.findAll('button').find(b => b.text() === '去准备讲义')!.trigger('click')
  expect(w.emitted('open-handouts')).toHaveLength(1)
  expect(w.text()).toContain('资料可选')
  expect(api.post).not.toHaveBeenCalled()
  w.unmount()
})

it('renders and selects leaves below four recursive category levels', async () => {
  const tree = { revision_id: 'tree', categories: Array.from({ length: 4 }, (_, i) => ({ id: `c${i}`, name: `分类${i}`, parent_id: i ? `c${i - 1}` : null })),
    knowledge_points: [{ knowledge_id: 'kp', parent_id: 'c3', name: 'CPU作用', statement: 'CPU执行指令', source_refs: [] }], relations: [], misconceptions: [] }
  api.get.mockResolvedValue({ data: { ...state(), tree, history: [tree], knowledge_revision: 'tree' } })
  const w = mount(View, { props: { courseId: 'c' } }); await flushPromises()
  const leaf = w.find('[data-knowledge-id="kp"]')
  expect(leaf).toBeDefined()
  await leaf!.trigger('click')
  expect(w.get('.point-card h2').text()).toBe('CPU作用')
  w.unmount()
})

it('reads every section of an ordinary handout before a tree has been adopted', async () => {
  api.get.mockResolvedValue({ data: { ...state(), handouts: [{ topic: 'cpu', title: 'CPU', current_revision_id: 'r', revisions: [{ revision_id: 'r', sections: [
    { section_node_id: 'one', blocks: [{ block_id: 'b1', content: '第一节段落' }] },
    { section_node_id: 'two', blocks: [{ block_id: 'b2', content: '第二节段落' }] },
  ] }] }] } })
  const w = mount(View, { props: { courseId: 'c' } }); await flushPromises()
  await w.findAll('button').find(b => b.text() === '查看讲义')!.trigger('click')
  expect(w.text()).toContain('第一节段落')
  expect(w.text()).toContain('第二节段落')
  expect(w.text()).not.toContain('先采用知识树')
  expect(w.findAll('button').some(b => b.text() === '生成本讲讲义')).toBe(false)
  w.unmount()
})
