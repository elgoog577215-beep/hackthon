import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { activeLocale } from '@/shared/i18n'
import { teachingDiagramSamples } from '../../../dev/teaching-diagram-samples'

const mocks = vi.hoisted(() => ({ renderSvg: vi.fn(), post: vi.fn(), success: vi.fn(), error: vi.fn() }))
vi.mock('@/utils/mermaid', async original => ({ ...await original<typeof import('@/utils/mermaid')>(), renderMermaidSvg: mocks.renderSvg }))
vi.mock('@/utils/http', () => ({ default: { post: mocks.post } }))
vi.mock('element-plus', () => ({ ElMessage: { success: mocks.success, error: mocks.error } }))
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

const payload = JSON.stringify(teachingDiagramSamples.find(sample => sample.type === 'flowchart'))
const diagram = '```lingzhi-diagram\n' + payload + '\n```'
const mermaid = '```mermaid\nflowchart LR\nA --> B\n```'
const code = '```python\nprint("a < b")\n```'
const wrappers: VueWrapper[] = []
function create(content: string, enableCodeRun = false) {
  const wrapper = mount(MarkdownRenderer, { attachTo: document.body, props: { content, enableCodeRun } })
  wrappers.push(wrapper)
  return wrapper
}
async function settle() { await new Promise(resolve => requestAnimationFrame(resolve)); await nextTick(); await flushPromises() }
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.clearAllMocks(); activeLocale.value = 'zh'
  mocks.renderSvg.mockResolvedValue('<svg xmlns="http://www.w3.org/2000/svg" id="chart"><defs><marker id="arrow"/></defs><path marker-end="url(#arrow)"/></svg>')
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.setAttribute('open', ''); this.querySelector('button')?.focus() } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.removeAttribute('open'); this.dispatchEvent(new Event('close')) } })
})
afterEach(() => { for (const wrapper of wrappers.splice(0)) wrapper.unmount(); activeLocale.value = 'zh' })

describe('shared renderer keeps active reading state', () => {
  it('keeps the actual dialog, details, focus and scroll nodes connected throughout appended text', async () => {
    const wrapper = create(diagram)
    await settle()
    const host = wrapper.find('.teaching-diagram-host').element
    const details = wrapper.find('details').element as HTMLDetailsElement
    details.open = true
    const scroller = wrapper.find('.diagram-scroll').element as HTMLElement
    scroller.scrollLeft = 37
    await wrapper.find('.diagram-tools button').trigger('click')
    await settle()
    const dialog = wrapper.find('dialog').element as HTMLDialogElement
    const focused = document.activeElement
    const mutations: MutationRecord[] = []
    const observer = new MutationObserver(records => mutations.push(...records))
    observer.observe(wrapper.element, { childList: true, subtree: true })
    for (let i = 1; i <= 8; i++) { await wrapper.setProps({ content: diagram + '\n\n' + '说明'.repeat(i) }); await settle() }
    observer.disconnect()
    expect(wrapper.find('.teaching-diagram-host').element).toBe(host)
    expect(wrapper.find('dialog').element).toBe(dialog)
    expect(dialog.open).toBe(true)
    expect(details.open).toBe(true)
    expect(scroller.scrollLeft).toBe(37)
    expect(document.activeElement).toBe(focused)
    expect(mutations.flatMap(record => [...record.removedNodes]).some(node => node === host || node.contains(dialog))).toBe(false)
  })

  it('keeps identical diagrams distinct and cleans them on replacement or clear', async () => {
    const wrapper = create(diagram)
    await settle()
    const first = wrapper.find('figure').element
    await wrapper.setProps({ content: `${diagram}\n\n${diagram}` }); await settle()
    expect(wrapper.findAll('figure')).toHaveLength(2)
    expect(wrapper.findAll('figure')[0]!.element).toBe(first)
    const ids = wrapper.findAll('[id]').map(node => node.attributes('id'))
    expect(ids.length).toBe(new Set(ids).size)
    await wrapper.setProps({ content: 'New answer' }); await settle()
    expect(first.isConnected).toBe(false)
    expect(wrapper.find('dialog').exists()).toBe(false)
    await wrapper.setProps({ content: diagram }); await settle()
    await wrapper.setProps({ content: '' }); await settle()
    expect(wrapper.element.childNodes.length).toBe(0)
  })

  it('does not render a pending Mermaid fence and renders its completed source only once', async () => {
    const wrapper = create('```mermaid\nflowchart LR\nA -->')
    await settle()
    expect(mocks.renderSvg).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('图表正在生成')
    await wrapper.setProps({ content: mermaid }); await settle()
    const svg = wrapper.find('.mermaid svg').element
    for (let i = 1; i <= 21; i++) { await wrapper.setProps({ content: mermaid + '\n\n' + '文字'.repeat(i) }); await settle() }
    expect(mocks.renderSvg).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.mermaid svg').element).toBe(svg)
  })

  it('shares pending identical Mermaid work and never writes stale results after replacement', async () => {
    const old = deferred<string>()
    mocks.renderSvg.mockReturnValueOnce(old.promise)
    const wrapper = create(`${mermaid}\n\n${mermaid}`)
    await settle()
    expect(mocks.renderSvg).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ content: `${mermaid}\n\n${mermaid}\n\nMore` }); await settle()
    expect(mocks.renderSvg).toHaveBeenCalledTimes(1)
    old.resolve('<svg xmlns="http://www.w3.org/2000/svg" id="same"><path id="node"/></svg>')
    await settle()
    const ids = wrapper.findAll('[id]').map(node => node.attributes('id'))
    expect(ids.length).toBe(new Set(ids).size)
    const stale = deferred<string>()
    mocks.renderSvg.mockReturnValueOnce(stale.promise)
    await wrapper.setProps({ content: mermaid.replace('A --> B', 'C --> D') }); await settle()
    await wrapper.setProps({ content: 'Replacement' }); await settle()
    stale.resolve('<svg xmlns="http://www.w3.org/2000/svg"><text>Old result</text></svg>'); await settle()
    expect(wrapper.text()).toBe('Replacement')
    expect(wrapper.find('svg').exists()).toBe(false)
  })

  it('translates a displayed Mermaid fallback without recreating open details', async () => {
    mocks.renderSvg.mockRejectedValueOnce(new Error('Unsupported'))
    const wrapper = create(mermaid)
    await settle()
    const details = wrapper.find('details').element as HTMLDetailsElement
    details.open = true
    activeLocale.value = 'en'; await settle()
    expect(wrapper.text()).toContain('Diagram cannot be rendered')
    expect(wrapper.text()).toContain('View source')
    expect(wrapper.find('details').element).toBe(details)
    expect(details.open).toBe(true)
    expect(mocks.renderSvg).toHaveBeenCalledTimes(1)
  })
})

