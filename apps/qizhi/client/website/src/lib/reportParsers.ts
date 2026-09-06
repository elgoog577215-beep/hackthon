export interface TeachSegment {
  type: string
  content: string
  start_time: string
  end_time: string
  keypoint: string
}

export interface TeachSection {
  summary: string
  fileStructure: TeachSegment[]
}

export interface KnowledgeNode {
  id: string
  title: string
  start_time?: string
  end_time?: string
  children: KnowledgeNode[]
  level: number
}

export interface KnowledgeGraphNodeData {
  id: string
  word: string
  details: string
  children: KnowledgeGraphNodeData[]
  time_range?: { start: string; end: string }
  level: number
}

export type TranscriptSegment = { start: number; end: number; text: string }

export function tryParseJsonLike(value: unknown): unknown {
  if (typeof value !== 'string') return value
  const s = value.trim()
  if (!s) return value
  const normalized = s.startsWith('{') || s.startsWith('[') ? s : ''
  if (!normalized) return value
  try {
    return JSON.parse(normalized)
  } catch {
    try {
      const jsonish = normalized.replace(/'/g, '"')
      return JSON.parse(jsonish)
    } catch {
      return value
    }
  }
}

export function asAnalysisReportRecord(value: unknown): Record<string, unknown> | null {
  if (value != null && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

export function extractTranscriptSegments(report: unknown): TranscriptSegment[] {
  const r = tryParseJsonLike(report)
  if (!r || typeof r !== 'object') return []
  const obj = r as Record<string, unknown>

  const direct = tryParseJsonLike(obj.transcript)
  if (Array.isArray(direct)) {
    return direct
      .map((x) => {
        if (!x || typeof x !== 'object') return null
        const o = x as Record<string, unknown>
        const start = typeof o.start === 'number' ? o.start : Number(o.start)
        const end = typeof o.end === 'number' ? o.end : Number(o.end)
        const text = typeof o.text === 'string' ? o.text : (o.text != null ? String(o.text) : '')
        if (!Number.isFinite(start) || !Number.isFinite(end) || !text.trim()) return null
        return { start, end, text: text.trim() }
      })
      .filter(Boolean) as TranscriptSegment[]
  }

  const result = obj.result
  if (result && typeof result === 'object') {
    const resObj = result as Record<string, unknown>
    const inner = tryParseJsonLike(resObj.transcript)
    if (Array.isArray(inner)) {
      return inner
        .map((x) => {
          if (!x || typeof x !== 'object') return null
          const o = x as Record<string, unknown>
          const start = typeof o.start === 'number' ? o.start : Number(o.start)
          const end = typeof o.end === 'number' ? o.end : Number(o.end)
          const text = typeof o.text === 'string' ? o.text : (o.text != null ? String(o.text) : '')
          if (!Number.isFinite(start) || !Number.isFinite(end) || !text.trim()) return null
          return { start, end, text: text.trim() }
        })
        .filter(Boolean) as TranscriptSegment[]
    }
  }
  return []
}

export function formatSec(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00'
  const s = Math.floor(sec)
  const mm = Math.floor(s / 60)
  const ss = s % 60
  return `${mm}:${String(ss).padStart(2, '0')}`
}

export function parseTimeToSeconds(s: string): number {
  if (!s) return 0
  const parts = s.split(':').map((v) => Number(v))
  if (parts.some((n) => Number.isNaN(n))) return 0
  if (parts.length === 3) return (parts[0] ?? 0) * 3600 + (parts[1] ?? 0) * 60 + (parts[2] ?? 0)
  if (parts.length === 2) return (parts[0] ?? 0) * 60 + (parts[1] ?? 0)
  if (parts.length === 1) return parts[0] ?? 0
  return 0
}

export function formatSection(value: unknown): string {
  if (!value) return '暂无数据'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function hasData(value: unknown): boolean {
  if (value == null) return false
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'object') return Object.keys(value).length > 0
  return true
}

export function getStr(obj: Record<string, unknown> | Record<string, unknown>[] | undefined, key: string): string {
  if (!obj || Array.isArray(obj) || obj[key] == null) return ''
  const v = obj[key]
  return typeof v === 'string' ? v : String(v)
}

export function getArr(obj: Record<string, unknown> | undefined, key: string): string[] | undefined {
  if (!obj || !Array.isArray(obj[key])) return undefined
  const arr = obj[key] as unknown[]
  return arr.every((x) => typeof x === 'string') ? (arr as string[]) : undefined
}

export function getNum(obj: Record<string, unknown> | undefined, key: string): number | null {
  if (!obj || obj[key] == null) return null
  const v = obj[key]
  if (typeof v === 'number' && !Number.isNaN(v)) return v
  if (typeof v === 'string') {
    const n = Number(v)
    return Number.isNaN(n) ? null : n
  }
  return null
}

export function parseTeachSummary(value: unknown): TeachSection[] {
  if (!value) return []
  let data = value
  if (typeof value === 'string') {
    try {
      data = JSON.parse(value)
    } catch {
      return []
    }
  }
  if (!Array.isArray(data)) return []
  const result: TeachSection[] = []
  for (const item of data) {
    if (!item || typeof item !== 'object') continue
    const obj = item as Record<string, unknown>
    const summary = typeof obj.summary === 'string' ? obj.summary : ''
    const fileStructure: TeachSegment[] = []
    if (Array.isArray(obj.file_structure)) {
      for (const seg of obj.file_structure) {
        if (!seg || typeof seg !== 'object') continue
        const s = seg as Record<string, unknown>
        fileStructure.push({
          type: typeof s.type === 'string' ? s.type : '',
          content: typeof s.content === 'string' ? s.content : '',
          start_time: typeof s.start_time === 'string' ? s.start_time : '',
          end_time: typeof s.end_time === 'string' ? s.end_time : '',
          keypoint:
            typeof s.keypoint === 'string'
              ? s.keypoint
              : typeof s.keypoint_name === 'string'
                ? s.keypoint_name
                : '',
        })
      }
    }
    result.push({ summary, fileStructure })
  }
  return result
}

export function parseKnowledgeTree(value: unknown): KnowledgeNode[] {
  if (!value) return []
  let data = value
  if (typeof value === 'string') {
    try {
      data = JSON.parse(value)
    } catch {
      return []
    }
  }
  if (!Array.isArray(data)) return []

  const parseNode = (item: unknown, level: number): KnowledgeNode | null => {
    if (!item || typeof item !== 'object') return null
    const obj = item as Record<string, unknown>
    const id = typeof obj.id === 'string' ? obj.id : ''
    const title = typeof obj.title === 'string' ? obj.title : ''
    const start_time = typeof obj.start_time === 'string' ? obj.start_time : undefined
    const end_time = typeof obj.end_time === 'string' ? obj.end_time : undefined

    const children: KnowledgeNode[] = []
    if (Array.isArray(obj.children)) {
      for (const child of obj.children) {
        const parsed = parseNode(child, level + 1)
        if (parsed) children.push(parsed)
      }
    }

    return { id, title, start_time, end_time, children, level }
  }

  const result: KnowledgeNode[] = []
  for (const item of data) {
    const node = parseNode(item, 0)
    if (node) result.push(node)
  }
  return result
}

export function parseKnowledgeGraph(value: unknown): KnowledgeGraphNodeData[] {
  if (!value) return []
  let data = value
  if (typeof value === 'string') {
    try {
      data = JSON.parse(value)
    } catch {
      return []
    }
  }
  let items: unknown[] = []
  if (typeof data === 'object' && data !== null) {
    const obj = data as Record<string, unknown>
    if (obj.result && typeof obj.result === 'object') {
      const innerResult = obj.result as Record<string, unknown>
      if (Array.isArray(innerResult.result)) {
        items = innerResult.result
      } else if (Array.isArray(obj.result)) {
        items = obj.result
      }
    } else if (Array.isArray(obj.result)) {
      items = obj.result
    }
  }
  if (!Array.isArray(items) || items.length === 0) {
    if (Array.isArray(data)) items = data
    else return []
  }

  const parseNode = (item: unknown, level: number): KnowledgeGraphNodeData | null => {
    if (!item || typeof item !== 'object') return null
    const obj = item as Record<string, unknown>
    const id = typeof obj.id === 'string' ? obj.id : ''
    const word = typeof obj.word === 'string' ? obj.word : ''
    const details = typeof obj.details === 'string' ? obj.details : ''

    let time_range: { start: string; end: string } | undefined
    if (obj.time_range && typeof obj.time_range === 'object') {
      const tr = obj.time_range as Record<string, unknown>
      const start = typeof tr.start === 'string' ? tr.start : ''
      const end = typeof tr.end === 'string' ? tr.end : ''
      if (start || end) time_range = { start, end }
    }

    const children: KnowledgeGraphNodeData[] = []
    if (Array.isArray(obj.children)) {
      for (const child of obj.children) {
        const parsed = parseNode(child, level + 1)
        if (parsed) children.push(parsed)
      }
    }

    return { id, word, details, children, time_range, level }
  }

  const result: KnowledgeGraphNodeData[] = []
  for (const item of items) {
    const node = parseNode(item, 0)
    if (node) result.push(node)
  }
  return result
}

export function parseVolumeData(value: unknown): number[] {
  if (!value) return []
  let data = value
  if (typeof value === 'string') {
    try {
      data = JSON.parse(value)
    } catch {
      return []
    }
  }
  let items: unknown[] = []
  if (typeof data === 'object' && data !== null) {
    const obj = data as Record<string, unknown>
    if (obj.data && typeof obj.data === 'object') {
      const dataObj = obj.data as Record<string, unknown>
      if (Array.isArray(dataObj.result)) {
        items = dataObj.result
      }
    } else if (Array.isArray(obj.result)) {
      items = obj.result
    }
  }
  if (!Array.isArray(items) || items.length === 0) {
    if (Array.isArray(data)) items = data
    else return []
  }
  return items.filter((x): x is number => typeof x === 'number' && !Number.isNaN(x))
}

export function clampRadarScore(n: number): number {
  if (!Number.isFinite(n)) return 0
  let x = n
  if (x >= 0 && x <= 1) x *= 100
  if (x < 0) return 0
  if (x > 100) return 100
  return x
}

export function parseRadarChartInput(raw: unknown): { labels: string[]; values: number[] } | null {
  const trimLabel = (s: string) => {
    const t = s.trim()
    if (!t) return ''
    return t.length > 10 ? `${t.slice(0, 9)}…` : t
  }

  if (raw == null) return null

  if (Array.isArray(raw)) {
    const labels: string[] = []
    const values: number[] = []
    for (const item of raw) {
      if (!item || typeof item !== 'object') continue
      const o = item as Record<string, unknown>
      const label = trimLabel(
        String(o.label ?? o.name ?? o.dimension ?? o.axis ?? o.key ?? o.title ?? '').trim(),
      )
      const valRaw = o.value ?? o.score ?? o.val ?? o.num ?? o.weight
      const num = typeof valRaw === 'number' ? valRaw : Number(valRaw)
      if (label) {
        labels.push(label)
        values.push(clampRadarScore(num))
      }
    }
    return labels.length >= 3 && labels.length === values.length ? { labels, values } : null
  }

  if (typeof raw === 'object') {
    const o = raw as Record<string, unknown>
    const nested = o.series ?? o.points ?? o.items ?? o.axes ?? o.data
    if (nested != null && nested !== raw) {
      const inner = parseRadarChartInput(nested)
      if (inner) return inner
    }
    const dims = o.dimensions ?? o.labels
    const vals = o.values ?? o.scores
    if (Array.isArray(dims) && Array.isArray(vals) && dims.length === vals.length && dims.length >= 3) {
      const labels = dims.map((d) => trimLabel(String(d)))
      const values = vals.map((v) => clampRadarScore(typeof v === 'number' ? v : Number(v)))
      if (labels.every(Boolean)) return { labels, values }
    }

    const reserved = new Set([
      'series', 'points', 'items', 'axes', 'data',
      'dimensions', 'labels', 'values', 'scores',
    ])
    const pairs: { label: string; value: number }[] = []
    for (const [k, v] of Object.entries(o)) {
      if (reserved.has(k)) continue
      let num: number | null = null
      if (typeof v === 'number' && Number.isFinite(v)) num = v
      else if (typeof v === 'string' && v.trim() !== '') {
        const parsed = Number(String(v).trim().replace(/,/g, ''))
        if (Number.isFinite(parsed)) num = parsed
      }
      if (num == null) continue
      const label = trimLabel(k)
      if (label) pairs.push({ label, value: clampRadarScore(num) })
    }
    if (pairs.length >= 3) {
      return {
        labels: pairs.map((p) => p.label),
        values: pairs.map((p) => p.value),
      }
    }
  }

  return null
}

export function collectKnowledgeTitles(node: unknown, acc: string[]): void {
  if (!node || typeof node !== 'object') return
  const obj = node as Record<string, unknown>
  if (Array.isArray(obj.file_structure)) {
    for (const child of obj.file_structure) collectKnowledgeTitles(child, acc)
    return
  }
  const title = typeof obj.title === 'string' ? obj.title.trim() : ''
  if (title) acc.push(title)
  if (Array.isArray(obj.children)) {
    for (const child of obj.children) collectKnowledgeTitles(child, acc)
  }
}

export function isNonEmptyReportRecord(report: unknown): boolean {
  return report != null && typeof report === 'object' && Object.keys(report as Record<string, unknown>).length > 0
}

export function formatRadarScore(v: number | undefined | null): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return String(Math.round(v))
}
