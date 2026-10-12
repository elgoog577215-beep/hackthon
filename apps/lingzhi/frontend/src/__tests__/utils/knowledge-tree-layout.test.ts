import { describe, expect, it } from 'vitest'
import demo from '@/demo/knowledge-profile.json'
import type { KnowledgeProfile } from '@/types/knowledge-profile'
import { createKnowledgeTree, layoutKnowledgeTree } from '@/utils/knowledge-tree-layout'

const profile = demo.cases.at(-1)!.profile as KnowledgeProfile
describe('horizontal knowledge tree', () => {
  it('places each unique knowledge point once, to the right of its ancestors', () => {
    const tree = createKnowledgeTree(profile, 'C')
    const layout = layoutKnowledgeTree(tree, new Set())
    const points = layout.nodes.filter(n => n.kind === 'knowledge')
    expect(points).toHaveLength(10)
    expect(new Set(points.map(n => n.sourceId)).size).toBe(10)
    for (const edge of layout.edges) expect(edge.target.x).toBeGreaterThan(edge.source.x + edge.source.width)
    for (let i = 0; i < points.length; i++) for (let j = i + 1; j < points.length; j++) {
      const a = points[i]!, b = points[j]!
      expect(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y).toBe(true)
    }
  })
  it('collapses a branch without losing its count or changing the course summary', () => {
    const tree = createKnowledgeTree(profile, 'C')
    const layout = layoutKnowledgeTree(tree, new Set(['branch:condition']))
    expect(layout.nodes.filter(n => n.kind === 'knowledge')).toHaveLength(6)
    expect(layout.nodes.find(n => n.id === 'branch:condition')?.count).toBe(4)
    expect(tree.progress).toBe(profile.summary.verified_progress)
  })
  it('search retains the complete ancestor path and unknown stays null', () => {
    const tree = createKnowledgeTree(profile, 'C', '中间结果')
    const layout = layoutKnowledgeTree(tree, new Set())
    expect(layout.nodes.map(n => n.kind)).toEqual(['course', 'branch', 'knowledge'])
    expect(layout.nodes.at(-1)?.progress).toBeNull()
    expect(tree.progress).toBe(profile.summary.verified_progress)
  })
})
