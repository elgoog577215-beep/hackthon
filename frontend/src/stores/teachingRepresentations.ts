import { defineStore } from 'pinia'
import http from '../utils/http'

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

export const useTeachingRepresentationsStore = defineStore('teachingRepresentations', {
  state: () => ({
    courseId: '',
    registry: null as Record<string, any> | null,
    selectedId: '',
    selectedSpec: null as TeachingRepresentationSpec | null,
    quality: null as Record<string, any> | null,
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
      this.building = true
      this.courseId = courseId
      try {
        const response = await http.post(`/api/courses/${courseId}/teaching-representations/build`)
        this.registry = response.data.registry
        this.quality = response.data.quality
        const available = this.representations
        if (!this.selectedId || !available.some(item => item.representation_id === this.selectedId)) {
          this.selectedId = available[0]?.representation_id || ''
        }
        if (this.selectedId) await this.loadSpec(this.selectedId)
        return response.data
      } finally {
        this.building = false
      }
    },
    async ensure(courseId: string) {
      await this.load(courseId)
      if (!this.representations.length) await this.build(courseId)
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
      return this.selectedSpec
    },
    async downloadSlides(representationId: string) {
      if (!this.courseId) return
      const response = await http.get(
        `/api/courses/${this.courseId}/teaching-representations/${representationId}/export.pptx`,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${this.courseId}-slides.pptx`
      anchor.click()
      URL.revokeObjectURL(url)
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
