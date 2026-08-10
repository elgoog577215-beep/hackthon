import { defineStore } from 'pinia'
import http, { learnerIdentityHeaders, withApiBase } from '../utils/http'
import {
  advanceSlideBuildStep,
  isFinalV5CandidateReplay,
} from '../utils/slide-build-progress'

export type RepresentationType = 'outline' | 'lesson_plan' | 'handout' | 'practice_sheet' | 'slide_deck' | 'diagram'
export type SlideDeckMode = 'full' | 'teaching' | 'concise'
export type SlideDeckTheme =
  | 'qizhi-classroom'
  | 'academic-editorial'
  | 'grid-notebook'
  | 'modern-geometric'
  | 'dark-tech'
  | 'qingfeng-classroom'
  | 'academic-bluegray'
export type SlideDeckPreviewSource = 'draft' | 'published'
export type SlideDeckCandidateStatus = '' | 'v5_ready' | 'v5_needs_manual_edit' | 'v5_failed'

export interface SlideDeckBuildOptions {
  mode: SlideDeckMode
  theme: Exclude<SlideDeckTheme, 'qingfeng-classroom' | 'academic-bluegray'>
  forceRebuild?: boolean
  webImageRetrieval?: {
    enabled: boolean
    mode?: 'wide_safe'
    targetCount?: number
  }
}

export interface TeachingRepresentation {
  representation_id: string
  representation_type: RepresentationType
  variant_key?: string
  spec_id: string
  status: 'planned' | 'building' | 'ready' | 'stale' | 'failed' | 'archived'
  stale_unit_ids: string[]
  stale_reasons: string[]
  revision: string
  updated_at: string
  visual_engine_update_available?: boolean
  visual_engine_update_reason?: string
  course_logic_upgrade_required?: boolean
  course_logic_upgrade_reason?: string
}

export interface TeachingRepresentationSpec {
  spec_id: string
  representation_type: RepresentationType
  payload: {
    compiler_version: string
    content: Record<string, any>
  }
  unit_bindings: Record<string, Array<Record<string, any>>>
  revision: string
}

export function preferredRepresentationForType(
  representations: TeachingRepresentation[],
  type: RepresentationType,
  registry?: Record<string, any> | null,
): TeachingRepresentation | undefined {
  const candidates = representations.filter(item => (
    item.representation_type === type && item.status !== 'archived'
  ))
  if (!candidates.length) return undefined
  let eligible = candidates
  if (type === 'slide_deck') {
    const targetSchema = String(registry?.slide_deck_target_schema || '')
    if (targetSchema === 'blocked') return undefined
    if (['slide_deck_v3', 'slide_deck_v4', 'slide_deck_v5'].includes(targetSchema)) {
      const specsById = new Map<string, TeachingRepresentationSpec>(
        (registry?.specs || []).map((spec: TeachingRepresentationSpec) => [spec.spec_id, spec]),
      )
      eligible = candidates.filter(item => (
        specsById.get(item.spec_id)?.payload?.content?.schema_version === targetSchema
      ))
      if (!eligible.length) return undefined
    }
  }
  return eligible.slice().sort((left, right) => {
    const readyDelta = Number(right.status === 'ready') - Number(left.status === 'ready')
    if (readyDelta) return readyDelta
    const variantDelta = Number(Boolean(right.variant_key)) - Number(Boolean(left.variant_key))
    if (variantDelta) return variantDelta
    return String(right.updated_at || '').localeCompare(String(left.updated_at || ''))
  })[0]
}

export interface TeachingRepresentationBuildEvent {
  event: string
  progress?: number
  stage?: string
  code?: string
  message?: string
  action?: string
  retryable?: boolean
  slide?: Record<string, any>
  quality?: Record<string, any>
  build?: Record<string, any>
  registry?: Record<string, any>
  sequence?: number
  task_id?: string
  visual_plan?: Record<string, any>
  asset_id?: string
  completed?: number
  total?: number
  target_schema?: string
  engine_schema?: string
  candidate_stage?: string
  candidate_status?: string
  failure?: Partial<TeachingRepresentationBuildFailure>
  source_revision?: string
  chapter_id?: string
  page_id?: string
  estimated_slide_count?: number
  allocation_plan?: { pages?: Array<Record<string, any>> }
  chapter?: Record<string, any>
  title?: string
  part_index?: number
  part_count?: number
  part_id?: string
  repair_attempt?: number
  repair_attempts?: number
}

export interface SlideDeckBuildDetail {
  event: string
  message?: string
  completed: number
  total: number
  itemTitle?: string
  itemId?: string
  partIndex?: number
  partCount?: number
  repairAttempt?: number
  candidateStage?: string
}

