import { describe, expect, it } from 'vitest'
import demo from '@/demo/knowledge-profile.json'
import type { KnowledgeProfile } from '@/types/knowledge-profile'
import { createContentKnowledgeTree, createKnowledgeTree, filterKnowledgeTree, layoutKnowledgeTree } from '@/utils/knowledge-tree-layout'

const profile = demo.cases.at(-1)!.profile as KnowledgeProfile
describe('horizontal knowledge tree', () => {
  it('preserves mixed leaf depths and every ancestor beyond six levels', () => {
    const categories = Array.from({ length: 9 }, (_, i) => ({ id: `c${i}`, name: `主题${i}`, parent_id: i ? `c${i - 1}` : null, scope: `范围${i}` }))
    const tree = createContentKnowledgeTree('c', '递归', categories, [
      { knowledge_id: 'simple', parent_id: 'c1', name: '递归定义' },
      { knowledge_id: 'deep', parent_id: 'c8', name: '调用树分析', statement: '重复子问题' },
    ])
    const layout = layoutKnowledgeTree(tree, new Set())
    const shallow = layout.nodes.find(node => node.sourceId === 'simple')!
    const deep = layout.nodes.find(node => node.sourceId === 'deep')!
    expect(deep.x).toBeGreaterThan(shallow.x)
    expect(layout.nodes.find(node => node.sourceId === 'c8')).toMatchObject({ scope: '范围8' })
    const search = layoutKnowledgeTree(filterKnowledgeTree(tree, '重复子问题'), new Set())
    expect(search.nodes.filter(node => node.kind === 'branch').map(node => node.sourceId)).toEqual(categories.map(c => c.id))
    expect(search.nodes.filter(node => node.kind === 'knowledge').map(node => node.sourceId)).toEqual(['deep'])
    const folded = layoutKnowledgeTree(tree, new Set(['branch:c4']))
    expect(folded.nodes.some(node => node.sourceId === 'deep')).toBe(false)
    expect(folded.nodes.some(node => node.sourceId === 'simple')).toBe(true)
    expect(folded.nodes.find(node => node.sourceId === 'c4')?.count).toBe(1)
  })
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
