import { defineStore } from 'pinia'
import http, { getTeacherIdentity, withApiBase } from '../utils/http'
import { createUuid } from '../utils/client-id'

export type TeacherLessonJobStatus = 'pending' | 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled'

export interface TeacherLessonPlanRevision {
  revision_id: string
  lesson_unit_id: string
  source_outline_revision_id: string
  generation_source: string
  status: 'draft' | 'needs_ai_review' | 'confirmed'
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
  confirmed_at?: string
}

export interface TeacherLessonPlanAsset {
  lesson_unit_id: string
  working_revision_id: string
  confirmed_revision_id: string
  source_state: 'current' | 'stale'
  revisions: TeacherLessonPlanRevision[]
  ai_candidates?: TeacherLessonPlanCandidate[]
  script_confirmation?: {
    confirmed_revision_id?: string
    source_lesson_plan_revision_id?: string
    source_state?: 'current' | 'stale'
    confirmed_at?: string
  }
  ppt_assets: TeacherLessonPptAsset[]
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
  engagement_mode?: 'passive' | 'active' | 'constructive' | 'interactive' | string
  access_support?: string[]
  grouping?: string
  transition?: string
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
  status: 'suggested' | 'draft' | 'confirmed'
  confirmed: boolean
  source_state: 'current' | 'stale'
}

export interface TeacherLessonScriptState {
  current_revision_id: string
  confirmed_revision_id: string
  source_lesson_plan_revision_id: string
  source_state: 'current' | 'stale'
  ready: boolean
  confirmed: boolean
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
  confirmed_at: string
  sections: TeacherLessonScriptSection[]
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
  status: 'draft' | 'needs_ai_review'
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
  plan: Record<string, any>
  status: 'pending' | 'accepted' | 'rejected'
  created_at: string
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
  stream_sequence?: number
  stream_batches?: Record<string, string>
  stream_complete?: boolean
  requirements?: string
  total_blocks?: number
  completed_blocks?: number
  current_block_id?: string
  current_block_title?: string
  block_states?: Record<string, 'pending' | 'running' | 'completed' | 'failed'>
  result_sections?: TeacherLessonScriptSection[]
  updated_at?: string
}

export interface TeacherLessonJobStreamEvent {
  event: 'lesson_plan_stream' | 'lesson_plan_complete' | 'lesson_plan_failed'
    | 'lesson_plan_cancelled' | 'lesson_script_stream' | 'lesson_script_complete'
    | 'lesson_script_failed' | 'lesson_script_cancelled' | 'error'
  job?: TeacherLessonJob
  job_id?: string
  message?: string
}

export interface TeacherLessonAuthoringView {
  schema_version: 'teacher_lesson_authoring_view_v1'
  pipeline_version?: 'standard_lesson_plan_v1'
  plan_schema_version?: 'course_teaching_plan_v3'
  course_id: string
  outline_revision_id: string
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
  return String(detail?.message || detail || error?.message || fallback)
}

