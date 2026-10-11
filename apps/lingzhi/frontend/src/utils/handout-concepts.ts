/** Read-only projection of the existing lesson knowledge contract. No inferred edges. */
export const handoutRelationTypes = ['prerequisite', 'derives', 'applies_to', 'contrasts_with', 'equivalent_to', 'generalizes'] as const
export type HandoutRelationType = typeof handoutRelationTypes[number]
export interface HandoutConcept { id: string; name: string; statement: string; anchor: string; external: boolean }
export interface HandoutRelation {
  id: string; source: string; target: string; type: HandoutRelationType; reason: string
  conditions: string[]; distinction: string; steps: string[]; sourceRefs: (string | Record<string, unknown>)[]
  groupId: string; groupOperator: string; necessity: string
}
export interface HandoutConceptSection { id: string; title: string; anchor: string; blockAnchors: string[]; nodes: HandoutConcept[]; relations: HandoutRelation[] }
export interface HandoutReadingSection { id: string; title: string; anchor: string; blocks: { id: string; title?: string; anchor: string; content: string; knowledge: string[] }[] }
const record = (v: unknown): Record<string, any> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : {}
const list = (v: unknown): any[] => Array.isArray(v) ? v : []
const text = (v: unknown): string => typeof v === 'string' ? v.trim() : ''
const names = (v: unknown): string[] => list(v).map(text).filter(Boolean)

export function buildHandoutConceptSections(rawPlans: unknown, reading: HandoutReadingSection[]): HandoutConceptSection[] {
  const plans = list(rawPlans).map(record)
  const points = new Map<string, { data: Record<string, any>; section: string }>()
  const identities = new Map<string, string>()
  for (const plan of plans) for (const group of list(plan.knowledge_structure)) for (const raw of list(record(group).knowledge_points)) {
    const point = record(raw), name = text(point.name)
    if (!name) continue
    if (!points.has(name)) points.set(name, { data: point, section: text(plan.node_id) })
    for (const alias of [name, point.knowledge_id, point.knowledge_key, ...names(point.aliases)]) if (text(alias)) identities.set(text(alias), name)
  }
  function locate(name: string): string {
    const point = points.get(name)?.data || {}
    const aliases = [name, ...names(point.aliases)]
    const blocks = reading.flatMap(section => section.blocks)
    // Exact identity binding wins over text. Literal text locates prose only;
    // it never supplies or verifies a knowledge relation.
    const bound = blocks.filter(block => block.knowledge.some(key => identities.get(key) === name || aliases.includes(key)))
    if (bound.length) return (bound.find(block => aliases.some(alias => block.content.includes(alias))) || bound[0])!.anchor
    const titled = blocks.find(block => aliases.some(alias => block.title?.includes(alias)))
    if (titled) return titled.anchor
    const literal = blocks.find(block => aliases.some(alias => block.content.includes(alias)))
    return literal?.anchor || ''
  }
  return reading.map(section => {
    const plan = plans.find(p => p.node_id === section.id) || {}
    const owned = new Set(list(plan.knowledge_structure).flatMap(group => list(record(group).knowledge_points).map(p => text(record(p).name))).filter(Boolean))
    const candidates = [...list(plan.knowledge_relations)]
    for (const name of owned) for (const relation of list(points.get(name)?.data.relations)) candidates.push({ ...record(relation), source_name: name })
    const relations: HandoutRelation[] = [], seen = new Map<string, HandoutRelation>()
    for (const raw of candidates) {
      const value = record(raw)
      const source = identities.get(text(value.source_name || value.source_key || value.source_knowledge_id)) || ''
      const target = identities.get(text(value.target_name || value.target_key || value.target_knowledge_id)) || ''
      const type = text(value.relation_type) as HandoutRelationType
      if (!source || !target || source === target || !handoutRelationTypes.includes(type) || !text(value.reason)) continue
      const symmetric = type === 'equivalent_to' || type === 'contrasts_with'
      const pair = symmetric ? [source, target].sort() : [source, target]
      const signature = JSON.stringify([type, ...pair, names(value.conditions), text(value.relation_group_id), text(value.group_operator), text(value.necessity)])
      const refs = list(value.source_refs).filter(ref => typeof ref === 'string' || (ref && typeof ref === 'object' && !Array.isArray(ref)))
      const existing = seen.get(signature)
      if (existing) {
        for (const ref of refs) if (!existing.sourceRefs.some(saved => JSON.stringify(saved) === JSON.stringify(ref))) existing.sourceRefs.push(ref)
        if (!existing.steps.length) existing.steps = names(value.derivation_steps)
        if (!existing.distinction) existing.distinction = text(value.distinction)
        continue
      }
      const relation = { id: signature, source, target, type, reason: text(value.reason), conditions: names(value.conditions), distinction: text(value.distinction), steps: names(value.derivation_steps), sourceRefs: refs, groupId: text(value.relation_group_id), groupOperator: text(value.group_operator).toUpperCase(), necessity: text(value.necessity) }
      seen.set(signature, relation)
      relations.push(relation)
    }
    const included = new Set([...owned, ...names(plan.reused_knowledge_names).map(name => identities.get(name) || name)])
    relations.forEach(edge => { included.add(edge.source); included.add(edge.target) })
    const nodes = [...included].filter(name => points.has(name)).map(name => ({ id: name, name, statement: text(points.get(name)?.data.statement || points.get(name)?.data.description), anchor: locate(name), external: !owned.has(name) }))
    return { id: section.id, title: section.title, anchor: section.anchor, blockAnchors: section.blocks.map(block => block.anchor), nodes, relations }
  })
}

/** Dependency ranks with cycles condensed, while symmetric/comparison edges stay lateral. */
export function conceptLayers(section: HandoutConceptSection): HandoutConcept[][] {
  const edges = section.relations.flatMap(edge => edge.type === 'contrasts_with' ? [] : edge.type === 'equivalent_to' ? [edge, { ...edge, source: edge.target, target: edge.source }] : [edge])
  const reachable = (start: string, target: string) => {
    const visited = new Set<string>(), queue = [start]
    while (queue.length) {
      const current = queue.pop()!
      if (current === target) return true
      if (visited.has(current)) continue
      visited.add(current)
      queue.push(...edges.filter(edge => edge.source === current).map(edge => edge.target))
    }
    return false
  }
  const groups: string[][] = []
  for (const node of section.nodes) {
    const group = groups.find(g => reachable(g[0]!, node.id) && reachable(node.id, g[0]!))
    if (group) group.push(node.id); else groups.push([node.id])
  }
  const groupOf = (id: string) => groups.findIndex(g => g.includes(id))
  const cache = new Map<number, number>()
  function rank(i: number): number {
    if (cache.has(i)) return cache.get(i)!
    const parents = edges.filter(edge => groupOf(edge.target) === i && groupOf(edge.source) !== i).map(edge => groupOf(edge.source))
    const value = parents.length ? 1 + Math.max(...parents.map(rank)) : 0
    cache.set(i, value)
    return value
  }
  const rows: HandoutConcept[][] = []
  section.nodes.forEach(node => { const level = rank(groupOf(node.id)); (rows[level] ||= []).push(node) })
  return rows
}
