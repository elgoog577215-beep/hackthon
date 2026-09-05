export interface MarkdownHeading {
  id: string
  level: number
  title: string
  line: number
  startLine: number
  endLine: number
  path: string[]
  children: MarkdownHeading[]
}

export interface SelectionContext {
  found: boolean
  index: number
  selectedText: string
  beforeContext: string
  afterContext: string
  headingPath: string[]
}

export interface ReplacementResult {
  content: string
  replaced: boolean
  reason?: string
}

const HEADING_RE = /^(#{1,6})\s+(.+?)\s*#*\s*$/
const FENCE_RE = /^\s*(```|~~~)/

const slugify = (title: string, line: number) => {
  const base = title
    .trim()
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
  return `${base || 'heading'}-${line + 1}`
}

export const flattenHeadings = (headings: MarkdownHeading[]): MarkdownHeading[] => {
  const result: MarkdownHeading[] = []
  const visit = (items: MarkdownHeading[]) => {
    items.forEach((item) => {
      result.push(item)
      visit(item.children)
    })
  }
  visit(headings)
  return result
}

export const parseMarkdownHeadings = (markdown: string): MarkdownHeading[] => {
  const lines = (markdown || '').split(/\r?\n/)
  const roots: MarkdownHeading[] = []
  const stack: MarkdownHeading[] = []
  let inFence = false

  lines.forEach((line, index) => {
    if (FENCE_RE.test(line)) {
      inFence = !inFence
      return
    }
    if (inFence) return

    const match = line.match(HEADING_RE)
    if (!match) return

    const level = match[1]!.length
    const title = match[2]!.trim()

    while (stack.length > 0 && stack[stack.length - 1]!.level >= level) {
      const closed = stack.pop()
      if (closed) closed.endLine = index - 1
    }

    const parent = stack[stack.length - 1]
    const heading: MarkdownHeading = {
      id: slugify(title, index),
      level,
      title,
      line: index,
      startLine: index,
      endLine: lines.length - 1,
      path: parent ? [...parent.path, title] : [title],
      children: [],
    }

    if (parent) {
      parent.children.push(heading)
    } else {
      roots.push(heading)
    }
    stack.push(heading)
  })

  while (stack.length > 0) {
    const heading = stack.pop()
    if (heading) heading.endLine = lines.length - 1
  }

  return roots
}

export const buildVisibleMarkdown = (markdown: string, foldedIds: Set<string>): string => {
  if (!foldedIds.size) return markdown
  const lines = (markdown || '').split(/\r?\n/)
  const headings = flattenHeadings(parseMarkdownHeadings(markdown))
  const foldedByStartLine = new Map<number, MarkdownHeading>()
  const hiddenLines = new Set<number>()

  headings.forEach((heading) => {
    if (!foldedIds.has(heading.id)) return
    foldedByStartLine.set(heading.startLine, heading)
    for (let line = heading.startLine + 1; line <= heading.endLine; line += 1) {
      hiddenLines.add(line)
    }
  })

  const output: string[] = []
  lines.forEach((line, index) => {
    if (hiddenLines.has(index)) return
    output.push(line)
    const folded = foldedByStartLine.get(index)
    if (folded && folded.endLine > folded.startLine) {
      const foldedLineCount = folded.endLine - folded.startLine
      output.push('')
      output.push(`> 已折叠 ${foldedLineCount} 行内容。`)
    }
  })

  return output.join('\n')
}

const flexiblePattern = (text: string) => {
  const parts = text.trim().split(/\s+/).filter(Boolean).map(escapeRegExp)
  return parts.length ? new RegExp(parts.join('\\s+'), 'g') : null
}

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const scoreOccurrence = (
  markdown: string,
  index: number,
  length: number,
  beforeContext = '',
  afterContext = '',
) => {
  let score = 0
  const beforeWindow = markdown.slice(Math.max(0, index - 500), index)
  const afterWindow = markdown.slice(index + length, index + length + 500)
  const beforeNeedle = beforeContext.trim().slice(-120)
  const afterNeedle = afterContext.trim().slice(0, 120)

  if (beforeNeedle && beforeWindow.includes(beforeNeedle)) score += beforeNeedle.length
  if (afterNeedle && afterWindow.includes(afterNeedle)) score += afterNeedle.length
  return score
}

const findBestOccurrence = (
  markdown: string,
  selectedText: string,
  beforeContext = '',
  afterContext = '',
) => {
  const selected = selectedText.trim()
  if (!selected) return null

  const candidates: Array<{ index: number; length: number; score: number }> = []
  let index = markdown.indexOf(selected)
  while (index >= 0) {
    candidates.push({
      index,
      length: selected.length,
      score: scoreOccurrence(markdown, index, selected.length, beforeContext, afterContext),
    })
    index = markdown.indexOf(selected, index + selected.length)
  }

  if (candidates.length === 0) {
    const pattern = flexiblePattern(selected)
    if (pattern) {
      let match: RegExpExecArray | null
      while ((match = pattern.exec(markdown)) !== null) {
        candidates.push({
          index: match.index,
          length: match[0].length,
          score: scoreOccurrence(markdown, match.index, match[0].length, beforeContext, afterContext),
        })
      }
    }
  }

  if (candidates.length === 0) return null
  candidates.sort((a, b) => b.score - a.score || a.index - b.index)
  return candidates[0]
}

const findHeadingPathAtOffset = (markdown: string, offset: number) => {
  const line = markdown.slice(0, Math.max(0, offset)).split(/\r?\n/).length - 1
  const headings = flattenHeadings(parseMarkdownHeadings(markdown))
  const owner = headings
    .filter((heading) => heading.startLine <= line && heading.endLine >= line)
    .sort((a, b) => b.level - a.level)[0]
  return owner?.path || []
}

export const getSelectionContext = (
  markdown: string,
  selectedText: string,
  limit = 600,
): SelectionContext => {
  const match = findBestOccurrence(markdown, selectedText)
  if (!match) {
    return {
      found: false,
      index: -1,
      selectedText: selectedText.trim(),
      beforeContext: '',
      afterContext: '',
      headingPath: [],
    }
  }

  return {
    found: true,
    index: match.index,
    selectedText: markdown.slice(match.index, match.index + match.length),
    beforeContext: markdown.slice(Math.max(0, match.index - limit), match.index),
    afterContext: markdown.slice(match.index + match.length, match.index + match.length + limit),
    headingPath: findHeadingPathAtOffset(markdown, match.index),
  }
}

export const replaceSelectedMarkdown = (
  markdown: string,
  selectedText: string,
  replacementText: string,
  beforeContext = '',
  afterContext = '',
): ReplacementResult => {
  const match = findBestOccurrence(markdown, selectedText, beforeContext, afterContext)
  if (!match) {
    return {
      content: markdown,
      replaced: false,
      reason: '无法在 Markdown 原文中定位该选区',
    }
  }

  return {
    content: `${markdown.slice(0, match.index)}${replacementText}${markdown.slice(match.index + match.length)}`,
    replaced: true,
  }
}
