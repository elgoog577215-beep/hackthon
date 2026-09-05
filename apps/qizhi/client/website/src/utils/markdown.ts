/**
 * Markdown / LaTeX 渲染工具
 *
 * 只做「字符串 → 安全 HTML」的无副作用转换，便于放在 computed 里按消息内容缓存，
 * 避免在 ChatView 模板上直接调用函数导致每次流式增量都把所有历史消息重新解析一遍。
 */

import DOMPurify from 'dompurify'
import katex from 'katex'
import { marked } from 'marked'

/** 与智能对话、资源预览等共用：启用 GFM + 单换行转 <br> */
marked.use({
  gfm: true,
  breaks: true,
})

/**
 * 去掉后端可能返回的 markdown 代码围栏（```markdown ... ```），
 * 否则整段会被当作代码块显示，无法按标题、列表等渲染。
 */
export function stripMarkdownCodeFence(text: string): string {
  if (!text || typeof text !== 'string') return text
  let s = text.trim()
  if (!s) return text
  if (s.startsWith('```')) {
    const firstLineEnd = s.indexOf('\n')
    if (firstLineEnd !== -1) {
      s = s.slice(firstLineEnd + 1)
    } else {
      s = s.slice(3)
    }
  }
  if (s.endsWith('```')) {
    s = s.slice(0, -3).trimEnd()
  }
  return s
}

/**
 * 修正模型常见但 CommonMark 不认的强调写法，避免页面上直接露出星号：
 * - 全角星号 ＊ → *
 * - ** 粗体 **（分隔符内侧有空格）→ **粗体**
 */
function normalizeMarkdownEmphasis(text: string): string {
  let s = text.replace(/\uFF0A/g, '*')
  s = s.replace(/\*\*([\s\u00A0]*)([^*\n]+?)([\s\u00A0]*)\*\*/g, (_m, lead, inner, trail) => {
    const body = String(inner)
    if (!body.trim()) return _m
    if (lead || trail) return `**${body.trim()}**`
    return `**${body}**`
  })
  return s
}

/** 围栏代码块或行内代码，用于粗体预替换时跳过（RegExp 构造避免源码里反引号被误解析） */
const MARKDOWN_CODE_SEGMENT = new RegExp('(```[\\s\\S]*?```|`[^`\\n]+`)', 'g')

function wrapStrong(inner: string, fallback: string): string {
  const body = inner.trim()
  if (!body) return fallback
  return `<strong>${body}</strong>`
}

/**
 * 将 ** / __ 粗体转为 <strong>，弥补 marked 在部分 CJK 边界（如「__粗体__测试」）下不解析的问题。
 * 仅在非代码片段中替换，避免破坏 ``` 与 ` 内字面量星号。
 */
function replaceMarkdownBoldWithHtml(text: string): string {
  const segments = text.split(MARKDOWN_CODE_SEGMENT)
  return segments
    .map((seg, i) => {
      if (i % 2 === 1) return seg
      return seg
        .replace(/\*\*([^*\n]+?)\*\*/g, (_m, inner: string) => wrapStrong(inner, _m))
        .replace(/__([^_\n]+?)__/g, (_m, inner: string) => wrapStrong(inner, _m))
    })
    .join('')
}

/**
 * 将 Markdown 文本中的 LaTeX 公式替换为 KaTeX 渲染后的 HTML
 * 支持形式：\( ... \) 行内，\[ ... \] 与 $$ ... $$ 块级
 */
function renderMathWithKatex(text: string): string {
  const optionsInline = { displayMode: false, throwOnError: false } as const
  const optionsBlock = { displayMode: true, throwOnError: false } as const

  // 块级：$$ ... $$
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_m, expr: string) =>
    katex.renderToString(expr.trim(), optionsBlock)
  )
  // 块级：\[ ... \]
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, (_m, expr: string) =>
    katex.renderToString(expr.trim(), optionsBlock)
  )
  // 行内：\( ... \)
  text = text.replace(/\\\((.+?)\\\)/g, (_m, expr: string) =>
    katex.renderToString(expr.trim(), optionsInline)
  )
  // 行内：$ ... $（在处理完 $$ 后再处理，避免冲突）
  text = text.replace(/\$([^$\n]+?)\$/g, (_m, expr: string) =>
    katex.renderToString(expr.trim(), optionsInline)
  )

  return text
}

// DOMPurify 白名单：保留 KaTeX 需要的 SVG/MathML 节点；禁止脚本与事件属性。
// KaTeX 输出里会有大量 class/style/aria-*，默认配置已能放行，这里只额外允许常见 target。
const SANITIZE_CONFIG = {
  ADD_ATTR: ['target', 'aria-label', 'title', 'type'],
  USE_PROFILES: { html: true, mathMl: true, svg: true },
}

/** 为 fenced code 的 <pre> 包裹工具栏（智能对话复制按钮） */
function wrapMarkdownCodeBlocks(html: string): string {
  return html.replace(/<pre\b([^>]*)>([\s\S]*?)<\/pre>/gi, (_match, attrs: string, inner: string) => {
    const preAttrs = attrs ?? ''
    return (
      '<div class="md-code-block">' +
      '<div class="md-code-block__toolbar">' +
      '<button type="button" class="md-code-block__copy" aria-label="复制代码" title="复制代码"></button>' +
      `</div><pre${preAttrs}>${inner}</pre></div>`
    )
  })
}

/** 从代码块 DOM 提取纯文本（优先 code 节点） */
export function getMarkdownCodeBlockText(block: HTMLElement): string {
  const pre = block.querySelector('pre')
  if (!pre) return ''
  const code = pre.querySelector('code')
  return (code ?? pre).textContent ?? ''
}

/**
 * 将后端返回的字符串进行简单转义还原，并渲染为 Markdown+LaTeX HTML。
 * 经 DOMPurify 清洗，避免 LLM 注入的 `<img onerror>` 等属性级 XSS 向量。
 *
 * 该函数是纯函数：对同一输入总是返回同一输出，便于在 Vue `computed` 里按消息内容缓存。
 */
export function renderMarkdown(raw: string): string {
  if (!raw) return ''

  // 还原后端可能返回的转义换行符 / 制表符
  let text = raw.replace(/\\n/g, '\n').replace(/\\t/g, '\t')

  // 兼容后端可能返回的二次转义：\\( \\) \\[ \\] \\$ 等
  text = text
    .replace(/\\\\\(/g, '\\(')
    .replace(/\\\\\)/g, '\\)')
    .replace(/\\\\\[/g, '\\[')
    .replace(/\\\\\]/g, '\\]')
    .replace(/\\\\\$/g, '$')

  text = normalizeMarkdownEmphasis(text)
  text = replaceMarkdownBoldWithHtml(text)

  // 先用 KaTeX 渲染 LaTeX 公式，再交给 marked 处理 Markdown
  text = renderMathWithKatex(text)

  const html = wrapMarkdownCodeBlocks(marked.parse(text) as string)
  return DOMPurify.sanitize(html, SANITIZE_CONFIG) as unknown as string
}
