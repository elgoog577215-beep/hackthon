import mermaid from 'mermaid'

const KNOWN_DIAGRAM_TYPES = new Set([
  'graph',
  'flowchart',
  'sequenceDiagram',
  'classDiagram',
  'stateDiagram',
  'erDiagram',
  'gantt',
  'pie',
  'mindmap',
  'timeline',
  'gitGraph',
  'journey',
  'sankey-beta',
  'quadrantChart',
])

const COMMENT_LINE_RE = /^\s*%%/

const getFirstMeaningfulLine = (code: string): string => {
  return code
    .split('\n')
    .map(line => line.trim())
    .find(line => line && !COMMENT_LINE_RE.test(line)) || ''
}

export const getMermaidDiagramType = (code: string): string => {
  const firstLine = getFirstMeaningfulLine(code)
  return firstLine.split(/[\s\n]/)[0] || ''
}

export const isRenderableMermaidSource = (code: string): boolean => {
  const trimmed = code.trim()
  if (!trimmed) return false

  const firstWord = getMermaidDiagramType(trimmed)
  if (KNOWN_DIAGRAM_TYPES.has(firstWord)) return true

  return trimmed.includes('-->') || trimmed.includes('---')
}

const MERMAID_CONFIG = {
  startOnLoad: false,
  theme: 'base' as const,
  securityLevel: 'strict' as const,
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
  flowchart: {
    htmlLabels: false,
  },
  themeVariables: {
    primaryColor: '#8b5cf6',
    primaryTextColor: '#0f172a',
    primaryBorderColor: '#7c3aed',
    lineColor: '#334155',
    secondaryColor: '#ede9fe',
    tertiaryColor: '#ffffff',
    mainBkg: '#f8fafc',
    nodeBorder: '#cbd5e1',
    clusterBkg: '#f1f5f9',
    clusterBorder: '#cbd5e1',
    titleColor: '#0f172a',
    edgeLabelBackground: '#ffffff',
  },
}

let isInitialized = false

export const initializeMermaid = () => {
  if (isInitialized) return
  mermaid.initialize(MERMAID_CONFIG)
  isInitialized = true
}

const repairMermaidLabelText = (label: string): string => {
  let repaired = label
    .replace(/\r\n?/g, '\n')
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\u00A0/g, ' ')
    .replace(/\t/g, '    ')

  repaired = repaired.replace(/([A-Za-z_][\w]*)\("([^"\n]+)"\)/g, '$1($2)')
  repaired = repaired.replace(/\("([^"\n]+)"\)/g, '($1)')
  repaired = repaired.replace(/\["([^"\n]+)"\]/g, '[$1]')
  repaired = repaired.replace(/\{"([^"\n]+)"\}/g, '{$1}')

  return repaired.replace(/"/g, "'")
}

const sanitizeQuotedLabels = (input: string): string => {
  const pairs: Record<string, string> = {
    '[': ']',
    '(': ')',
    '{': '}',
    '|': '|',
  }

  let output = ''
  for (let i = 0; i < input.length; i++) {
    const start = input[i]
    const end = start ? pairs[start] : undefined

    if (end && input[i + 1] === '"') {
      let j = i + 2
      while (j < input.length) {
        if (input[j] === '"' && input[j + 1] === end) {
          const content = input.slice(i + 2, j)
          output += `${start}"${repairMermaidLabelText(content)}"${end}`
          i = j + 1
          break
        }
        j++
      }

      if (j < input.length) {
        continue
      }
    }

    output += start
  }

  return output
}

export const prepareMermaidBlockSource = (code: string): string => {
  const trimmed = code.trim()
  if (!trimmed) return ''

  const firstWord = getMermaidDiagramType(trimmed)
  if (!KNOWN_DIAGRAM_TYPES.has(firstWord) && !trimmed.startsWith('%%') && (trimmed.includes('-->') || trimmed.includes('---'))) {
    return `graph TD\n${trimmed}`
  }

  return trimmed
}

