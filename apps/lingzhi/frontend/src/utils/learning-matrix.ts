import type { KnowledgeProfileNode } from '../types/knowledge-profile'
import type { PracticeAttempt, LearningAssetItem } from '../stores/courseWorkspace'
import type { Note } from '../stores/types'

export type MatrixSupport = 'independent' | 'assisted' | 'solution_seen' | 'unknown'
export interface MatrixAttempt {
  id: string; questionId: string; questionLabel: string; number: number; time: string
  outcome: 'correct' | 'incorrect' | 'pending'; support: MatrixSupport
  answer: string; feedback: string; question: LearningAssetItem | null; nodeId: string
}
export interface MatrixRow {
  point: KnowledgeProfileNode; attempts: MatrixAttempt[]; notes: Note[]; activity: boolean
  current: 'unassessed' | 'pending' | 'review' | 'verify' | 'independent_pass'
  practice?: { nodeId: string; revision: string }
}
interface MatrixInput {
  points: KnowledgeProfileNode[]; attempts: PracticeAttempt[]; notes: Note[]; questions: LearningAssetItem[]
  courseId: string; version: string; userId?: string; preview: boolean
}

const revision = (q: Record<string, any>) => String(q.task_revision_id || q.revision_id || q.question_revision_id || '')
const time = (a: PracticeAttempt) => String(a.submitted_at || a.created_at || a.updated_at || '')
const text = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (value == null) return ''
  return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
}
function support(a: PracticeAttempt): MatrixSupport {
  if (a.solution_revealed || a.result?.solution_revealed) return 'solution_seen'
  if ((a.revealed_hint_levels || []).length || Number(a.ai_support_level) > 0 || Number(a.support_level) > 0 || Number(a.result?.support_level) > 0) return 'assisted'
  return Array.isArray(a.revealed_hint_levels) && typeof a.solution_revealed === 'boolean' && typeof a.ai_support_level === 'number' ? 'independent' : 'unknown'
}
function matchesNote(note: Note, point: KnowledgeProfileNode): boolean {
  if (note.syncState !== 'saved' || note.recordType !== 'note' || note.status === 'archived') return false
  const metadata = note.metadata || {}
  const candidates = [note.anchor, metadata, metadata.content_anchor, (metadata.context_ref as any)?.content_anchor]
  return candidates.some((c: any) => c?.concept_ids?.includes(point.knowledge_id)
    && c.knowledge_revision_refs?.[point.knowledge_id] === point.knowledge_revision_id)
}

/** Read only. Keep all saved attempts; view expansion never changes evidence or scores. */
export function buildLearningMatrix(input: MatrixInput): MatrixRow[] {
  const byRevision = new Map(input.questions.map(q => [revision(q), q]))
  const seen = new Set<string>()
  const attempts = input.preview ? [] : input.attempts.filter(a => {
    if (!a.attempt_id || seen.has(a.attempt_id) || a.course_id !== input.courseId || a.course_version_id !== input.version
      || (input.userId && a.user_id !== input.userId) || !['submitted', 'grading', 'graded'].includes(a.status)) return false
    seen.add(a.attempt_id); return true
  }).slice().sort((a, b) => time(a).localeCompare(time(b)) || a.attempt_id.localeCompare(b.attempt_id))
  const questionNumbers = new Map<string, number>()
  for (const a of attempts) if (!questionNumbers.has(revision(a))) questionNumbers.set(revision(a), questionNumbers.size + 1)
  return input.points.map(point => {
    const rows: MatrixAttempt[] = attempts.filter(a => a.concept_ids?.includes(point.knowledge_id)
      && a.knowledge_revision_refs?.[point.knowledge_id] === point.knowledge_revision_id).map(a => {
      const r = a.result || {}
      const reliable = a.status === 'graded' && typeof r.passed === 'boolean' && Number(r.grading_confidence) >= .72
        && !['pending_review', 'submitted_for_review'].includes(r.status) && !r.historical_only && r.evidence_strength !== 'invalid'
        && new Set(a.concept_ids).size === 1
      const answer = a.submitted_answer_payload || a.answer_payload || {}
      return { id: a.attempt_id, questionId: revision(a), questionLabel: `Q${questionNumbers.get(revision(a))}`,
        number: Number(a.attempt_number) || 1, time: time(a), outcome: reliable ? r.passed ? 'correct' : 'incorrect' : 'pending',
        support: support(a), answer: text(answer.answer ?? answer.text ?? answer.code ?? answer.selected_option ?? answer),
        feedback: text(r.feedback || r.explanation || r.reason || ''), question: byRevision.get(revision(a)) || null,
        nodeId: String(a.node_id || '') }
    })
    const notes = input.preview ? [] : input.notes.filter(n => matchesNote(n, point))
    const last = rows.at(-1)
    const current: MatrixRow['current'] = !last ? 'unassessed' : last.outcome === 'pending' ? 'pending'
      : last.outcome === 'incorrect' ? 'review' : last.support === 'independent' ? 'independent_pass' : 'verify'
    const question = input.questions.find(q => {
      const ids = q.primary_knowledge_ids || q.concept_ids || []
      return ids.length === 1 && ids[0] === point.knowledge_id && q.knowledge_revision_refs?.[point.knowledge_id] === point.knowledge_revision_id
        && q.node_id && revision(q)
    })
    return { point, attempts: rows, notes, current, activity: rows.length > 0 || notes.length > 0 || (!input.preview && point.activity_count > 0),
      ...(question ? { practice: { nodeId: question.node_id!, revision: revision(question) } } : {}) }
  })
}
