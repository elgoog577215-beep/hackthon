export interface SlideVisualNode {
  node_id: string
  label: string
  emphasis?: string
  source_fragment_ids?: string[]
}

export interface SlideVisualEdge {
  source: string
  target: string
  label?: string
  relation?: string
}

export interface SlideVisual {
  visual_id: string
  kind: string
  purpose: string
  source_fragment_ids?: string[]
  alt_text: string
  asset_id?: string
  nodes?: SlideVisualNode[]
  edges?: SlideVisualEdge[]
  parameters?: Record<string, any>
}
