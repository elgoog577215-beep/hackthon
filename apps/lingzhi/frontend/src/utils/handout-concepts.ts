/** Read-only projection of the existing lesson knowledge contract. No inferred edges. */
export const handoutRelationTypes = ['prerequisite', 'derives', 'applies_to', 'contrasts_with', 'equivalent_to', 'generalizes'] as const
export type HandoutRelationType = typeof handoutRelationTypes[number]
export interface HandoutConcept { id: string; name: string; statement: string; anchor: string; external: boolean }
export interface HandoutRelation {
  id: string; source: string; target: string; type: HandoutRelationType; reason: string
  conditions: string[]; distinction: string; steps: string[]; sourceRefs: (string | Record<string, unknown>)[]
  groupId: string; groupOperator: string; necessity: string
}
export interface HandoutCoverage {
  status: string; scope_known: boolean; semantics_verified: false; source_knowledge_revision: string
  rows: { knowledge_id: string; name: string; revision_id: string; block_ids: string[]; explanation_block_ids: string[]; example_block_ids: string[]; exercise_block_ids: string[] }[]
  invalid_refs: { block_id: string; knowledge_id: string; reason: string }[]
}
export interface HandoutConceptSection { id: string; title: string; anchor: string; blockAnchors: string[]; nodes: HandoutConcept[]; relations: HandoutRelation[]; sourceStatus?: string; sourceRevision?: string; coverage?: HandoutCoverage }
export interface HandoutReadingSection { id: string; title: string; anchor: string; blocks: { id: string; title?: string; anchor: string; content: string; knowledge: string[]; knowledgeRefs?: { knowledge_id: string; revision_id: string }[]; sourceRevision?: string }[] }
const record = (v: unknown): Record<string, any> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : {}
const list = (v: unknown): any[] => Array.isArray(v) ? v : []
const text = (v: unknown): string => typeof v === 'string' ? v.trim() : ''
const names = (v: unknown): string[] => list(v).map(text).filter(Boolean)

export function buildHandoutConceptSections(rawPlans: unknown, reading: HandoutReadingSection[]): HandoutConceptSection[] {
  const plans = list(rawPlans).map(record)
  const planPoints = (plan: Record<string, any>) => list(plan.knowledge_structure).flatMap(group => list(record(group).knowledge_points).map(record))
  // Legacy display keys are scoped and never written back as formal identities.
  const identity = (point: Record<string, any>, section: string) => text(point.knowledge_id || point.knowledge_key) || `legacy:${section}:${text(point.name)}`
  return reading.map(section => {
    const plan = plans.find(p => p.node_id === section.id) || {}
    const revision = text(plan.source_knowledge_revision)
    const compatible = plans.filter(p => text(p.source_knowledge_revision) === revision)
    const points = new Map<string, Record<string, any>>()
    // Prefer this section's point payload and historical revision.
    for (const p of [plan, ...compatible]) for (const point of planPoints(p)) {
      if (text(point.name)) {
        const id = identity(point, text(p.node_id))
        if (!points.has(id)) points.set(id, point)
      }
    }
    const owned = new Set(planPoints(plan).map(p => identity(p, section.id)))
    const aliases = new Map<string, Set<string>>()
    for (const [id, point] of points) for (const alias of [point.name, point.knowledge_key, ...names(point.aliases)]) {
      if (!text(alias)) continue
      const matches = aliases.get(text(alias)) || new Set<string>()
      matches.add(id); aliases.set(text(alias), matches)
    }
    function resolve(value: unknown): string {
      const key = text(value)
      if (points.has(key)) return key
      const matches = aliases.get(key)
      return matches?.size === 1 ? [...matches][0]! : ''
    }
    function endpoint(value: Record<string, any>, side: 'source' | 'target'): string {
      const id = text(value[`${side}_knowledge_id`] || value[`${side}_id`])
      return id ? (points.has(id) ? id : '') : resolve(value[`${side}_name`] || value[`${side}_key`])
    }
    function locate(id: string): string {
      const point = points.get(id)!
      const compatibleSections = new Set(compatible.map(p => text(p.node_id)))
      const blocks = [section, ...reading.filter(s => s.id !== section.id && compatibleSections.has(s.id))].flatMap(s => s.blocks)
      const bound = blocks.find(block => revision
        ? block.sourceRevision === revision && block.knowledgeRefs?.some(ref => ref.knowledge_id === id && Boolean(ref.revision_id) && ref.revision_id === point.revision_id)
        : block.knowledge.some(key => resolve(key) === id))
      if (bound) return bound.anchor
      // Literal fallback is only navigation for unversioned legacy prose, and
      // only for unambiguous names. It is never coverage or relation evidence.
      if (revision) return ''
      const labels = [text(point.name), ...names(point.aliases)].filter(label => resolve(label) === id)
      const titled = blocks.find(block => labels.some(label => block.title?.includes(label)))
      return titled?.anchor || blocks.find(block => labels.some(label => block.content.includes(label)))?.anchor || ''
    }
    const candidates = [...list(plan.knowledge_relations)]
    for (const id of owned) for (const relation of list(points.get(id)?.relations)) candidates.push({ ...record(relation), source_knowledge_id: id })
    const relations: HandoutRelation[] = [], seen = new Map<string, HandoutRelation>()
    for (const raw of candidates) {
      const value = record(raw), source = endpoint(value, 'source'), target = endpoint(value, 'target')
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
      seen.set(signature, relation); relations.push(relation)
    }
    const included = new Set([...owned, ...names(plan.reused_knowledge_names).map(resolve).filter(Boolean)])
    relations.forEach(edge => { included.add(edge.source); included.add(edge.target) })
    const nodes = [...included].filter(id => points.has(id)).map(id => ({ id, name: text(points.get(id)!.name), statement: text(points.get(id)!.statement || points.get(id)!.description), anchor: locate(id), external: !owned.has(id) }))
    return { id: section.id, title: section.title, anchor: section.anchor, blockAnchors: section.blocks.map(block => block.anchor), nodes, relations,
      sourceStatus: text(plan.knowledge_source_status), sourceRevision: revision,
      coverage: plan.knowledge_coverage as HandoutCoverage | undefined }
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
