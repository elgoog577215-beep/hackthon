import type { SlideVisual } from '../types/slideVisual'

const IMAGE_KINDS = new Set([
  'source_image',
  'retrieved_image',
  'generated_illustration',
])

export function isRenderableSlideVisual(visual?: SlideVisual | null): boolean {
  if (!visual) return false
  if (IMAGE_KINDS.has(visual.kind)) return Boolean(visual.asset_id)
  if (['relational_diagram', 'rule_diagram'].includes(visual.kind)) {
    return (visual.nodes?.length || 0) >= 2
  }
  if (visual.kind === 'coordinate_plot') {
    return Array.isArray(visual.parameters?.points)
      && visual.parameters.points.length > 0
  }
  if (visual.kind === 'chart') {
    return Array.isArray(visual.parameters?.values)
      && visual.parameters.values.length > 0
  }
  if (visual.kind === 'formula') {
    return Boolean(String(visual.parameters?.formula || visual.alt_text || '').trim())
  }
  if (visual.kind === 'table') {
    return Array.isArray(visual.parameters?.rows)
      && visual.parameters.rows.length > 0
  }
  return false
}
