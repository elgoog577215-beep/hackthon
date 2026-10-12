import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import Workbench from '@/components/TeacherCourseWorkbench.vue'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'

beforeEach(async () => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
  await setLocale('zh')
  vi.spyOn(http, 'get').mockResolvedValue({ data: { total: 0 } })
})

it('switches the existing center to knowledge and restores the original stage without opening a dialog', async () => {
  const w = shallowMount(Workbench, { props: { courseId: 'c', courseTitle: '计算机系统', generationOptions: {} } })
  await flushPromises()
  const knowledge = w.findAll('.stage-rail button').find(b => b.text().includes('知识树'))!
  await knowledge.trigger('click'); await flushPromises()
  expect(w.find('.workbench-center teacher-knowledge-manager-stub').exists()).toBe(true)
  expect(w.getComponent(Manager).props('treeOnly')).toBe(true)
  expect(w.find('.context-pane').exists()).toBe(false)
  expect(knowledge.classes()).toContain('active')
  expect(w.emitted('open-knowledge')).toBeUndefined()
  await w.findAll('.stage-rail button').find(b => b.text().includes('大纲'))!.trigger('click')
  await flushPromises()
  expect(w.findComponent(Manager).exists()).toBe(false)
  expect(w.get('.workbench-center').text()).toContain('教学目标')
  w.unmount()
})

it('tree-only mode keeps the tree and version actions without lecture tabs or unrelated panels', async () => {
  const tree = { revision_id: 'k1', categories: [{ id: 'root', name: '处理器', parent_id: null }],
    knowledge_points: [{ knowledge_id: 'pc', name: '程序计数器', statement: 'PC保存指令地址', parent_id: 'root', source_refs: [] }], relations: [], misconceptions: [] }
  vi.mocked(http.get).mockResolvedValue({ data: { enabled: true, can_edit: true, workflow: 'knowledge_first_generic_v1', source_mode: 'handouts',
    title: '计算机系统', tree, history: [tree], knowledge_revision: 'k1', jobs: [], handouts: [], source_handouts: [], can_generate_tree: true } })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } })
  await flushPromises()
  expect(w.get('nav').text()).toContain('程序计数器')
  expect(w.find('.point-card').exists()).toBe(false)
  expect(w.find('.handout-source-panel').exists()).toBe(false)
  expect(w.find('.tabs').exists()).toBe(false)
  expect(w.find('.source-review').exists()).toBe(false)
  expect(w.find('.manager-tools').exists()).toBe(false)
  expect(w.findAll('button').some(b => b.text().includes('更新候选'))).toBe(true)
  w.unmount()
})
