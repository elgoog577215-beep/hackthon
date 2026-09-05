import { describe, expect, it, vi } from 'vitest'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    run: vi.fn(),
  },
}))

vi.mock('highlight.js/styles/atom-one-dark.css', () => ({}))

import { renderMarkdown } from '@/utils/markdown'

const katexErrors = (html: string) => {
  const box = document.createElement('div')
  box.innerHTML = html
  return Array.from(box.querySelectorAll('.katex-error')).map((el) => el.getAttribute('title') || el.textContent || '')
}

const renderedText = (html: string) => {
  const box = document.createElement('div')
  box.innerHTML = html
  return box.textContent || ''
}

const katexText = (html: string) => {
  const box = document.createElement('div')
  box.innerHTML = html
  return Array.from(box.querySelectorAll('.katex')).map(el => el.textContent || '').join(' ')
}

describe('renderMarkdown – 真实 KaTeX 兼容', () => {
  it('把裸露的 LaTeX 打字机代码恢复为 Markdown 行内代码', () => {
    const html = renderMarkdown(String.raw`可验证行为：\texttt{find("span", class\_="price")} 是从根开始第几个子节点被命中。`)
    const box = document.createElement('div')
    box.innerHTML = html

    expect(box.querySelector('code')?.textContent).toBe('find("span", class_="price")')
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0)
    expect(renderedText(html)).not.toContain('\\texttt')
  })

  it('保留显式数学区和代码块里的 texttt 原语义', () => {
    const html = renderMarkdown([
      String.raw`数学记号 $\texttt{token\_id}$ 应继续交给 KaTeX。`,
      String.raw`$$\texttt{build()}$$`,
      '',
      '```latex',
      String.raw`\texttt{literal\_source}`,
      '```',
    ].join('\n'))
    const box = document.createElement('div')
    box.innerHTML = html

    expect(box.querySelectorAll('.katex').length).toBeGreaterThanOrEqual(2)
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0)
    expect(box.querySelector('pre code')?.textContent).toContain(String.raw`\texttt{literal\_source}`)
  })

  it('修复公式外壳中误转义的 texttt 右花括号', () => {
    const html = renderMarkdown(String.raw`| 检查项 | 正确做法 | 常见错误 |
| --- | --- | --- |
| None 处理 | 用 $\texttt{if result:\} result.get\_text()$ | 跳过判空 |`)
    const box = document.createElement('div')
    box.innerHTML = html

    expect(box.querySelector('tbody code')?.textContent).toBe('if result: result.get_text()')
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0)
    expect(renderedText(html)).not.toContain('\\texttt')
  })

  it('合并被模型换行拆开的 Markdown 表格行并清理孤立美元符', () => {
    const html = renderMarkdown([
      '| 检查项 | 正确做法 | 常见错误 |',
      '| --- | --- | --- |',
      String.raw`| 文本提取 | 用 $\texttt{.get\_text()}$`,
      String.raw`$ 或 $\texttt{.string}$（仅无子节点时） | 对含子标签的 Tag 直接用 $\texttt{.string}$，得到 None |$`,
    ].join('\n'))
    const box = document.createElement('div')
    box.innerHTML = html
    const rows = Array.from(box.querySelectorAll('tbody tr'))
    const cells = Array.from(rows[0]?.querySelectorAll('td') || []).map(cell => cell.textContent?.trim())

    expect(rows).toHaveLength(1)
    expect(cells).toEqual([
      '文本提取',
      '用 .get_text() 或 .string（仅无子节点时）',
      '对含子标签的 Tag 直接用 .string，得到 None',
    ])
    expect(renderedText(html)).not.toContain('$')
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0)
  })

  it('剥离已放入 Markdown 代码跨度的冗余 LaTeX 外壳', () => {
    const html = renderMarkdown('已有 `\\texttt{find("span", class\\_="price")}` 需保留代码语义。')
    const box = document.createElement('div')
    box.innerHTML = html

    expect(box.querySelector('code')?.textContent).toBe('find("span", class_="price")')
    expect(renderedText(html)).not.toContain('\\texttt')
  })

  it('渲染模型输出中的脏 display 分隔符时不产生 KaTeX 红错', () => {
    const html = renderMarkdown('$$$$\\begin{pmatrix}\n\\cos m\\omega_j & -\\sin m\\omega_j \\\\ \\sin m\\omega_j & \\cos m\\omega_j\n\\end{pmatrix}$$$$在复数域中，这等价于$x^{\\prime} = x \\cdot e^{i m \\omega_j}$。')
    expect(katexErrors(html)).toEqual([])
  })

  it('渲染相邻 display 公式时不把分隔符漏进 KaTeX', () => {
    const html = renderMarkdown('$$p(y_w \\succ y_l | x) = \\sigma\\left( \\beta \\log\\frac{\\pi_\\theta(y_w|x)}{\\pi_{\\text{ref}}(y_w|x)} - \\beta \\log\\frac{\\pi_\\theta(y_l|x)}{\\pi_{\\text{ref}}(y_l|x)} \\right)$$$$= \\sigma\\left( x \\right)$$')
    expect(katexErrors(html)).toEqual([])
  })

  it('渲染矩阵连乘中的 $$=$$ 分隔符时不让矩阵内容错位', () => {
    const html = renderMarkdown('$$$$\\begin{pmatrix}x\\end{pmatrix}$$=$$\\begin{pmatrix}\\cos x & -\\sin x \\\\ \\sin x & \\cos x\\end{pmatrix}$$$$\\begin{pmatrix}y\\end{pmatrix}$$$$在复数域中，这等价于$x^{\\prime}=x$。')
    expect(katexErrors(html)).toEqual([])
  })

  it('渲染课程原文中的 RoPE 矩阵链时不产生 KaTeX 红错', () => {
    const html = renderMarkdown('则位置$m$处的RoPE变换为对每个二维子空间$(x^{(2j)}, x^{(2j+1)})$应用旋转：$$$$\\begin{pmatrix}\n x^{\\prime(2j)} \\\\ x^{\\prime(2j+1)} \n\\end{pmatrix}$$=$$\\begin{pmatrix}\n \\cos m\\omega\\_j & -\\sin m\\omega\\_j \\\\ \\sin m\\omega\\_j & \\cos m\\omega\\_j \n\\end{pmatrix}$$$$\\begin{pmatrix}\n x^{(2j)} \\\\ x^{(2j+1)} \n\\end{pmatrix}$$$$在复数域中，这等价于$x^{\\prime} = x \\cdot e^{i m \\omega\\_j}$。那么，两个向量$q\\_m$和$k\\_n$在复数域中的内积（实部）为：$$\\langle q\\_m e^{i m\\omega\\_j}, \\ k\\_n e^{i n\\omega\\_j} \\rangle = \\text{Re}[q\\_m \\bar{k}\\_n e^{i(m-n)\\omega\\_j}]$$')
    expect(katexErrors(html)).toEqual([])
  })

  it('渲染内联前缀接块级矩阵时不泄漏占位符', () => {
    const html = renderMarkdown('$\\mathbf{W} =$$\\begin{bmatrix}0.8 & -1.5\\\\-2.0 & 0.1\\end{bmatrix}$$$')
    expect(html).not.toContain('__MATH_BLOCK')
    expect(katexErrors(html)).toEqual([])
  })

  it('矩阵后的 Markdown 列表不会被 $$$$ 误吞进下一个公式', () => {
    const html = renderMarkdown('$$$$\\begin{pmatrix}1 & 2 \\\\ 0 & 1\\end{pmatrix}$$$$-$R_2 \\leftarrow R_2 - R_1$：$$$$\\begin{pmatrix}1 & 2 \\\\ -1 & -1\\end{pmatrix}$$$$')
    expect(katexErrors(html)).toEqual([])
    expect(renderedText(html)).not.toContain('$$')
    expect(renderedText(html)).not.toContain('\\begin{pmatrix}')
  })

  it('行内等号前缀与三美元块级矩阵可以正确分界', () => {
    const html = renderMarkdown('$A =$$$\\begin{bmatrix}1 & 2 \\\\ 3 & 4\\end{bmatrix}$$$$**结果检查**')
    expect(katexErrors(html)).toEqual([])
    expect(renderedText(html)).not.toContain('\\begin{bmatrix}')
    expect(renderedText(html)).toContain('结果检查')
  })

  it('中文正文后的三美元环境会在独立行开启', () => {
    const html = renderMarkdown('按分量写出：$$$\\begin{cases}x + y = 1 \\\\ x - y = 0\\end{cases}$$$**继续求解**')
    expect(katexErrors(html)).toEqual([])
    expect(renderedText(html)).not.toContain('\\begin{cases}')
    expect(renderedText(html)).toContain('继续求解')
  })

  it('两个三美元矩阵之间的等号不泄漏分隔符', () => {
    const html = renderMarkdown('$$$\\begin{bmatrix}1 \\\\ 2\\end{bmatrix}$$$=$$$\\begin{bmatrix}3 \\\\ 4\\end{bmatrix}$$$')
    expect(katexErrors(html)).toEqual([])
    expect(renderedText(html)).not.toContain('\\begin{bmatrix}')
    expect(renderedText(html)).not.toContain('$$')
  })

  it('矩阵乘法链中的六美元连续分隔符不破坏后续矩阵', () => {
    const html = renderMarkdown('$\\mathbf{y}=P\\mathbf{x}$，即$$$$\\begin{bmatrix}2 \\\\ 3 \\\\ 1\\end{bmatrix}$$$=$$$\\begin{bmatrix}1 & 0 & 1 \\\\ 0 & 1 & 1 \\\\ 1 & 1 & 0\\end{bmatrix}$$$$$$\\begin{bmatrix}x_1 \\\\ x_2 \\\\ x_3\\end{bmatrix}$$$$。')
    expect(katexErrors(html)).toEqual([])
    expect(renderedText(html)).not.toContain('\\begin{bmatrix}')
    expect(renderedText(html)).not.toContain('$$')
  })

  it('局部缺少右花括号时使用可读降级而不是 KaTeX 红错', () => {
    const html = renderMarkdown('普朗克常数 $$h \\approx 6.626 \\times 10^{-34} \\text{ J·s$$ 用于量子计算。')
    expect(katexErrors(html)).toEqual([])
    expect(html).toContain('math-fallback')
    expect(renderedText(html)).toContain('6.626')
    expect(renderedText(html)).toContain('用于量子计算')
  })

  it('重复上标的旧公式不影响后续正文阅读', () => {
    const html = renderMarkdown('$$\\frac{d^2x}{dt^2} + \\omega^0^2 x = 0$$\n\n其中 $\\omega_0$ 是固有角频率。')
    expect(katexErrors(html)).toEqual([])
    expect(html).toContain('math-fallback')
    expect(renderedText(html)).toContain('固有角频率')
  })

  it('坏外层分隔符不会吞掉完整公式环境或后续正文', () => {
    const html = renderMarkdown('势能为：\n$$\nV(x)=\\begin{cases}0 & 0<x<L \\\\ \\infty & otherwise\\end{cases}\n不含时薛定谔方程为：$E\\psi=H\\psi$。')
    expect(katexErrors(html)).toEqual([])
    expect(renderedText(html)).not.toMatch(/MATHDISPLAYPLACEHOLDER|\\begin\{cases\}|\$\$/)
    expect(renderedText(html)).toContain('势能为')
    expect(renderedText(html)).toContain('不含时薛定谔方程')
  })

  it('孤立 display 分隔符与裸 LaTeX 命令不会显示为原始标记', () => {
    const html = renderMarkdown('令自由变量为 t，\\quad t \\in \\mathbb{R}。\n$$')
    expect(katexErrors(html)).toEqual([])
    expect(renderedText(html)).not.toContain('$$')
    expect(renderedText(html)).not.toContain('\\mathbb')
    expect(renderedText(html)).toContain('令自由变量')
  })

  it('双重转义的行内向量公式仍能渲染且不泄漏 Markdown 标记', () => {
    const html = renderMarkdown('> **关键辨析**：向量$\\\\vec{a} = (a_1, a_2)$的坐标$(a_1, a_2)$与终点$A$的坐标是**一致**的。')
    expect(katexErrors(html)).toEqual([])
    expect(html).not.toContain('math-fallback')
    expect(html).toContain('accent-body')
    expect(renderedText(html)).not.toContain('\\vec')
    expect(renderedText(html)).not.toContain('**')
    expect(renderedText(html)).toContain('关键辨析')
  })

  it('裸公式后紧接中文解释时只渲染公式段', () => {
    const html = renderMarkdown('k\\vec{a} = (k a_1)\\mathbf{i} + (k a_2)\\mathbf{j} = (k a_1, k a_2)这证明了坐标运算规则与几何运算规则完全等价。')
    expect(katexErrors(html)).toEqual([])
    expect(html).not.toContain('math-fallback')
    expect(renderedText(html)).not.toContain('\\vec')
    expect(renderedText(html)).toContain('这证明了坐标运算规则与几何运算规则完全等价。')
    expect(katexText(html)).not.toContain('这证明了')
  })

  it('行内 span 公式嵌套块级矩阵时合并为独立完整公式', () => {
    const html = renderMarkdown('$ U = \\text{span}\\left(\n$$\n\\begin{bmatrix}1 \\\\ 0 \\\\ 0\\end{bmatrix}\n$$\n,\n$$\n\\begin{bmatrix}0 \\\\ 1 \\\\ 0\\end{bmatrix}\n$$\n\\right) $，$ W = \\text{span}\\left(\n$$\n\\begin{bmatrix}0 \\\\ 1 \\\\ 0\\end{bmatrix}\n$$\n,\n$$\n\\begin{bmatrix}0 \\\\ 0 \\\\ 1\\end{bmatrix}\n$$\n\\right) $。')
    expect(katexErrors(html)).toEqual([])
    expect(html).not.toContain('math-fallback')
    expect(renderedText(html)).not.toMatch(/\\(?:text|begin|right)|\$\$/)
    expect(renderedText(html)).toContain('，')
  })

  it('AI 正文候选中的粗体时间标签与行内代码保持标准 Markdown 结构', () => {
    const html = renderMarkdown([
      '2. **LSTM 的“物理直觉”**：',
      '   * **t=0**：LSTM 看到 `θ(0)`，知道了单摆的起始位置。',
      '   * **t=1**：LSTM 看到 `θ(0.1)`，并与刚刚记下的 `θ(0)` 对比。',
      '   * **t=9**：最终隐藏状态 `h10` 编码了单摆的位置、速度和加速度。',
      '4. **学习与修正**：误差信号从 t=9 一直传回 t=0。',
    ].join('\n'))
    const box = document.createElement('div')
    box.innerHTML = html

    expect(katexErrors(html)).toEqual([])
    expect(box.querySelectorAll('ol > li')).toHaveLength(2)
    expect(box.querySelectorAll('ul > li')).toHaveLength(3)
    expect(box.querySelectorAll('strong')).toHaveLength(5)
    expect(box.querySelectorAll('code:not(.math-fallback)')).toHaveLength(4)
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0)
    expect(renderedText(html)).not.toContain('**')
  })

  it('含裸公式的 Markdown 表格仍保持表格结构', () => {
    const html = renderMarkdown([
      '| 参数 | 当前值 | 说明 |',
      '| --- | --- | --- |',
      '| 步长 | x_t = 1 | 初始状态 |',
    ].join('\n'))
    const box = document.createElement('div')
    box.innerHTML = html

    expect(box.querySelector('table')).not.toBeNull()
    expect(box.querySelectorAll('tbody tr')).toHaveLength(1)
    expect(box.querySelectorAll('td')).toHaveLength(3)
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0)
    expect(renderedText(html)).toContain('初始状态')
  })

  it('查询参数含等号和下划线的 Markdown 链接不会被公式识别吞掉', () => {
    const html = renderMarkdown('[查看 t=0 的说明](https://example.com/guide?step=t_0)')
    const box = document.createElement('div')
    box.innerHTML = html
    const link = box.querySelector('a')

    expect(link).not.toBeNull()
    expect(link?.getAttribute('href')).toBe('https://example.com/guide?step=t_0')
    expect(link?.textContent).toBe('查看 t=0 的说明')
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0)
  })

  it('列表中的裸公式只渲染公式前缀，不吞掉后续中文解释', () => {
    const html = renderMarkdown('- x_t = 1 表示初始状态。')
    const box = document.createElement('div')
    box.innerHTML = html

    expect(box.querySelector('ul > li')).not.toBeNull()
    expect(box.querySelector('.katex')).not.toBeNull()
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0)
    expect(renderedText(html)).toContain('表示初始状态。')
    expect(katexText(html)).not.toContain('表示初始状态')
  })
})
