import { describe, expect, it } from 'vitest'
import { buildHandoutConceptSections } from '../../utils/handout-concepts'

const plan = (node_id: string, knowledge_id: string, revision = '') => ({ node_id,
  source_knowledge_revision: revision,
  knowledge_structure: [{ knowledge_points: [{ name: '同名知识', knowledge_id, revision_id: 'p1', statement: node_id }] }],
})
const reading = ['s1', 's2'].map((id, i) => ({ id, title: id, anchor: id,
  blocks: [{ id: `b${i}`, anchor: `b${i}`, content: '同名知识', knowledge: [`k${i}`] }],
}))

describe('handout stable identity', () => {
  it('keeps same-name points distinct and locates each in its own section', () => {
    const sections = buildHandoutConceptSections([plan('s1', 'k0'), plan('s2', 'k1')], reading)
    expect(sections.map(s => s.nodes.map(n => [n.id, n.anchor]))).toEqual([[['k0', 'b0']], [['k1', 'b1']]])
  })

  it('prefers the current passage when a stable point is reused in multiple lessons', () => {
    const sections = buildHandoutConceptSections([plan('s1', 'k0'), plan('s2', 'k0')],
      reading.map(s => ({ ...s, blocks: s.blocks.map(b => ({ ...b, knowledge: ['k0'] })) })))
    expect(sections[1]!.nodes[0]!.anchor).toBe('b1')
  })

  it('never substitutes a name when an explicit relation ID is unknown', () => {
    const p = { ...plan('s1', 'k0'), knowledge_relations: [
      { source_knowledge_id: 'deleted', source_name: '同名知识', target_knowledge_id: 'k1', relation_type: 'derives', reason: 'reason' },
    ] }
    expect(buildHandoutConceptSections([p, plan('s2', 'k1')], reading)[0]!.relations).toEqual([])
  })

  it('does not borrow changed points from a different historical tree', () => {
    const p = { ...plan('s1', 'k0', 'old'), knowledge_relations: [
      { source_knowledge_id: 'k0', target_knowledge_id: 'k1', relation_type: 'derives', reason: 'reason' },
    ] }
    expect(buildHandoutConceptSections([p, plan('s2', 'k1', 'new')], reading)[0]!.relations).toEqual([])
  })

  it('keeps unavailable historical sources visible without pretending current content is a match', () => {
    const section = buildHandoutConceptSections([{ node_id: 's1', source_knowledge_revision: 'missing',
      knowledge_source_status: 'unavailable', knowledge_structure: [], knowledge_coverage: { status: 'unavailable', rows: [] } }], reading)[0]!
    expect(section.nodes).toEqual([])
    expect(section.sourceStatus).toBe('unavailable')
    expect(section.sourceRevision).toBe('missing')
  })
})
