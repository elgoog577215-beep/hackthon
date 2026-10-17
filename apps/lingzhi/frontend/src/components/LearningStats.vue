<template>
  <div class="learning-overview">
    <div class="overview-tools"><button :disabled="loading" :aria-label="t('courseWorkspace.learningOverview.refresh', '刷新学习概况')" @click="refresh"><RefreshCw :size="17" :class="{ spinning: loading }" /></button><button v-if="closable" :aria-label="t('learningDock.closeStats', '关闭学习概况')" @click="emit('close')"><X :size="18" /></button></div>
    <LearningMatrix :rows="rows" :sections="sections" :course-id="course.currentCourseId" :view-key="`${course.currentCourseId}:${course.currentCourseVersionId}:${getStudyIdentity()?.id || 'preview'}`" :course-title="course.currentCourse?.course_name || ''" :preview="preview" :loading="loading" :error="error"
      @refresh="refresh" @knowledge="emit('openKnowledge', $event)" @lecture="emit('openLecture', $event)" @record="emit('openRecord', $event)" @practice="(node, revision) => emit('openPractice', node, revision)" />
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RefreshCw, X } from 'lucide-vue-next'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore, type LearningAssetItem, type PracticeAttempt } from '../stores/courseWorkspace'
import { useLearnerModelStore } from '../stores/learnerModel'
import { useNoteStore } from '../stores/notes'
import { courseStudyProfile, knowledgeFirstStudyLibrary, type CourseStudyLibrary } from '../utils/knowledge-study'
import { buildLearningMatrix } from '../utils/learning-matrix'
import { isTeacherPreviewCourse } from '../utils/teacher-preview'
import { getStudyIdentity } from '../utils/study-identity'
import http, { teacherRequestConfig } from '../utils/http'
import type { KnowledgeProfile, KnowledgeProfileNode } from '../types/knowledge-profile'
import type { Note } from '../stores/types'
import { t } from '../shared/i18n'
import LearningMatrix from './LearningMatrix.vue'
defineProps<{ closable?: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void; (e: 'selectKnowledge', p: KnowledgeProfileNode | null): void
  (e: 'askKnowledge', p: KnowledgeProfileNode): void; (e: 'discussEvidence', p: KnowledgeProfileNode, evidence: KnowledgeProfileNode['evidence'][number]): void
  (e: 'openLecture', p: KnowledgeProfileNode): void; (e: 'openKnowledge', p: KnowledgeProfileNode): void
  (e: 'openRecord', id: string): void; (e: 'openPractice', nodeId: string, revision: string): void
}>()
const course = useCourseStore(), workspace = useCourseWorkspaceStore(), learner = useLearnerModelStore(), notes = useNoteStore()
const loading = ref(false), error = ref(''), library = ref<CourseStudyLibrary | null>(null), personal = ref<KnowledgeProfile | null>(null)
const attempts = ref<PracticeAttempt[]>([]), questions = ref<LearningAssetItem[]>([])
const savedNotes = ref<Note[]>([])
const preview = computed(() => isTeacherPreviewCourse(course.currentCourseId))
const profile = computed(() => library.value ? courseStudyProfile(library.value, course.currentCourseId, course.currentCourseVersionId, personal.value, preview.value) : personal.value)
const rows = computed(() => buildLearningMatrix({ points: profile.value?.nodes || [], attempts: attempts.value, notes: savedNotes.value, questions: questions.value,
  courseId: course.currentCourseId, version: course.currentCourseVersionId, userId: getStudyIdentity()?.id || learner.model?.user_id, preview: preview.value }))
const sections = computed(() => {
  const ids = new Set(rows.value.flatMap(r => r.point.section_refs))
  return course.nodes.filter(n => ids.has(n.node_id)).map(n => ({ id: n.node_id, name: n.node_name }))
})
let sequence = 0
async function refresh() {
  const id = course.currentCourseId, version = course.currentCourseVersionId, isPreview = preview.value, request = ++sequence
  const current = () => request === sequence && course.currentCourseId === id && course.currentCourseVersionId === version && preview.value === isPreview
  attempts.value = []; questions.value = []; savedNotes.value = []; personal.value = null; library.value = null; error.value = ''
  if (!id) return
  loading.value = true
  try {
    const assets = isPreview ? await workspace.loadPreviewKnowledge(id, true) : (await http.get(`/api/courses/${id}/learning-assets`)).data?.assets
    if (!current()) return
    questions.value = [...(assets?.questions || []), ...(assets?.final_assessment || [])]
    const view = assets?.knowledge_library?.[0]
    library.value = view?.schema_version === 'knowledge_library_view_v3' ? view : null
    if (!assets?.knowledge_tree_authoritative && !library.value?.nodes.some(n => n.node_type === 'knowledge_point' && n.covered_by_course && !['rejected', 'deleted', 'archived'].includes(n.status))) {
      try {
        const source = await http.get(`/api/courses/${id}/knowledge-first`, isPreview ? teacherRequestConfig() : undefined)
        if (!current()) return
        library.value = knowledgeFirstStudyLibrary(source.data, course.nodes.map(n => n.node_id)) || library.value
      } catch { /* Legacy courses can have no adopted knowledge-first tree. */ }
    }
    if (isPreview) return
    const results = await Promise.allSettled([
      learner.load(id), http.get(`/api/courses/${id}/practice/history`, { params: { view: 'all' } }),
      notes.loadCourseRecords(id, { throwOnError: true }),
    ])
    if (!current()) return
    const [model, history] = results
    if (model.status === 'fulfilled') personal.value = model.value?.knowledge_profile || null
    if (history.status === 'fulfilled') attempts.value = history.value.data?.attempts || []
    if (results[2].status === 'fulfilled') savedNotes.value = results[2].value || []
    if (results.some(r => r.status === 'rejected')) error.value = t('learningMatrix.partialError', '部分学习记录读取失败，请重试；未读取不代表没有记录。')
  } catch {
    if (current()) error.value = t('learningMatrix.loadError', '学习矩阵暂时无法读取，请重试。')
  } finally { if (current()) loading.value = false }
}
watch(() => [course.currentCourseId, course.currentCourseVersionId], () => { void refresh() }, { immediate: true })
onBeforeUnmount(() => { sequence++ })
</script>
<style scoped>
.learning-overview{height:100%;overflow:auto;position:relative;padding:24px;background:var(--lz-surface,#fff);color:var(--lz-text);min-width:0}.overview-tools{display:flex;justify-content:flex-end;gap:8px;margin-bottom:4px}.overview-tools button{display:grid;place-items:center;padding:7px;border:1px solid var(--lz-border,#e8e0f0);border-radius:8px;background:var(--lz-surface,#fff);color:var(--lz-text-secondary);cursor:pointer}.overview-tools button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}.spinning{animation:matrix-spin 1s linear infinite}@keyframes matrix-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.spinning{animation:none}}@media(max-width:600px){.learning-overview{padding:14px}}
</style>
