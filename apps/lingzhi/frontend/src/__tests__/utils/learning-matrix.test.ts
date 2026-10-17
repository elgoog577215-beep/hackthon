import { describe, expect, it } from 'vitest'
import { buildLearningMatrix } from '@/utils/learning-matrix'

const point = (id = 'k1') => ({ knowledge_id: id, knowledge_revision_id: `r-${id}`, name: id, section_refs: ['s1'], block_refs: ['b1'], activity_count: 0 })
const attempt = (id: string, passed: boolean | undefined = true, extra = {}) => ({
  attempt_id: id, user_id: 'u1', course_id: 'c1', course_version_id: 'v1', task_revision_id: 'q1',
  concept_ids: ['k1'], knowledge_revision_refs: { k1: 'r-k1' }, attempt_number: 1,
  status: 'graded', created_at: `2026-10-17T10:${id.slice(-2).padStart(2, '0')}:00Z`,
  answer_payload: { answer: '-2' }, revealed_hint_levels: [], ai_support_level: 0, solution_revealed: false,
  result: { passed, grading_confidence: .95 }, ...extra,
})
const project = (attempts: any[] = [], extra = {}) => buildLearningMatrix({
  courseId: 'c1', version: 'v1', userId: 'u1', points: [point(), point('k2')],
  attempts, notes: [], questions: [], preview: false, ...extra,
} as any)

describe('knowledge learning matrix is a read-only projection of every attempt', () => {
  it('retains independent failure, assisted correction and a later independent pass', () => {
    const result = project([attempt('a01', false), attempt('a02', true, { revealed_hint_levels: [1], attempt_number: 2 }), attempt('a03', true, { task_revision_id: 'q2' })])
    expect(result[0].attempts.map(a => [a.outcome, a.support])).toEqual([['incorrect', 'independent'], ['correct', 'assisted'], ['correct', 'independent']])
    expect(result[0].current).toBe('independent_pass')
    expect(result[1].attempts).toEqual([])
  })
  it('marks complete-answer exposure separately even when the answer is correct', () => {
    const row = project([attempt('a01', true, { solution_revealed: true })])[0]
    expect(row.attempts[0].outcome).toBe('correct')
    expect(row.attempts[0].support).toBe('solution_seen')
    expect(row.current).toBe('verify')
  })
  it('preserves an earlier success when a newer independent attempt fails', () => {
    const row = project([attempt('a01'), attempt('a02', false)])[0]
    expect(row.attempts).toHaveLength(2)
    expect(row.current).toBe('review')
  })
  it.each([
    { user_id: 'other' }, { course_id: 'other' }, { course_version_id: 'old' },
    { knowledge_revision_refs: { k1: 'old' } }, { knowledge_revision_refs: {} },
    { status: 'abandoned' }, { status: 'invalidated' },
  ])('does not paint other identities, historical revisions or cancelled attempts red/green: %j', change => {
    expect(project([attempt('a01', true, change)])[0].attempts).toEqual([])
  })
  it.each([
    { status: 'grading' }, { result: { passed: true, grading_confidence: .2 } },
    { result: { passed: true, grading_confidence: .95, status: 'pending_review' } },
    { concept_ids: ['k1', 'k2'], knowledge_revision_refs: { k1: 'r-k1', k2: 'r-k2' } },
    { result: { passed: true, grading_confidence: .95, historical_only: true } },
  ])('keeps unresolved grading/attribution neutral: %j', change => {
    expect(project([attempt('a01', true, change)])[0].attempts[0].outcome).toBe('pending')
  })
  it('never labels missing help metadata as independent', () => {
    const a = attempt('a01'); delete (a as any).revealed_hint_levels; delete (a as any).ai_support_level; delete (a as any).solution_revealed
    expect(project([a])[0].attempts[0].support).toBe('unknown')
  })
  it('deduplicates event retries by attempt identity without losing separate submissions', () => {
    expect(project([attempt('a01'), attempt('a01'), attempt('a02')])[0].attempts).toHaveLength(2)
  })
  it('does not use newer question text for an old question revision', () => {
    const rows = project([attempt('a01')], { questions: [{ revision_id: 'q-new', prompt: 'New private answer', question_id: 'q1' }] })
    expect(rows[0].attempts[0].question).toBeNull()
  })
  it('uses only saved, exact knowledge revision notes; chapter proximity is not enough', () => {
    const notes = [
      { id: 'n1', recordType: 'note', syncState: 'saved', anchor: { concept_ids: ['k1'], knowledge_revision_refs: { k1: 'r-k1' } } },
      { id: 'n2', recordType: 'note', syncState: 'saved', nodeId: 's1' },
      { id: 'n3', recordType: 'note', syncState: 'local_only', anchor: { concept_ids: ['k1'], knowledge_revision_refs: { k1: 'r-k1' } } },
      { id: 'n4', recordType: 'note', syncState: 'saved', metadata: { concept_ids: ['k1'], knowledge_revision_refs: { k1: 'old' } } },
    ]
    expect(project([], { notes })[0].notes.map(n => n.id)).toEqual(['n1'])
  })
  it('does not load personal facts into a teacher preview and does not mutate input', () => {
    const a = attempt('a01'); const before = JSON.stringify(a)
    expect(project([a], { preview: true })[0].attempts).toEqual([])
    expect(JSON.stringify(a)).toBe(before)
  })
})
