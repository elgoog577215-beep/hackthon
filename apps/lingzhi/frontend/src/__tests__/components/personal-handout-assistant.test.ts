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
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('personal handout assistant', () => {
  it('describes the selected passage instead of offering a misleading whole-chapter shortcut', async () => {
    const view = page(); await flushPromises()
    expect(view.get('.assistant-prompts button').text()).toBe('解释选中内容')
    await view.setProps({ context: { ...context, block_id: '', quote: '' } })
    expect(view.get('.assistant-prompts button').text()).toBe('解释这一章')
  })
  it('restores history before accepting a question, keeping text typed while waiting', async () => {
    let finish!: (value: unknown) => void
    api.assistant.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const view = page()
    await view.get('textarea').setValue('先写下这个问题')
    expect(view.text()).toContain('正在恢复这份讲义的对话')
    expect(view.get('footer button').attributes('disabled')).toBeDefined()
    await view.get('form').trigger('submit')
    expect(api.ask).not.toHaveBeenCalled()
    finish({ conversation_id: 'conv', messages: [] }); await flushPromises()
    expect(view.get('textarea').element).toHaveProperty('value', '先写下这个问题')
    expect(view.get('footer button').attributes('disabled')).toBeUndefined()
  })
  it('ignores an older history response arriving after a successful send', async () => {
    vi.useFakeTimers()
    const view = page(); await flushPromises()
    api.ask.mockRejectedValueOnce(new Error('响应丢失'))
    await view.get('textarea').setValue('解释向量')
    await view.get('form').trigger('submit'); await flushPromises()
    let oldHistory!: (value: unknown) => void
    api.assistant.mockImplementationOnce(() => new Promise(resolve => { oldHistory = resolve }))
    await view.get('[role="alert"] button').trigger('click')
    api.ask.mockResolvedValueOnce(conversation('pending'))
    api.assistant.mockResolvedValue(conversation('running', '新的已保存回复'))
    await view.get('form').trigger('submit'); await flushPromises()
    oldHistory({ conversation_id: 'conv', messages: [] }); await flushPromises()
    expect(view.text()).toContain('新的已保存回复')
    expect(view.get('footer button').attributes('disabled')).toBeDefined()
    expect(api.ask).toHaveBeenCalledTimes(2)
  })
  it('follows growing replies, pauses when reading earlier text, and returns on request', async () => {
    vi.useFakeTimers()
    api.assistant.mockResolvedValue(conversation('running', '第一段回复'))
    const view = page(), thread = view.get('.assistant-thread').element as HTMLElement
    let height = 400, top = 0
    Object.defineProperties(thread, {
      clientHeight: { get: () => 200 }, scrollHeight: { get: () => height },
      scrollTop: { get: () => top, set: value => { top = Math.max(0, Math.min(value, height - 200)) } },
    })
    await flushPromises(); expect(top).toBe(200)
    height = 700; api.assistant.mockResolvedValue(conversation('running', '第二段更长的回复'))
    await vi.advanceTimersByTimeAsync(1500); await flushPromises(); expect(top).toBe(500)
    thread.scrollTop = 80; await view.get('.assistant-thread').trigger('scroll')
    height = 900; api.assistant.mockResolvedValue(conversation('complete', '最后一段完整的回复'))
    await vi.advanceTimersByTimeAsync(1500); await flushPromises(); expect(top).toBe(80)
    await view.get('.latest-reply').trigger('click'); await flushPromises(); expect(top).toBe(700)
  })
  it('follows a diagram laid out after its text without pulling a reader away from earlier content', async () => {
    let resized!: () => void
    vi.stubGlobal('ResizeObserver', class {
      constructor(private callback: () => void) {}
      observe(target: Element) { if (target.parentElement?.classList.contains('assistant-thread')) resized = this.callback }
      disconnect() {}
    })
    api.assistant.mockResolvedValue(conversation('complete', 'A diagram will be laid out here'))
    const view = page(), thread = view.get('.assistant-thread').element as HTMLElement
    let height = 400, top = 0
    Object.defineProperties(thread, {
      clientHeight: { get: () => 200 }, scrollHeight: { get: () => height },
      scrollTop: { get: () => top, set: value => { top = Math.max(0, Math.min(value, height - 200)) } },
    })
    await flushPromises(); expect(top).toBe(200)
    height = 800; await view.get('.assistant-thread').trigger('scroll')
    resized(); await flushPromises(); expect(top).toBe(600)
    thread.scrollTop = 50; await view.get('.assistant-thread').trigger('scroll')
    height = 1100; resized(); await flushPromises(); expect(top).toBe(50)
    expect(view.find('.latest-reply').exists()).toBe(true)
  })
  it('keeps the submitted context and new input when the reader changes chapter while waiting', async () => {
    const view = page(); await flushPromises()
    let finish!: (value: unknown) => void
    api.ask.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await view.get('textarea').setValue('解释选中内容')
    await view.get('form').trigger('submit')
    await view.setProps({ context: { ...context, section_id: 's2', section_title: '矩阵', quote: '' } })
    await view.get('textarea').setValue('下一章的问题')
    api.assistant.mockResolvedValue(conversation('complete', '第一章的回复'))
    finish(conversation('complete', '第一章的回复')); await flushPromises()
    expect(api.ask.mock.calls[0]![1]).toMatchObject({ section_id: 's1', quote: 'u + 2v' })
    expect(view.get('.assistant-message small').text()).toContain('向量 · 线性组合')
    expect(view.get('textarea').element).toHaveProperty('value', '下一章的问题')
  })
  it('still allows asking when browser draft storage is unavailable', async () => {
    const view = page(); await flushPromises()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage blocked') })
    api.ask.mockResolvedValue(conversation('complete', '已保存'))
    await view.get('textarea').setValue('请解释')
    await view.get('form').trigger('submit'); await flushPromises()
    expect(api.ask).toHaveBeenCalledTimes(1)
    expect(view.find('[role="alert"]').exists()).toBe(false)
  })
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
    expect(view.get('.personal-assistant').attributes('aria-label')).toBe('AI assistant')
    expect(view.text()).toContain('Discussing')
    expect(view.text()).toContain('Explain with a diagram')
    expect(view.text()).toContain('u + 2v')
  })
})
