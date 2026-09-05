export interface TextPositionAnchor {
  start: number
  end: number
  prefix: string
  suffix: string
  occurrence: number
}

export interface TextQuoteAnchor extends Record<string, unknown> {
  text_quote: string
  text_position: TextPositionAnchor
}

export interface ResolvedTextPosition {
  status: 'exact' | 'quote_remap' | 'ambiguous' | 'missing'
  start: number
  end: number
  occurrence: number
}

const quotePositions = (content: string, quote: string): number[] => {
  const positions: number[] = []
  let cursor = 0
  while (quote && cursor <= content.length) {
    const index = content.indexOf(quote, cursor)
    if (index < 0) break
    positions.push(index)
    cursor = index + Math.max(1, quote.length)
  }
  return positions
}

const positionPayload = (content: string, quote: string, start: number): TextPositionAnchor => ({
  start,
  end: start + quote.length,
  prefix: content.slice(Math.max(0, start - 80), start),
  suffix: content.slice(start + quote.length, start + quote.length + 80),
  occurrence: quotePositions(content, quote).filter(position => position < start).length,
})

export function buildTextQuoteAnchor(range: Range, root: HTMLElement, quote = range.toString()): TextQuoteAnchor {
  const content = root.textContent || ''
  const before = document.createRange()
  before.selectNodeContents(root)
  before.setEnd(range.startContainer, range.startOffset)
  const start = Math.max(0, before.toString().length)
  return {
    text_quote: quote,
    text_position: positionPayload(content, quote, start),
  }
}

export function resolveTextQuoteAnchor(
  content: string,
  quote: string,
  anchor?: Partial<TextPositionAnchor> | null,
): ResolvedTextPosition {
  const start = Math.max(0, Number(anchor?.start || 0))
  const end = Math.max(start, Number(anchor?.end || 0))
  if (end > start && content.slice(start, end) === quote) {
    return { status: 'exact', start, end, occurrence: Number(anchor?.occurrence || 0) }
  }
  const positions = quotePositions(content, quote)
  if (!positions.length) return { status: 'missing', start: -1, end: -1, occurrence: -1 }

  const prefix = String(anchor?.prefix || '').slice(-80)
  const suffix = String(anchor?.suffix || '').slice(0, 80)
  const occurrence = Math.max(0, Number(anchor?.occurrence || 0))
  const candidates = positions.map((position, index) => {
    const candidateEnd = position + quote.length
    let score = 0
    if (prefix && content.slice(Math.max(0, position - prefix.length), position) === prefix) score += 4
    if (suffix && content.slice(candidateEnd, candidateEnd + suffix.length) === suffix) score += 4
    if (index === occurrence) score += 1
    return { position, index, score, distance: Math.abs(position - start) }
  }).sort((left, right) => right.score - left.score || left.distance - right.distance)

  const best = candidates[0]!
  const second = candidates[1]
  if (second && second.score === best.score && second.distance === best.distance && !prefix && !suffix) {
    return { status: 'ambiguous', start: -1, end: -1, occurrence: -1 }
  }
  return {
    status: 'quote_remap',
    start: best.position,
    end: best.position + quote.length,
    occurrence: best.index,
  }
}
