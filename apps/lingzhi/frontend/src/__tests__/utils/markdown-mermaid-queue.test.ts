import { describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createMarkdownMermaidQueue, identifyMermaidSvg } from '@/utils/markdown-mermaid-queue'

const svg = '<svg xmlns="http://www.w3.org/2000/svg" id="diagram"><path id="node"/></svg>'
const host = () => document.createElement('div')
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(yes => { resolve = yes })
  return { promise, resolve }
}

describe('bounded Mermaid work', () => {
  it('drops obsolete queued sources before they run and suppresses a removed active host', async () => {
    const pending = deferred<string>()
    const render = vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValue(svg)
    const display = vi.fn()
    const queue = createMarkdownMermaidQueue('queue', render, display)
    const first = host(), old = host(), current = host()
    queue.observe(first, 'first')
    queue.observe(old, 'obsolete'); queue.forget(old)
    queue.observe(current, 'current'); queue.forget(first)
    pending.resolve(svg); await flushPromises()
    expect(render.mock.calls.map(call => call[1])).toEqual(['first', 'current'])
    expect(display).toHaveBeenCalledOnce()
    expect(display.mock.calls[0]![0]).toBe(current)
    queue.dispose()
  })

  it('retries a failed source on a fresh host after a temporary import failure', async () => {
    const render = vi.fn().mockRejectedValueOnce(new Error('Failed to fetch dynamically imported module')).mockResolvedValueOnce(svg)
    const display = vi.fn()
    const queue = createMarkdownMermaidQueue('recover', render, display)
    const first = host(), next = host()
    queue.observe(first, 'same'); await flushPromises()
    queue.observe(first, 'same'); await flushPromises()
    expect(render).toHaveBeenCalledOnce()
    queue.forget(first); queue.observe(next, 'same'); await flushPromises()
    expect(render).toHaveBeenCalledTimes(2)
    expect(display.mock.calls[1]![1].svg).toContain('<svg')
    queue.dispose()
  })

  it('limits cached sources and reuses a recently completed source', async () => {
    const render = vi.fn().mockResolvedValue(svg)
    const queue = createMarkdownMermaidQueue('bounded', render, vi.fn())
    for (let i = 0; i < 17; i++) { const el = host(); queue.observe(el, `source-${i}`); await flushPromises(); queue.forget(el) }
    queue.observe(host(), 'source-16'); await flushPromises()
    expect(render).toHaveBeenCalledTimes(17)
    queue.observe(host(), 'source-0'); await flushPromises()
    expect(render).toHaveBeenCalledTimes(18)
    queue.dispose()
  })

  it('ignores active results and removes all queued work after disposal', async () => {
    const pending = deferred<string>()
    const render = vi.fn().mockReturnValue(pending.promise), display = vi.fn()
    const queue = createMarkdownMermaidQueue('disposed', render, display)
    queue.observe(host(), 'active'); queue.observe(host(), 'queued'); queue.dispose()
    pending.resolve(svg); await flushPromises()
    expect(render).toHaveBeenCalledOnce(); expect(display).not.toHaveBeenCalled()
  })

  it('keeps cached SVG marker, link, CSS and accessible-label references local to each instance', () => {
    const source = '<svg xmlns="http://www.w3.org/2000/svg" id="root"><style>#root .node{fill:#ffffff} #node.active{stroke:#112233}</style><title id="title">Title</title><defs><marker id="arrow"/></defs><path id="node" class="node" marker-end="url(#arrow)" aria-labelledby="title"/><use href="#node"/></svg>'
    const doc = new DOMParser().parseFromString(identifyMermaidSvg(source, 'copy'), 'image/svg+xml')
    const path = doc.querySelector('path')!
    const marker = doc.querySelector('marker')!
    expect(path.getAttribute('marker-end')).toBe(`url(#${marker.id})`)
    expect(path.getAttribute('aria-labelledby')).toBe(doc.querySelector('title')!.id)
    expect(doc.querySelector('use')!.getAttribute('href')).toBe(`#${path.id}`)
    expect(doc.querySelector('style')!.textContent).toContain(`#${path.id}.active`)
    expect(doc.querySelector('style')!.textContent).toContain('#ffffff')
    expect(doc.querySelector('style')!.textContent).not.toContain('#root ')
  })

  it('preserves hexadecimal colors that happen to match a user-defined Gantt task ID', () => {
    const source = '<svg xmlns="http://www.w3.org/2000/svg" id="chart"><style>#chart{fill:#fff} #fff.active{stroke:#ffffff;filter:url(#fff)}</style><rect id="fff" fill="#fff" style="stroke:#fff;filter:url(#fff)"/><rect id="ffffff" fill="#ffffff"/></svg>'
    const doc = new DOMParser().parseFromString(identifyMermaidSvg(source, 'gantt'), 'image/svg+xml')
    const rects = doc.querySelectorAll('rect')
    expect(rects[0]!.getAttribute('fill')).toBe('#fff')
    expect(rects[1]!.getAttribute('fill')).toBe('#ffffff')
    expect(rects[0]!.getAttribute('style')).toBe(`stroke:#fff;filter:url(#${rects[0]!.id})`)
    expect(doc.querySelector('style')!.textContent).toBe(`#${doc.documentElement.id}{fill:#fff} #${rects[0]!.id}.active{stroke:#ffffff;filter:url(#${rects[0]!.id})}`)
  })
})
