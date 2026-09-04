import { defineStore } from 'pinia'
import http, { getTeacherIdentity, teacherReadRequestConfig } from '../utils/http'

export type ScriptVisualType = 'diagram' | 'image' | 'animation'
export type ScriptVisualStatus = 'candidate' | 'accepted' | 'stale' | 'failed'

export interface ScriptVisualItem {
  representation_id: string
  representation_type: ScriptVisualType
  status: ScriptVisualStatus
  revision: string
  source: {
    lesson_unit_id: string
    script_revision_id: string
    section_node_id: string
    block_id: string
    block_content_fingerprint: string
    title: string
  }
  content: Record<string, any>
  artifact_ids: string[]
  stale_reasons: string[]
  created_at: string
  updated_at: string
}

export interface ScriptVisualRecommendation {
  block_id: string
  recommended_types: ScriptVisualType[]
  reason: string
  reason_code?: 'process_or_change' | 'concept_or_relation' | 'dense_content' | ''
}

export interface ScriptVisualView {
  schema_version: 'teacher_script_visual_view_v1'
  course_id: string
  lesson_unit_id: string
  script_revision_id: string
  recommendations: ScriptVisualRecommendation[]
  items: ScriptVisualItem[]
  representation_sets: Array<Record<string, any>>
}

const requestConfig = () => ({ headers: { 'X-User-Id': getTeacherIdentity() } })
const inflight = new Map<string, Promise<ScriptVisualView>>()

function scopeKey(courseId: string, lessonUnitId: string) {
  return `${courseId}\u0000${lessonUnitId}`
}

export const useTeacherScriptVisualStore = defineStore('teacher-script-visuals', {
  state: () => ({
    views: {} as Record<string, ScriptVisualView>,
    loading: {} as Record<string, boolean>,
    errors: {} as Record<string, string>,
    assetUrls: {} as Record<string, string>,
  }),
  actions: {
    view(courseId: string, lessonUnitId: string) {
      return this.views[scopeKey(courseId, lessonUnitId)]
    },
    async load(courseId: string, lessonUnitId: string, force = false) {
      const key = scopeKey(courseId, lessonUnitId)
      if (!force && this.views[key]) return this.views[key]
      if (inflight.has(key)) return inflight.get(key)!
      this.loading[key] = true
      this.errors[key] = ''
      const request = http.get<ScriptVisualView>(
        `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/visuals`,
        { ...teacherReadRequestConfig({ headers: { 'X-User-Id': getTeacherIdentity() } }), silentError: true },
      ).then(response => {
        this.views[key] = response.data
        return response.data
      }).catch((error: any) => {
        const detail = error?.response?.data?.detail
        this.errors[key] = String(detail?.message || detail || error?.message || 'visual_load_failed')
        throw error
      }).finally(() => {
        this.loading[key] = false
        if (inflight.get(key) === request) inflight.delete(key)
      })
      inflight.set(key, request)
      return request
    },
    async create(
      courseId: string,
      lessonUnitId: string,
      scriptRevisionId: string,
      sectionNodeId: string,
      blockId: string,
      expressionType: ScriptVisualType,
      instruction = '',
    ) {
      const response = await http.post<{ item: ScriptVisualItem }>(
        `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/visuals`,
        {
          script_revision_id: scriptRevisionId,
          section_node_id: sectionNodeId,
          block_id: blockId,
          expression_type: expressionType,
          instruction,
        },
        requestConfig(),
      )
      const key = scopeKey(courseId, lessonUnitId)
      const current = this.views[key]
      if (current) {
        current.items = current.items.filter(item => !(
          item.status === 'candidate'
          && item.source.block_id === blockId
          && item.representation_type === expressionType
        ))
        current.items.push(response.data.item)
      }
      return response.data.item
    },
    async resolve(
      courseId: string,
      lessonUnitId: string,
      scriptRevisionId: string,
      representationId: string,
      accept: boolean,
    ) {
      const response = await http.post<{ item: ScriptVisualItem }>(
        `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/visuals/${representationId}/resolve`,
        { script_revision_id: scriptRevisionId, accept },
        requestConfig(),
      )
      const key = scopeKey(courseId, lessonUnitId)
      const current = this.views[key]
      if (current) {
        const resolved = response.data.item
        current.items = current.items.filter(item => {
          if (item.representation_id === representationId) return false
          if (
            resolved.status === 'accepted'
            && item.status === 'accepted'
            && item.source.block_id === resolved.source.block_id
            && item.representation_type === resolved.representation_type
          ) return false
          return true
        })
        if (resolved.status === 'accepted') current.items.push(resolved)
      }
      return response.data.item
    },
    async imageUrl(courseId: string, item: ScriptVisualItem) {
      const assetId = item.artifact_ids[0]
      if (!assetId) return ''
      const cacheKey = `${item.representation_id}\u0000${assetId}`
      if (this.assetUrls[cacheKey]) return this.assetUrls[cacheKey]
      const response = await http.get<Blob>(
        `/api/courses/${courseId}/teaching-representations/${item.representation_id}/assets/${assetId}`,
        {
          ...teacherReadRequestConfig({ headers: { 'X-User-Id': getTeacherIdentity() } }),
          responseType: 'blob',
          silentError: true,
        },
      )
      const url = URL.createObjectURL(response.data)
      this.assetUrls[cacheKey] = url
      return url
    },
    releaseAssets() {
      Object.values(this.assetUrls).forEach(url => URL.revokeObjectURL(url))
      this.assetUrls = {}
    },
  },
})