function compactBuildDetail(
  event: TeachingRepresentationBuildEvent,
  estimatedSlideCount: number,
  completedUnitCount: number,
): SlideDeckBuildDetail {
  const eventCompleted = event.completed == null ? completedUnitCount : Number(event.completed)
  const eventTotal = event.total == null ? estimatedSlideCount : Number(event.total)
  const slide = event.slide || {}
  const chapter = event.chapter || {}
  return {
    event: String(event.event || event.stage || 'building'),
    message: String(event.message || ''),
    completed: eventCompleted,
    total: eventTotal,
    itemTitle: String(slide.title || chapter.title || event.title || ''),
    itemId: String(
      slide.unit_id
      || event.page_id
      || event.asset_id
      || event.part_id
      || chapter.chapter_id
      || '',
    ),
    partIndex: Number(event.part_index || 0),
    partCount: Number(event.part_count || 0),
    repairAttempt: Number(event.repair_attempt || event.repair_attempts || 0),
    candidateStage: String(event.candidate_stage || ''),
  }
}

export interface TeachingRepresentationBuildFailure {
  stage?: string
  code: string
  message: string
  action?: string
  retryable: boolean
  source_revision?: string
  chapter_id?: string
  page_id?: string
}

export class TeachingRepresentationBuildError extends Error {
  readonly failure: TeachingRepresentationBuildFailure

  constructor(failure: TeachingRepresentationBuildFailure) {
    super(failure.message)
    this.name = 'TeachingRepresentationBuildError'
    this.failure = failure
    Object.setPrototypeOf(this, new.target.prototype)
  }
}

const COURSE_LOGIC_FAILURES: Record<string, Omit<TeachingRepresentationBuildFailure, 'code'>> = {
  course_teaching_plan_not_ready: {
    message: '当前课程尚未完成正式教学计划，请先补全课程逻辑。',
    action: 'upgrade_course_logic',
    retryable: false,
  },
  course_knowledge_base_not_ready: {
    message: '当前课程尚未建立可用的正式知识库，请先补全课程逻辑。',
    action: 'upgrade_course_logic',
    retryable: false,
  },
  course_coherence_contract_not_ready: {
    message: '当前课程尚未通过课程连贯性检查，请先补全课程逻辑。',
    action: 'upgrade_course_logic',
    retryable: false,
  },
  course_teaching_plan_incomplete: {
    message: '正式教学计划缺少部分章节的教学契约，请重新补全课程逻辑。',
    action: 'upgrade_course_logic',
    retryable: false,
  },
}

function inferredCourseLogicCode(value: string) {
  const normalized = value.toLowerCase()
  if (
    normalized.includes('completed official course teaching plan')
    || normalized.includes('course_teaching_plan_not_ready')
  ) return 'course_teaching_plan_not_ready'
  if (
    normalized.includes('active official course knowledge base')
    || normalized.includes('course_knowledge_base_not_ready')
  ) return 'course_knowledge_base_not_ready'
  if (
    normalized.includes('active course coherence contract')
    || normalized.includes('course_coherence_contract_not_ready')
  ) return 'course_coherence_contract_not_ready'
  if (
    normalized.includes('teaching plan has no section contract')
    || normalized.includes('course_teaching_plan_incomplete')
  ) return 'course_teaching_plan_incomplete'
  return ''
}

export function normalizedBuildFailure(
  value: unknown,
  quality?: Record<string, any>,
): TeachingRepresentationBuildFailure {
  const explicit = value instanceof TeachingRepresentationBuildError
    ? value.failure
    : value && typeof value === 'object' && !(value instanceof Error)
      ? value as Partial<TeachingRepresentationBuildFailure>
      : {}
  const context = {
    ...(explicit.stage ? { stage: String(explicit.stage) } : {}),
    ...(explicit.source_revision ? { source_revision: String(explicit.source_revision) } : {}),
    ...(explicit.chapter_id ? { chapter_id: String(explicit.chapter_id) } : {}),
    ...(explicit.page_id ? { page_id: String(explicit.page_id) } : {}),
  }
  const rawMessage = String(
    explicit.message
    || (value instanceof Error ? value.message : typeof value === 'string' ? value : '')
    || '',
  )
  const blockerCodes = (quality?.blockers || []).map(
    (item: Record<string, any>) => String(item?.code || ''),
  )
  const explicitCode = String(explicit.code || '')
  const courseLogicCode = (
    (explicitCode && COURSE_LOGIC_FAILURES[explicitCode] ? explicitCode : '')
    || blockerCodes.find((code: string) => COURSE_LOGIC_FAILURES[code])
    || inferredCourseLogicCode(`${explicitCode} ${rawMessage}`)
  )
  if (courseLogicCode) {
    const preset = COURSE_LOGIC_FAILURES[courseLogicCode]!
    return {
      ...context,
      code: courseLogicCode,
      message: explicit.message ? String(explicit.message) : preset.message,
      action: explicit.action ? String(explicit.action) : preset.action,
      retryable: explicit.retryable ?? false,
    }
  }
  const normalizedError = `${explicitCode} ${rawMessage}`.toLowerCase()
  if (normalizedError.includes('split_required') || blockerCodes.includes('deck_split_required')) {
    return { code: 'deck_split_required', message: rawMessage || '课件需要拆分后生成。', retryable: false }
  }
  if (
    normalizedError.includes('no capacity-safe layout')
    || normalizedError.includes('layout_capacity_failed')
  ) {
    return { code: 'layout_capacity_failed', message: rawMessage || '课件内容超过版式容量。', retryable: true }
  }
  if (
    normalizedError.includes('quality_gate_failed')
    || blockerCodes.length
    || quality?.passed === false
  ) {
    return { code: 'quality_gate_failed', message: rawMessage || '课件未通过质量检查。', retryable: true }
  }
  const code = explicitCode || 'teaching_representation_build_failed'
  return {
    ...context,
    code,
    message: explicit.message
      ? String(explicit.message)
      : '课件生成遇到异常，请稍后重试。',
    ...(explicit.action ? { action: String(explicit.action) } : {}),
    retryable: explicit.retryable ?? true,
  }
}

