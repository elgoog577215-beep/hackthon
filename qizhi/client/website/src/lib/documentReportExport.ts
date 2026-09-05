/**
 * 教学文档分析报告 —— Word (.docx) 导出
 *
 * 使用 docx 库在浏览器端生成 Word 文档，无需后端支持。
 * 报告内容包括：文档概要、总分、六维度评分表、能力总结、改进建议、分段详情。
 */
import type { DocumentAnalysisResult } from '../api/document'
import type { IParagraphOptions, TableCell } from 'docx'

type DocxModule = typeof import('docx')
let _docx: DocxModule | null = null
let _saveAs: typeof import('file-saver').saveAs | null = null

async function loadDeps() {
  if (!_docx) _docx = await import('docx')
  if (!_saveAs) _saveAs = (await import('file-saver')).saveAs
  return { docx: _docx, saveAs: _saveAs }
}

// ---- 设计令牌 ----
const BRAND_BLUE = '1358E4'
const COLOR_HIGH = '38A169'
const COLOR_MID = 'D69E2E'
const COLOR_LOW = 'E53E3E'
const HEADER_BG = 'F0F4FF'
const LIGHT_GRAY = 'F5F5F5'
const FONT_FAMILY = '微软雅黑'

function scoreColor(score: number): string {
  if (score >= 80) return COLOR_HIGH
  if (score >= 60) return COLOR_MID
  return COLOR_LOW
}

function scoreLabel(score: number): string {
  if (score >= 80) return '优秀'
  if (score >= 60) return '良好'
  return '待改进'
}

// ---- 通用构建 helpers ----

function d() { return _docx! }

function createThinBorder() {
  const border = {
    style: d().BorderStyle.SINGLE,
    size: 1,
    color: 'DDDDDD',
  }
  return { top: border, bottom: border, left: border, right: border }
}

function headerCell(text: string, width?: number): any {
  return new (d().TableCell)({
    children: [
      new (d().Paragraph)({
        children: [
          new (d().TextRun)({
            text,
            bold: true,
            size: 20, // 10pt
            font: FONT_FAMILY,
            color: '333333',
          }),
        ],
        alignment: d().AlignmentType.CENTER,
        spacing: { before: 60, after: 60 },
      }),
    ],
    shading: { fill: HEADER_BG, type: d().ShadingType.CLEAR, color: 'auto' },
    borders: createThinBorder(),
    ...(width ? { width: { size: width, type: d().WidthType.PERCENTAGE } } : {}),
  })
}

function bodyCell(
  text: string,
  opts?: {
    color?: string
    bold?: boolean
    width?: number
    alignment?: IParagraphOptions['alignment']
  },
): TableCell {
  return new (d().TableCell)({
    children: [
      new (d().Paragraph)({
        children: [
          new (d().TextRun)({
            text,
            size: 20,
            font: FONT_FAMILY,
            color: opts?.color ?? '555555',
            bold: opts?.bold ?? false,
          }),
        ],
        alignment: opts?.alignment ?? d().AlignmentType.LEFT,
        spacing: { before: 40, after: 40 },
      }),
    ],
    borders: createThinBorder(),
    ...(opts?.width ? { width: { size: opts.width, type: d().WidthType.PERCENTAGE } } : {}),
  })
}

function sectionTitle(text: string): any {
  return new (d().Paragraph)({
    children: [
      new (d().TextRun)({
        text,
        bold: true,
        size: 28, // 14pt
        font: FONT_FAMILY,
        color: BRAND_BLUE,
      }),
    ],
    heading: d().HeadingLevel.HEADING_2,
    spacing: { before: 360, after: 160 },
  })
}

function bodyText(text: string, opts?: { indent?: number }): any {
  return new (d().Paragraph)({
    children: [
      new (d().TextRun)({
        text,
        size: 22, // 11pt
        font: FONT_FAMILY,
        color: '444444',
      }),
    ],
    spacing: { before: 60, after: 60, line: 360 },
    indent: opts?.indent ? { left: opts.indent } : undefined,
  })
}

