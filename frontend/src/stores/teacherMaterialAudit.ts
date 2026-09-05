import { defineStore } from 'pinia'
import http, { teacherRequestConfig } from '../utils/http'

export type MaterialDocumentType = 'outline' | 'lesson_plan' | 'script' | 'ppt' | 'question_bank' | 'school_material' | 'other'
export type MaterialAbsorptionAction = 'absorb' | 'reference_only' | 'ignore'
export type MaterialSourceRole = 'primary' | 'reference' | 'candidate'

export interface MaterialAuditSource {
  asset_id: string
  filename: string
  relative_path: string
  action: MaterialAbsorptionAction
  role: MaterialSourceRole
  version_role: 'current' | 'older' | 'reference' | 'unknown'
  parse_status?: 'parsed' | 'degraded' | 'failed' | 'metadata_only' | 'unknown'
  parse_quality?: Record<string, number | boolean | string>
  parse_warnings?: string[]
}

export interface MaterialAuditIssue {
  code: string
  message: string
  target_id?: string
  target_label?: string
  asset_id?: string
  filename?: string
}

export interface StructuredMaterialBlock {
  block_id: string
  kind: string
  text: string
  source?: {
    asset_id: string
    document_id: string
    source_block_id: string
    role: string
    locator: { page?: number; slide?: number; section_path?: string[] }
  }
}

export interface StructuredMaterialSection {
  section_id: string
  title: string
  source_asset_id: string
  source_role: string
  blocks: StructuredMaterialBlock[]
}

export interface MaterialAuditTarget {
  target_id: string
  target_type: 'outline' | 'lesson_plan' | 'script' | 'ppt'
  target_scope_id: string
  target_scope_label: string
  title: string
  status: 'ready' | 'needs_decision'
  sources: MaterialAuditSource[]
  issues: MaterialAuditIssue[]
  review_items?: MaterialAuditIssue[]
  structured_draft?: {
    schema_version: string
    title: string
    sections: StructuredMaterialSection[]
    source_documents?: Array<{
      asset_id: string
      filename: string
      role: string
      parse_status: string
      parse_warnings?: string[]
    }>
  }
}

export interface MaterialAbsorptionPlan {
  schema_version: string
  plan_id: string
  status: 'ready' | 'needs_decision' | 'stale' | 'partially_executed' | 'executed'
  targets: MaterialAuditTarget[]
  unresolved_items: MaterialAuditIssue[]
  scope_options: Array<{ scope_id: string; label: string }>
  summary: {
    target_count: number
    working_draft_count: number
    unresolved_count: number
    source_count: number
  }
  execution?: {
    receipts?: Array<{
      bundle_id: string
      plan_id: string
      target_ids?: string[]
      status: string
      executed_at: string
    }>
  }
}

export interface MaterialAuditAsset {
  asset_id: string
  filename: string
  relative_path: string
  document_type: MaterialDocumentType
  version_role?: 'current' | 'older' | 'reference' | 'unknown'
  parse_status?: string
  parse_quality?: Record<string, number | boolean | string>
  parse_warnings?: string[]
  parse_error?: string
  structure_matches?: Array<{ node_id: string; title?: string }>
  absorption_decision?: {
    action?: MaterialAbsorptionAction
    role?: 'primary' | 'reference'
    target_scope_id?: string
  }
}

export interface MaterialAuditPackage {
  package_id: string
  course_id: string
  course_name?: string
  assets: MaterialAuditAsset[]
  asset_count: number
  material_absorption?: MaterialAbsorptionPlan
}

function errorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  return String(detail?.message || detail || error?.message || fallback)
}

