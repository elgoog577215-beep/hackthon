import { beforeEach, describe, expect, it } from 'vitest'
import { renderMarkdown } from '@/utils/markdown'
import {
  onRenderFailure,
  recordRenderFailure,
  renderFailureCount,
  renderFailures,
  resetRenderFailureListeners,
  resetRenderFailures,
  withRenderContext,
} from '@/utils/render-diagnostics'

describe('L3a 渲染失败可观测', () => {
  beforeEach(() => {
    resetRenderFailures()
    resetRenderFailureListeners()
  })

  it('KaTeX 渲染失败时记录信号，而不是静默降级', () => {
    // `\frac` with no arguments is invalid; KaTeX throws and the renderer
    // degrades to <code class="math-fallback">. That degradation used to leave
    // no trace at all.
    const html = renderMarkdown('公式：$\\frac{}{$ 结束')

    expect(html).toContain('math-fallback')
    expect(renderFailureCount()).toBeGreaterThan(0)
    expect(renderFailures()[0]!.kind).toBe('math')
  })

  it('正常公式不产生失败记录，不制造噪声', () => {
    const html = renderMarkdown('公式：$x^2 + y^2 = z^2$')

    expect(html).not.toContain('math-fallback')
    expect(renderFailureCount()).toBe(0)
  })

  it('失败可归属到具体内容块，供发布门定位', () => {
    withRenderContext('L2-1-1', () => {
      renderMarkdown('坏公式 $\\frac{}{$ 一')
    })
    withRenderContext('L2-2-3', () => {
      renderMarkdown('坏公式 $\\begin{}{$ 二')
    })

    expect(renderFailureCount('L2-1-1')).toBe(1)
    expect(renderFailureCount('L2-2-3')).toBe(1)
    expect(renderFailureCount()).toBe(2)
  })

  it('订阅者能实时收到失败事件，可用于上报', () => {
    const seen: string[] = []
    const stop = onRenderFailure(failure => seen.push(failure.kind))

    renderMarkdown('坏公式 $\\frac{}{$ 三')
    expect(seen).toEqual(['math'])

    stop()
    renderMarkdown('又一个坏公式 $\\frac{}{$ 四')
    expect(seen).toEqual(['math'])
  })

  it('上报器自身抛错不能影响渲染', () => {
    onRenderFailure(() => {
      throw new Error('reporter is broken')
    })

    expect(() => renderMarkdown('坏公式 $\\frac{}{$ 五')).not.toThrow()
    expect(renderFailureCount()).toBe(1)
  })

  it('记录的原文有长度上限，避免超长内容撑爆内存', () => {
    recordRenderFailure('block', 'x'.repeat(5000), new Error('y'.repeat(5000)))
    const failure = renderFailures()[0]!

    expect(failure.source.length).toBeLessThanOrEqual(400)
    expect(failure.detail.length).toBeLessThanOrEqual(400)
  })

  it('记录条数有上限，长时间运行不会无限增长', () => {
    for (let index = 0; index < 260; index += 1) {
      recordRenderFailure('math', `formula-${index}`)
    }

    const all = renderFailures()
    expect(all.length).toBe(200)
    // The newest records survive: the tail is what a reporter needs.
    expect(all[all.length - 1]!.source).toBe('formula-259')
  })

  it('返回的是副本，调用方无法篡改内部记录', () => {
    recordRenderFailure('math', 'x')
    renderFailures().push({ kind: 'block', source: 'injected', detail: '', contextId: '' })

    expect(renderFailureCount()).toBe(1)
  })
})
