export function scoreClass(score: number): string {
  if (!(score > 0)) return 'score-none'
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-mid'
  return 'score-low'
}

export function fmtScore(score: unknown): string {
  const n = Number(score ?? 0)
  return n > 0 ? String(n) : '—'
}

export function fmtScoreCn(score: unknown): string {
  const n = Number(score ?? 0)
  return n > 0 ? `${n}分` : '—'
}

export function toScore(score: unknown): number {
  return Number(score ?? 0)
}

export function formatTime(seconds: unknown): string {
  const s = Number(seconds ?? 0)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export function timeStrToSeconds(t: unknown): number {
  const str = String(t ?? '').trim()
  if (!str) return 0
  const parts = str.split(':')
  if (parts.length === 3) {
    return parseInt(parts[0] ?? '0') * 3600 + parseInt(parts[1] ?? '0') * 60 + parseFloat(parts[2] ?? '0')
  } else if (parts.length === 2) {
    return parseInt(parts[0] ?? '0') * 60 + parseFloat(parts[1] ?? '0')
  }
  const n = parseFloat(str)
  return isNaN(n) ? 0 : n
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    unstarted: '待分析',
    waiting: '分析中',
    success: '分析完成',
    failed: '分析失败',
  }
  return map[status] ?? status
}

export function stripMarkdown(md: string): string {
  return String(md ?? '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s*[-*+]\s+/gm, '• ')
    .trim()
}
