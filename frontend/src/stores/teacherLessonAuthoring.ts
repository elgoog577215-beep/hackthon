import { defineStore } from 'pinia'
import http, { getTeacherIdentity, teacherIdentityHeaders, teacherReadRequestConfig, withApiBase } from '../utils/http'
import { createUuid } from '../utils/client-id'
import { postGenerationStream, type GenerationProgress } from '../shared/generation-stream'
import { t } from '../shared/i18n'

export type TeacherLessonJobStatus = 'pending' | 'running' | 'paused' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled'

export interface TeacherMaterialWorkingDraft {
  revision_id: string
  bundle_id: string
  plan_id: string
  package_id: string
  target_id: string
  target_type: 'outline' | 'lesson_plan' | 'script' | 'ppt'
  target_scope_id: string
  target_scope_label: string
  title: string
  status: 'working_draft' | 'superseded'
  source_state: 'current' | 'stale'
  structured_document: Record<string, any>
  source_refs: Array<Record<string, any>>
  created_at: string
}

export interface TeacherLessonPlanRevision {
  revision_id: string
  lesson_unit_id: string
  source_outline_revision_id: string
  source_arrangement_revision_id?: string
  generation_source: string
  warnings: Array<Record<string, unknown>>
  source_refs?: Array<Record<string, unknown>>
  pipeline_version?: 'standard_lesson_plan_v1'
  quality_report?: {
    schema_version: 'teacher_lesson_plan_quality_v1'
    pipeline_version: 'standard_lesson_plan_v1'
    passed: boolean
    blocking_issues: Array<{ code: string; message: string; section_id?: string }>
    review_issues: Array<{ code: string; message: string; section_id?: string }>
    metrics: Record<string, number>
  }
  plan: Record<string, any>
  actor: string
  created_at: string
}

export interface TeacherLessonPlanAsset {
  lesson_unit_id: string
  working_revision_id: string
  source_state: 'current' | 'stale'
  ready?: boolean
  unavailable_reason?: string
  can_generate?: boolean
  generation_unavailable_reason?: string
  current_revision?: TeacherLessonPlanRevision | null
  ai_candidate?: TeacherLessonPlanCandidate | null
  ppt_assets: TeacherLessonPptAsset[]
  material_drafts?: Record<string, TeacherMaterialWorkingDraft[]>
  current_material_draft_ids?: Record<string, string>
}

export interface TeacherLessonArrangementBlock {
  block_id: string
  module_id: string
  section_node_id: string
  section_title: string
  name: string
  role: string
  purpose: string
  content_summary: string
  planned_minutes: number
  teacher_activity: string
  student_activity: string
  expected_output: string
  check_method?: string
  feedback_strategy?: string
  adaptation_options?: string[]
  resource_refs?: string[]
  tools?: string[]
  engagement_mode?: 'passive' | 'active' | 'constructive' | 'interactive' | string
  access_support?: string
  grouping?: string
  transition?: string
  safety_boundary?: string
  block_contract_version?: string
  required: boolean
}

export interface TeacherLessonArrangement {
  schema_version: 'teacher_lesson_arrangement_v1'
  revision_id: string
  lesson_unit_id: string
  source_outline_revision_id: string
  lesson_type: 'theory' | 'practice' | 'theory_practice' | 'case_discussion' | 'experiment_inquiry' | 'project_workshop' | 'review_assessment'
  lesson_type_label: string
  teaching_semantics_version?: string
  lesson_type_recommendation_reason?: string
  lesson_type_contract?: Record<string, unknown>
  required_learning_cycle?: string[]
  classroom_constraints?: Record<string, unknown>
  quality_rules?: string[]
  blocks: TeacherLessonArrangementBlock[]
  source_state: 'current' | 'stale'
  ready?: boolean
}

export interface TeacherLessonScriptState {
  current_revision_id: string
  legacy_source_fingerprint?: string
  source_lesson_plan_revision_id: string
  source_state: 'current' | 'stale'
  ready: boolean
  unavailable_reason?: string
  can_generate?: boolean
  generation_unavailable_reason?: string
  publication_eligible?: boolean
  generation_source?: string
  quality_contract_version?: string
  quality_report?: {
    schema_version?: string
    pipeline_version?: string
    passed: boolean
    publication_eligible?: boolean
    blocking_issues: Array<{ code: string; message: string; section_node_id?: string }>
    review_issues: Array<{ code: string; message: string; section_node_id?: string }>
    metrics: Record<string, number>
  }
  sections: TeacherLessonScriptSection[]
  actor?: string
  updated_at?: string
  ai_candidate?: TeacherLessonScriptCandidate | null
}

export interface TeacherLessonScriptCandidate {
  candidate_id: string
  base_revision_id: string
  source_lesson_plan_revision_id: string
  section_node_id: string
  instruction: string
  replacement_text: string
  material_asset_ids: string[]
  status: 'pending' | 'accepted' | 'rejected' | 'superseded'
  created_at: string
}

export interface TeacherLessonScriptBlock {
  block_id: string
  module_id: string
  role: string
  title: string
  content: string
  required?: boolean
  knowledge_names?: string[]
  planned_minutes?: number | null
  generation_source?: 'model' | 'local_recovery' | 'teacher_edit' | string
  source_plan_context?: {
    teacher_activity?: string
    student_activity?: string
  }
  teacher_activity?: string
  student_activity?: string
}