describe('shared code actions', () => {
  it('copies exact code once, prevents parent delegation and updates feedback on language switch', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const outer = vi.fn()
    document.body.addEventListener('click', outer)
    const wrapper = create(code)
    await settle()
    await wrapper.find('.copy-btn').trigger('click'); await flushPromises()
    document.body.removeEventListener('click', outer)
    expect(writeText).toHaveBeenCalledOnce()
    expect(writeText).toHaveBeenCalledWith('print("a < b")\n')
    expect(outer).not.toHaveBeenCalled()
    expect(wrapper.find('.copy-btn').text()).toBe('已复制')
    activeLocale.value = 'en'; await settle()
    expect(wrapper.find('.copy-btn').text()).toBe('Copied')
    expect(wrapper.find('.copy-btn').attributes('title')).toBe('Copy code')
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('runs Python from its real metadata and preserves output while appending ordinary text', async () => {
    mocks.post.mockResolvedValue({ data: { output: '<script>safe text</script>' } })
    const wrapper = create(code, true)
    await settle()
    await wrapper.find('.code-run-button').trigger('click'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledOnce()
    expect(mocks.post).toHaveBeenCalledWith('/api/execute', { code: 'print("a < b")\n', language: 'python', timeout: 10 }, { signal: expect.any(AbortSignal) })
    const result = wrapper.find('.code-run-result').element
    await wrapper.setProps({ content: code + '\n\nAfter' }); await settle()
    expect(wrapper.find('.code-run-result').element).toBe(result)
    expect(result.textContent).toBe('<script>safe text</script>')
    expect(wrapper.find('script').exists()).toBe(false)
  })

  it('keeps execution disabled and removes an enabled action when switched off', async () => {
    const wrapper = create(code, false)
    await settle()
    expect(wrapper.find('.code-run-button').exists()).toBe(false)
    await wrapper.setProps({ enableCodeRun: true }); await settle()
    expect(wrapper.find('.code-run-button').exists()).toBe(true)
    await wrapper.setProps({ enableCodeRun: false }); await settle()
    expect(wrapper.find('.code-run-button').exists()).toBe(false)
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('switches an in-flight run and its failure feedback into the active language', async () => {
    const request = deferred<unknown>()
    mocks.post.mockReturnValueOnce(request.promise)
    const wrapper = create(code, true)
    await settle()
    await wrapper.find('.code-run-button').trigger('click')
    activeLocale.value = 'en'; await settle()
    expect(wrapper.find('.code-run-button').text()).toBe('Running…')
    expect(wrapper.find('.code-run-result').text()).toBe('Running…')
    request.reject(new Error('failed')); await settle()
    expect(wrapper.find('.code-run-result').text()).toBe('Execution failed')
    expect(mocks.error).toHaveBeenCalledWith('Code execution failed')
  })

  it.each([null, 'Invalid operation'])('does not present HTTP 200 execution failure as successful empty output (%s)', async error => {
    activeLocale.value = 'en'
    mocks.post.mockResolvedValueOnce({ data: { success: false, output: '', error } })
    const wrapper = create(code, true)
    await settle()
    await wrapper.find('.code-run-button').trigger('click'); await settle()
    expect(wrapper.find('.code-run-result').text()).toContain('Execution failed')
    expect(wrapper.find('.code-run-result').text()).not.toContain('No output')
    if (error) expect(wrapper.find('.code-run-result').text()).toContain(error)
  })

  it('aborts obsolete execution and ignores its completion after the document changes', async () => {
    const request = deferred<unknown>()
    mocks.post.mockReturnValueOnce(request.promise)
    const wrapper = create(code, true)
    await settle()
    await wrapper.find('.code-run-button').trigger('click')
    const signal = mocks.post.mock.calls[0]![2].signal as AbortSignal
    await wrapper.setProps({ content: 'Other document' }); await settle()
    expect(signal.aborted).toBe(true)
    request.resolve({ data: { output: 'obsolete' } }); await settle()
    expect(wrapper.text()).toBe('Other document')
    expect(mocks.success).not.toHaveBeenCalled()
  })
})
