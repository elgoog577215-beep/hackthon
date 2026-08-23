import { defineStore } from 'pinia'
import http, { getTeacherIdentity } from '../utils/http'

export type TeacherLessonJobStatus = 'pending' | 'running' | 'completed' | 'completed_with_warnings' | 'failed'

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

export interface TeacherLessonScriptState {
  current_revision_id: string
  confirmed_revision_id: string
  source_lesson_plan_revision_id: string
  source_state: 'current' | 'stale'
  ready: boolean
  confirmed: boolean
  confirmed_at: string
  sections: Array<{
    section_node_id: string
    title: string
    content: string
  }>
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
  engine?: 'slide_deck_v6'
  working_v6_revision_id?: string
  working_representation_id?: string
  synthetic_course_id?: string
  v6_revisions?: Array<{
    revision_id: string
    engine: 'slide_deck_v6'
    synthetic_course_id: string
    representation_id: string
    spec_id: string
    source_lesson_plan_revision_id: string
    source_script_revision_id: string
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
    error: '',
  }),
  getters: {
    lessonById: state => (lessonUnitId: string) => state.lessons.find(item => item.lesson_unit_id === lessonUnitId),
    activeJobByLesson: state => (lessonUnitId: string) => state.jobs.find(item => (
      item.lesson_unit_id === lessonUnitId
      && ['pending', 'running'].includes(item.status)
    )),
    latestJobByLesson: state => (lessonUnitId: string) => [...state.jobs]
      .reverse()
      .find(item => item.lesson_unit_id === lessonUnitId),
  },
  actions: {
    async load(courseId: string) {
      if (this.courseId !== courseId) {
        this.courseId = courseId
        this.outlineRevisionId = ''
        this.lessons = []
        this.jobs = []
      }
      this.loading = true
      this.error = ''
      try {
        const response = await http.get<TeacherLessonAuthoringView>(
          `/api/teacher/courses/${courseId}/lesson-authoring`,
          requestConfig(),
        )
        this.courseId = courseId
        this.outlineRevisionId = response.data.outline_revision_id
        this.lessons = response.data.lessons
        this.jobs = response.data.jobs
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
    ) {
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.post<{ job: TeacherLessonJob }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/plan/generate`,
          {
            request_id: crypto.randomUUID(),
            source_package_id: source?.packageId || '',
            source_asset_id: source?.assetId || '',
            requirements,
            material_asset_ids: Array.from(new Set(materialAssetIds.filter(Boolean))),
          },
          requestConfig(),
        )
        const job = response.data.job
        this.jobs = [...this.jobs.filter(item => item.id !== job.id), job]
        void this.pollJob(courseId, job.id)
        return job
      } catch (error) {
        this.error = errorMessage(error, '本讲教案生成失败')
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
        if (['completed', 'completed_with_warnings', 'failed'].includes(job.status)) {
          await this.load(courseId)
          return job
        }
        await new Promise(resolve => setTimeout(resolve, 1500))
      }
      return this.jobs.find(item => item.id === jobId)
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
    ) {
      this.actionLessonId = lessonUnitId
      this.error = ''
      try {
        const response = await http.post<{ lesson: TeacherLessonProjection }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/generate`,
          { requirements, material_asset_ids: materialAssetIds },
          requestConfig(),
        )
        const index = this.lessons.findIndex(item => item.lesson_unit_id === lessonUnitId)
        if (index >= 0) this.lessons[index] = response.data.lesson
        return response.data.lesson
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
    ) {
      this.error = ''
      try {
        const response = await http.post<{
          base_revision_id: string
          section_node_id: string
          replacement_text: string
        }>(
          `/api/teacher/courses/${courseId}/lessons/${lessonUnitId}/script/rewrite-candidate`,
          {
            base_revision_id: baseRevisionId,
            section_node_id: sectionNodeId,
            instruction,
          },
          requestConfig(),
        )
        return response.data
      } catch (error) {
        this.error = errorMessage(error, 'AI 优化讲稿失败')
        throw error
      }
    },
    async createAiCandidate(
      courseId: string,
      lessonUnitId: string,
      baseRevisionId: string,
      instruction: string,
      sectionNodeId = '',
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