export interface TeacherLessonScriptSection {
  section_node_id: string
  title: string
  content: string
  schema_version?: 'teacher_script_v2'
  content_perspective?: 'neutral' | 'teacher_delivery'
  lesson_archetype?: Record<string, any>
  blocks?: TeacherLessonScriptBlock[]
  pipeline_version?: string
  quality_report?: {
    passed: boolean
    blocking_issues: Array<{ code: string; message: string }>
    review_issues: Array<{ code: string; message: string }>
    metrics: Record<string, number>
  }
}

export interface TeacherLessonPptRevision {
  revision_id: string
  lesson_unit_id: string
  source_lesson_plan_revision_id: string
  generation_source: string
  status: 'draft'
  warnings: Array<Record<string, unknown>>
  deck: { schema_version: string; title: string; slides: TeacherLessonPptSlide[] }
  actor: string
  created_at: string
}

export interface TeacherLessonPptSlide {
  slide_id: string
  title: string
  body: string[]
  speaker_notes: string
}

export interface TeacherLessonPptCandidate {
  candidate_id: string
  asset_id: string
  base_revision_id: string
  instruction: string
  slide_indexes: number[]
  deck: TeacherLessonPptRevision['deck']
  status: 'pending' | 'accepted' | 'rejected'
  created_at: string
}

export interface TeacherLessonPptAsset {
  asset_id: string
  lesson_unit_id: string
  role: 'primary' | 'supplemental'
  working_revision_id: string
  source_lesson_plan_revision_id: string
  source_script_revision_id?: string
  source_state: 'current' | 'stale'
  ready?: boolean
  unavailable_reason?: string
  revisions: TeacherLessonPptRevision[]
  ai_candidates: TeacherLessonPptCandidate[]
  engine?: 'slide_deck_v6' | 'uploaded_pptx'
  working_v6_revision_id?: string
  working_representation_id?: string
  synthetic_course_id?: string
  ppt_manuscript_revision?: string
  ppt_manuscript_status?: 'draft' | 'confirmed'
  v6_revisions?: Array<{
    revision_id: string
    engine: 'slide_deck_v6'
    synthetic_course_id: string
    representation_id: string
    spec_id: string
    source_lesson_plan_revision_id: string
    source_script_revision_id: string
    ppt_manuscript_revision?: string
    ppt_manuscript_status?: 'draft' | 'confirmed'
    candidate_status: string
    created_at: string
  }>
}

export interface TeacherLessonPlanCandidate {
  candidate_id: string
  lesson_unit_id: string
  base_revision_id: string
  instruction: string
  section_node_id: string
  target_field?: string
  target_item_id?: string
  selected_text?: string
  plan: Record<string, any>
  status: 'pending' | 'accepted' | 'rejected'
  created_at: string
}

export interface TeacherLessonPlanAiTarget {
  sectionNodeId?: string
  field?: string
  itemId?: string
  selectedText?: string
}

export interface TeacherLessonProjection {
  lesson_unit_id: string
  number: number
  title: string
  duration_minutes: number
  sections: Array<{ section_node_id: string; title: string }>
  arrangement: TeacherLessonArrangement
  script: TeacherLessonScriptState
  plan: TeacherLessonPlanAsset
  material_drafts?: Partial<Record<'lesson_plan' | 'script' | 'ppt', TeacherMaterialWorkingDraft>>
}

export interface TeacherLessonStreamDeltaEvent {
  event?: string
  stream_event?: string
  lesson_unit_id?: string
  block_id?: string
  shard_id?: string
  sequence?: number
  delta?: string
}

export interface TeacherLessonJob {
  id: string
  course_id: string
  lesson_unit_id: string
  type: string
  status: TeacherLessonJobStatus
  progress: number
  phase: string
  message: string
  warnings: Array<Record<string, unknown>>
  error?: { code: string; message: string; retryable?: boolean } | null
  result_revision_id?: string
  parent_job_id?: string
  batch_position?: number
  batch_size?: number
  pause_requested?: boolean
  stream_sequence?: number
  stream_batches?: Record<string, string>
  stream_events?: TeacherLessonStreamDeltaEvent[]
  last_stream_event?: TeacherLessonStreamDeltaEvent
  stream_complete?: boolean
  requirements?: string
  total_blocks?: number
  completed_blocks?: number
  current_block_id?: string
  current_block_title?: string
  block_states?: Record<string, 'pending' | 'running' | 'completed' | 'failed'>
  result_sections?: TeacherLessonScriptSection[]
  streamed_block_content?: Record<string, string>
  streamed_delta_chunks?: Record<string, Record<string, string>>
  streamed_sequence_by_shard?: Record<string, number>
  streamed_reset_sequence_by_shard?: Record<string, number>
  created_at?: string
  updated_at?: string
}

export interface TeacherLessonJobStreamEvent {
  event: 'lesson_plan_stream' | 'lesson_plan_complete' | 'lesson_plan_failed'
    | 'lesson_plan_cancelled' | 'lesson_plan_paused' | 'lesson_script_stream' | 'lesson_script_complete'
    | 'lesson_script_failed' | 'lesson_script_cancelled' | 'lesson_script_paused' | 'error'
  job?: TeacherLessonJob
  job_id?: string
  lesson_unit_id?: string
  block_id?: string
  shard_id?: string
  sequence?: number
  delta?: string
  stream_event?: string
  message?: string
}

