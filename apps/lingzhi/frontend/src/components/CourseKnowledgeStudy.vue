<template>
  <section class="course-knowledge-study">
    <header v-show="!selectedId" class="study-header"><div><h2>{{ t('courseKnowledgeStudy.title') }}</h2><p>{{ courseTitle }}</p></div><div><button :disabled="loading" :aria-label="t('courseKnowledgeStudy.refresh')" @click="load"><RefreshCw :size="17" /></button><button class="return-reading" @click="emit('close')"><ArrowLeft :size="16" />{{ t('courseKnowledgeStudy.returnReading') }}</button></div></header>
    <p v-if="preview && !selectedId" class="study-notice">{{ t('courseKnowledgeStudy.preview') }}</p>
    <p v-else-if="personalError && !selectedId" class="study-notice" role="status">{{ t('courseKnowledgeStudy.personalUnavailable') }}</p>
    <div v-if="loading" class="study-state" role="status">{{ t('knowledgeLibrary.loading') }}</div>
    <div v-else-if="error" class="study-state" role="alert"><p>{{ error }}</p><button @click="load">{{ t('knowledgeLibrary.retry') }}</button></div>
    <div v-else-if="profile?.availability !== 'ready'" class="study-state"><p>{{ t('courseKnowledgeStudy.empty') }}</p></div>
    <KnowledgeMasteryProfile v-else ref="profileRef" knowledge-only :profile="profile" :course-title="courseTitle" :learning-content="content" :practice-ids="practiceIds"
      @select="selectPoint" @evidence="(point, evidence) => emit('evidence', point, evidence)" @lecture="emit('lecture', $event)" @practice="practice" />
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowLeft, RefreshCw } from 'lucide-vue-next'
import KnowledgeMasteryProfile from './KnowledgeMasteryProfile.vue'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useLearnerModelStore } from '../stores/learnerModel'
import { courseStudyProfile, knowledgeFirstStudyLibrary, knowledgeFirstStudyExamples, type CourseStudyLibrary } from '../utils/knowledge-study'
import type { KnowledgeProfile, KnowledgeProfileNode } from '../types/knowledge-profile'
import http, { teacherRequestConfig } from '../utils/http'
import { t } from '../shared/i18n'

