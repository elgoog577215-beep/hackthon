import { beforeEach, describe, expect, it } from 'vitest'
import {
  renderDiagnosticsFor,
  validateRenderedContent,
} from '@/utils/render-validation'
import { resetRenderFailures } from '@/utils/render-diagnostics'

describe('L3b 真实渲染校验接入发布链路', () => {
  beforeEach(() => {
    resetRenderFailures()
  })

  it('干净内容通过校验', () => {
    const result = validateRenderedContent([
      { id: 'L2-1-1', content: '勾股定理：$a^2 + b^2 = c^2$，其中 $c$ 是斜边。' },
      { id: 'L2-1-2', content: '## 小节\n\n普通正文，没有公式。' },
    ])

    expect(result.passed).toBe(true)
    expect(result.checkedCount).toBe(2)
    expect(result.issues).toEqual([])
  })

  it('坏公式被真实渲染拦下，并定位到具体内容块', () => {
    const result = validateRenderedContent([
      { id: 'L2-1-1', content: '正常：$x^2$' },
      { id: 'L2-2-3', content: '坏的：$\\frac{}{$' },
    ])

    expect(result.passed).toBe(false)
    expect(result.issues.every(issue => issue.contextId === 'L2-2-3')).toBe(true)
  })

  it('检出正则层看不见的环境名不匹配', () => {
    // `$$` count is even and every delimiter is paired, so the backend's
    // string checks pass it. Only a real renderer sees the mismatch.
    const content = '$$\\begin{aligned}x=1\\end{align}$$'
    const result = validateRenderedContent([{ id: 'L2-3-1', content }])

    expect(content.split('$$').length - 1).toBe(2)
    expect(result.passed).toBe(false)
  })

  it('检出 \\left 与 \\right 不配对', () => {
    const result = validateRenderedContent([
      { id: 'L2-4-1', content: '$$\\left( x + y$$' },
    ])

    expect(result.passed).toBe(false)
  })

  it('空内容不计入校验数量，也不算失败', () => {
    const result = validateRenderedContent([
      { id: 'a', content: '   ' },
      { id: 'b', content: '' },
    ])

    expect(result.checkedCount).toBe(0)
    expect(result.passed).toBe(true)
  })

  it('一个坏块不会污染其他块的计数', () => {
    const result = validateRenderedContent([
      { id: 'bad', content: '$\\frac{}{$' },
      { id: 'good', content: '$x + 1$' },
    ])

    expect(result.issues.some(issue => issue.contextId === 'bad')).toBe(true)
    expect(result.issues.some(issue => issue.contextId === 'good')).toBe(false)
  })

  it('同一处坏公式不被重复计成多个失败', () => {
    const result = validateRenderedContent([
      { id: 'L2-5-1', content: '$\\frac{}{$' },
    ])

    // Visible marker plus reported failure describe the same event.
    expect(result.issues.length).toBeLessThanOrEqual(2)
  })

  it('结果可直接转成后端 evaluate_node_content 需要的形状', () => {
    const result = validateRenderedContent([
      { id: 'L2-6-1', content: '$\\frac{}{$' },
      { id: 'L2-6-2', content: '$y = 2$' },
    ])

    const bad = renderDiagnosticsFor(result, 'L2-6-1')
    const good = renderDiagnosticsFor(result, 'L2-6-2')

    expect(bad.math_failure_count + bad.block_failure_count).toBeGreaterThan(0)
    expect(good.math_failure_count).toBe(0)
    expect(good.block_failure_count).toBe(0)
  })

  it('覆盖 markdown-real-katex 已验证过的真实脏输出', () => {
    // These are the exact shapes the existing regression suite proved the
    // renderer handles; the gate must agree they are acceptable.
    const result = validateRenderedContent([
      {
        id: 'dirty-1',
        content:
          '$$$$\\begin{pmatrix}\\cos m & -\\sin m \\\\ \\sin m & \\cos m\\end{pmatrix}$$$$后接文字。',
      },
    ])

    expect(result.passed).toBe(true)
  })
})
