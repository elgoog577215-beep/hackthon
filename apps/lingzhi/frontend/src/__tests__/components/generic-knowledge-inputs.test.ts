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

it('accepts legacy Office materials and allows text-extracted PPT after flagging it for review', async () => {
  const state: any = { enabled: true, workflow: 'knowledge_first_generic_v1', can_edit: true, title: '课程',
    document_revision: 'd', knowledge_revision: '', jobs: [], history: [], handouts: [], tree: null,
    inputs: { requirements: '课程目标', target_audience: '', lesson_count: 1, material_asset_ids: [] } }
  const assets: any[] = [{ material_asset_id: 'empty-ppt', filename: '没有文字.ppt', parse_status: 'degraded', parse_quality: { block_count: 0 } }]
  api.get.mockImplementation(async (url: string) => ({ data: url === '/api/materials' ? { assets } : state }))
  api.post.mockImplementation(async (url: string) => {
    if (url === '/api/materials') {
      const asset = { asset_id: 'legacy-ppt', material_asset_id: 'legacy-ppt', filename: '旧版课件.ppt', parse_status: 'degraded', parse_quality: { block_count: 2 } }
      assets.push(asset)
      return { data: asset }
    }
    return { data: {} }
  })
  const wrapper = mount(View, { props: { courseId: 'c' } }); await flushPromises()
  const fileInput = wrapper.get('input[type="file"]')
  expect(fileInput.attributes('accept')).toContain('.ppt')
  expect(fileInput.attributes('accept')).toContain('.doc')
  expect(fileInput.attributes('accept')).toContain('.xls')
  Object.defineProperty(fileInput.element, 'files', { value: [new File(['legacy'], '旧版课件.ppt')] })
  fileInput.element.dispatchEvent(new Event('change'))
  await flushPromises()

  const choices = wrapper.findAll('input[type="checkbox"]')
  const legacyChoice = choices.find(choice => (choice.element as HTMLInputElement).value === 'legacy-ppt')!
  const emptyChoice = choices.find(choice => (choice.element as HTMLInputElement).value === 'empty-ppt')!
  expect((legacyChoice.element as HTMLInputElement).checked).toBe(true)
  expect(legacyChoice.attributes('disabled')).toBeUndefined()
  expect(emptyChoice.attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('已提取，建议复核')
  wrapper.unmount()
})