type StudyQuestion = { asset_id?:string; question_id?:string; node_id?:string; task_revision_id?:string; revision_id?:string; concept_ids?:string[]; primary_knowledge_ids?:string[]; knowledge_revision_refs?:Record<string,string> }
const props=defineProps<{ visible:boolean; preview:boolean }>()
const emit=defineEmits<{ (e:'select',point:KnowledgeProfileNode|null):void; (e:'close'):void; (e:'lecture',point:KnowledgeProfileNode):void; (e:'evidence',point:KnowledgeProfileNode,evidence:KnowledgeProfileNode['evidence'][number]):void; (e:'practice',nodeId:string,revision:string):void }>()
const course=useCourseStore(), workspace=useCourseWorkspaceStore(), learner=useLearnerModelStore()
const profileRef=ref<InstanceType<typeof KnowledgeMasteryProfile>|null>(null)
const library=ref<CourseStudyLibrary|null>(null), personal=ref<KnowledgeProfile|null>(null)
const examples=ref<Record<string,{example:string;exampleMarkdown:true}>>({})
const sourceTitle=ref('')
const courseTitle=computed(()=>course.currentCourse?.course_name || sourceTitle.value)
const questions=ref<StudyQuestion[]>([]), selectedId=ref(''), loading=ref(false), error=ref(''), personalError=ref(false)
let request=0
const profile=computed(()=>library.value ? courseStudyProfile(library.value,course.currentCourseId,course.currentCourseVersionId,personal.value,props.preview):null)
const content=computed(()=>Object.fromEntries((library.value?.nodes || []).map(n=>[n.knowledge_id,{
  rule:n.statement || n.description,
  ...examples.value[n.knowledge_id],
  ...(n.counterexamples?.length ? { example:n.counterexamples[0],exampleTitle:t('courseKnowledgeStudy.counterexample') } : {}),
}])))
function questionFor(id:string) {
  const node=library.value?.nodes.find(n=>n.knowledge_id===id)
  return questions.value.find(q=>node && (node.question_ids?.some(key=>key===q.asset_id || key===q.question_id) || ((q.primary_knowledge_ids || q.concept_ids || []).length===1 && (q.primary_knowledge_ids || q.concept_ids || []).includes(id) && q.knowledge_revision_refs?.[id]===node.revision_id))
    && Boolean(q.task_revision_id || q.revision_id) && course.nodes.some(n=>n.node_id===(q.node_id || node.section_ids[0])))
}
const practiceIds=computed(()=>profile.value?.nodes.filter(n=>questionFor(n.knowledge_id)).map(n=>n.knowledge_id) || [])
function practice(point:KnowledgeProfileNode) { const q=questionFor(point.knowledge_id); if(q) emit('practice',q.node_id || point.section_refs[0] || '',q.task_revision_id || q.revision_id || '') }
function selectPoint(point:KnowledgeProfileNode|null) { selectedId.value=point?.knowledge_id || ''; emit('select',point) }
function closePoint() { profileRef.value?.closePoint() }
async function load() {
  const id=course.currentCourseId, version=course.currentCourseVersionId, preview=props.preview, token=++request
  sourceTitle.value=''; library.value=null; personal.value=null; questions.value=[]; examples.value={}; closePoint(); selectedId.value=''; error.value=''; personalError.value=false
  if(!id || !props.visible) return
  loading.value=true
  const current=()=>token===request && course.currentCourseId===id && course.currentCourseVersionId===version && props.preview===preview
  try {
    const assets=preview ? await workspace.loadPreviewKnowledge(id, true) : (await http.get(`/api/courses/${id}/learning-assets`)).data?.assets
    if(!current()) return
    const view=assets?.knowledge_library?.[0]
    library.value=view?.schema_version==='knowledge_library_view_v3' ? view : null
    sourceTitle.value=library.value?.nodes.find(n=>n.node_type==='course')?.name || ''
    questions.value=assets?.questions || []
    if(!assets?.knowledge_tree_authoritative && !library.value?.nodes.some(n=>n.node_type==='knowledge_point' && n.covered_by_course && !['rejected','deleted','archived'].includes(n.status))) {
      // Knowledge-first courses own an adopted tree before the legacy asset view is available.
      try {
        const response=await http.get(`/api/courses/${id}/knowledge-first`,preview ? teacherRequestConfig() : undefined)
        if(!current()) return
        // Preview documents have a derived revision; knowledge is bound by its own adopted revision.
        const adopted=knowledgeFirstStudyLibrary(response.data,course.nodes.map(n=>n.node_id))
        if(adopted) { sourceTitle.value=String(response.data.title || ''); library.value=adopted; examples.value=knowledgeFirstStudyExamples(response.data,adopted) }
      } catch { /* A legacy course can legitimately have no knowledge-first source. */ }
    }
    if(!library.value) throw new Error(t('knowledgeProfile.noTreeHint'))
    if(!preview) {
      try { const model=await learner.load(id); if(current()) personal.value=model?.knowledge_profile || null }
      catch { if(current()) personalError.value=true }
    }
  } catch { if(current()) error.value=t('knowledgeLibrary.loadFailed') }
  finally { if(current()) loading.value=false }
}
watch(()=>[course.currentCourseId,course.currentCourseVersionId,props.preview,props.visible],()=>{ void load() },{immediate:true})
watch(()=>[profile.value,course.focusKnowledgeId,loading.value] as const,async ([current,id,busy])=>{
  if(busy || !props.visible || !id || !current?.nodes.some(n=>n.knowledge_id===id)) return
  await nextTick()
  if(course.focusKnowledgeId!==id || !props.visible) return
  await profileRef.value?.openPoint(id)
  course.focusKnowledgeId=''
})
watch(()=>learner.model,model=>{ if(!props.preview && learner.courseId===course.currentCourseId) personal.value=model?.knowledge_profile || null })
onBeforeUnmount(()=>{ request++ })
defineExpose({ closePoint, refresh:load })
</script>
<style scoped>
.course-knowledge-study { min-width:0; height:100%; overflow:auto; color:#49365e; background:#fff; }.study-header { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:24px 24px 12px; }.study-header h2 { font-size:23px; margin:0 0 7px; }.study-header p { color:#93819f; font-size:13px; margin:0; }.study-header>div:last-child { display:flex; gap:8px; }.study-header button { display:grid; place-items:center; padding:8px; border:1px solid #e8def0; border-radius:8px; background:#fff; color:#86659e; cursor:pointer; }.study-notice { margin:8px 24px; padding:10px 14px; border-radius:8px; background:#f5f1fb; color:#8c749f; font-size:13px; line-height:1.7; }.study-state { padding:45px 24px; color:#8a729c; text-align:center; }.study-state button { padding:8px 16px; border:1px solid #ddcee9; border-radius:8px; color:#765591; background:#fff; cursor:pointer; }
</style>

<style scoped>
.study-header button.return-reading { display:flex; gap:6px; white-space:nowrap; padding:8px 11px; font-size:14px; }.study-header>div:first-child { min-width:0; }.study-header>div:last-child { flex:none; }
</style>
