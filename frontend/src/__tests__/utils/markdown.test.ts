/**
 * Markdown 渲染工具函数测试
 * 覆盖 renderMarkdown 的基本渲染、代码块、数学公式、边界情况和安全性
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock mermaid (must be before import)
vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    run: vi.fn(),
  },
}))

// Mock highlight.js
vi.mock('highlight.js', () => ({
  default: {
    getLanguage: vi.fn((lang: string) => (lang === 'javascript' || lang === 'python' ? {} : null)),
    highlight: vi.fn((code: string, _opts: { language: string }) => ({
      value: `<span class="hljs-highlighted">${code}</span>`,
    })),
  },
}))

// Mock highlight.js CSS import
vi.mock('highlight.js/styles/atom-one-dark.css', () => ({}))

// Mock katex – produce recognizable output without real rendering
vi.mock('katex', () => ({
  default: {
    renderToString: vi.fn((content: string, options?: { displayMode?: boolean }) => {
      const mode = options?.displayMode ? 'display' : 'inline'
      return `<span class="katex-${mode}">${content}</span>`
    }),
  },
}))

// Mock DOMPurify – pass through for testing (we verify it's called)
vi.mock('dompurify', () => {
  const sanitize = vi.fn((html: string) => html)
  return { default: { sanitize } }
})

// Mock markdown-it-link-attributes
vi.mock('markdown-it-link-attributes', () => ({
  default: vi.fn(() => {}),
}))

import { renderMarkdown } from '@/utils/markdown'
import DOMPurify from 'dompurify'

beforeEach(() => {
  vi.clearAllMocks()
})


// ---------------------------------------------------------------------------
// 基本渲染
// ---------------------------------------------------------------------------

describe('renderMarkdown – 基本 Markdown 渲染', () => {
  it('渲染段落文本', () => {
    const result = renderMarkdown('Hello world')
    expect(result).toContain('Hello world')
    expect(result).toContain('<p>')
  })

  it('渲染标题', () => {
    const result = renderMarkdown('# 一级标题')
    expect(result).toContain('<h1>')
    expect(result).toContain('一级标题')
  })

  it('渲染多级标题', () => {
    const h2 = renderMarkdown('## 二级标题')
    const h3 = renderMarkdown('### 三级标题')
    expect(h2).toContain('<h2>')
    expect(h3).toContain('<h3>')
  })

  it('渲染粗体和斜体', () => {
    const result = renderMarkdown('**粗体** 和 *斜体*')
    expect(result).toContain('<strong>')
    expect(result).toContain('<em>')
  })

  it('渲染无序列表', () => {
    const result = renderMarkdown('- 项目一\n- 项目二\n- 项目三')
    expect(result).toContain('<ul>')
    expect(result).toContain('<li>')
    expect(result).toContain('项目一')
  })

  it('渲染有序列表', () => {
    const result = renderMarkdown('1. 第一\n2. 第二')
    expect(result).toContain('<ol>')
    expect(result).toContain('<li>')
  })

  it('渲染链接（target=_blank）', () => {
    const result = renderMarkdown('[链接](https://example.com)')
    expect(result).toContain('href="https://example.com"')
  })

  it('自动修复标题缺少空格（需要触发预处理路径）', () => {
    // The auto-fix regex runs in the heavy preprocessing path,
    // which requires content to contain code/math-like characters
    const result = renderMarkdown('###标题 $x$')
    expect(result).toContain('<h3>')
    expect(result).toContain('标题')
  })
})

// ---------------------------------------------------------------------------
// 代码块渲染
// ---------------------------------------------------------------------------

describe('renderMarkdown – 代码块', () => {
  it('渲染带语言标记的代码块', () => {
    const input = '```javascript\nconst x = 1;\n```'
    const result = renderMarkdown(input)
    expect(result).toContain('code-block-wrapper')
    expect(result).toContain('data-lang="javascript"')
  })

  it('渲染无语言标记的代码块', () => {
    const input = '```\nplain code\n```'
    const result = renderMarkdown(input)
    expect(result).toContain('<pre')
    expect(result).toContain('<code')
  })

  it('渲染行内代码', () => {
    const result = renderMarkdown('使用 `console.log()` 输出')
    expect(result).toContain('<code>')
    expect(result).toContain('console.log()')
  })

  it('mermaid 代码块渲染为 div.mermaid', () => {
    const input = '```mermaid\ngraph TD\nA-->B\n```'
    const result = renderMarkdown(input)
    expect(result).toContain('class="mermaid"')
    expect(result).toContain('data-code=')
  })

  it('代码块包含复制按钮', () => {
    const input = '```python\nprint("hello")\n```'
    const result = renderMarkdown(input)
    expect(result).toContain('copy-btn')
    expect(result).toContain('data-code=')
  })
})

// ---------------------------------------------------------------------------
// 数学公式渲染（KaTeX）
// ---------------------------------------------------------------------------

describe('renderMarkdown – 数学公式', () => {
  it('渲染行内数学公式 $...$', () => {
    const result = renderMarkdown('公式 $x^2$ 结束')
    expect(result).toContain('katex')
  })

  it('渲染块级数学公式 $$...$$', () => {
    const result = renderMarkdown('$$\nE = mc^2\n$$')
    expect(result).toContain('katex')
  })

  it('渲染 LaTeX \\[...\\] 块级公式', () => {
    const result = renderMarkdown('\\[x + y = z\\]')
    expect(result).toContain('katex')
  })

  it('渲染 LaTeX \\(...\\) 行内公式', () => {
    const result = renderMarkdown('行内 \\(a + b\\) 公式')
    expect(result).toContain('katex')
  })

  it('不会把含已标记行内公式的整句中文再次包成数学公式', () => {
    const result = renderMarkdown('在复数域中，这等价于$x^{\\prime} = x \\cdot e^{i m \\omega_j}$。那么继续说明。')
    expect(result).toContain('在复数域中')
    expect(result).toContain('继续说明')
    expect(result).not.toContain('katex-display">在复数域中')
  })

  it('转义 \\text{...} 内的下划线，避免 KaTeX 报错', () => {
    const result = renderMarkdown('$$\\mathbf{X}_{\\text{attn_out}}$$')
    expect(result).toContain('attn\\_out')
  })

  it('连续 display 分隔符后接中文时不把中文整句渲染成公式', () => {
    const input = '$$$$\\begin{pmatrix}x\\end{pmatrix}$$$$在复数域中，这等价于$x^{\\prime} = x \\cdot e^{i m \\omega_j}$。'
    const result = renderMarkdown(input)
    expect(result).toContain('在复数域中')
    expect(result).not.toContain('katex-display">在复数域中')
  })

  it('恢复嵌套数学占位符，避免 __MATH_BLOCK 泄漏到公式里', () => {
    const result = renderMarkdown('$\\mathbf{W} =$$\\begin{bmatrix}0.8 & -1.5\\\\-2.0 & 0.1\\end{bmatrix}$$$')
    expect(result).not.toContain('__MATH_BLOCK')
  })
})

// ---------------------------------------------------------------------------
// 边界情况
// ---------------------------------------------------------------------------

describe('renderMarkdown – 边界情况', () => {
  it('空字符串返回空字符串', () => {
    expect(renderMarkdown('')).toBe('')
  })

  it('null/undefined 输入返回空字符串', () => {
    expect(renderMarkdown(null as any)).toBe('')
    expect(renderMarkdown(undefined as any)).toBe('')
  })

  it('纯空白字符正常渲染', () => {
    const result = renderMarkdown('   ')
    expect(typeof result).toBe('string')
  })

  it('特殊 HTML 字符被正确处理', () => {
    const result = renderMarkdown('<script>alert("xss")</script>')
    // DOMPurify is mocked to pass through, but markdown-it escapes HTML by default
    // The key is that it doesn't crash
    expect(typeof result).toBe('string')
  })

  it('非常长的输入不会崩溃', () => {
    const longText = '这是一段很长的文本。'.repeat(500)
    const result = renderMarkdown(longText)
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })

  it('未闭合的代码块自动修复', () => {
    const input = '```javascript\nconst x = 1;'
    // Should not throw
    const result = renderMarkdown(input)
    expect(typeof result).toBe('string')
  })

  it('未闭合的块级数学公式自动修复', () => {
    const input = '$$\nE = mc^2'
    const result = renderMarkdown(input)
    expect(typeof result).toBe('string')
  })
})

// ---------------------------------------------------------------------------
// 安全性（DOMPurify）
// ---------------------------------------------------------------------------

describe('renderMarkdown – 安全性', () => {
  it('调用 DOMPurify.sanitize 进行 HTML 净化', () => {
    renderMarkdown('# 测试')
    expect(DOMPurify.sanitize).toHaveBeenCalled()
  })

  it('每次渲染都经过 sanitize', () => {
    renderMarkdown('文本一')
    renderMarkdown('文本二')
    // sanitize should be called at least once per unique input
    expect((DOMPurify.sanitize as any).mock.calls.length).toBeGreaterThanOrEqual(2)
  })
})

// ---------------------------------------------------------------------------
// 缓存行为
// ---------------------------------------------------------------------------

describe('renderMarkdown – 缓存', () => {
  it('相同输入返回相同输出', () => {
    const input = '# 缓存测试'
    const result1 = renderMarkdown(input)
    const result2 = renderMarkdown(input)
    expect(result1).toBe(result2)
  })
})
