/**
 * 课堂教学视频分析报告 —— 原生 PDF 导出（pdf-lib）。
 *
 * 设计目标：与报告详情页「相似」、文字可选中/可搜索、文件小。
 * - 中文字体用 HarmonyOS Sans SC 子集（public/fonts/*.subset.ttf），按需 fetch；
 *   embedFont({ subset: true }) 仅嵌入实际用到的字形，最终 PDF 很小。
 * - 图表由调用方用 ECharts getDataURL 导出为 PNG 传入，这里嵌入为图片。
 * - 版式为 PDF 重排（A4、栏宽、分页、页脚页码），并非像素级复制网页。
 */
import { PDFDocument, PDFFont, PDFPage, rgb, type RGB } from 'pdf-lib'
import fontkit from '@pdf-lib/fontkit'

export interface ReportPdfDimension {
  key: string
  name: string
  score: number
  color: string
  desc: string
}

export interface ReportPdfChart {
  caption: string
  /** ECharts getDataURL 产出的 data:image/png;base64,... */
  dataUrl: string
}

export interface ReportPdfInput {
  title: string
  videoName: string
  date: string
  statusLabel: string
  overall: number
  dimensions: ReportPdfDimension[]
  summary: string
  suggestions: string[]
  /** 维度 key → 该维度下的图表（按出现顺序） */
  dimensionCharts: Record<string, ReportPdfChart[]>
}

// ---- 设计令牌（与报告页一致的品牌色系）----
const BRAND = hex('#1358e4')
const INK = hex('#161b22')
const INK2 = hex('#41474f')
const INK3 = hex('#8a9099')
const LINE = hex('#e6e8ec')
const SOFT = hex('#eef3fd')

const A4 = { w: 595.28, h: 841.89 }
const MARGIN = 44
const FOOTER_H = 28

function hex(h: string): RGB {
  const n = h.replace('#', '')
  return rgb(parseInt(n.slice(0, 2), 16) / 255, parseInt(n.slice(2, 4), 16) / 255, parseInt(n.slice(4, 6), 16) / 255)
}

