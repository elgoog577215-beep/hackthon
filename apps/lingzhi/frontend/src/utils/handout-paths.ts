import { handoutContentType } from './handout-content'
import type { ReferenceSection } from './handout-reference'

export type ReadingToolState = 'ready' | 'legacy' | 'missing' | 'stale'
export type PathStage = 'start' | 'choice' | 'step' | 'result' | 'check'
export interface LearningPathStep {
  id: string; parentId: string; stage: PathStage; text: string; reason: string; condition: string
  sources: { blockId: string; title: string }[]
}
export interface LearningPath { id: string; title: string; kind: 'derivation' | 'method' | 'example'; steps: LearningPathStep[] }
export interface LearningPathSection {
  id: string; title: string; state: ReadingToolState; paths: LearningPath[]
  passages: { blockId: string; title: string }[]
}
const record = (v: unknown): Record<string, any> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : {}
const list = (v: unknown): any[] => Array.isArray(v) ? v : []
const text = (v: unknown): string => typeof v === 'string' ? v.trim() : ''

/** Project version-bound, source-backed paths. Never turn graph edges into a proof. */
export function buildHandoutPaths(rawPlans: unknown[], sections: ReferenceSection[], revisionId: string, states: Record<string, ReadingToolState> = {}): LearningPathSection[] {
  return sections.map(section => {
    const plan = rawPlans.map(record).find(p => p.node_id === section.id) || {}
    const state = states[section.id] || 'missing'
    const allowed = section.blocks.filter(b => !b.answer_to && !['answer', 'exercise', 'question', 'review_question', 'guiding_question'].includes(handoutContentType(b.content_type)))
    const passages = allowed.filter(b => ['derivation', 'method', 'example', 'case'].includes(handoutContentType(b.content_type))).map(b => ({ blockId: b.block_id, title: b.title }))
    const paths: LearningPath[] = []
    if (state === 'ready' && plan.handout_revision_id === revisionId && plan.reading_schema_version === 'study_reading_v1') {
      for (const value of list(plan.learning_paths).map(record)) {
        const steps: LearningPathStep[] = [], seen = new Set<string>()
        let valid = Boolean(text(value.id) && text(value.title) && ['derivation', 'method', 'example'].includes(value.kind))
        for (const step of list(value.steps).map(record)) {
          const id = text(step.id), parentId = text(step.parent_id)
          const sources = list(step.source_refs).map(record).flatMap(ref => {
            const block = allowed.find(b => b.block_id === ref.block_id)
            return block && ref.kind === 'handout' && ref.revision_id === revisionId && ref.node_id === section.id
              ? [{ blockId: block.block_id, title: block.title }] : []
          })
          if (!id || seen.has(id) || !text(step.text) || !sources.length || sources.length !== list(step.source_refs).length
            || !['start', 'choice', 'step', 'result', 'check'].includes(step.stage)
            || (!steps.length ? parentId || step.stage !== 'start' : !seen.has(parentId) || step.stage === 'start')) valid = false
          seen.add(id)
          steps.push({ id, parentId, stage: step.stage, text: text(step.text), reason: text(step.reason), condition: text(step.condition), sources })
        }
        if (valid && steps.length >= 2) paths.push({ id: value.id, title: value.title, kind: value.kind, steps })
      }
    }
    return { id: section.id, title: section.title, state, paths, passages }
  })
}

/** Preorder keeps sibling branches together, even if the saved list is breadth-first. */
export function pathRows(path: LearningPath) {
  const result: { step: LearningPathStep; depth: number; parentText: string }[] = []
  function visit(parent: string, depth: number) {
    for (const step of path.steps.filter(s => s.parentId === parent)) {
      result.push({ step, depth, parentText: path.steps.find(s => s.id === parent)?.text || '' })
      visit(step.id, depth + 1)
    }
  }
  visit('', 0)
  return result
}