export const normalizeMermaidCode = (code: string): string => {
  return sanitizeQuotedLabels(prepareMermaidBlockSource(code))
    .replace(/\r\n?/g, '\n')
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\u00A0/g, ' ')
    .replace(/\t/g, '    ')
    .trim()
}

export const addMermaidSafetyMargin = (svgMarkup: string): string => {
  if (typeof window === 'undefined') return svgMarkup

  const parser = new DOMParser()
  const doc = parser.parseFromString(svgMarkup, 'image/svg+xml')
  const svg = doc.documentElement

  if (!svg || svg.tagName.toLowerCase() !== 'svg') {
    return svgMarkup
  }

  const extraNodeWidth = 20
  const extraNodeHeight = 12

  const viewBox = svg.getAttribute('viewBox')
  if (viewBox) {
    const parts = viewBox.split(/\s+/).map(Number)
    if (parts.length === 4 && parts.every(Number.isFinite)) {
      svg.setAttribute('viewBox', parts.join(' '))
    }
  }

  const width = svg.getAttribute('width')
  if (width) {
    const match = width.match(/^([\d.]+)(px)?$/)
    if (match) {
      const nextWidth = Number(match[1] || '0')
      svg.setAttribute('width', `${nextWidth}${match[2] || ''}`)
    }
  }

  const currentStyle = svg.getAttribute('style') || ''
  const nextStyle = /overflow\s*:/.test(currentStyle)
    ? currentStyle.replace(/overflow\s*:[^;]+;?/g, 'overflow: visible;')
    : `${currentStyle}${currentStyle && !currentStyle.trim().endsWith(';') ? ';' : ''}overflow: visible;`
  svg.setAttribute('style', nextStyle)

  const expandAndRecenter = (node: Element, extraWidth: number, extraHeight: number) => {
    const widthAttr = node.getAttribute('width')
    if (widthAttr) {
      const currentWidth = Number(widthAttr)
      if (Number.isFinite(currentWidth)) {
        node.setAttribute('width', String(currentWidth + extraWidth))
      }
    }

    const xAttr = node.getAttribute('x')
    if (xAttr && extraWidth !== 0) {
      const currentX = Number(xAttr)
      if (Number.isFinite(currentX)) {
        node.setAttribute('x', String(currentX - extraWidth / 2))
      }
    }

    const heightAttr = node.getAttribute('height')
    if (heightAttr) {
      const currentHeight = Number(heightAttr)
      if (Number.isFinite(currentHeight)) {
        node.setAttribute('height', String(currentHeight + extraHeight))
      }
    }

    const yAttr = node.getAttribute('y')
    if (yAttr && extraHeight !== 0) {
      const currentY = Number(yAttr)
      if (Number.isFinite(currentY)) {
        node.setAttribute('y', String(currentY - extraHeight / 3))
      }
    }
  }

  const adjusted = new Set<Element>()
  ;[
    'rect.basic.label-container',
    'rect.label-container',
    'g.node rect',
    'g.node foreignObject',
    'clipPath rect',
  ].forEach(selector => {
    svg.querySelectorAll(selector).forEach(node => {
      if (adjusted.has(node)) return
      adjusted.add(node)

      expandAndRecenter(node, extraNodeWidth, extraNodeHeight)
    })
  })

  return svg.outerHTML
}

export const isMermaidErrorSvg = (svgMarkup: string): boolean => {
  return (
    /class=["'][^"']*\berror-text\b/.test(svgMarkup) ||
    svgMarkup.includes('Syntax error in text') ||
    svgMarkup.includes('mermaid version')
  )
}

export const renderMermaidSvg = async (id: string, code: string): Promise<string> => {
  initializeMermaid()
  if (!isRenderableMermaidSource(code)) {
    throw new Error('Unsupported Mermaid diagram type')
  }
  const cleaned = normalizeMermaidCode(code)
  const { svg } = await mermaid.render(id, cleaned)
  if (isMermaidErrorSvg(svg)) {
    throw new Error('Mermaid returned an error diagram')
  }
  return addMermaidSafetyMargin(svg)
}
