import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const api = vi.hoisted(() => ({ assistant: vi.fn(), ask: vi.fn(), continueAnswer: vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi: api, StudyApiError: class extends Error { constructor(public status: number, message: string) { super(message) } } }))
import Assistant from '@/components/PersonalHandoutAssistant.vue'
import { activeLocale } from '@/shared/i18n'
const context = { section_id: 's1', section_title: '向量', block_id: 'b1', block_title: '线性组合', quote: 'u + 2v' }
const conversation = (status: string, content = '') => ({ conversation_id: 'conv', messages: [
  { message_id: 'u', role: 'user', content: '为什么？', status: 'complete', context_ref: context },
  { message_id: 'a', role: 'assistant', content, status, context_ref: context, task_ref: { task_id: 'task1' } },
] })
let wrapper: VueWrapper | undefined
function page(owner = 'student-a') { wrapper = mount(Assistant, { props: { ownerId: owner, materialId: 'material-a', revisionId: 'revision-a', context }, global: { stubs: { MarkdownRenderer: { props: ['content'], template: '<div>{{ content }}</div>' } } } }); return wrapper }
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); activeLocale.value = 'zh'; api.assistant.mockResolvedValue({ conversation_id: 'conv', messages: [] }) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers() })
describe('personal handout assistant', () => {
  it('binds selected text to the material revision and polls the same saved response', async () => {
    vi.useFakeTimers(); const view = page(); await flushPromises()
    api.assistant.mockResolvedValue(conversation('running', '开始解释'))
    api.ask.mockResolvedValue(conversation('pending'))
    await view.get('textarea').setValue('为什么线性组合需要系数？')
    await view.get('form').trigger('submit'); await flushPromises()
    expect(api.ask.mock.calls[0]![0]).toBe('material-a')
    expect(api.ask.mock.calls[0]![1]).toMatchObject({ revision_id: 'revision-a', section_id: 's1', block_id: 'b1', quote: 'u + 2v', text: '为什么线性组合需要系数？' })
    expect(view.text()).toContain('开始解释')
    expect(view.get('footer button').attributes('disabled')).toBeDefined()
    api.assistant.mockResolvedValue(conversation('complete', '保存的完整解释'))
    await vi.advanceTimersByTimeAsync(1500); await flushPromises()
    expect(view.text()).toContain('保存的完整解释')
    expect(api.ask).toHaveBeenCalledTimes(1)
    expect(view.text()).toContain('对话已保存')
  })
  it('retains input and request identity after a lost response, restoring only its owner’s draft', async () => {
    const view = page(); await flushPromises()
    api.ask.mockRejectedValue(new Error('连接中断'))
    await view.get('textarea').setValue('请画向量图')
    await view.get('form').trigger('submit'); await flushPromises()
    const id = api.ask.mock.calls[0]![1].request_id
    expect(view.get('textarea').element).toHaveProperty('value', '请画向量图')
    await view.get('form').trigger('submit'); await flushPromises()
    expect(api.ask.mock.calls[1]![1].request_id).toBe(id)
    view.unmount(); wrapper = undefined
    const other = page('student-b'); await flushPromises()
    expect(other.get('textarea').element).toHaveProperty('value', '')
    other.unmount(); wrapper = undefined
    const original = page(); await flushPromises()
    expect(original.get('textarea').element).toHaveProperty('value', '请画向量图')
  })
  it('loads interrupted answers without an automatic retry, continuing only on a click', async () => {
    api.assistant.mockResolvedValue(conversation('paused', '保留的片段'))
    const view = page(); await flushPromises()
    expect(view.text()).toContain('保留的片段')
    expect(api.ask).not.toHaveBeenCalled(); expect(api.continueAnswer).not.toHaveBeenCalled()
    await view.get('.assistant-message.assistant button').trigger('click'); await flushPromises()
    expect(api.continueAnswer).toHaveBeenCalledExactlyOnceWith('material-a', 'task1')
  })
  it('renders the English counterpart and keeps the exact selected context', async () => {
    activeLocale.value = 'en'; const view = page(); await flushPromises()
    expect(view.text()).toContain('AI assistant')
    expect(view.text()).toContain('Explain with a diagram')
    expect(view.text()).toContain('u + 2v')
  })
})