export interface TeacherLessonAuthoringView {
  schema_version: 'teacher_lesson_authoring_view_v1'
  pipeline_version?: 'standard_lesson_plan_v1'
  plan_schema_version?: 'course_teaching_plan_v3'
  course_id: string
  outline_revision_id: string
  outline_material_draft?: TeacherMaterialWorkingDraft | null
  lessons: TeacherLessonProjection[]
  jobs: TeacherLessonJob[]
}

export interface TeacherLessonKnowledgeEvidence {
  schema_version: 'teacher_lesson_knowledge_evidence_v1'
  course_id: string
  lesson_unit_id: string
  points: Array<{
    section_node_id: string
    section_title: string
    name: string
    statement: string
    sources: string[]
    conflict: boolean
  }>
  conflict_count: number
}

const requestConfig = () => ({ headers: { 'X-User-Id': getTeacherIdentity() } })
const readRequestConfig = () => teacherReadRequestConfig({ headers: { 'X-User-Id': getTeacherIdentity() } })

const decodeJsonStreamString = (value: string) => {
  try {
    return JSON.parse(`"${value}"`) as string
  } catch {
    return value
      .replace(/\\u([0-9a-fA-F]{4})/g, (_match, code) => String.fromCharCode(Number.parseInt(code, 16)))
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, ' ')
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, '\\')
  }
}

const usefulLessonPlanStreamValue = (value: string) => {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (normalized.length < 2) return ''
  if (/^(?:L[12]-|TP-B|course_|teacher_|standard_|lesson_|module_)/i.test(normalized)) return ''
  if (/^[A-Za-z0-9_.:-]+$/.test(normalized) && !normalized.includes(' ')) return ''
  return normalized
}

const lessonPlanStreamValues = (raw: string) => {
  const values: string[] = []
  let index = 0
  let previousSignificant = ''
  while (index < raw.length) {
    const character = raw.charAt(index)
    if (character !== '"') {
      if (!/\s/.test(character)) previousSignificant = character
      index += 1
      continue
    }
    const beforeString = previousSignificant
    index += 1
    let token = ''
    let escaped = false
    let closed = false
    while (index < raw.length) {
      const current = raw.charAt(index)
      if (escaped) {
        token += `\\${current}`
        escaped = false
        index += 1
        continue
      }
      if (current === '\\') {
        escaped = true
        index += 1
        continue
      }
      if (current === '"') {
        closed = true
        index += 1
        break
      }
      token += current
      index += 1
    }
    if (!closed) {
      if (beforeString === ':' || beforeString === '[') {
        const partial = usefulLessonPlanStreamValue(decodeJsonStreamString(token))
        if (partial) values.push(partial)
      }
      break
    }
    let lookahead = index
    while (lookahead < raw.length && /\s/.test(raw.charAt(lookahead))) lookahead += 1
    const isKey = raw.charAt(lookahead) === ':'
    if (!isKey) {
      const decoded = usefulLessonPlanStreamValue(decodeJsonStreamString(token))
      if (decoded && values[values.length - 1] !== decoded) values.push(decoded)
    }
    previousSignificant = '"'
  }
  return values
}

export function lessonPlanStreamSegments(batches: Record<string, string> | undefined) {
  return Object.entries(batches || {})
    .sort(([left], [right]) => left.localeCompare(right))
    .flatMap(([, raw]) => lessonPlanStreamValues(String(raw || '')))
}

