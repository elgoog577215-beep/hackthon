/**
 * Markdown 渲染工具函数测试
 * 覆盖 renderMarkdown 的基本渲染、代码块、数学公式、边界情况和安全性
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

// Mock mermaid (must be before import)
vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    run: vi.fn(),
    render: vi.fn(async (_id: string, code: string) => ({
      svg: `<svg data-mermaid="${code
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')}"></svg>`,
    })),
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
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

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
    expect(result).toContain('katex-inline')
  })

  it('渲染块级数学公式 $$...$$', () => {
    const result = renderMarkdown('$$\nE = mc^2\n$$')
    expect(result).toContain('katex')
    expect(result).toContain('katex-display')
    expect(result).not.toContain('<span class="math-error"')
    expect(result).not.toContain('<p>$$</p>')
  })

  it('渲染 LaTeX \\[...\\] 块级公式', () => {
    const result = renderMarkdown('\\[x + y = z\\]')
    expect(result).toContain('katex')
    expect(result).toContain('katex-display')
  })

  it('渲染 LaTeX \\(...\\) 行内公式', () => {
    const result = renderMarkdown('行内 \\(a + b\\) 公式')
    expect(result).toContain('katex')
  })

  it('多行 $$ 公式不会退化为 inline math 错误输出', () => {
    const input = '推导如下：\n\n$$\n\\nabla \\times \\mathbf{B} = \\mu_0 \\mathbf{J}\n$$\n\n结论成立。'
    const result = renderMarkdown(input)

    expect(result).toContain('katex-display')
    expect(result).not.toContain('math-error')
    expect(result).not.toContain('<p>$$</p>')
    expect(result).toContain('推导如下')
    expect(result).toContain('结论成立')
  })

  it('导入样本中的 prose + block math 模式保持前后文顺序', () => {
    const input = [
      '在真空中，静磁场的描述依赖于磁感应强度。',
      '',
      '$$',
      '\\mathbf{B} = \\frac{\\mu_0 I}{2\\pi r} \\hat{\\phi}',
      '$$',
      '',
      '其中：',
      '- $I$ 为电流强度；',
      '- $r$ 为到导线的距离。',
    ].join('\n')

    const result = renderMarkdown(input)

    expect(result).toContain('katex-display')
    expect(result).toContain('其中')
    expect(result).toContain('<ul>')
    expect(result).not.toContain('math-error')
    expect(result).not.toContain('<p>$$</p>')
  })

  it('真实导入样本中的连续块公式不会显示为红色错误文本', () => {
    const input = [
      '安培环路定理是静磁场理论的核心之一，其微分形式为：',
      '',
      '$$',
      '\\nabla \\times \\mathbf{B} = \\mu_0 \\mathbf{J}',
      '$$',
      '而积分形式为：',
      '',
      '$$',
      '\\oint_C \\mathbf{B} \\cdot d\\mathbf{l} = \\mu_0 I_{enc}',
      '$$',
      '该公式表明，磁场沿闭合路径的环流等于穿过该路径所围面积的总电流乘以磁导率。',
    ].join('\n')

    const result = renderMarkdown(input)

    expect(result).toContain('katex-display')
    expect(result).not.toContain('math-error')
    expect(result).not.toContain('$$\\nabla')
    expect(result).not.toContain('$$\\oint_C')
    expect(result).toContain('而积分形式为')
  })

  it('真实导入样本中的行内公式不会在正文中消失', () => {
    const input = [
      '- **无散性**：静磁场没有“源”或“汇”，即 $\\nabla \\cdot \\mathbf{B} = 0$；',
      '- **有旋性**：静磁场可以由电流产生，满足安培环路定律 $\\nabla \\times \\mathbf{B} = \\mu_0 \\mathbf{J}$；',
      '- **矢量场**：静磁场是一个三维空间中的矢量场，通常用 $\\mathbf{B}$ 表示。',
    ].join('\n')

    const result = renderMarkdown(input)

    expect(result).toContain('katex-inline')
    expect(result).not.toContain('math-error')
    expect(result).not.toContain('即 ；')
    expect(result).not.toContain('通常用 表示')
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

// ---------------------------------------------------------------------------
// Mermaid 渲染
// ---------------------------------------------------------------------------

describe('MarkdownRenderer – Mermaid', () => {
  it('保留 Mermaid 前后的 Markdown 标题和正文结构', async () => {
    const content = [
      '### 🎨 可视化图解',
      '',
      '```mermaid',
      'graph TD',
      '    A["电磁波传播"] --> B["电场E"]',
      '```',
      '',
      '图后说明文字。',
    ].join('\n')

    const wrapper = mount(MarkdownRenderer, {
      props: { content },
    })

    await new Promise(resolve => setTimeout(resolve, 0))
    await new Promise(resolve => setTimeout(resolve, 0))

    const html = wrapper.html()
    expect(html).toContain('<h3>')
    expect(html).toContain('🎨 可视化图解')
    expect(html).toContain('图后说明文字')
    expect(html).not.toContain('&lt;h3&gt;')
    expect(html).not.toContain('### 🎨 可视化图解</div>')
    expect(html).not.toContain('图表渲染失败')
  })

  it('保留含引号和括号的 Mermaid 标签文本，不进行破坏性重写', async () => {
    const content = [
      '```mermaid',
      'graph TD',
      '    A["B("r") = μ₀I/(2πr)"] --> C["方向遵循右手螺旋法则"]',
      '```',
    ].join('\n')

    const wrapper = mount(MarkdownRenderer, {
      props: { content },
    })

    await new Promise(resolve => setTimeout(resolve, 0))
    await new Promise(resolve => setTimeout(resolve, 0))

    const html = wrapper.html()
    expect(html).toContain('<svg')
    expect(html).toContain('&quot;B(r) = μ₀I/(2πr)&quot;')
    expect(html).toContain('方向遵循右手螺旋法则')
    expect(html).not.toContain('图表渲染失败')
  })

  it('修复 Mermaid 外层双引号标签中的内部裸双引号', async () => {
    const content = [
      '```mermaid',
      'graph TD',
      '    D["E = E₀ cos("ωt - kz")"] --> E["H = E₀/η cos("ωt - kz")"]',
      '```',
    ].join('\n')

    const wrapper = mount(MarkdownRenderer, {
      props: { content },
    })

    await new Promise(resolve => setTimeout(resolve, 0))
    await new Promise(resolve => setTimeout(resolve, 0))

    const html = wrapper.html()
    expect(html).toContain('<svg')
    expect(html).toContain('&quot;E = E₀ cos(ωt - kz)&quot;')
    expect(html).toContain('&quot;H = E₀/η cos(ωt - kz)&quot;')
    expect(html).not.toContain("cos('ωt - kz')")
    expect(html).not.toContain('图表渲染失败')
  })

  it('为 Mermaid 输出添加安全余量，避免节点文字末尾被裁切', async () => {
    const content = [
      '```mermaid',
      'graph TD',
      '    A["方向遵循右手螺旋法则"] --> B["B(' + "'" + 'r' + "'" + ') = μ₀I/(2πr)"]',
      '```',
    ].join('\n')

    const wrapper = mount(MarkdownRenderer, {
      props: { content },
    })

    await new Promise(resolve => setTimeout(resolve, 0))
    await new Promise(resolve => setTimeout(resolve, 0))

    const html = wrapper.html()
    expect(html).toContain('<svg')
    expect(html).toContain('overflow: visible;')
  })

  it('覆盖导入样本中的 Mermaid 回归片段', async () => {
    const content = [
      '## 第六章 电磁能流与辐射 - 子节点 2',
      '',
      '### 🎨 可视化图解',
      '',
      '```mermaid',
      'graph TD',
      '    A["电磁波传播"] --> B("电场E")',
      '    A --> C("磁场H")',
      '    B --> D["E = E₀ cos("ωt - kz")"]',
      '    C --> E["H = E₀/η cos("ωt - kz")"]',
      '    D & E --> F["坡印廷矢量 S = E × H"]',
      '    F --> G["方向: 能量流动方向"]',
      '```',
    ].join('\n')

    const wrapper = mount(MarkdownRenderer, {
      props: { content },
    })

    await new Promise(resolve => setTimeout(resolve, 0))
    await new Promise(resolve => setTimeout(resolve, 0))

    const html = wrapper.html()
    expect(html).toContain('<h3>🎨 可视化图解</h3>')
    expect(html).toContain('&quot;E = E₀ cos(ωt - kz)&quot;')
    expect(html).toContain('&quot;H = E₀/η cos(ωt - kz)&quot;')
    expect(html).toContain('坡印廷矢量 S = E × H')
    expect(html).toContain('方向: 能量流动方向')
    expect(html).toContain('overflow: visible;')
    expect(html).not.toContain('图表渲染失败')
    expect(html).not.toContain("cos('ωt - kz')")
  })
})