export const useTeacherMaterialAuditStore = defineStore('teacher-material-audit', {
  state: () => ({
    courseId: '',
    requestSequence: 0,
    coursePackage: null as MaterialAuditPackage | null,
    loading: false,
    refreshing: false,
    executing: false,
    updatingAssetIds: [] as string[],
    error: '',
  }),
  getters: {
    plan: state => state.coursePackage?.material_absorption || null,
  },
  actions: {
    async load(courseId: string) {
      if (this.courseId !== courseId) { this.coursePackage = null; this.refreshing = false; this.executing = false; this.updatingAssetIds = [] }
      this.courseId = courseId
      const sequence = ++this.requestSequence
      this.loading = true
      this.error = ''
      try {
        const payload = (await http.get<MaterialAuditPackage[]>(
          '/api/teacher-course-spaces',
          teacherRequestConfig({ params: { course_id: courseId }, silentError: true }),
        )).data
        if (this.courseId !== courseId || sequence !== this.requestSequence) return null
        const packages = Array.isArray(payload) ? payload : []
        const summary = packages.find(item => String(item.course_id || '') === courseId)
        if (!summary) {
          this.coursePackage = null
          return null
        }
        const loaded = (await http.get<MaterialAuditPackage>(
          `/api/teacher-course-spaces/${summary.package_id}`,
          teacherRequestConfig({ silentError: true }),
        )).data
        if (this.courseId !== courseId || sequence !== this.requestSequence) return null
        this.coursePackage = loaded
        if (
          Array.isArray(this.coursePackage.assets) && this.coursePackage.assets.length
          && !this.coursePackage.material_absorption?.plan_id
        ) await this.refresh()
        return this.coursePackage
      } catch (error) {
        if (this.courseId === courseId && sequence === this.requestSequence) this.error = errorMessage(error, '材料审计读取失败')
        return null
      } finally {
        if (this.courseId === courseId) this.loading = false
      }
    },
    async refresh() {
      if (!this.coursePackage) return null
      const courseId = this.courseId
      const packageId = this.coursePackage.package_id
      const sequence = ++this.requestSequence
      this.refreshing = true
      this.error = ''
      try {
        const response = await http.post<{ package: MaterialAuditPackage }>(
          `/api/teacher-course-spaces/${packageId}/material-absorption/refresh`,
          {},
          teacherRequestConfig(),
        )
        if (this.courseId !== courseId || sequence !== this.requestSequence) return null
        this.coursePackage = response.data.package
        return this.coursePackage.material_absorption || null
      } catch (error) {
        if (this.courseId === courseId && sequence === this.requestSequence) this.error = errorMessage(error, '材料审计更新失败')
        throw error
      } finally {
        if (this.courseId === courseId) this.refreshing = false
      }
    },
    async updateDecision(
      assetId: string,
      decision: {
        action?: MaterialAbsorptionAction
        role?: 'primary' | 'reference'
        target_scope_id?: string
        version_role?: 'current' | 'older' | 'reference' | 'unknown'
      },
    ) {
      if (!this.coursePackage) return null
      const courseId = this.courseId
      const packageId = this.coursePackage.package_id
      const sequence = ++this.requestSequence
      this.updatingAssetIds = [...new Set([...this.updatingAssetIds, assetId])]
      this.error = ''
      try {
        const response = await http.patch<{ package: MaterialAuditPackage }>(
          `/api/teacher-course-spaces/${packageId}/assets/${assetId}/absorption`,
          decision,
          teacherRequestConfig(),
        )
        if (this.courseId !== courseId || sequence !== this.requestSequence) return null
        this.coursePackage = response.data.package
        return this.coursePackage.material_absorption || null
      } catch (error) {
        if (this.courseId === courseId && sequence === this.requestSequence) this.error = errorMessage(error, '材料审计选择保存失败')
        throw error
      } finally {
        if (this.courseId === courseId) this.updatingAssetIds = this.updatingAssetIds.filter(item => item !== assetId)
      }
    },
    async updateDocumentType(assetId: string, documentType: MaterialDocumentType) {
      if (!this.coursePackage) return null
      const courseId = this.courseId
      const packageId = this.coursePackage.package_id
      const sequence = ++this.requestSequence
      this.updatingAssetIds = [...new Set([...this.updatingAssetIds, assetId])]
      this.error = ''
      try {
        const updated = (await http.patch<MaterialAuditAsset>(
          `/api/teacher-course-spaces/${packageId}/assets/${assetId}`,
          { document_type: documentType },
          teacherRequestConfig(),
        )).data
        if (this.courseId !== courseId || sequence !== this.requestSequence || !this.coursePackage) return null
        this.coursePackage.assets = this.coursePackage.assets.map(asset => asset.asset_id === assetId ? { ...asset, ...updated } : asset)
        await this.refresh()
        return this.coursePackage.material_absorption || null
      } catch (error) {
        if (this.courseId === courseId && sequence === this.requestSequence) this.error = errorMessage(error, '材料类型保存失败')
        throw error
      } finally {
        if (this.courseId === courseId) this.updatingAssetIds = this.updatingAssetIds.filter(item => item !== assetId)
      }
    },
    async execute(targetIds: string[] = []) {
      if (!this.coursePackage) return null
      const courseId = this.courseId
      const packageId = this.coursePackage.package_id
      const sequence = ++this.requestSequence
      this.executing = true
      this.error = ''
      try {
        const response = await http.post<{
          package: MaterialAuditPackage
          receipt: Record<string, any>
          authoring_receipt: Record<string, any>
        }>(
          `/api/teacher-course-spaces/${packageId}/material-absorption/execute`,
          { target_ids: targetIds },
          teacherRequestConfig(),
        )
        if (this.courseId !== courseId || sequence !== this.requestSequence) return null
        this.coursePackage = response.data.package
        return response.data
      } catch (error) {
        if (this.courseId === courseId && sequence === this.requestSequence) this.error = errorMessage(error, '结构化工作稿生成失败')
        throw error
      } finally {
        if (this.courseId === courseId) this.executing = false
      }
    },
  },
})
