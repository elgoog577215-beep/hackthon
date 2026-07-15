import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  render: vi.fn(),
  initialize: vi.fn(),
}))

vi.mock('mermaid', () => ({
  default: {
    initialize: mocks.initialize,
    render: mocks.render,
  },
}))

import {
  isMermaidErrorSvg,
  isRenderableMermaidSource,
  prepareMermaidBlockSource,
  renderMermaidSvg,
} from '@/utils/mermaid'

describe('mermaid utils', () => {
  it('识别 Mermaid 支持的图表类型', () => {
    expect(isRenderableMermaidSource('graph TD\nA --> B')).toBe(true)
    expect(isRenderableMermaidSource('sequenceDiagram\nA->>B: hi')).toBe(true)
  })

  it('把缺少类型但有箭头的内容补成 graph TD', () => {
    expect(prepareMermaidBlockSource('A --> B')).toBe('graph TD\nA --> B')
  })

  it('不把旧 lineChart 语法交给 Mermaid 渲染器', async () => {
    await expect(renderMermaidSvg('m1', 'lineChart\nx-axis Iteration')).rejects.toThrow('Unsupported Mermaid diagram type')
    expect(mocks.render).not.toHaveBeenCalled()
  })

  it('识别 Mermaid 返回的错误 SVG 并进入降级路径', async () => {
    mocks.render.mockResolvedValueOnce({
      svg: '<svg><g><text class="error-text">Syntax error in text</text><text>mermaid version 11.12.2</text></g></svg>',
    })

    await expect(renderMermaidSvg('m2', 'graph TD\nA --> B')).rejects.toThrow('Mermaid returned an error diagram')
    expect(isMermaidErrorSvg('<svg><text class="error-text">Syntax error in text</text></svg>')).toBe(true)
  })
})
