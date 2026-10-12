import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'

const tree = (revision = 'base') => ({ revision_id: revision,
  categories: [{ id: 'c', name: '硬件', parent_id: null }],
  knowledge_points: [{ knowledge_id: 'cpu-k', name: 'CPU知识', parent_id: 'c', section_refs: ['cpu'] },
    { knowledge_id: 'memory-k', name: '主存知识', parent_id: 'c', section_refs: ['memory'] }], relations: [], misconceptions: [] })
const state = () => ({ enabled: true, source_mode: 'handouts', workflow: 'knowledge_first_generic_v1', can_edit: true,
  title: '计算机系统', document_revision: 'd', knowledge_revision: 'base', tree: tree(), history: [tree()], jobs: [], handouts: [],
  can_generate_tree: true, source_handouts: [{ lesson_id: 'cpu' }, { lesson_id: 'memory' }],
  lesson_options: [{ lesson_id: 'cpu', title: '处理器', can_generate: true }, { lesson_id: 'memory', title: '主存', can_generate: true }], candidates: [] })
beforeEach(async () => {
  vi.restoreAllMocks()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zh })))
  await setLocale('zh')
  vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
})

it('switches lecture trees and sends only the selected lecture when generating', async () => {
  vi.spyOn(http, 'get').mockResolvedValue({ data: state() })
  const w = mount(Manager, { props: { courseId: 'c', treeOnly: true } }); await flushPromises()
  expect(w.get('nav').text()).toContain('CPU知识')
  expect(w.get('nav').text()).not.toContain('主存知识')
  await w.get('select[aria-label="讲次"]').setValue('memory')
  expect(w.get('nav').text()).toContain('主存知识')
  expect(w.get('nav').text()).not.toContain('CPU知识')
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
