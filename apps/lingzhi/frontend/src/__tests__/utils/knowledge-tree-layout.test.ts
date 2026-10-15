import { describe, expect, it } from 'vitest'
import demo from '@/demo/knowledge-profile.json'
import type { KnowledgeProfile } from '@/types/knowledge-profile'
import { createContentKnowledgeTree, createKnowledgeTree, filterKnowledgeTree, layoutKnowledgeTree } from '@/utils/knowledge-tree-layout'

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
  it('builds a teacher tree with nested categories and keeps uncategorized points reachable', () => {
    const tree = createContentKnowledgeTree('course', '处理器', [
      { id: 'root', name: '硬件' }, { id: 'child', parent_id: 'root', name: '处理器' },
    ], [
      { knowledge_id: 'cpu', parent_id: 'child', name: 'CPU作用', statement: 'CPU执行指令' },
      { knowledge_id: 'orphan', parent_id: 'missing', name: '主存' },
    ])
    expect(tree.count).toBe(2)
    expect(tree.children[0]?.count).toBe(1)
    expect(layoutKnowledgeTree(tree, new Set()).nodes.filter(node => node.kind === 'knowledge').map(node => node.sourceId)).toEqual(['cpu', 'orphan'])
    const filtered = filterKnowledgeTree(tree, '执行指令')
    expect(layoutKnowledgeTree(filtered, new Set()).nodes.map(node => node.label)).toEqual(['处理器', '硬件', '处理器', 'CPU作用'])
    expect(filtered.count).toBe(2)
    expect(filterKnowledgeTree(tree, '不存在').children).toEqual([])
  })
})
