import { defineStore } from 'pinia'
import http, { learnerIdentityHeaders, withApiBase } from '../utils/http'

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

export interface SlideDeckBuildOptions {
  mode: SlideDeckMode
  theme: Exclude<SlideDeckTheme, 'qingfeng-classroom' | 'academic-bluegray'>
  forceRebuild?: boolean
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

export interface TeachingRepresentationBuildEvent {
  event: string
  progress?: number
  stage?: string
  message?: string
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
}

export async function consumeTeachingRepresentationStream(
  response: Response,
  onEvent: (event: TeachingRepresentationBuildEvent) => void,
) {
  if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`)
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
    liveSlides: [] as Array<Record<string, any>>,
    buildProgress: 0,
    buildStage: '',
    buildError: '',
    buildTaskId: '',
    buildPaused: false,
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
      this.liveSlides = []
      this.buildProgress = 0
      this.buildStage = ''
      this.buildError = ''
      this.buildTaskId = ''
      this.buildPaused = false
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
      this.buildError = ''
      this.buildPaused = false
      this.liveSlides = []
      this.draftSlideQuality = null
      this.slidePreviewSource = 'published'
      this.slideQuality = this.publishedSlideQuality
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
              }),
            } : {}),
          },
        )
        const completedRef: { value?: TeachingRepresentationBuildEvent } = {}
        await consumeTeachingRepresentationStream(response, event => {
          if (!isCurrentAttempt()) return
          if (event.task_id) this.buildTaskId = event.task_id
          this.buildProgress = Math.max(this.buildProgress, Number(event.progress || 0))
          if (event.stage) this.buildStage = event.stage
          if (event.event === 'story_plan') this.buildStage = 'story_plan'
          if (event.event === 'chapter_plan') this.buildStage = 'chapter_plan'
          if (event.event === 'episode_progress') this.buildStage = 'episode_progress'
          if (event.event === 'layout_plan') this.buildStage = 'layout_plan'
          if (event.event === 'deck_plan') this.buildStage = 'slide_plan'
          if (event.event === 'visual_plan') this.buildStage = 'visual_plan'
          if (event.event === 'asset_progress' || event.event === 'asset_ready') {
            this.buildStage = 'asset_compilation'
          }
          if (event.event === 'slide_upsert' && event.slide) {
            this.buildStage = 'slide_build'
            if (this.slidePreviewSource !== 'draft') {
              this.slidePreviewSource = 'draft'
              this.slideQuality = this.draftSlideQuality
            }
            const index = this.liveSlides.findIndex(slide => slide.unit_id === event.slide?.unit_id)
            if (index >= 0) this.liveSlides.splice(index, 1, event.slide)
            else this.liveSlides.push(event.slide)
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
          if (event.event === 'repair_progress') this.buildStage = 'repair_progress'
          if (event.event === 'build_blocked') {
            this.settleFailedSlideDraft(event.quality)
            this.buildError = 'quality_gate_failed'
          }
          if (event.event === 'build_complete') completedRef.value = event
          if (
            event.event === 'build_complete'
            && String(event.build?.status || '').startsWith('failed')
          ) {
            this.settleFailedSlideDraft(event.quality)
            this.buildError = 'quality_gate_failed'
          }
          if (event.event === 'error') this.buildError = event.message || 'Teaching representation build failed'
          if (event.event === 'paused') this.buildPaused = true
        })
        if (!isCurrentAttempt()) return completedRef.value
        if (this.buildPaused) return completedRef.value
        if (this.buildError) throw new Error(this.buildError)
        const completed = completedRef.value
        if (!completed?.registry) throw new Error('Teaching representation build ended without a registry')
        this.registry = completed.registry
        this.quality = completed.quality || null
        this.slidePreviewSource = 'published'
        this.publishedSlideQuality = completed.quality || this.draftSlideQuality
        this.draftSlideQuality = null
        this.slideQuality = this.publishedSlideQuality
        this.buildProgress = 100
        this.buildStage = 'complete'
        const available = this.representations
        const requestedVariant = options ? `${options.mode}:${options.theme}` : ''
        const requestedRepresentation = requestedVariant
          ? available.find(item => item.representation_type === 'slide_deck' && item.variant_key === requestedVariant)
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
          this.buildError = error instanceof Error ? error.message : String(error)
        }
        throw error
      } finally {
        if (isCurrentAttempt()) this.building = false
      }
    },
    async buildSlideDeckVariant(courseId: string, options: SlideDeckBuildOptions) {
      return this.buildProgressive(courseId, options)
    },
    settleFailedSlideDraft(quality?: Record<string, any>) {
      if (quality) this.draftSlideQuality = quality
      const publishedContent = this.selectedSpec?.payload?.content
      const hasPublishedDeck = (
        this.selectedRepresentation?.status === 'ready'
        && ['slide_deck_v2', 'slide_deck_v3', 'slide_deck_v4'].includes(publishedContent?.schema_version)
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
      this.liveSlides = this.liveSlides.slice(0, 5)
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
      this.buildStage = 'paused'
    },
    async resumeBuild() {
      if (!this.buildTaskId || !this.courseId) return
      const courseId = this.courseId
      await http.post(`/api/tasks/${this.buildTaskId}/resume`)
      this.buildPaused = false
      this.building = true
      this.buildError = ''
      this.buildStage = 'resuming'
      try {
        for (;;) {
          const response = await http.get(`/api/tasks/${this.buildTaskId}`)
          const task = response.data || {}
          this.buildProgress = Math.max(this.buildProgress, Number(task.progress || 0))
          this.buildStage = String(task.phase || task.current_phase || this.buildStage)
          if (task.status === 'completed') {
            await this.load(courseId)
            this.buildProgress = 100
            this.buildStage = 'complete'
            return task
          }
          if (task.status === 'failed') throw new Error(task.error || 'Teaching representation build failed')
          if (task.status === 'paused') {
            this.buildPaused = true
            return task
          }
          await new Promise(resolve => window.setTimeout(resolve, 400))
        }
      } catch (error) {
        this.buildError = error instanceof Error ? error.message : String(error)
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
      await http.delete(`/api/tasks/${this.buildTaskId}`)
      this.buildTaskId = ''
      this.buildPaused = false
      this.building = false
      this.buildStage = 'cancelled'
    },
    async ensure(courseId: string) {
      const registry = await this.load(courseId)
      if (!registry || this.courseId !== courseId) return
      if (!this.representations.length && !this.deferMissingSlideBuild) {
        await this.buildProgressive(courseId)
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
        && !['slide_deck_v2', 'slide_deck_v3', 'slide_deck_v4'].includes(content?.schema_version)
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
      if (['slide_deck_v2', 'slide_deck_v3', 'slide_deck_v4'].includes(spec?.payload?.content?.schema_version)) {
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
