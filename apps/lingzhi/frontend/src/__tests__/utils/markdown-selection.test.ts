import { describe, expect, it } from 'vitest'
import {
  flattenHeadings,
  getSelectionContext,
  parseMarkdownHeadings,
  replaceSelectedMarkdown,
} from '@/utils/markdownSelection'

describe('markdownSelection', () => {
  it('解析 Markdown 标题父子关系', () => {
    const tree = parseMarkdownHeadings([
      '# 课程导入',
      '开场',
      '## 理论推导',
      '推导内容',
      '### 关键公式',
      '公式内容',
      '## 应用落地',
      '应用内容',
    ].join('\n'))

    expect(tree).toHaveLength(1)
    const root = tree[0]!
    expect(root.title).toBe('课程导入')
    expect(root.children.map((item) => item.title)).toEqual(['理论推导', '应用落地'])
    expect(root.children[0]!.children[0]!.path).toEqual(['课程导入', '理论推导', '关键公式'])
  })

  it('能计算每个标题控制的正文范围', () => {
    const markdown = '# A\nA1\n## B\nB1\nB2\n## C\nC1'
    const heading = flattenHeadings(parseMarkdownHeadings(markdown)).find((item) => item.title === 'B')

    expect(heading).toBeTruthy()
    expect(heading!.startLine).toBe(2)
    expect(heading!.endLine).toBe(4)
    expect(markdown).toContain('B1')
  })

  it('能按选区定位标题路径和上下文', () => {
    const markdown = '# 导入\n开场\n## 推导\n需要修改的表达。\n## 应用\n结尾'
    const context = getSelectionContext(markdown, '需要修改的表达。')

    expect(context.found).toBe(true)
    expect(context.headingPath).toEqual(['导入', '推导'])
    expect(context.beforeContext).toContain('## 推导')
    expect(context.afterContext).toContain('## 应用')
  })

  it('替换重复选区时优先使用前后文定位', () => {
    const markdown = '## A\n重复文本\n\n## B\n重复文本\n'
    const result = replaceSelectedMarkdown(markdown, '重复文本', '替换后', '## B\n', '\n')

    expect(result.replaced).toBe(true)
    expect(result.content).toBe('## A\n重复文本\n\n## B\n替换后\n')
  })

  it('无法定位选区时不会静默替换', () => {
    const result = replaceSelectedMarkdown('正文', '不存在', '替换')

    expect(result.replaced).toBe(false)
    expect(result.content).toBe('正文')
  })
})
