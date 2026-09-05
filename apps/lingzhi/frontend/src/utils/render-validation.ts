/**
 * Real-render validation of course content, callable by the publication gate.
 *
 * `markdown-real-katex.test.ts` already proved this works: it runs the real
 * `renderMarkdown` (and therefore real `katex.renderToString`) over dirty model
 * output and asserts no `.katex-error` survives. But it is a fixed-corpus
 * regression test — it never sees the content a course actually generated.
 *
 * This module is the same capability with the corpus removed, so a caller can
 * hand it arbitrary blocks and get back a verdict. It reuses the L3a diagnostic
 * channel rather than re-deriving failures: a formula that KaTeX rejects is
 * already recorded there, and `.katex-error`/`math-fallback` in the output are
 * the visible evidence of the same event.
 */

import { renderMarkdown } from './markdown'
import {
  renderFailureCount,
  resetRenderFailures,
  withRenderContext,
} from './render-diagnostics'

export interface RenderValidationIssue {
  contextId: string
  /** `katex_error`: KaTeX emitted its red error node.
   *  `math_fallback`: the formula degraded to raw source.
   *  `render_failure`: the renderer reported a failure through diagnostics. */
  code: 'katex_error' | 'math_fallback' | 'render_failure'
  detail: string
}

export interface RenderValidationResult {
  passed: boolean
  checkedCount: number
  issues: RenderValidationIssue[]
  /** Per-content counts, for a gate that wants to point at one block. */
  failureCountByContext: Record<string, number>
}

export interface ContentToValidate {
  id: string
  content: string
}

function collect(html: string, selector: string): string[] {
  // jsdom in tests, a real document in the browser; both parse the same way.
  const box = document.createElement('div')
  box.innerHTML = html
  return Array.from(box.querySelectorAll(selector)).map(
    element => element.getAttribute('title') || element.textContent || '',
  )
}

/**
 * Render every piece of content for real and report what broke.
 *
 * Note this deliberately renders rather than pattern-matches: the whole point
 * of L3b is that only a real renderer catches mismatched environment names,
 * misnested groups and unbalanced `\left\right`, which no regex tier can see.
 */
export function validateRenderedContent(
  items: ContentToValidate[],
): RenderValidationResult {
  const issues: RenderValidationIssue[] = []
  const failureCountByContext: Record<string, number> = {}
  let checkedCount = 0

  for (const item of items) {
    const contextId = String(item?.id || '')
    const content = String(item?.content || '')
    if (!content.trim()) continue
    checkedCount += 1

    // Each block is measured independently so one broken block cannot mask or
    // inflate another's count.
    resetRenderFailures()
    const html = withRenderContext(contextId, () => renderMarkdown(content))

    for (const detail of collect(html, '.katex-error')) {
      issues.push({ contextId, code: 'katex_error', detail })
    }
    for (const detail of collect(html, '.math-fallback')) {
      issues.push({ contextId, code: 'math_fallback', detail })
    }
    const reported = renderFailureCount(contextId)
    if (reported > 0) {
      failureCountByContext[contextId] = reported
      // Only add a distinct issue when the visible markers missed it, so a
      // single bad formula is not counted three times.
      const alreadySeen = issues.some(issue => issue.contextId === contextId)
      if (!alreadySeen) {
        issues.push({
          contextId,
          code: 'render_failure',
          detail: `${reported} 处渲染失败`,
        })
      }
    }
  }

  resetRenderFailures()
  return {
    passed: issues.length === 0,
    checkedCount,
    issues,
    failureCountByContext,
  }
}

/**
 * Shape the result for `evaluate_node_content`'s `render_diagnostics` argument.
 *
 * Keeps the wire contract in one place so the backend gate and this validator
 * cannot drift apart.
 */
export function renderDiagnosticsFor(
  result: RenderValidationResult,
  contextId: string,
): { math_failure_count: number; block_failure_count: number } {
  const forContext = result.issues.filter(issue => issue.contextId === contextId)
  return {
    math_failure_count: forContext.filter(
      issue => issue.code === 'katex_error' || issue.code === 'math_fallback',
    ).length,
    block_failure_count: forContext.filter(issue => issue.code === 'render_failure').length,
  }
}
