import { defineStore } from 'pinia'
import http from '../utils/http'
import type { SlideDeckTheme } from './teachingRepresentations'

export type BuiltinPptTheme = Exclude<SlideDeckTheme, 'qingfeng-classroom' | 'academic-bluegray'>

export interface PptTemplateAsset {
  asset_id: string
  role: string
  filename: string
  mime_type: string
  sha256: string
  size: number
}

export interface PersonalPptTemplatePack {
  pack_id: string
  name: string
  status: 'draft' | 'published'
  base_theme: BuiltinPptTheme
  latest_version: number
  version?: number
  manifest_digest?: string
  extracted_style?: Record<string, any>
  representative_pages?: Array<Record<string, any>>
  preview_slides?: Array<Record<string, any>>
  brand?: Record<string, any>
  compiled_theme?: Record<string, any>
  text_box_styles?: Record<string, any>
  semantic_page_mappings?: Record<string, number>
  assets?: PptTemplateAsset[]
  compile?: { status: string; progress: number; errors: string[] }
}

export interface BuiltinPptTemplatePack {
  pack_id: BuiltinPptTheme
  name: string
  status: 'builtin'
  version: string
  base_theme: BuiltinPptTheme
  preview: string
}

export interface CreatePptTemplateDraftInput {
  name: string
  baseTheme: BuiltinPptTheme
  referencePptx?: File | null
  logo?: File | null
  referenceImages?: File[]
  brand?: Record<string, unknown>
}

export const usePptTemplatePacksStore = defineStore('pptTemplatePacks', {
  state: () => ({
    builtIn: [] as BuiltinPptTemplatePack[],
    personal: [] as PersonalPptTemplatePack[],
    personalTemplatesEnabled: false,
    loading: false,
    saving: false,
    error: '',
    assetUrls: new Map<string, string>(),
  }),
  actions: {
    async load() {
      this.loading = true
      this.error = ''
      try {
        const { data } = await http.get('/api/ppt-template-packs', { silentError: true })
        this.builtIn = Array.isArray(data?.built_in) ? data.built_in : []
        this.personal = Array.isArray(data?.personal) ? data.personal : []
        this.personalTemplatesEnabled = Boolean(data?.personal_templates_enabled)
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    },
    async createDraft(input: CreatePptTemplateDraftInput) {
      this.saving = true
      this.error = ''
      try {
        const form = new FormData()
        form.append('name', input.name)
        form.append('base_theme', input.baseTheme)
        form.append('brand_json', JSON.stringify(input.brand || {}))
        if (input.referencePptx) form.append('reference_pptx', input.referencePptx)
        if (input.logo) form.append('logo', input.logo)
        for (const image of input.referenceImages || []) form.append('reference_images', image)
        const { data } = await http.post('/api/ppt-template-packs/import', form)
        this.personal = [data, ...this.personal.filter(item => item.pack_id !== data.pack_id)]
        return data as PersonalPptTemplatePack
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
        throw error
      } finally {
        this.saving = false
      }
    },
    async updateDraft(packId: string, changes: Record<string, unknown>) {
      const { data } = await http.patch(`/api/ppt-template-packs/${encodeURIComponent(packId)}/draft`, changes)
      this.personal = this.personal.map(item => item.pack_id === packId ? data : item)
      return data as PersonalPptTemplatePack
    },
    async publish(packId: string) {
      this.saving = true
      try {
        const { data } = await http.post(`/api/ppt-template-packs/${encodeURIComponent(packId)}/publish`)
        this.personal = this.personal.map(item => item.pack_id === packId
          ? { ...item, status: 'published', latest_version: data.version, manifest_digest: data.manifest_digest }
          : item)
        return data as PersonalPptTemplatePack
      } finally {
        this.saving = false
      }
    },
    async hide(packId: string) {
      await http.delete(`/api/ppt-template-packs/${encodeURIComponent(packId)}`)
      this.personal = this.personal.filter(item => item.pack_id !== packId)
      this.releasePackAssets(packId)
    },
    async assetUrl(packId: string, assetId: string, version?: number) {
      const key = `${packId}@${version || 'latest'}:${assetId}`
      const cached = this.assetUrls.get(key)
      if (cached) return cached
      const query = version ? `?version=${version}` : ''
      const { data } = await http.get(
        `/api/ppt-template-packs/${encodeURIComponent(packId)}/assets/${encodeURIComponent(assetId)}${query}`,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(data)
      this.assetUrls.set(key, url)
      return url
    },
    releasePackAssets(packId: string) {
      for (const [key, url] of this.assetUrls) {
        if (!key.startsWith(`${packId}@`)) continue
        URL.revokeObjectURL(url)
        this.assetUrls.delete(key)
      }
    },
    releaseAllAssets() {
      for (const url of this.assetUrls.values()) URL.revokeObjectURL(url)
      this.assetUrls.clear()
    },
  },
})