export const useTeacherLessonAuthoringStore = defineStore('teacher-lesson-authoring', {
  state: () => ({
    courseId: '',
    outlineRevisionId: '',
    lessons: [] as TeacherLessonProjection[],
    jobs: [] as TeacherLessonJob[],
    loading: false,
    actionLessonId: '',
    streamingJobIds: {} as Record<string, boolean>,
    error: '',
  }),
  getters: {
    lessonById: state => (lessonUnitId: string) => state.lessons.find(item => item.lesson_unit_id === lessonUnitId),
    activeJobByLesson: state => (lessonUnitId: string) => state.jobs.find(item => (
      item.lesson_unit_id === lessonUnitId
      && item.type === 'teacher_lesson_plan_generation'
      && ['pending', 'running'].includes(item.status)
    )),
    latestJobByLesson: state => (lessonUnitId: string) => [...state.jobs]
      .reverse()
      .find(item => item.lesson_unit_id === lessonUnitId && item.type === 'teacher_lesson_plan_generation'),
    latestScriptJobByLesson: state => (lessonUnitId: string) => [...state.jobs]
      .reverse()
      .find(item => item.lesson_unit_id === lessonUnitId && item.type === 'teacher_lesson_script_generation'),
  },
  actions: {
    async load(courseId: string) {
      if (this.courseId !== courseId) {
        this.courseId = courseId
        this.outlineRevisionId = ''
        this.lessons = []
        this.jobs = []
        this.streamingJobIds = {}
      }
      this.loading = true
      this.error = ''
      try {
        const response = await http.get<TeacherLessonAuthoringView>(
          `/api/teacher/courses/${courseId}/lesson-authoring`,
          { ...requestConfig(), silentError: true },
        )
        this.courseId = courseId
        this.outlineRevisionId = response.data.outline_revision_id
        this.lessons = response.data.lessons
        this.jobs = response.data.jobs
        response.data.jobs
          .filter(job => ['pending', 'running'].includes(job.status))
          .forEach(job => { void this.streamJob(courseId, job.id) })
        return response.data
      } catch (error) {
        this.error = errorMessage(error, '分讲教案状态读取失败')
        throw error
      } finally {
        this.loading = false
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
          requestConfig(),
        )
        const job = response.data.job
        this.jobs = [...this.jobs.filter(item => item.id !== job.id), job]
        void this.streamJob(courseId, job.id)
        return job
      } catch (error) {
        this.error = errorMessage(error, '本讲教案生成失败')
        throw error
      } finally {
        this.actionLessonId = ''
      }
    },
    async confirmArrangement(
      courseId: string,
      lessonUnitId: string,
      arrangement: Pick<TeacherLessonArrangement, 'lesson_type' | 'blocks'>,
    ) {
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.put<{ lesson: TeacherLessonProjection }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/arrangement/confirm`,
          {
            lesson_type: arrangement.lesson_type,
            blocks: arrangement.blocks,
          },
          requestConfig(),
        )
        this.replaceLessonProjection(lessonUnitId, response.data.lesson)
        return response.data.lesson
      } catch (error) {
        this.error = errorMessage(error, '本讲课型与教学块确认失败')
        throw error
      } finally {
        this.actionLessonId = ''
      }
    },
    async loadKnowledgeEvidence(courseId: string, lessonUnitId: string) {
      const response = await http.get<TeacherLessonKnowledgeEvidence>(
        `/api/teacher/courses/${courseId}/knowledge-evidence`,
        { ...requestConfig(), params: { lesson_unit_id: lessonUnitId } },
      )
      return response.data
    },
    async pollJob(courseId: string, jobId: string) {
      for (let attempt = 0; attempt < 180; attempt += 1) {
        const response = await http.get<{ job: TeacherLessonJob }>(
          `/api/teacher/courses/${courseId}/lesson-jobs/${jobId}`,
          requestConfig(),
        )
        const job = response.data.job
        this.jobs = [...this.jobs.filter(item => item.id !== job.id), job]
        if (['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(job.status)) {
          await this.load(courseId)
          return job
        }
        await new Promise(resolve => setTimeout(resolve, 1500))
      }
      return this.jobs.find(item => item.id === jobId)
    },
    async streamJob(courseId: string, jobId: string) {
      if (this.streamingJobIds[jobId]) return this.jobs.find(item => item.id === jobId)
      this.streamingJobIds = { ...this.streamingJobIds, [jobId]: true }
      let terminal = false
      try {
        const response = await fetch(
          withApiBase(`/api/teacher/courses/${courseId}/lesson-jobs/${jobId}/stream`),
          {
            headers: {
              Accept: 'text/event-stream',
              'X-User-Id': getTeacherIdentity(),
            },
          },
        )
        await consumeLessonPlanStream(response, event => {
          const job = event.job
          if (!job) {
            if (event.event === 'error') this.error = event.message || '本讲生成流已中断'
            return
          }
          this.jobs = [...this.jobs.filter(item => item.id !== job.id), job]
          terminal = ['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(job.status)
        })
        if (terminal) await this.load(courseId)
        return this.jobs.find(item => item.id === jobId)
      } catch {
        const current = this.jobs.find(item => item.id === jobId)
        if (current && !['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(current.status)) {
          return this.pollJob(courseId, jobId)
        }
        return current
      } finally {
        const next = { ...this.streamingJobIds }
        delete next[jobId]
        this.streamingJobIds = next
      }
    },
    async cancelJob(courseId: string, jobId: string) {
      const response = await http.delete<{ job: TeacherLessonJob }>(
        `/api/teacher/courses/${courseId}/lesson-jobs/${jobId}`,
        requestConfig(),
      )
      const job = response.data.job
      this.jobs = [...this.jobs.filter(item => item.id !== job.id), job]
      return job
    },
    async saveDraft(courseId: string, lessonUnitId: string, plan: Record<string, any>) {
      const response = await http.patch<{ lesson: TeacherLessonPlanAsset }>(
        `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/draft`,
        { plan, source_outline_revision_id: this.outlineRevisionId },
        requestConfig(),
      )
      this.replaceLessonAsset(lessonUnitId, response.data.lesson)
      return response.data.lesson
    },
    async confirm(courseId: string, lessonUnitId: string, revisionId: string) {
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.post<{ lesson: TeacherLessonPlanAsset }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/confirm`,
          { revision_id: revisionId },
          requestConfig(),
        )
        this.replaceLessonAsset(lessonUnitId, response.data.lesson)
        await this.load(courseId)
        return response.data.lesson
      } catch (error) {
        this.error = errorMessage(error, '本讲教案确认失败')
        throw error
      } finally {
        this.actionLessonId = ''
      }
    },
    async confirmScript(courseId: string, lessonUnitId: string, revisionId: string) {
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.post<{ lesson: TeacherLessonProjection }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/confirm`,
          { revision_id: revisionId },
          requestConfig(),
        )
        this.replaceLessonProjection(lessonUnitId, response.data.lesson)
        return response.data.lesson
      } catch (error) {
        this.error = errorMessage(error, '本讲讲稿确认失败')
        throw error
      } finally {
        this.actionLessonId = ''
      }
    },
    async generateScript(
      courseId: string,
      lessonUnitId: string,
      requirements = '',
      materialAssetIds: string[] = [],
      resumeJobId = '',
    ) {
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
          requestConfig(),
        )
        const job = response.data.job
        this.jobs = [...this.jobs.filter(item => item.id !== job.id), job]
        void this.streamJob(courseId, job.id)
        return job
      } catch (error) {
        this.error = errorMessage(error, '本讲讲稿生成失败')
        throw error
      } finally {
        this.actionLessonId = ''
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
        const index = this.lessons.findIndex(item => item.lesson_unit_id === lessonUnitId)
        if (index >= 0) this.lessons[index] = response.data.lesson
        return response.data.lesson
      } catch (error) {
        this.error = errorMessage(error, '讲稿保存失败')
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
        const response = await http.post<{ candidate: TeacherLessonScriptCandidate }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/rewrite-candidate`,
          {
            base_revision_id: baseRevisionId,
            section_node_id: sectionNodeId,
            instruction,
            material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean))),
          },
          requestConfig(),
        )
        return response.data.candidate
      } catch (error) {
        this.error = errorMessage(error, 'AI 优化讲稿失败')
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
      this.replaceLessonProjection(lessonUnitId, response.data.lesson)
      return response.data
    },
    async createAiCandidate(
      courseId: string,
      lessonUnitId: string,
      baseRevisionId: string,
      instruction: string,
      sectionNodeId = '',
      materialAssetIds: string[] = [],
    ) {
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.post<{ candidate: TeacherLessonPlanCandidate }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/ai-candidates`,
          {
            instruction,
            section_node_id: sectionNodeId,
            base_revision_id: baseRevisionId,
            material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean))),
          },
          requestConfig(),
        )
        return response.data.candidate
      } catch (error) {
        this.error = errorMessage(error, 'AI 教案优化失败')
        throw error
      } finally {
        this.actionLessonId = ''
      }
    },
    async resolveAiCandidate(
      courseId: string,
      lessonUnitId: string,
      candidateId: string,
      accept: boolean,
    ) {
      const response = await http.post<{ lesson: TeacherLessonPlanAsset }>(
        `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/ai-candidates/${candidateId}/resolve`,
        { accept },
        requestConfig(),
      )
      this.replaceLessonAsset(lessonUnitId, response.data.lesson)
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
