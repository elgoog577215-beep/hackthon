import { expect, it } from 'vitest'
import { createContentKnowledgeTree, filterKnowledgeTree, layoutKnowledgeTree } from '@/utils/knowledge-tree-layout'

it('searches only bound names and retains the same point and ancestor path', () => {
  const point = { knowledge_id: 'stable', name: '势函数', parent_id: 'methods', aliases: ['潜在函数', 'PF'],
    terms: [{ name: '势函数', english_name: 'Potential Function' }],
    term_candidates: [{ english_name: 'Invented Function' }] }
  const tree = createContentKnowledgeTree('c', '课程', [{ id: 'methods', name: '分析方法' }], [point])
  for (const query of ['  POTENTIAL   function  ', 'ＰＦ', '潜在函数']) {
    const nodes = layoutKnowledgeTree(filterKnowledgeTree(tree, query), new Set()).nodes
    expect(nodes.map(n => n.kind)).toEqual(['course', 'branch', 'knowledge'])
    expect(nodes.at(-1)?.sourceId).toBe('stable')
  }
  expect(filterKnowledgeTree(tree, 'Invented').children).toEqual([])
})

it('uses a short display name while retaining old names and complete knowledge for search', () => {
  const point = { knowledge_id: 'stable', name: '函数可导时导数给出切线斜率', display_name: '切线斜率',
    statement: '切线斜率等于该点导数。', display_aliases: ['导数的几何意义'], parent_id: 'g' }
  const tree = createContentKnowledgeTree('c', '微积分', [{ id: 'g', name: '导数应用' }], [point])
  const leaf = layoutKnowledgeTree(tree, new Set()).nodes.find(n => n.kind === 'knowledge')!
  expect(leaf.label).toBe('切线斜率')
  expect(leaf.sourceId).toBe('stable')
  for (const query of ['函数可导时', '切线斜率', '导数的几何意义', '该点导数']) {
    expect(layoutKnowledgeTree(filterKnowledgeTree(tree, query), new Set()).nodes.at(-1)?.sourceId).toBe('stable')
  }
})
