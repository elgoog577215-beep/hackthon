import { describe, expect, it } from 'vitest'
import { isRenderableSlideVisual } from '../../utils/slideVisual'

describe('isRenderableSlideVisual', () => {
  it('rejects semantic placeholders without an actual asset or structure', () => {
    expect(isRenderableSlideVisual({
      visual_id: 'placeholder',
      kind: 'generated_illustration',
      purpose: 'comparison',
      alt_text: '结构化对照',
    })).toBe(false)
    expect(isRenderableSlideVisual({
      visual_id: 'empty-table',
      kind: 'table',
      purpose: 'evidence',
      alt_text: '结构化对照',
      parameters: {},
    })).toBe(false)
  })

  it('accepts real assets and data-backed editable visuals', () => {
    expect(isRenderableSlideVisual({
      visual_id: 'image',
      kind: 'source_image',
      purpose: 'evidence',
      alt_text: '实验结果',
      asset_id: 'asset-1',
    })).toBe(true)
    expect(isRenderableSlideVisual({
      visual_id: 'diagram',
      kind: 'relational_diagram',
      purpose: 'structure',
      alt_text: '概念关系',
      nodes: [
        { node_id: 'a', label: 'A' },
        { node_id: 'b', label: 'B' },
      ],
      edges: [{ source: 'a', target: 'b' }],
    })).toBe(true)
  })
})