function emptyLine(): any {
  return new (d().Paragraph)({ children: [], spacing: { before: 80, after: 80 } })
}

// ---- 报告各段落构建 ----

function buildTitleSection(data: DocumentAnalysisResult): any[] {
  const now = new Date()
  const dateStr = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`
  return [
    new (d().Paragraph)({
      children: [
        new (d().TextRun)({
          text: '教学文档分析报告',
          bold: true,
          size: 40, // 20pt
          font: FONT_FAMILY,
          color: BRAND_BLUE,
        }),
      ],
      alignment: d().AlignmentType.CENTER,
      spacing: { before: 200, after: 120 },
    }),
    new (d().Paragraph)({
      children: [
        new (d().TextRun)({
          text: `文件名：${data.file_name}　　类型：${data.file_type.toUpperCase()}　　段落数：${data.total_segments}`,
          size: 20,
          font: FONT_FAMILY,
          color: '777777',
        }),
      ],
      alignment: d().AlignmentType.CENTER,
      spacing: { after: 40 },
    }),
    new (d().Paragraph)({
      children: [
        new (d().TextRun)({
          text: `生成日期：${dateStr}`,
          size: 20,
          font: FONT_FAMILY,
          color: '999999',
        }),
      ],
      alignment: d().AlignmentType.CENTER,
      spacing: { after: 200 },
    }),
  ]
}

function buildOverallScore(data: DocumentAnalysisResult): any[] {
  const sc = data.overall_score
  return [
    sectionTitle('一、综合评分'),
    new (d().Paragraph)({
      children: [
        new (d().TextRun)({
          text: `${sc} 分`,
          bold: true,
          size: 48, // 24pt
          font: FONT_FAMILY,
          color: scoreColor(sc),
        }),
        new (d().TextRun)({
          text: `　（${scoreLabel(sc)}）`,
          size: 24,
          font: FONT_FAMILY,
          color: scoreColor(sc),
        }),
      ],
      alignment: d().AlignmentType.CENTER,
      spacing: { before: 120, after: 200 },
    }),
  ]
}

function buildDimensionTable(data: DocumentAnalysisResult): any[] {
  const rows: any[] = []

  // Header row
  rows.push(
    new (d().TableRow)({
      children: [
        headerCell('维度', 20),
        headerCell('得分', 12),
        headerCell('评语', 68),
      ],
      tableHeader: true,
    }),
  )

  for (const dim of data.dimension_scores) {
    rows.push(
      new (d().TableRow)({
        children: [
          bodyCell(dim.dimension, { bold: true, width: 20, alignment: d().AlignmentType.CENTER }),
          bodyCell(`${dim.score}`, { color: scoreColor(dim.score), bold: true, width: 12, alignment: d().AlignmentType.CENTER }),
          bodyCell(dim.comments || '--', { width: 68 }),
        ],
      }),
    )
  }

  return [
    sectionTitle('二、六维度评估'),
    new (d().Table)({
      rows,
      width: { size: 100, type: d().WidthType.PERCENTAGE },
      layout: d().TableLayoutType.FIXED,
    }),
  ]
}

function buildCapabilitySummary(data: DocumentAnalysisResult): any[] {
  if (!data.capability_summary) return []
  return [
    sectionTitle('三、能力总结'),
    bodyText(data.capability_summary),
  ]
}

function buildImprovementSuggestions(data: DocumentAnalysisResult): any[] {
  if (!data.improvement_suggestions.length) return []
  const paragraphs: any[] = [sectionTitle('四、改进建议')]
  data.improvement_suggestions.forEach((sug, idx) => {
    paragraphs.push(
      new (d().Paragraph)({
        children: [
          new (d().TextRun)({
            text: `${idx + 1}. ${sug}`,
            size: 22,
            font: FONT_FAMILY,
            color: '444444',
          }),
        ],
        spacing: { before: 60, after: 60, line: 360 },
        indent: { left: 240 },
      }),
    )
  })
  return paragraphs
}

function buildSegmentDetails(data: DocumentAnalysisResult): any[] {
  if (!data.segment_details.length) return []
  const elements: any[] = [sectionTitle('五、分段详情')]

  for (const seg of data.segment_details) {
    // Segment heading
    const segTitle = seg.segment_title
      ? `段落 ${seg.segment_index}：${seg.segment_title}`
      : `段落 ${seg.segment_index}`

    elements.push(
      new (d().Paragraph)({
        children: [
          new (d().TextRun)({
            text: segTitle,
            bold: true,
            size: 24,
            font: FONT_FAMILY,
            color: '333333',
          }),
        ],
        heading: d().HeadingLevel.HEADING_3,
        spacing: { before: 240, after: 120 },
      }),
    )

    // Dimension table for this segment
    const segRows: any[] = [
      new (d().TableRow)({
        children: [
          headerCell('维度', 15),
          headerCell('得分', 10),
          headerCell('优点', 25),
          headerCell('不足', 25),
          headerCell('建议', 25),
        ],
        tableHeader: true,
      }),
    ]

    for (const dim of seg.dimensions) {
      segRows.push(
        new (d().TableRow)({
          children: [
            bodyCell(dim.dimension, { bold: true, width: 15, alignment: d().AlignmentType.CENTER }),
            bodyCell(`${dim.score}`, { color: scoreColor(dim.score), bold: true, width: 10, alignment: d().AlignmentType.CENTER }),
            buildMultiLineCell(dim.strengths, 25),
            buildMultiLineCell(dim.weaknesses, 25),
            buildMultiLineCell(dim.suggestions, 25),
          ],
        }),
      )
    }

    elements.push(
      new (d().Table)({
        rows: segRows,
        width: { size: 100, type: d().WidthType.PERCENTAGE },
        layout: d().TableLayoutType.FIXED,
      }),
    )
  }

  return elements
}

/** Build a table cell containing a bulleted list of items (or '--' if empty). */
function buildMultiLineCell(items: string[], width: number): any {
  if (!items.length) {
    return bodyCell('--', { width, alignment: d().AlignmentType.CENTER })
  }

  const paragraphs = items.map(
    (item) =>
      new (d().Paragraph)({
        children: [
          new (d().TextRun)({
            text: `• ${item}`,
            size: 18, // 9pt
            font: FONT_FAMILY,
            color: '555555',
          }),
        ],
        spacing: { before: 20, after: 20 },
      }),
  )

  return new (d().TableCell)({
    children: paragraphs,
    borders: createThinBorder(),
    width: { size: width, type: d().WidthType.PERCENTAGE },
  })
}

function buildFooter(): any[] {
  return [
    emptyLine(),
    new (d().Paragraph)({
      children: [
        new (d().TextRun)({
          text: '—— 本报告由 MentorAI（启智）平台自动生成 ——',
          size: 18,
          font: FONT_FAMILY,
          color: 'AAAAAA',
          italics: true,
        }),
      ],
      alignment: d().AlignmentType.CENTER,
      spacing: { before: 400 },
    }),
  ]
}

// ---- 主导出函数 ----

export async function exportDocumentReport(data: DocumentAnalysisResult): Promise<void> {
  await loadDeps()
  const children: any[] = [
    ...buildTitleSection(data),
    ...buildOverallScore(data),
    ...buildDimensionTable(data),
    ...buildCapabilitySummary(data),
    ...buildImprovementSuggestions(data),
    ...buildSegmentDetails(data),
    ...buildFooter(),
  ]

  const doc = new (d().Document)({
    styles: {
      default: {
        document: {
          run: {
            font: FONT_FAMILY,
            size: 22,
          },
        },
      },
    },
    sections: [
      {
        properties: {
          page: {
            margin: {
              top: 1440,    // 1 inch
              right: 1080,  // 0.75 inch
              bottom: 1440,
              left: 1080,
            },
          },
        },
        children,
      },
    ],
  })

  const blob = await d().Packer.toBlob(doc)
  const baseName = data.file_name.replace(/\.[^.]+$/, '')
  _saveAs!(blob, `${baseName}_分析报告.docx`)
}
