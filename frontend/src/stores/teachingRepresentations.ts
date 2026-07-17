import { defineStore } from 'pinia'
import http, { learnerIdentityHeaders, withApiBase } from '../utils/http'

export type RepresentationType = 'outline' | 'lesson_plan' | 'handout' | 'practice_sheet' | 'slide_deck'

export interface TeachingRepresentation {
  representation_id: string
  representation_type: RepresentationType
  spec_id: string
  status: 'planned' | 'building' | 'ready' | 'stale' | 'failed' | 'archived'
  stale_unit_ids: string[]
  stale_reasons: string[]
  revision: string
  updated_at: string
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
    liveSlides: [] as Array<Record<string, any>>,
    buildProgress: 0,
    buildStage: '',
    buildError: '',
    loading: false,
    building: false,
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
    async load(courseId: string) {
      this.loading = true
      this.courseId = courseId
      try {
        const response = await http.get(`/api/courses/${courseId}/teaching-representations`)
        this.registry = response.data.registry
        const available = this.representations
        if (!this.selectedId || !available.some(item => item.representation_id === this.selectedId)) {
          this.selectedId = available[0]?.representation_id || ''
        }
        if (this.selectedId) await this.loadSpec(this.selectedId)
        return this.registry
      } finally {
        this.loading = false
      }
    },
    async build(courseId: string) {
      return this.buildProgressive(courseId)
    },
    async buildProgressive(courseId: string) {
      this.building = true
      this.courseId = courseId
      this.buildProgress = 0
      this.buildStage = 'planning'
      this.buildError = ''
      this.liveSlides = []
      try {
        const response = await fetch(
          withApiBase(`/api/courses/${courseId}/teaching-representations/build/stream`),
          { method: 'POST', headers: learnerIdentityHeaders({ Accept: 'text/event-stream' }) },
        )
        const completedRef: { value?: TeachingRepresentationBuildEvent } = {}
        await consumeTeachingRepresentationStream(response, event => {
          this.buildProgress = Math.max(this.buildProgress, Number(event.progress || 0))
          if (event.stage) this.buildStage = event.stage
          if (event.event === 'deck_plan') this.buildStage = 'slide_plan'
          if (event.event === 'slide_upsert' && event.slide) {
            this.buildStage = 'slide_build'
            const index = this.liveSlides.findIndex(slide => slide.unit_id === event.slide?.unit_id)
            if (index >= 0) this.liveSlides.splice(index, 1, event.slide)
            else this.liveSlides.push(event.slide)
          }
          if (event.event === 'slide_quality' && event.quality) {
            this.buildStage = 'quality'
            this.slideQuality = event.quality
          }
          if (event.event === 'build_blocked') this.buildError = 'quality_gate_failed'
          if (event.event === 'build_complete') completedRef.value = event
          if (
            event.event === 'build_complete'
            && String(event.build?.status || '').startsWith('failed')
          ) {
            this.buildError = 'quality_gate_failed'
          }
          if (event.event === 'error') this.buildError = event.message || 'Teaching representation build failed'
        })
        if (this.buildError) throw new Error(this.buildError)
        const completed = completedRef.value
        if (!completed?.registry) throw new Error('Teaching representation build ended without a registry')
        this.registry = completed.registry
        this.quality = completed.quality || null
        this.buildProgress = 100
        this.buildStage = 'complete'
        const available = this.representations
        if (!this.selectedId || !available.some(item => item.representation_id === this.selectedId)) {
          this.selectedId = available[0]?.representation_id || ''
        }
        if (this.selectedId) await this.loadSpec(this.selectedId)
        return completed
      } catch (error) {
        this.buildError = error instanceof Error ? error.message : String(error)
        throw error
      } finally {
        this.building = false
      }
    },
    async ensure(courseId: string) {
      await this.load(courseId)
      if (!this.representations.length) {
        await this.buildProgressive(courseId)
        return
      }
      const slideRepresentation = this.representations.find(item => item.representation_type === 'slide_deck')
      const slideSpec = (this.registry?.specs || []).find(
        (item: TeachingRepresentationSpec) => item.spec_id === slideRepresentation?.spec_id,
      ) as TeachingRepresentationSpec | undefined
      const content = slideSpec?.payload?.content
      if (slideRepresentation && content?.schema_version !== 'slide_deck_v2') {
        await this.buildProgressive(courseId)
      }
    },
    async select(representationId: string) {
      this.selectedId = representationId
      await this.loadSpec(representationId)
    },
    async loadSpec(representationId: string) {
      if (!this.courseId || !representationId) return null
      const response = await http.get(
        `/api/courses/${this.courseId}/teaching-representations/${representationId}/spec`,
      )
      this.selectedSpec = response.data.spec
      if (this.selectedSpec?.payload?.content?.schema_version === 'slide_deck_v2') {
        const summary = this.selectedSpec.payload.content.quality_summary
        if (summary) this.slideQuality = summary
      }
      return this.selectedSpec
    },
    async downloadSlides(representationId: string, deckTitle?: string) {
      if (!this.courseId) return
      const response = await http.get(
        `/api/courses/${this.courseId}/teaching-representations/${representationId}/export.pptx`,
        { responseType: 'blob' },
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