function terminalPipelineFailureQuality(
  message: unknown,
  failure = normalizedBuildFailure(message),
) {
  const issue = {
    severity: 'critical',
    code: failure.code === 'teaching_representation_build_failed'
      ? 'slide_variant_rebuild_failed'
      : failure.code,
    message: failure.message,
  }
  return {
    passed: false,
    score: 0,
    issues: [issue],
    blockers: [issue],
  }
}

export async function consumeTeachingRepresentationStream(
  response: Response,
  onEvent: (event: TeachingRepresentationBuildEvent) => void,
) {
  if (!response.ok) {
    const body = await response.text()
    let payload: any
    try {
      payload = JSON.parse(body)
    } catch {
      throw new Error(body || `HTTP ${response.status}`)
    }
    const detail = payload?.detail || payload?.error || payload
    throw new TeachingRepresentationBuildError(normalizedBuildFailure(detail))
  }
  if (!response.body) throw new Error('Teaching representation stream is unavailable')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const flush = (chunk: string) => {
    const data = chunk
      .split(/\r?\n/)
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n')
    if (!data) return
    onEvent(JSON.parse(data) as TeachingRepresentationBuildEvent)
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

export const useTeachingRepresentationsStore = defineStore('teachingRepresentations', {
  state: () => ({
    courseId: '',
    registry: null as Record<string, any> | null,
    selectedId: '',
    selectedSpec: null as TeachingRepresentationSpec | null,
    quality: null as Record<string, any> | null,
    slideQuality: null as Record<string, any> | null,
    publishedSlideQuality: null as Record<string, any> | null,
    draftSlideQuality: null as Record<string, any> | null,
    slidePreviewSource: 'published' as SlideDeckPreviewSource,
    slideTargetSchema: '',
    slideCandidateSchema: '',
    slidePublishedSchema: '',
    slideCandidateStatus: '' as SlideDeckCandidateStatus,
    liveSlides: [] as Array<Record<string, any>>,
    buildProgress: 0,
    buildStage: '',
    buildDisplayStep: 0,
    buildDetail: null as SlideDeckBuildDetail | null,
    buildEstimatedSlideCount: 0,
    buildCompletedUnitCount: 0,
    buildError: '',
    buildFailure: null as TeachingRepresentationBuildFailure | null,
    buildTaskId: '',
    buildPaused: false,
    buildStreamActive: false,
    loading: false,
    building: false,
    deferMissingSlideBuild: false,
    courseRequestToken: 0,
    loadRequestToken: 0,
    specRequestToken: 0,
    buildAttemptToken: 0,
  }),
  getters: {
    representations(state): TeachingRepresentation[] {
      return (state.registry?.representations || []) as TeachingRepresentation[]
    },
    selectedRepresentation(state): TeachingRepresentation | null {
      return (state.registry?.representations || []).find(
        (item: TeachingRepresentation) => item.representation_id === state.selectedId,
      ) || null
    },
  },
  actions: {
    switchCourse(courseId: string) {
      if (this.courseId === courseId) return
      this.courseId = courseId
      this.courseRequestToken += 1
      this.loadRequestToken += 1
      this.specRequestToken += 1
      this.buildAttemptToken += 1
      this.registry = null
      this.selectedId = ''
      this.selectedSpec = null
      this.quality = null
      this.slideQuality = null
      this.publishedSlideQuality = null
      this.draftSlideQuality = null
      this.slidePreviewSource = 'published'
      this.slideTargetSchema = ''
      this.slideCandidateSchema = ''
      this.slidePublishedSchema = ''
      this.slideCandidateStatus = ''
      this.liveSlides = []
      this.buildProgress = 0
      this.buildStage = ''
      this.buildDisplayStep = 0
      this.buildDetail = null
      this.buildEstimatedSlideCount = 0
      this.buildCompletedUnitCount = 0
      this.buildError = ''
      this.buildFailure = null
      this.buildTaskId = ''
      this.buildPaused = false
      this.buildStreamActive = false
      this.loading = false
      this.building = false
    },
    async load(courseId: string) {
      this.switchCourse(courseId)
      const courseToken = this.courseRequestToken
      const requestToken = ++this.loadRequestToken
      this.specRequestToken += 1
      const isCurrentRequest = () => (
        this.courseId === courseId
        && this.courseRequestToken === courseToken
        && this.loadRequestToken === requestToken
      )
      this.loading = true
      try {
        const response = await http.get(`/api/courses/${courseId}/teaching-representations`)
        if (!isCurrentRequest()) return null
        this.registry = response.data.registry
        this.slideTargetSchema = String(this.registry?.slide_deck_target_schema || '')
        this.slideCandidateSchema = String(this.registry?.slide_deck_candidate_schema || '')
        this.slidePublishedSchema = String(this.registry?.slide_deck_published_schema || '')
        this.slideCandidateStatus = String(
          this.registry?.slide_deck_candidate_status || '',
        ) as SlideDeckCandidateStatus
        const available = this.representations
        if (!this.selectedId || !available.some(item => item.representation_id === this.selectedId)) {
          this.selectedId = available[0]?.representation_id || ''
        }
        if (this.selectedId) await this.loadSpec(this.selectedId)
        if (!isCurrentRequest()) return null
        return this.registry
      } finally {
        if (isCurrentRequest()) this.loading = false
      }
    },
    async upgradeCourseLogic(courseId: string) {
      this.switchCourse(courseId)
      const courseToken = this.courseRequestToken
      const response = await http.post(
        `/api/courses/${courseId}/teaching-representations/course-logic/upgrade`,
      )
      if (
        this.courseId === courseId
        && this.courseRequestToken === courseToken
        && response.data?.registry
      ) {
        this.registry = response.data.registry
        this.selectedId = ''
        this.selectedSpec = null
        this.buildError = ''
        this.buildFailure = null
      }
      return response.data
    },
    async build(courseId: string) {
      return this.buildProgressive(courseId)
    },
    async buildProgressive(courseId: string, options?: SlideDeckBuildOptions) {
      this.switchCourse(courseId)
      this.loadRequestToken += 1
      this.loading = false
      const courseToken = this.courseRequestToken
      const attemptToken = ++this.buildAttemptToken
      this.specRequestToken += 1
      const isCurrentAttempt = () => (
        this.courseId === courseId
        && this.courseRequestToken === courseToken
        && this.buildAttemptToken === attemptToken
      )
      this.building = true
      this.buildProgress = 0
      this.buildStage = 'planning'
      this.buildDisplayStep = 0
      this.buildStreamActive = false
      this.buildDetail = {
        event: 'planning',
        completed: 0,
        total: 0,
      }
      this.buildEstimatedSlideCount = 0
      this.buildCompletedUnitCount = 0
      this.buildError = ''
      this.buildFailure = null
      this.buildPaused = false
      this.liveSlides = []
      this.draftSlideQuality = null
      this.slidePreviewSource = 'published'
      this.slideQuality = this.publishedSlideQuality
      this.slideTargetSchema = String(
        this.registry?.slide_deck_target_schema || this.slideTargetSchema || '',
      )
      this.slideCandidateSchema = ''
      this.slideCandidateStatus = ''
      let durableMonitorStarted = false
      try {
        const response = await fetch(
          withApiBase(options
            ? `/api/courses/${courseId}/teaching-representations/slide-decks/build/stream`
            : `/api/courses/${courseId}/teaching-representations/build/stream`),
          {
            method: 'POST',
            headers: learnerIdentityHeaders({
              Accept: 'text/event-stream',
              ...(options ? { 'Content-Type': 'application/json' } : {}),
            }),
            ...(options ? {
              body: JSON.stringify({
                mode: options.mode,
                theme: options.theme,
                force_rebuild: options.forceRebuild === true,
                ...(options.webImageRetrieval ? {
                  web_image_retrieval: {
                    enabled: options.webImageRetrieval.enabled,
                    mode: options.webImageRetrieval.mode || 'wide_safe',
                    ...(options.webImageRetrieval.targetCount == null
                      ? {}
                      : { target_count: options.webImageRetrieval.targetCount }),
                  },
                } : {}),
              }),
            } : {}),
          },
        )
        const completedRef: { value?: TeachingRepresentationBuildEvent } = {}
        this.buildStreamActive = true
        await consumeTeachingRepresentationStream(response, event => {
          if (!isCurrentAttempt()) return
          const finalCandidateReplay = isFinalV5CandidateReplay(event)
          if (event.task_id) {
            this.buildTaskId = event.task_id
            if (!durableMonitorStarted) {
              durableMonitorStarted = true
              this.monitorDurableBuild(courseId, event.task_id, courseToken, attemptToken)
            }
          }
          this.buildProgress = Math.max(this.buildProgress, Number(event.progress || 0))
          if (event.target_schema) this.slideTargetSchema = String(event.target_schema)
          if (event.candidate_status) {
            this.slideCandidateStatus = event.candidate_status as SlideDeckCandidateStatus
          }
          if (event.stage && !finalCandidateReplay) this.buildStage = event.stage
          if (event.event === 'deck_plan') {
            this.buildEstimatedSlideCount = Math.max(
              this.buildEstimatedSlideCount,
              Number(event.estimated_slide_count || 0),
            )
          }
          if (event.event === 'layout_plan') {
            this.buildEstimatedSlideCount = Math.max(
              this.buildEstimatedSlideCount,
              event.allocation_plan?.pages?.length || 0,
            )
          }
          if (event.event === 'story_plan') this.buildStage = 'story_plan'
          if (event.event === 'chapter_plan') this.buildStage = 'chapter_plan'
          if (event.event === 'episode_progress') this.buildStage = 'episode_progress'
          if (event.event === 'layout_plan') this.buildStage = 'layout_plan'
          if (event.event === 'deck_plan') this.buildStage = 'slide_plan'
          if (event.event === 'visual_plan') this.buildStage = 'visual_plan'
          if (event.event === 'asset_progress' || event.event === 'asset_ready') {
            this.buildStage = 'asset_compilation'
          }
          if (
            event.event === 'slide_reset'
            && finalCandidateReplay
          ) {
            this.liveSlides = []
            this.slideCandidateSchema = 'slide_deck_v5'
          }
          if (event.event === 'slide_upsert' && event.slide) {
            const strictV5 = this.slideTargetSchema === 'slide_deck_v5'
            const acceptedV5Candidate = (
              event.engine_schema === 'slide_deck_v5'
              && ['final_contract', 'render_verified'].includes(String(event.candidate_stage || ''))
            )
            if (strictV5 && !acceptedV5Candidate) return
            if (acceptedV5Candidate) this.slideCandidateSchema = 'slide_deck_v5'
            if (!finalCandidateReplay) this.buildStage = 'slide_build'
            if (this.slidePreviewSource !== 'draft') {
              this.slidePreviewSource = 'draft'
              this.slideQuality = this.draftSlideQuality
            }
            const index = this.liveSlides.findIndex(slide => slide.unit_id === event.slide?.unit_id)
            if (index >= 0) this.liveSlides.splice(index, 1, event.slide)
            else this.liveSlides.push(event.slide)
            this.buildCompletedUnitCount = this.liveSlides.length
          }
          if (event.event === 'slide_quality' && event.quality) {
            this.buildStage = 'quality'
            this.draftSlideQuality = event.quality
            if (this.liveSlides.length) {
              this.slidePreviewSource = 'draft'
              this.slideQuality = event.quality
            }
          }
          if (event.event === 'visual_quality' && event.quality) {
            this.buildStage = 'visual_quality'
            this.draftSlideQuality = {
              ...(this.draftSlideQuality || {}),
              visual: event.quality,
            }
          }
          if (event.event === 'render_review') this.buildStage = 'render_review'
          if (event.event === 'semantic_repair') this.buildStage = 'semantic_repair'
          if (event.event === 'image_search') this.buildStage = 'image_search'
          if (event.event === 'render_repair') this.buildStage = 'render_repair'
          if (event.event === 'repair_progress') this.buildStage = 'repair_progress'
          if (event.event === 'quality_fallback') {
            this.buildStage = 'quality_fallback'
            this.liveSlides = []
            this.draftSlideQuality = null
            this.buildFailure = null
            this.buildError = ''
            if (this.publishedSlideQuality) {
              this.slidePreviewSource = 'published'
              this.slideQuality = this.publishedSlideQuality
            }
          }
          if (event.event === 'build_blocked') {
            const failure = normalizedBuildFailure(event, event.quality)
            this.settleFailedSlideDraft(event.quality)
            this.buildFailure = failure
            this.buildError = failure.code
          }
          if (event.event === 'build_failed') {
            const failure = normalizedBuildFailure(event, event.quality)
            const terminalQuality = event.quality || terminalPipelineFailureQuality(event.message, failure)
            this.settleFailedSlideDraft(terminalQuality)
            this.buildFailure = failure
            this.buildError = failure.code
          }
          if (event.event === 'build_complete') completedRef.value = event
          if (
            event.event === 'build_complete'
            && String(event.build?.status || '').startsWith('failed')
          ) {
            const completionFailure = (
              event.code
              || event.message
              || event.quality
            )
              ? event
              : this.buildFailure || {
                  code: 'quality_gate_failed',
                  message: '课件未通过质量检查。',
                }
            const failure = normalizedBuildFailure(
              completionFailure,
              event.quality || this.draftSlideQuality || undefined,
            )
            this.settleFailedSlideDraft(event.quality)
            this.buildFailure = failure
            this.buildError = failure.code
          }
          if (event.event === 'error') {
            const failure = normalizedBuildFailure(event, event.quality)
            this.buildFailure = failure
            this.buildError = failure.code
          }
          if (event.event === 'paused') this.buildPaused = true
          this.buildDisplayStep = advanceSlideBuildStep(
            this.buildDisplayStep,
            this.buildStage,
            this.buildProgress,
          )
          this.buildDetail = compactBuildDetail(
            event,
            this.buildEstimatedSlideCount,
            this.buildCompletedUnitCount,
          )
        })
        if (isCurrentAttempt()) this.buildStreamActive = false
        if (!isCurrentAttempt()) return completedRef.value
        if (this.buildPaused) return completedRef.value
        if (this.buildError) throw new Error(this.buildError)
        const completed = completedRef.value
        if (!completed?.registry) throw new Error('Teaching representation build ended without a registry')
        this.registry = completed.registry
        this.slideTargetSchema = String(
          completed.target_schema
          || completed.registry?.slide_deck_target_schema
          || this.slideTargetSchema
          || '',
        )
        this.slideCandidateStatus = String(
          completed.build?.candidate_status
          || this.slideCandidateStatus
          || '',
        ) as SlideDeckCandidateStatus
        this.quality = completed.quality || null
        this.slidePreviewSource = 'published'
        this.publishedSlideQuality = completed.quality || this.draftSlideQuality
        this.draftSlideQuality = null
        this.slideQuality = this.publishedSlideQuality
        this.buildProgress = 100
        this.buildStage = 'complete'
        this.buildDisplayStep = 9
        this.buildFailure = null
        const available = this.representations
        const requestedVariant = options ? `${options.mode}:${options.theme}` : ''
        const requestedRepresentation = requestedVariant
          ? available.find(item => (
              item.representation_type === 'slide_deck'
              && (
                item.variant_key === requestedVariant
                || item.variant_key?.startsWith(`${requestedVariant}:part:`)
              )
            ))
          : null
        if (requestedRepresentation) {
          this.selectedId = requestedRepresentation.representation_id
        } else if (!this.selectedId || !available.some(item => item.representation_id === this.selectedId)) {
          this.selectedId = available[0]?.representation_id || ''
        }
        if (this.selectedId) await this.loadSpec(this.selectedId)
        return completed
      } catch (error) {
        if (isCurrentAttempt()) {
          const failure = normalizedBuildFailure(error, this.draftSlideQuality || undefined)
          this.buildFailure = failure
          this.buildError = failure.code
        }
        throw error
      } finally {
        if (isCurrentAttempt()) {
          this.buildStreamActive = false
          this.building = false
        }
      }
    },
    monitorDurableBuild(
      courseId: string,
      taskId: string,
      courseToken: number,
      attemptToken: number,
    ) {
      const isCurrentAttempt = () => (
        this.courseId === courseId
        && this.courseRequestToken === courseToken
        && this.buildAttemptToken === attemptToken
        && this.buildTaskId === taskId
      )
      window.setTimeout(async () => {
        if (!isCurrentAttempt() || !this.building) return
        try {
          const response = await http.get(`/api/tasks/${taskId}`)
          if (!isCurrentAttempt()) return
          const task = response.data || {}
          const status = String(task.status || '')
          this.buildProgress = Math.max(this.buildProgress, Number(task.progress || 0))
          if (!this.buildStreamActive) {
            this.buildStage = String(task.phase || task.current_phase || this.buildStage)
            this.buildDisplayStep = advanceSlideBuildStep(
              this.buildDisplayStep,
              this.buildStage,
              this.buildProgress,
            )
          }
          if (['failed', 'completed', 'cancelled', 'paused'].includes(status)) {
            this.buildStreamActive = false
            this.applyDurableBuildTask(task)
            this.buildAttemptToken += 1
            if (status === 'completed') {
              await this.load(courseId)
              if (this.courseId === courseId) {
                this.settleCompletedSlideBuild()
                this.buildProgress = 100
                this.buildStage = 'complete'
                this.buildDisplayStep = 9
              }
            }
            return
          }
        } catch {
          // The SSE stream remains authoritative while a transient poll fails.
        }
        if (isCurrentAttempt() && this.building) {
          this.monitorDurableBuild(courseId, taskId, courseToken, attemptToken)
        }
      }, 1_000)
    },
    applyDurableBuildTask(task: Record<string, any>) {
      const status = String(task.status || '')
      this.buildTaskId = String(task.id || this.buildTaskId)
      this.buildProgress = Math.max(this.buildProgress, Number(task.progress || 0))
      this.buildStage = String(task.phase || task.current_phase || this.buildStage)
      if (status === 'failed') {
        const failure = normalizedBuildFailure(
          task.error_detail || task.error || task.message,
          task.result?.quality || task.quality,
        )
        const quality = (
          task.result?.quality
          || task.quality
          || terminalPipelineFailureQuality(task.message || task.error, failure)
        )
        this.settleFailedSlideDraft(quality)
        this.building = false
        this.buildPaused = false
        this.buildProgress = Math.max(this.buildProgress, 100)
        this.buildStage = 'build_blocked'
        this.buildFailure = failure
        this.buildError = failure.code
      } else if (status === 'completed') {
        this.building = false
        this.buildPaused = false
        this.buildProgress = 100
        this.buildStage = 'complete'
        this.buildError = ''
        this.buildFailure = null
      } else if (status === 'paused') {
        this.building = false
        this.buildPaused = true
        this.buildStage = 'paused'
      } else if (status === 'cancelled') {
        this.building = false
        this.buildPaused = false
        this.buildStage = 'cancelled'
        this.buildError = ''
        this.buildFailure = null
      } else if (['pending', 'running'].includes(status)) {
        this.building = true
        this.buildPaused = false
      }
      this.buildDisplayStep = advanceSlideBuildStep(
        this.buildDisplayStep,
        this.buildStage,
        this.buildProgress,
      )
    },
    async recoverDurableBuild(courseId: string) {
      this.switchCourse(courseId)
      const response = await http.get(`/api/courses/${courseId}/task`)
      if (this.courseId !== courseId) return null
      const task = response.data || {}
      if (!['slide_deck_variant_build', 'teaching_representation_build'].includes(String(task.type || ''))) {
        return null
      }
      this.applyDurableBuildTask(task)
      if (String(task.status || '') === 'completed') {
        await this.load(courseId)
        if (this.courseId === courseId) this.settleCompletedSlideBuild()
      }
      if (['pending', 'running'].includes(String(task.status || ''))) {
        const courseToken = this.courseRequestToken
        const attemptToken = ++this.buildAttemptToken
        this.monitorDurableBuild(
          courseId,
          String(task.id || ''),
          courseToken,
          attemptToken,
        )
      }
      return task
    },
    async buildSlideDeckVariant(courseId: string, options: SlideDeckBuildOptions) {
      return this.buildProgressive(courseId, options)
    },
    async rebuildCurrentRepresentations(courseId: string) {
      await this.buildProgressive(courseId)
      return this.buildSlideDeckVariant(courseId, {
        mode: 'teaching',
        theme: 'qizhi-classroom',
        forceRebuild: true,
      })
    },
    settleCompletedSlideBuild(quality?: Record<string, any>) {
      const publishedContent = this.selectedSpec?.payload?.content
      const publishedQuality = (
        quality
        || publishedContent?.quality_summary
        || this.publishedSlideQuality
        || null
      )
      this.liveSlides = []
      this.slidePreviewSource = 'published'
      this.draftSlideQuality = null
      this.publishedSlideQuality = publishedQuality
      this.slideQuality = publishedQuality
      this.slidePublishedSchema = String(publishedContent?.schema_version || '')
      this.slideCandidateStatus = String(
        publishedContent?.candidate_status || this.slideCandidateStatus || '',
      ) as SlideDeckCandidateStatus
      if (quality) this.quality = quality
    },
    settleFailedSlideDraft(quality?: Record<string, any>) {
      if (quality) this.draftSlideQuality = quality
      const publishedContent = this.selectedSpec?.payload?.content
      const hasPublishedDeck = (
        this.selectedRepresentation?.status === 'ready'
        && ['slide_deck_v2', 'slide_deck_v3', 'slide_deck_v4', 'slide_deck_v5'].includes(publishedContent?.schema_version)
      )
      if (hasPublishedDeck) {
        this.liveSlides = []
        this.slidePreviewSource = 'published'
        this.slideQuality = (
          this.publishedSlideQuality
          || publishedContent?.quality_summary
          || null
        )
        return
      }
      if (this.liveSlides.length) {
        this.slidePreviewSource = 'draft'
        this.slideQuality = this.draftSlideQuality
      } else {
        this.slidePreviewSource = 'published'
        this.slideQuality = this.publishedSlideQuality
      }
    },
    async pauseBuild() {
      if (!this.buildTaskId || !this.building) return
      await http.post(`/api/tasks/${this.buildTaskId}/pause`)
      this.buildPaused = true
      this.building = false
      this.buildStreamActive = false
      this.buildStage = 'paused'
    },
    async resumeBuild() {
      if (!this.buildTaskId || !this.courseId) return
      const courseId = this.courseId
      await http.post(`/api/tasks/${this.buildTaskId}/resume`)
      this.buildPaused = false
      this.building = true
      this.buildError = ''
      this.buildFailure = null
      this.buildStage = 'resuming'
      try {
        for (;;) {
          const response = await http.get(`/api/tasks/${this.buildTaskId}`)
          const task = response.data || {}
          this.buildProgress = Math.max(this.buildProgress, Number(task.progress || 0))
          this.buildStage = String(task.phase || task.current_phase || this.buildStage)
          this.buildDisplayStep = advanceSlideBuildStep(
            this.buildDisplayStep,
            this.buildStage,
            this.buildProgress,
          )
          if (task.status === 'completed') {
            await this.load(courseId)
            this.settleCompletedSlideBuild()
            this.buildProgress = 100
            this.buildStage = 'complete'
            this.buildDisplayStep = 9
            return task
          }
          if (task.status === 'failed') {
            this.applyDurableBuildTask(task)
            throw new Error(this.buildError)
          }
          if (task.status === 'paused') {
            this.buildPaused = true
            return task
          }
          await new Promise(resolve => window.setTimeout(resolve, 400))
        }
      } catch (error) {
        const failure = normalizedBuildFailure(error, this.draftSlideQuality || undefined)
        this.buildFailure = failure
        this.buildError = failure.code
        throw error
      } finally {
        this.building = false
      }
    },
    async cancelBuild() {
      if (!this.buildTaskId) return
      // Invalidate the active SSE consumer before deleting the durable task.
      // Otherwise its terminal "task removed" event can race with this action
      // and overwrite the intentional cancelled state with a build error.
      this.buildAttemptToken += 1
      this.buildError = ''
      this.buildFailure = null
      await http.delete(`/api/tasks/${this.buildTaskId}`)
      this.buildTaskId = ''
      this.buildPaused = false
      this.building = false
      this.buildStreamActive = false
      this.buildStage = 'cancelled'
    },
    async ensure(courseId: string) {
      const registry = await this.load(courseId)
      if (!registry || this.courseId !== courseId) return
      if (!this.representations.length) {
        if (this.deferMissingSlideBuild) {
          await this.recoverDurableBuild(courseId)
        } else {
          await this.buildProgressive(courseId)
        }
        return
      }
      const slideRepresentation = this.representations.find(item => item.representation_type === 'slide_deck')
      const slideSpec = (this.registry?.specs || []).find(
        (item: TeachingRepresentationSpec) => item.spec_id === slideRepresentation?.spec_id,
      ) as TeachingRepresentationSpec | undefined
      const content = slideSpec?.payload?.content
      if (
        !this.deferMissingSlideBuild
        && slideRepresentation
        && !['slide_deck_v2', 'slide_deck_v3', 'slide_deck_v4', 'slide_deck_v5'].includes(content?.schema_version)
      ) {
        await this.buildProgressive(courseId)
      }
    },
    async select(representationId: string) {
      this.selectedId = representationId
      await this.loadSpec(representationId)
    },
    async loadSpec(representationId: string) {
      if (!this.courseId || !representationId) return null
      const courseId = this.courseId
      const courseToken = this.courseRequestToken
      const requestToken = ++this.specRequestToken
      const response = await http.get(
        `/api/courses/${courseId}/teaching-representations/${representationId}/spec`,
      )
      if (
        this.courseId !== courseId
        || this.courseRequestToken !== courseToken
        || this.specRequestToken !== requestToken
      ) return null
      const spec = (response.data.spec || null) as TeachingRepresentationSpec | null
      this.selectedSpec = spec
      if (['slide_deck_v2', 'slide_deck_v3', 'slide_deck_v4', 'slide_deck_v5'].includes(spec?.payload?.content?.schema_version)) {
        this.slidePublishedSchema = String(spec?.payload?.content?.schema_version || '')
        this.slideCandidateStatus = String(
          spec?.payload?.content?.candidate_status || this.slideCandidateStatus || '',
        ) as SlideDeckCandidateStatus
        const summary = spec?.payload.content.quality_summary
        if (summary) {
          this.publishedSlideQuality = summary
          if (this.slidePreviewSource === 'published') this.slideQuality = summary
        }
      }
      return spec
    },
    async downloadSlides(
      representationId: string,
      deckTitle?: string,
      theme: SlideDeckTheme = 'qingfeng-classroom',
    ) {
      if (!this.courseId) return
      const response = await http.get(
        `/api/courses/${this.courseId}/teaching-representations/${representationId}/export.pptx`,
        { params: { theme }, responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      const safeTitle = String(deckTitle || this.courseId || '课程课件')
        .replace(/[\\/:*?"<>|]/g, '_')
        .trim()
      anchor.download = `${safeTitle || '课程课件'}.pptx`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 100)
    },
    async previewEdit(
      representationId: string,
      payload: { unit_id: string; field: string; before: unknown; after: unknown; semantic_intent?: boolean },
    ) {
      const response = await http.post(
        `/api/courses/${this.courseId}/teaching-representations/${representationId}/edits/preview`,
        payload,
      )
      return response.data
    },
    async applyEdit(
      representationId: string,
      payload: { unit_id: string; field: string; before: unknown; after: unknown; decision: 'representation_only' | 'course_semantic'; semantic_intent?: boolean },
    ) {
      const response = await http.post(
        `/api/courses/${this.courseId}/teaching-representations/${representationId}/edits/apply`,
        payload,
      )
      if (response.data.registry) {
        this.registry = response.data.registry
        await this.loadSpec(representationId)
      }
      return response.data
    },
  },
})
