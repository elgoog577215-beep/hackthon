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