async function consumeLessonPlanStream(
  response: Response,
  onEvent: (event: TeacherLessonJobStreamEvent) => void,
) {
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`)
  if (!response.body) throw new Error('Lesson plan stream is unavailable')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const flush = (chunk: string) => {
    const data = chunk
      .split(/\r?\n/)
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n')
    if (data) onEvent(JSON.parse(data) as TeacherLessonJobStreamEvent)
  }
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const chunks = buffer.split(/\r?\n\r?\n/)
    buffer = chunks.pop() || ''
    chunks.forEach(flush)
    if (done) break
  }
  if (buffer.trim()) flush(buffer)
}

const errorMessage = (error: any, fallback: string) => {
  const detail = error?.response?.data?.detail
  if (error?.code === 'ECONNABORTED' || /timeout/i.test(String(error?.message || ''))) {
    return '读取时间过长，请重新尝试。已生成的内容仍然保留。'
  }
  return String(detail?.message || detail || error?.message || fallback)
}

const lessonAuthoringViewRequests = new Map<string, Promise<TeacherLessonAuthoringView>>()

const fetchLessonAuthoringView = (courseId: string, afterCurrent = false): Promise<TeacherLessonAuthoringView> => {
  const existing = lessonAuthoringViewRequests.get(courseId)
  if (existing) {
    if (!afterCurrent) return existing
    return existing
      .catch(() => undefined)
      .then(() => fetchLessonAuthoringView(courseId))
  }
  const request = http.get<TeacherLessonAuthoringView>(
    `/api/teacher/courses/${courseId}/lesson-authoring`,
    { ...readRequestConfig(), silentError: true },
  ).then(response => response.data)
    .finally(() => {
      if (lessonAuthoringViewRequests.get(courseId) === request) {
        lessonAuthoringViewRequests.delete(courseId)
      }
    })
  lessonAuthoringViewRequests.set(courseId, request)
  return request
}

const LESSON_JOB_STATUS_ORDER: Record<TeacherLessonJobStatus, number> = {
  pending: 10,
  running: 20,
  paused: 30,
  failed: 40,
  cancelled: 40,
  completed_with_warnings: 50,
  completed: 60,
}
const TERMINAL_LESSON_JOB_STATUSES = new Set<TeacherLessonJobStatus>([
  'paused',
  'failed',
  'cancelled',
  'completed_with_warnings',
  'completed',
])

const lessonJobTimestamp = (job?: TeacherLessonJob) => {
  const value = Date.parse(String(job?.updated_at || ''))
  return Number.isFinite(value) ? value : 0
}

export function mergeLessonJobSnapshot(
  previous: TeacherLessonJob | undefined,
  incoming: TeacherLessonJob,
): TeacherLessonJob {
  if (!previous || previous.id !== incoming.id) return incoming
  const previousTimestamp = lessonJobTimestamp(previous)
  const incomingTimestamp = lessonJobTimestamp(incoming)
  if (previousTimestamp && incomingTimestamp) {
    if (incomingTimestamp < previousTimestamp) return previous
    if (incomingTimestamp > previousTimestamp) return { ...previous, ...incoming }
  }
  if (LESSON_JOB_STATUS_ORDER[incoming.status] < LESSON_JOB_STATUS_ORDER[previous.status]) return previous
  return { ...previous, ...incoming }
}

export function mergeLessonJobSnapshots(
  current: TeacherLessonJob[],
  incoming: TeacherLessonJob[],
): TeacherLessonJob[] {
  return incoming.reduce((jobs, job) => {
    const index = jobs.findIndex(item => item.id === job.id)
    if (index < 0) return [...jobs, job]
    const next = [...jobs]
    next[index] = mergeLessonJobSnapshot(jobs[index], job)
    return next
  }, [...current])
}

const LESSON_JOB_OBSERVER_LIMIT = 4

const prioritizedActiveLessonJobs = (jobs: TeacherLessonJob[]) => [...jobs]
  .sort((left, right) => (
    Number(right.status === 'running') - Number(left.status === 'running')
    || Number(left.batch_position || 0) - Number(right.batch_position || 0)
    || String(left.id || '').localeCompare(String(right.id || ''))
  ))
  .slice(0, LESSON_JOB_OBSERVER_LIMIT)

export const lessonJobsToObserve = (jobs: TeacherLessonJob[]) => {
  const active = jobs.filter(job => ['pending', 'running'].includes(job.status))
  const scriptJobs = active.filter(job => job.type === 'teacher_lesson_script_generation')
  const lessonPlanJobs = active.filter(job => job.type !== 'teacher_lesson_script_generation')
  return [
    ...prioritizedActiveLessonJobs(scriptJobs),
    ...prioritizedActiveLessonJobs(lessonPlanJobs),
  ]
}

function streamChunkContent(chunks: Record<string, string>): string {
  return Object.entries(chunks)
    .sort(([left], [right]) => {
      const [leftSequence, ...leftShardParts] = left.split(':')
      const [rightSequence, ...rightShardParts] = right.split(':')
      return Number(leftSequence) - Number(rightSequence)
        || leftShardParts.join(':').localeCompare(rightShardParts.join(':'))
    })
    .map(([, value]) => value)
    .join('')
}

function withoutShardChunks(chunks: Record<string, string>, shardId: string): Record<string, string> {
  return Object.fromEntries(
    Object.entries(chunks).filter(([key]) => key.split(':').slice(1).join(':') !== shardId),
  )
}

function mergeSingleLessonJobStreamEvent(
  previous: TeacherLessonJob | undefined,
  event: TeacherLessonJobStreamEvent,
): TeacherLessonJob | undefined {
  const incoming = event.job
  const jobId = String(incoming?.id || event.job_id || '')
  if (!jobId || (!incoming && !previous)) return previous
  const base = { ...(previous || {}), ...(incoming || {}) } as TeacherLessonJob
  const eventLessonId = String(event.lesson_unit_id || incoming?.lesson_unit_id || '')
  if (eventLessonId && base.lesson_unit_id && eventLessonId !== base.lesson_unit_id) return previous

  const blockId = String(event.block_id || incoming?.current_block_id || '')
  if (!blockId) return base
  const shardId = String(event.shard_id || blockId)
  const sequence = Number(event.sequence)
  const sequenceKey = `${blockId}:${shardId}`
  const previousSequences = previous?.streamed_sequence_by_shard || {}
  const lastSequence = previousSequences[sequenceKey]
  const blockChunks = previous?.streamed_delta_chunks?.[blockId] || {}
  const resetSequences = previous?.streamed_reset_sequence_by_shard || {}
  const lastResetSequence = resetSequences[sequenceKey]
  const streamEvent = String(event.stream_event || '')
  const isReset = streamEvent === 'reset'
  if (Number.isFinite(sequence) && lastSequence !== undefined && sequence <= lastSequence) return base
  const retainedChunks = isReset ? withoutShardChunks(blockChunks, shardId) : blockChunks
  const delta = String(event.delta || '')
  if (!isReset && !delta) return base
  if (!isReset && Number.isFinite(sequence) && lastResetSequence !== undefined && sequence <= lastResetSequence) return base
  const chunkKey = Number.isFinite(sequence) ? `${sequence}:${shardId}` : ''
  if (!isReset && chunkKey && retainedChunks[chunkKey] !== undefined) return base
  const nextBlockChunks = chunkKey && delta ? { ...retainedChunks, [chunkKey]: delta } : retainedChunks
  const blockContent = Object.keys(nextBlockChunks).length
    ? streamChunkContent(nextBlockChunks)
    : chunkKey ? '' : `${isReset ? '' : previous?.streamed_block_content?.[blockId] || ''}${delta}`

  return {
    ...base,
    current_block_id: blockId,
    stream_sequence: Number.isFinite(sequence)
      ? Math.max(Number(base.stream_sequence || 0), sequence)
      : base.stream_sequence,
    streamed_block_content: {
      ...(previous?.streamed_block_content || {}),
      [blockId]: blockContent,
    },
    streamed_delta_chunks: {
      ...(previous?.streamed_delta_chunks || {}),
      ...((chunkKey || isReset) ? { [blockId]: nextBlockChunks } : {}),
    },
    streamed_sequence_by_shard: {
      ...previousSequences,
      ...(Number.isFinite(sequence) ? { [sequenceKey]: Math.max(lastSequence ?? sequence, sequence) } : {}),
    },
    streamed_reset_sequence_by_shard: {
      ...resetSequences,
      ...(isReset && Number.isFinite(sequence)
        ? { [sequenceKey]: Math.max(lastResetSequence ?? sequence, sequence) }
        : {}),
    },
  }
}

function reconcileLessonScriptStreamBatches(
  job: TeacherLessonJob,
  event: TeacherLessonJobStreamEvent,
): TeacherLessonJob {
  if (job.type !== 'teacher_lesson_script_generation' || !Object.keys(job.stream_batches || {}).length) return job
  const mappings = new Map<string, { blockId: string; lessonUnitId: string; sequence: number }>()
  const candidates: TeacherLessonStreamDeltaEvent[] = [
    ...(job.stream_events || []),
    ...(job.last_stream_event ? [job.last_stream_event] : []),
    {
      lesson_unit_id: event.lesson_unit_id,
      block_id: event.block_id,
      shard_id: event.shard_id,
      sequence: event.sequence,
    },
  ]
  candidates.forEach(item => {
    const shardId = String(item.shard_id || '')
    const blockId = String(item.block_id || '')
    const lessonUnitId = String(item.lesson_unit_id || job.lesson_unit_id || '')
    if (!shardId || !blockId || (lessonUnitId && lessonUnitId !== job.lesson_unit_id)) return
    const sequence = Number(item.sequence)
    const current = mappings.get(shardId)
    if (!current || !Number.isFinite(current.sequence) || (Number.isFinite(sequence) && sequence >= current.sequence)) {
      mappings.set(shardId, { blockId, lessonUnitId, sequence })
    }
  })

  let chunksByBlock = { ...(job.streamed_delta_chunks || {}) }
  const sequences = { ...(job.streamed_sequence_by_shard || {}) }
  const affectedBlocks = new Set<string>()
  Object.entries(job.stream_batches || {}).forEach(([shardId, content]) => {
    const mapping = mappings.get(shardId)
    if (!mapping) return
    const sequence = Number.isFinite(mapping.sequence) ? mapping.sequence : Number(job.stream_sequence || 0)
    const sequenceKey = `${mapping.blockId}:${shardId}`
    const retained = withoutShardChunks(chunksByBlock[mapping.blockId] || {}, shardId)
    chunksByBlock = {
      ...chunksByBlock,
      [mapping.blockId]: content ? { ...retained, [`${sequence}:${shardId}`]: String(content) } : retained,
    }
    sequences[sequenceKey] = Math.max(Number(sequences[sequenceKey] || 0), sequence)
    affectedBlocks.add(mapping.blockId)
  })
  if (!affectedBlocks.size) return job

  const blockContent = { ...(job.streamed_block_content || {}) }
  affectedBlocks.forEach(blockId => {
    blockContent[blockId] = streamChunkContent(chunksByBlock[blockId] || {})
  })
  return {
    ...job,
    streamed_delta_chunks: chunksByBlock,
    streamed_block_content: blockContent,
    streamed_sequence_by_shard: sequences,
  }
}

export function mergeLessonJobStreamEvent(
  previous: TeacherLessonJob | undefined,
  event: TeacherLessonJobStreamEvent,
): TeacherLessonJob | undefined {
  if (previous && TERMINAL_LESSON_JOB_STATUSES.has(previous.status)) return previous
  const jobId = String(event.job?.id || event.job_id || '')
  let merged = mergeSingleLessonJobStreamEvent(previous, {
    ...event,
    stream_event: undefined,
    delta: undefined,
  })
  const streamEvents = [...(event.job?.stream_events || [])].sort((left, right) => {
    const sequenceOrder = Number(left.sequence || 0) - Number(right.sequence || 0)
    if (sequenceOrder) return sequenceOrder
    const leftReset = String(left.event || left.stream_event || '') === 'reset'
    const rightReset = String(right.event || right.stream_event || '') === 'reset'
    return Number(rightReset) - Number(leftReset)
  })
  streamEvents.forEach(item => {
    merged = mergeSingleLessonJobStreamEvent(merged, {
      event: event.event,
      job_id: jobId,
      lesson_unit_id: item.lesson_unit_id,
      block_id: item.block_id,
      shard_id: item.shard_id,
      sequence: item.sequence,
      delta: item.delta,
      stream_event: item.stream_event || item.event,
    })
  })
  if (merged && event.job) merged = reconcileLessonScriptStreamBatches(merged, event)
  return mergeSingleLessonJobStreamEvent(merged, { ...event, job: undefined, job_id: jobId })
}

export const useTeacherLessonAuthoringStore = defineStore('teacher-lesson-authoring', {
  state: () => ({
    courseId: '',
    outlineRevisionId: '',
    lessons: [] as TeacherLessonProjection[],
    jobs: [] as TeacherLessonJob[],
    loading: false,
    refreshing: false,
    loadedCourseId: '',
    actionLessonId: '',
    streamingJobIds: {} as Record<string, boolean>,
    error: '',
    refreshError: '',
  }),
  getters: {
    lessonById: state => (lessonUnitId: string) => state.lessons.find(item => item.lesson_unit_id === lessonUnitId),
    activeJobByLesson: state => (lessonUnitId: string) => state.jobs.find(item => (
      item.lesson_unit_id === lessonUnitId
      && item.type === 'teacher_lesson_plan_generation'
      && ['pending', 'running'].includes(item.status)
    )),
    latestJobByLesson: state => (lessonUnitId: string) => state.jobs
      .map((job, index) => ({ job, index }))
      .filter(({ job }) => job.lesson_unit_id === lessonUnitId && job.type === 'teacher_lesson_plan_generation')
      .sort((left, right) => (
        (Date.parse(String(right.job.created_at || '')) || 0) - (Date.parse(String(left.job.created_at || '')) || 0)
        || right.index - left.index
        || String(right.job.id || '').localeCompare(String(left.job.id || ''))
      ))[0]?.job,
    latestScriptJobByLesson: state => (lessonUnitId: string) => state.jobs
      .map((job, index) => ({ job, index }))
      .filter(({ job }) => job.lesson_unit_id === lessonUnitId && job.type === 'teacher_lesson_script_generation')
      .sort((left, right) => (
        (Date.parse(String(right.job.created_at || '')) || 0) - (Date.parse(String(left.job.created_at || '')) || 0)
        || right.index - left.index
        || String(right.job.id || '').localeCompare(String(left.job.id || ''))
      ))[0]?.job,
  },
  actions: {
    async load(courseId: string, options: { afterCurrent?: boolean } = {}) {
      const hasSuccessfulSnapshot = this.loadedCourseId === courseId
      if (this.courseId !== courseId) {
        this.courseId = courseId
        this.outlineRevisionId = ''
        this.lessons = []
        this.jobs = []
        this.streamingJobIds = {}
        this.loadedCourseId = ''
        this.actionLessonId = ''
        this.error = ''
        this.refreshError = ''
      }
      this.loading = !hasSuccessfulSnapshot
      this.refreshing = hasSuccessfulSnapshot
      if (!hasSuccessfulSnapshot) this.error = ''
      this.refreshError = ''
      try {
        const response = await fetchLessonAuthoringView(courseId, options.afterCurrent)
        if (this.courseId !== courseId) return response
        this.courseId = courseId
        this.outlineRevisionId = response.outline_revision_id
        this.lessons = response.lessons
        this.jobs = mergeLessonJobSnapshots(this.jobs, response.jobs)
        this.loadedCourseId = courseId
        this.error = ''
        lessonJobsToObserve(this.jobs)
          .forEach(job => { void this.streamJob(courseId, job.id) })
        return response
      } catch (error) {
        if (this.courseId === courseId) {
          const message = errorMessage(error, '分讲教案状态读取失败')
          if (hasSuccessfulSnapshot) this.refreshError = message
          else this.error = message
        }
        throw error
      } finally {
        if (this.courseId === courseId) {
          this.loading = false
          this.refreshing = false
        }
      }
    },
    async generateLesson(
      courseId: string,
      lessonUnitId: string,
      source?: { packageId: string; assetId: string },
      requirements = '',
      materialAssetIds: string[] = [],
      resumeJobId = '',
    ) {
      if (!this.courseId) this.courseId = courseId
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.post<{ job: TeacherLessonJob }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/generate`,
          {
            request_id: createUuid(),
            resume_job_id: resumeJobId,
            source_package_id: source?.packageId || '',
            source_asset_id: source?.assetId || '',
            requirements,
            material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean))),
          },
          { ...requestConfig(), silentError: true },
        )
        const job = response.data.job
        if (this.courseId === courseId) {
          this.jobs = mergeLessonJobSnapshots(this.jobs, [job])
          void this.streamJob(courseId, job.id)
        }
        return job
      } catch (error) {
        if (this.courseId === courseId) this.error = errorMessage(error, '本讲教案生成失败')
        throw error
      } finally {
        if (this.courseId === courseId) this.actionLessonId = ''
      }
    },
    async generateAllLessons(
      courseId: string,
      source?: { packageId: string; assetId: string },
      requirements = '',
      materialAssetIds: string[] = [],
    ) {
      if (!this.courseId) this.courseId = courseId
      this.error = ''
      try {
        const response = await http.post<{
          parent_job: { id: string; child_job_ids: string[]; skipped_lesson_ids: string[]; total: number; started: number }
          jobs: TeacherLessonJob[]
        }>(
          `/api/teacher/courses/${courseId}/lesson-plans/generate-all`,
          {
            request_id: createUuid(),
            source_package_id: source?.packageId || '',
            source_asset_id: source?.assetId || '',
            requirements,
            material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean))),
          },
          { ...requestConfig(), silentError: true },
        )
        const incoming = response.data.jobs
        if (this.courseId === courseId) {
          this.jobs = mergeLessonJobSnapshots(this.jobs, incoming)
          lessonJobsToObserve(incoming).forEach(job => { void this.streamJob(courseId, job.id) })
        }
        return response.data
      } catch (error) {
        if (this.courseId === courseId) this.error = errorMessage(error, t('courseWorkbench.lessonBatch.failed'))
        throw error
      }
    },
    async updateLessonType(
      courseId: string,
      lessonUnitId: string,
      lessonType: TeacherLessonArrangement['lesson_type'],
    ) {
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.put<{ lesson: TeacherLessonProjection }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/arrangement/type`,
          { lesson_type: lessonType },
          requestConfig(),
        )
        if (this.courseId === courseId) this.replaceLessonProjection(lessonUnitId, response.data.lesson)
        return response.data.lesson
      } catch (error) {
        if (this.courseId === courseId) this.error = errorMessage(error, '课型保存失败')
        throw error
      } finally {
        if (this.courseId === courseId) this.actionLessonId = ''
      }
    },
    async loadKnowledgeEvidence(courseId: string, lessonUnitId: string) {
      const response = await http.get<TeacherLessonKnowledgeEvidence>(
        `/api/teacher/courses/${courseId}/knowledge-evidence`,
        { ...readRequestConfig(), params: { lesson_unit_id: lessonUnitId } },
      )
      return response.data
    },
    async pollJob(courseId: string, jobId: string) {
      if (!this.courseId) this.courseId = courseId
      for (let attempt = 0; attempt < 180; attempt += 1) {
        if (this.courseId !== courseId) return undefined
        const response = await http.get<{ job: TeacherLessonJob }>(
          `/api/teacher/courses/${courseId}/lesson-jobs/${jobId}`,
          readRequestConfig(),
        )
        if (this.courseId !== courseId) return undefined
        const job = response.data.job
        this.jobs = mergeLessonJobSnapshots(this.jobs, [job])
        const current = this.jobs.find(item => item.id === job.id) || job
        if (TERMINAL_LESSON_JOB_STATUSES.has(current.status)) {
          await this.load(courseId, { afterCurrent: true })
          return current
        }
        await new Promise(resolve => setTimeout(resolve, 1500))
      }
      return this.jobs.find(item => item.id === jobId)
    },
    async streamJob(courseId: string, jobId: string) {
      if (!this.courseId) this.courseId = courseId
      if (this.courseId !== courseId) return undefined
      if (this.streamingJobIds[jobId]) return this.jobs.find(item => item.id === jobId)
      this.streamingJobIds = { ...this.streamingJobIds, [jobId]: true }
      let terminal = false
      try {
        const response = await fetch(
          withApiBase(`/api/teacher/courses/${courseId}/lesson-jobs/${jobId}/stream`),
          {
            headers: teacherIdentityHeaders({
              Accept: 'text/event-stream',
              'X-User-Id': getTeacherIdentity(),
            }),
          },
        )
        await consumeLessonPlanStream(response, event => {
          if (this.courseId !== courseId) return
          const eventJobId = String(event.job?.id || event.job_id || jobId)
          const previous = this.jobs.find(item => item.id === eventJobId)
          const job = mergeLessonJobStreamEvent(previous, { ...event, job_id: eventJobId })
          if (!job) {
            if (event.event === 'error') this.error = event.message || '本讲生成流已中断'
            return
          }
          this.jobs = mergeLessonJobSnapshots(this.jobs, [job])
          terminal = TERMINAL_LESSON_JOB_STATUSES.has(
            (this.jobs.find(item => item.id === job.id) || job).status,
          )
        })
        if (terminal && this.courseId === courseId) await this.load(courseId, { afterCurrent: true })
        return this.jobs.find(item => item.id === jobId)
      } catch {
        if (this.courseId !== courseId) return undefined
        const current = this.jobs.find(item => item.id === jobId)
        if (current && !TERMINAL_LESSON_JOB_STATUSES.has(current.status)) {
          return this.pollJob(courseId, jobId)
        }
        return current
      } finally {
        if (this.courseId === courseId) {
          const next = { ...this.streamingJobIds }
          delete next[jobId]
          this.streamingJobIds = next
        }
      }
    },
    async cancelJob(courseId: string, jobId: string) {
      const response = await http.delete<{ job: TeacherLessonJob }>(
        `/api/teacher/courses/${courseId}/lesson-jobs/${jobId}`,
        requestConfig(),
      )
      const job = response.data.job
      if (this.courseId === courseId) this.jobs = mergeLessonJobSnapshots(this.jobs, [job])
      return job
    },
    async pauseJob(courseId: string, jobId: string) {
      const response = await http.post<{ job: TeacherLessonJob }>(
        `/api/teacher/courses/${courseId}/lesson-jobs/${jobId}/pause`,
        {},
        requestConfig(),
      )
      const job = response.data.job
      if (this.courseId === courseId) this.jobs = mergeLessonJobSnapshots(this.jobs, [job])
      return job
    },
    async saveDraft(
      courseId: string,
      lessonUnitId: string,
      plan: Record<string, any>,
      expectedCurrentRevisionId: string,
    ) {
      const response = await http.patch<{ lesson: TeacherLessonProjection }>(
        `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/draft`,
        {
          plan,
          source_outline_revision_id: this.outlineRevisionId,
          expected_current_revision_id: expectedCurrentRevisionId,
        },
        requestConfig(),
      )
      if (this.courseId === courseId) this.replaceLessonProjection(lessonUnitId, response.data.lesson)
      return response.data.lesson
    },
    async generateScript(
      courseId: string,
      lessonUnitId: string,
      requirements = '',
      materialAssetIds: string[] = [],
      resumeJobId = '',
    ) {
      if (!this.courseId) this.courseId = courseId
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.post<{ job: TeacherLessonJob }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/generate`,
          {
            request_id: createUuid(),
            resume_job_id: resumeJobId,
            requirements,
            material_asset_ids: materialAssetIds,
          },
          { ...requestConfig(), silentError: true },
        )
        const job = response.data.job
        if (this.courseId === courseId) {
          this.jobs = mergeLessonJobSnapshots(this.jobs, [job])
          void this.streamJob(courseId, job.id)
        }
        return job
      } catch (error) {
        if (this.courseId === courseId) this.error = errorMessage(error, '本讲讲义生成失败')
        throw error
      } finally {
        if (this.courseId === courseId) this.actionLessonId = ''
      }
    },
    async generateAllScripts(
      courseId: string,
      requirements = '',
    ) {
      if (!this.courseId) this.courseId = courseId
      this.error = ''
      try {
        const response = await http.post<{
          parent_job: { id: string; child_job_ids: string[]; skipped_lesson_ids: string[]; total: number; started: number }
          jobs: TeacherLessonJob[]
        }>(
          `/api/teacher/courses/${courseId}/lesson-scripts/generate-all`,
          {
            request_id: createUuid(),
            requirements,
          },
          { ...requestConfig(), silentError: true },
        )
        const incoming = response.data.jobs
        if (this.courseId === courseId) {
          this.jobs = mergeLessonJobSnapshots(this.jobs, incoming)
          incoming
            .filter(job => ['pending', 'running'].includes(job.status))
            .forEach(job => { void this.streamJob(courseId, job.id) })
        }
        return response.data
      } catch (error) {
        if (this.courseId === courseId) this.error = errorMessage(error, '全部讲义任务创建失败，请重试。')
        throw error
      }
    },
    async saveScriptDraft(
      courseId: string,
      lessonUnitId: string,
      baseRevisionId: string,
      sections: TeacherLessonScriptState['sections'],
    ) {
      this.error = ''
      try {
        const response = await http.put<{ lesson: TeacherLessonProjection }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/draft`,
          { base_revision_id: baseRevisionId, sections },
          requestConfig(),
        )
        if (this.courseId === courseId) {
          const index = this.lessons.findIndex(item => item.lesson_unit_id === lessonUnitId)
          if (index >= 0) this.lessons[index] = response.data.lesson
        }
        return response.data.lesson
      } catch (error) {
        if (this.courseId === courseId) this.error = errorMessage(error, '讲义保存失败')
        throw error
      }
    },
    async rewriteScriptSection(
      courseId: string,
      lessonUnitId: string,
      baseRevisionId: string,
      sectionNodeId: string,
      instruction: string,
      materialAssetIds: string[] = [],
    ) {
      this.error = ''
      try {
        const data = await postGenerationStream<{ candidate: TeacherLessonScriptCandidate }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/rewrite-candidate`,
          {
            base_revision_id: baseRevisionId,
            section_node_id: sectionNodeId,
            instruction,
            material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean))),
          },
          { headers: teacherIdentityHeaders() },
        )
        return data.candidate
      } catch (error) {
        if (this.courseId === courseId) this.error = errorMessage(error, 'AI 优化讲义失败')
        throw error
      }
    },
    async resolveScriptAiCandidate(
      courseId: string,
      lessonUnitId: string,
      candidateId: string,
      accept: boolean,
    ) {
      const response = await http.post<{
        lesson: TeacherLessonProjection
        candidate: TeacherLessonScriptCandidate
      }>(
        `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/ai-candidates/${candidateId}/resolve`,
        { accept },
        requestConfig(),
      )
      if (this.courseId === courseId) this.replaceLessonProjection(lessonUnitId, response.data.lesson)
      return response.data
    },
    async createAiCandidate(
      courseId: string,
      lessonUnitId: string,
      baseRevisionId: string,
      instruction: string,
      sectionNodeId = '',
      materialAssetIds: string[] = [],
      target: TeacherLessonPlanAiTarget = {},
      onProgress?: (progress: GenerationProgress) => void,
    ) {
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const data = await postGenerationStream<{ candidate: TeacherLessonPlanCandidate }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/ai-candidates`,
          {
            instruction,
            section_node_id: target.sectionNodeId || sectionNodeId,
            target_field: target.field || '',
            target_item_id: target.itemId || '',
            selected_text: target.selectedText || '',
            base_revision_id: baseRevisionId,
            material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean))),
          },
          { headers: teacherIdentityHeaders(), onProgress },
        )
        return data.candidate
      } catch (error) {
        if (this.courseId === courseId) this.error = errorMessage(error, 'AI 教案优化失败')
        throw error
      } finally {
        if (this.courseId === courseId) this.actionLessonId = ''
      }
    },
    async resolveAiCandidate(
      courseId: string,
      lessonUnitId: string,
      candidateId: string,
      accept: boolean,
    ) {
      const response = await http.post<{ lesson: TeacherLessonProjection }>(
        `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/ai-candidates/${candidateId}/resolve`,
        { accept },
        requestConfig(),
      )
      if (this.courseId === courseId) this.replaceLessonProjection(lessonUnitId, response.data.lesson)
      return response.data.lesson
    },
    replaceLessonAsset(lessonUnitId: string, plan: TeacherLessonPlanAsset) {
      this.lessons = this.lessons.map(item => (
        item.lesson_unit_id === lessonUnitId ? { ...item, plan } : item
      ))
    },
    replaceLessonProjection(lessonUnitId: string, lesson: TeacherLessonProjection) {
      this.lessons = this.lessons.map(item => (
        item.lesson_unit_id === lessonUnitId ? lesson : item
      ))
    },
  },
})
