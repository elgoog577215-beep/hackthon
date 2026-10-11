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
})
it('requires saved owned materials, persists course scope, and never presents a C17 root', async () => {
  const state: any = { enabled: true, workflow: 'knowledge_first_generic_v1', can_edit: true, title: '计算机系统',
    document_revision: 'd', knowledge_revision: '', jobs: [], history: [], handouts: [],
    inputs: { requirements: '', target_audience: '', lesson_count: 2, material_asset_ids: [] } }
  api.get.mockImplementation(async (url: string) => ({ data: url === '/api/materials' ? { assets: [{ material_asset_id: 'owned', filename: '教材.md', parse_status: 'parsed' }] } : state }))
  api.post.mockImplementation(async (url: string, body: any) => { if (url.endsWith('/inputs')) state.inputs = body; return { data: {} } })
  const wrapper = mount(View, { props: { courseId: 'c' } }); await flushPromises()
  const generate = () => wrapper.findAll('button').find(b => b.text() === '生成知识树')!
  expect(generate().attributes('disabled')).toBeDefined()
  expect(wrapper.text()).not.toContain('C17')
  await wrapper.get('textarea').setValue('理解处理器与存储层次')
  await wrapper.get('input[type=checkbox]').setValue(true)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/inputs', expect.objectContaining({ document_revision: 'd', requirements: '理解处理器与存储层次', lesson_count: 2, material_asset_ids: ['owned'] }))
  expect(generate().attributes('disabled')).toBeUndefined()
  expect(api.post).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})