function dataUrlToBytes(dataUrl: string): Uint8Array {
  const b64 = dataUrl.split(',')[1] ?? ''
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

let _fontCache: { regular: ArrayBuffer; bold: ArrayBuffer } | null = null
async function loadFonts(): Promise<{ regular: ArrayBuffer; bold: ArrayBuffer }> {
  if (_fontCache) return _fontCache
  const base = (import.meta.env.BASE_URL || '/').replace(/\/$/, '')
  const [regular, bold] = await Promise.all([
    fetch(`${base}/fonts/HarmonyOS_SC_Regular.subset.ttf`).then((r) => {
      if (!r.ok) throw new Error(`字体加载失败 (${r.status})`)
      return r.arrayBuffer()
    }),
    fetch(`${base}/fonts/HarmonyOS_SC_Bold.subset.ttf`).then((r) => {
      if (!r.ok) throw new Error(`字体加载失败 (${r.status})`)
      return r.arrayBuffer()
    }),
  ])
  _fontCache = { regular, bold }
  return _fontCache
}

/** 顶向下坐标的排版器：内部把 cursorY（距顶部）转换为 pdf-lib 的自底向上坐标。 */
class Layout {
  doc: PDFDocument
  regular: PDFFont
  bold: PDFFont
  page!: PDFPage
  y = MARGIN
  private title: string

  constructor(doc: PDFDocument, regular: PDFFont, bold: PDFFont, title: string) {
    this.doc = doc
    this.regular = regular
    this.bold = bold
    this.title = title
    this.addPage()
  }

  get contentW() {
    return A4.w - MARGIN * 2
  }
  private get bottomLimit() {
    return A4.h - MARGIN - FOOTER_H
  }

  addPage() {
    this.page = this.doc.addPage([A4.w, A4.h])
    this.y = MARGIN
  }

  /** 确保剩余空间 ≥ h，否则翻页 */
  ensure(h: number) {
    if (this.y + h > this.bottomLimit) this.addPage()
  }

  gap(dy: number) {
    this.y += dy
  }

  private wrap(text: string, font: PDFFont, size: number, maxW: number): string[] {
    const lines: string[] = []
    for (const para of String(text ?? '').split('\n')) {
      if (para === '') {
        lines.push('')
        continue
      }
      let line = ''
      for (const ch of para) {
        if (font.widthOfTextAtSize(line + ch, size) > maxW && line) {
          lines.push(line)
          line = ch
        } else {
          line += ch
        }
      }
      lines.push(line)
    }
    return lines
  }

  /** 段落文本（自动换行 + 跨页），返回结束后的 y。 */
  paragraph(
    text: string,
    opts: { size?: number; font?: PDFFont; color?: RGB; x?: number; maxW?: number; lineGap?: number; indent?: number } = {},
  ) {
    const size = opts.size ?? 10.5
    const font = opts.font ?? this.regular
    const color = opts.color ?? INK2
    const x = opts.x ?? MARGIN
    const maxW = opts.maxW ?? this.contentW - (opts.indent ?? 0)
    const lineH = size + (opts.lineGap ?? 5)
    for (const line of this.wrap(text, font, size, maxW)) {
      this.ensure(lineH)
      if (line) {
        this.page.drawText(line, { x: x + (opts.indent ?? 0), y: A4.h - this.y - size, size, font, color })
      }
      this.y += lineH
    }
  }

  /** 区块标题：左侧品牌竖条 + 加粗标题 + 底部细线 */
  heading(text: string, sub?: string) {
    this.gap(8)
    // 与后续内容保持在一起：底部空间不足以容纳标题+若干行内容时整体下移，避免孤行标题
    this.ensure(96)
    const top = this.y
    this.page.drawRectangle({ x: MARGIN, y: A4.h - top - 16, width: 4, height: 16, color: BRAND })
    this.page.drawText(text, { x: MARGIN + 12, y: A4.h - top - 14, size: 14, font: this.bold, color: INK })
    if (sub) {
      const tw = this.bold.widthOfTextAtSize(text, 14)
      this.page.drawText(sub, { x: MARGIN + 12 + tw + 8, y: A4.h - top - 13, size: 10, font: this.regular, color: INK3 })
    }
    this.y += 22
    this.page.drawLine({
      start: { x: MARGIN, y: A4.h - this.y },
      end: { x: A4.w - MARGIN, y: A4.h - this.y },
      thickness: 0.8,
      color: LINE,
    })
    this.y += 10
  }

  /** 顶部标题带（品牌色块 + 报告标题 + 元信息），仅首页顶部 */
  titleBand(title: string, meta: string[]) {
    const h = 76
    this.page.drawRectangle({ x: 0, y: A4.h - h, width: A4.w, height: h, color: BRAND })
    this.page.drawText(title, { x: MARGIN, y: A4.h - 40, size: 20, font: this.bold, color: rgb(1, 1, 1) })
    const metaLine = meta.filter(Boolean).join('    ·    ')
    if (metaLine) {
      this.page.drawText(metaLine, { x: MARGIN, y: A4.h - 60, size: 10, font: this.regular, color: rgb(0.85, 0.9, 1) })
    }
    this.y = h + 18
  }

  /** 综合得分（大数字）+ 标签 */
  overallScore(score: number) {
    this.ensure(56)
    const top = this.y
    this.page.drawText(fmt(score), { x: MARGIN, y: A4.h - top - 40, size: 44, font: this.bold, color: BRAND })
    const w = this.bold.widthOfTextAtSize(fmt(score), 44)
    this.page.drawText('综合得分', { x: MARGIN + w + 12, y: A4.h - top - 22, size: 12, font: this.regular, color: INK3 })
    this.page.drawText('满分 100', { x: MARGIN + w + 12, y: A4.h - top - 40, size: 9, font: this.regular, color: INK3 })
    this.y += 54
  }

  /** 五维得分条 */
  dimensionBars(dims: ReportPdfDimension[]) {
    const labelW = 64
    const barX = MARGIN + labelW + 6
    const barW = this.contentW - labelW - 6 - 46
    for (const d of dims) {
      this.ensure(20)
      const top = this.y
      this.page.drawText(d.name, { x: MARGIN, y: A4.h - top - 11, size: 10, font: this.regular, color: INK2 })
      this.page.drawRectangle({ x: barX, y: A4.h - top - 13, width: barW, height: 7, color: SOFT })
      const pct = Math.max(0, Math.min(100, d.score)) / 100
      if (pct > 0) {
        this.page.drawRectangle({ x: barX, y: A4.h - top - 13, width: barW * pct, height: 7, color: hex(d.color) })
      }
      this.page.drawText(`${fmt(d.score)}`, { x: barX + barW + 8, y: A4.h - top - 12, size: 10, font: this.bold, color: INK })
      this.y += 18
    }
  }

  bullets(items: string[], opts: { size?: number } = {}) {
    const size = opts.size ?? 10.5
    for (const it of items) {
      const startY = this.y
      this.ensure(size + 5)
      this.page.drawText('•', { x: MARGIN + 2, y: A4.h - startY - size, size, font: this.bold, color: BRAND })
      this.paragraph(it, { size, x: MARGIN + 14, maxW: this.contentW - 14 })
      if (this.y === startY) this.y += size + 5
    }
  }

  async image(dataUrl: string, caption: string) {
    let png
    try {
      png = await this.doc.embedPng(dataUrlToBytes(dataUrl))
    } catch {
      return
    }
    // 等比缩放到栏宽以内，限制最大高度
    const maxW = this.contentW
    const maxH = 300
    let w = png.width
    let h = png.height
    const ratio = Math.min(maxW / w, maxH / h, 1)
    w = w * ratio
    h = h * ratio
    this.gap(4)
    this.ensure(h + (caption ? 16 : 0) + 6)
    if (caption) {
      this.page.drawText(caption, { x: MARGIN, y: A4.h - this.y - 10, size: 9.5, font: this.regular, color: INK3 })
      this.y += 15
    }
    const x = MARGIN + (this.contentW - w) / 2
    this.page.drawImage(png, { x, y: A4.h - this.y - h, width: w, height: h })
    this.y += h + 8
  }

  /** 全部页面绘制页脚（页码 + 报告名），需在所有页生成后调用 */
  drawFooters() {
    const pages = this.doc.getPages()
    const total = pages.length
    pages.forEach((p, i) => {
      p.drawLine({
        start: { x: MARGIN, y: FOOTER_H + 6 },
        end: { x: A4.w - MARGIN, y: FOOTER_H + 6 },
        thickness: 0.6,
        color: LINE,
      })
      p.drawText(this.title, { x: MARGIN, y: FOOTER_H - 6, size: 8.5, font: this.regular, color: INK3 })
      const label = `${i + 1} / ${total}`
      const lw = this.regular.widthOfTextAtSize(label, 8.5)
      p.drawText(label, { x: A4.w - MARGIN - lw, y: FOOTER_H - 6, size: 8.5, font: this.regular, color: INK3 })
    })
  }
}

function fmt(n: number): string {
  const v = Number.isFinite(n) ? n : 0
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

/** 构建报告 PDF，返回字节流（用于下载）。 */
export async function buildReportPdf(input: ReportPdfInput): Promise<Uint8Array> {
  const { regular, bold } = await loadFonts()
  const doc = await PDFDocument.create()
  doc.registerFontkit(fontkit)
  // 注意：pdf-lib 的 subset:true 在大字库（CJK）上会丢字形——文本层正常、但视觉上大量
  // 汉字渲染为空白。故关闭其内置子集化，直接嵌入已用 pyftsubset 裁到 GB2312 的字体
  // （public/fonts/*.subset.ttf，约 1.6MB/权重，压缩后 ~1.2MB 进 PDF）。
  const regularFont = await doc.embedFont(regular, { subset: false })
  const boldFont = await doc.embedFont(bold, { subset: false })

  const L = new Layout(doc, regularFont, boldFont, input.title)

  // 首页标题带
  L.titleBand(input.title, [input.videoName, input.date, input.statusLabel])

  // 总览：综合得分 + 雷达图 + 五维得分条
  L.heading('总览')
  L.overallScore(input.overall)
  const overviewCharts = input.dimensionCharts['overview'] ?? []
  for (const c of overviewCharts) await L.image(c.dataUrl, c.caption)
  L.gap(4)
  L.dimensionBars(input.dimensions)

  // AI 总评
  if (input.summary && input.summary.trim()) {
    L.heading('AI 总评')
    L.paragraph(input.summary.trim())
  }

  // 改进建议
  if (input.suggestions.length) {
    L.heading('改进建议')
    L.bullets(input.suggestions)
  }

  // 各维度：标题（得分）+ 说明 + 图表
  for (const d of input.dimensions) {
    const charts = input.dimensionCharts[d.key] ?? []
    L.heading(d.name, `${fmt(d.score)} 分`)
    if (d.desc) L.paragraph(d.desc, { color: INK3, size: 10 })
    for (const c of charts) await L.image(c.dataUrl, c.caption)
  }

  L.drawFooters()
  return doc.save()
}
