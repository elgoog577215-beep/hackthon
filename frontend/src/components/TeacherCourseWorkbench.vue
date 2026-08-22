<template>
  <section class="teacher-workbench">
    <aside class="stage-rail" :aria-label="t('courseWorkbench.stageNavigation', '课程生产阶段')">
      <header><strong>{{ t('courseWorkbench.title', '课程工作台') }}</strong><small>{{ t('courseWorkbench.progress', '五类资产可独立创建') }}</small></header>
      <nav>
        <button v-for="stage in stages" :key="stage.id" type="button" :class="{ active: activeStage === stage.id }" @click="activeStage = stage.id">
          <span>{{ stage.step }}</span><component :is="stage.icon" :size="18" /><div><strong>{{ stage.label }}</strong><small>{{ stage.description }}</small></div><Check v-if="stageReady(stage.id)" :size="15" />
        </button>
      </nav>
      <section class="companion-entry">
        <small>{{ t('courseWorkbench.supporting.group', '其他课程文件') }}</small>
        <button type="button" :class="{ active: activeStage === 'companion' }" @click="activeStage = 'companion'">
          <FileCheck2 :size="18" /><div><strong>{{ t('courseWorkbench.supporting.title', '配套文档') }}</strong><small>{{ t('courseWorkbench.supporting.help', '学校模板快捷生成') }}</small></div><ChevronRight :size="16" />
        </button>
      </section>
      <footer><span>{{ readyStageCount }}/5</span><div><i :style="{ width: `${readyStageCount / 5 * 100}%` }" /></div></footer>
    </aside>

    <main ref="workbenchCenter" class="workbench-center">
      <header class="center-heading">
        <div><small>{{ activeStage === 'companion' ? t('courseWorkbench.supporting.kicker', '配套文档') : `${activeStageDefinition.step} / 05` }}</small><h2>{{ activeStageDefinition.label }}</h2><p>{{ activeStageDefinition.description }}</p></div>
        <button v-if="activeStage === 'foundation' && hasOutline" type="button" @click="emit('openOutline')"><FileText :size="15" />{{ t('courseWorkbench.reviewOutline', '审阅大纲') }}</button>
      </header>

      <section v-if="showStreaming" class="generation-surface" aria-live="polite">
        <header>
          <div><TriangleAlert v-if="generationFailed" :size="18" /><LoaderCircle v-else :size="18" class="spin" /><span><strong>{{ generationFailed ? t('courseWorkbench.generationInterrupted', '生成已中断') : t('courseWorkbench.generating', '正在生成课程大纲') }}</strong><small>{{ generationFailed ? generationError : currentGenerationLabel }}</small></span></div>
          <button v-if="generationRunning" type="button" @click="stopGeneration"><Pause :size="15" />{{ t('courseWorkbench.pause', '暂停') }}</button>
        </header>
        <div class="generation-progress"><i :style="{ transform: `scaleX(${generationProgress / 100})` }" /></div>
        <article class="stream-content">
          <section v-for="node in visibleStreamNodes" :key="node.node_id">
            <h3>{{ node.node_name }}</h3>
            <MarkdownRenderer :content="nodeContent(node)" />
            <span v-if="node.node_id === generationStore.currentGeneratingNodeId" class="stream-caret" />
          </section>
          <div v-if="!visibleStreamNodes.length && !generationFailed" class="stream-waiting"><LoaderCircle :size="20" class="spin" />{{ t('courseWorkbench.waitingForContent', 'AI 正在建立课程结构…') }}</div>
          <div v-else-if="!visibleStreamNodes.length" class="stream-waiting stream-failed"><TriangleAlert :size="22" />{{ t('courseWorkbench.noContentGenerated', '本次没有生成课程内容，请检查提示后重试。') }}</div>
        </article>
        <p v-if="generationError" class="generation-error" role="alert">{{ generationError }} <button type="button" @click="submitFoundation">{{ t('common.retry', '重试') }}</button></p>
      </section>

      <section v-else-if="activeStage === 'foundation' && hasOutline" class="formal-surface">
        <header><div><strong>{{ t('courseWorkbench.formalOutline', '正式课程大纲') }}</strong><small>{{ t('courseWorkbench.formalSaved', '已进入课程正式文件') }}</small></div><button type="button" @click="submitFoundation"><RefreshCw :size="15" />{{ t('courseWorkbench.regenerate', '重新生成') }}</button></header>
        <article><ol class="outline-list"><li v-for="node in outlinePreviewNodes" :key="node.node_id" :data-level="node.node_level"><span>{{ node.node_name }}</span><small>{{ Number(node.node_level || 0) === 1 ? t('courseWorkbench.chapter', '章节') : t('courseWorkbench.section', '小节') }}</small></li></ol></article>
      </section>

      <form v-else-if="activeStage === 'foundation'" class="stage-form" @submit.prevent="submitFoundation">
        <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.learningGoal', '教学目标') }} <b>*</b></span><textarea v-model.trim="foundation.goal" required rows="4" :placeholder="t('courseWorkbench.form.learningGoalPlaceholder', '学生完成课程后能够……')" /></label>
        <div class="form-grid">
          <label class="form-field"><span>{{ t('courseWorkbench.form.totalHours', '总学时') }}</span><input v-model.number="foundation.totalHours" type="number" min="1" max="1000" /></label>
          <label class="form-field"><span>{{ t('courseWorkbench.form.sessionCount', '预计课次') }}</span><input v-model.number="foundation.sessionCount" type="number" min="1" max="1000" /></label>
        </div>
        <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.requirements', '补充要求') }}</span><textarea v-model.trim="foundation.requirements" rows="4" :placeholder="t('courseWorkbench.form.requirementsPlaceholder', '例如：每章包含案例讨论，兼顾理论与实践')" /></label>
        <footer><span>{{ t('courseWorkbench.form.sourceHint', '右侧资料会与这些信息一起交给 AI') }}</span><button class="primary" type="submit" :disabled="generationStarting || !foundation.goal"><Sparkles :size="16" />{{ t('courseWorkbench.generateOutline', '生成课程大纲') }}</button></footer>
      </form>

      <CompanionDocumentStudio
        v-else-if="activeStage === 'companion'"
        :course-id="courseId"
        @saved="handleCompanionSaved"
      />

      <QuestionBankReviewPanel
        v-else-if="activeStage === 'question-bank'"
        class="question-workbench-surface"
        :course-id="courseId"
        :initial-node-ids="selectedLessonQuestionNodeIds"
        :initial-scope-label="selectedLesson?.title || ''"
        :material-asset-ids="activeReferences.map(item => item.material_asset_id)"
        @updated="questionBankReady = true"
      />

      <section v-else class="lesson-stage">
        <label class="lesson-selector"><span>{{ t('courseWorkbench.form.lesson', '选择课次') }}</span><select v-model="selectedLessonId"><option value="" disabled>{{ t('courseWorkbench.form.chooseLesson', '请选择课次') }}</option><option v-for="lesson in lessonStore.lessons" :key="lesson.lesson_unit_id" :value="lesson.lesson_unit_id">{{ String(lesson.number).padStart(2, '0') }} · {{ lesson.title }}</option></select></label>
        <div v-if="!lessonStore.lessons.length" class="prerequisite"><FileText :size="24" /><strong>{{ t('courseWorkbench.completeOutlineFirst', '请先生成并确认课程大纲') }}</strong><button type="button" @click="activeStage = 'foundation'">{{ t('courseWorkbench.backToFoundation', '返回课程基础') }}</button></div>

        <template v-else-if="activeStage === 'lesson'">
          <form v-if="selectedLesson && !workingLessonRevision" class="stage-form stage-form--lesson" @submit.prevent="generateLessonPlan">
            <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.lessonFocus', '本讲重点') }}</span><textarea v-model.trim="lessonRequirements" rows="4" :placeholder="t('courseWorkbench.form.lessonFocusPlaceholder', '填写重难点、教学方法或课堂活动要求')" /></label>
            <footer><span>{{ t('courseWorkbench.form.sourceHint', '右侧资料会与这些信息一起交给 AI') }}</span><button class="primary" type="submit" :disabled="lessonBusy || !selectedLessonId"><LoaderCircle v-if="lessonBusy" :size="16" class="spin" /><Sparkles v-else :size="16" />{{ t('courseWorkbench.generateLessonPlan', '生成本讲教案') }}</button></footer>
          </form>
          <section v-else-if="workingLessonRevision" class="formal-surface lesson-formal"><header><div><strong>{{ selectedLesson?.title }}</strong><small>{{ lessonJobLabel }}</small></div><button type="button" @click="emit('openTeachingPlan', selectedLessonId)"><Pencil :size="15" />{{ t('courseWorkbench.openEditor', '打开编辑') }}</button></header><article><MarkdownRenderer :content="lessonPlanMarkdown" /></article></section>
        </template>

        <template v-else-if="activeStage === 'script'">
          <section class="formal-surface lesson-formal"><header><div><strong>{{ t('courseWorkbench.script', '讲稿') }}</strong><small>{{ t('courseWorkbench.scriptPptSameSource', '与 PPT 结构化同源') }}</small></div><button type="button" :disabled="!selectedLessonId" @click="emit('openScript', selectedLessonId)"><Pencil :size="15" />{{ t('courseWorkbench.openEditor', '打开编辑') }}</button></header><article v-if="scriptMarkdown"><MarkdownRenderer :content="scriptMarkdown" /></article><div v-else class="empty-asset">{{ t('courseWorkbench.scriptPending', '课程内容生成后，这里会形成可编辑的轻量讲稿。') }}</div></section>
        </template>

        <template v-else-if="activeStage === 'ppt'">
          <section class="formal-surface lesson-formal"><header><div><strong>PPT</strong><small>{{ pptAsset ? t('courseWorkbench.formalSaved', '已进入课程正式文件') : t('courseWorkbench.pptFromScript', '从教案与讲稿生成') }}</small></div><button type="button" :disabled="pptBusy || !workingLessonRevision" @click="generatePpt"><LoaderCircle v-if="pptBusy" :size="15" class="spin" /><Presentation v-else :size="15" />{{ pptAsset ? t('courseWorkbench.openPpt', '打开 PPT') : t('courseWorkbench.generatePpt', '生成 PPT') }}</button></header><article v-if="pptAsset"><h3>{{ pptAsset.revisions?.at(-1)?.deck?.title || selectedLesson?.title }}</h3><ol><li v-for="slide in pptAsset.revisions?.at(-1)?.deck?.slides || []" :key="slide.slide_id">{{ slide.title }}</li></ol></article><div v-else class="empty-asset">{{ workingLessonRevision ? t('courseWorkbench.pptReadyToGenerate', '教案已准备好，可以生成配套 PPT。') : t('courseWorkbench.planBeforePpt', '请先生成并确认本讲教案。') }}</div></section>
        </template>
      </section>
    </main>

    <CourseReferenceTray v-model="activeReferences" :course-id="courseId" />
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, reactive, ref, watch } from 'vue'
import { BookOpenText, Check, ChevronRight, ClipboardList, FileCheck2, FileText, Layers3, ListChecks, LoaderCircle, Pause, Pencil, Presentation, RefreshCw, Sparkles, TriangleAlert } from 'lucide-vue-next'
import CompanionDocumentStudio from './CompanionDocumentStudio.vue'
import CourseReferenceTray, { type CourseReferenceItem } from './CourseReferenceTray.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import QuestionBankReviewPanel from './QuestionBankReviewPanel.vue'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'
import http, { teacherRequestConfig } from '../utils/http'

type CoreStageId = 'foundation' | 'lesson' | 'question-bank' | 'script' | 'ppt'
type StageId = CoreStageId | 'companion'
const props = withDefaults(defineProps<{ courseId: string; courseTitle: string; generationOptions: CourseGenerationOptions & { subject?: string }; generationStarting?: boolean; initialStage?: StageId }>(), { initialStage: 'foundation' })
const emit = defineEmits<{
  (event: 'generateOutline', payload: { subject: string; options: CourseGenerationOptions; references: CourseReferenceItem[] }): void
  (event: 'openOutline'): void
  (event: 'openTeachingPlan', lessonId: string): void
  (event: 'openScript', lessonId: string): void
}>()
const courseStore = useCourseStore(); const generationStore = useGenerationStore(); const lessonStore = useTeacherLessonAuthoringStore()
const activeStage = ref<StageId>(props.initialStage); const selectedLessonId = ref('')
const workbenchCenter = ref<HTMLElement | null>(null)
const referencesByStage = reactive<Record<StageId, CourseReferenceItem[]>>({ foundation: [], lesson: [], 'question-bank': [], script: [], ppt: [], companion: [] })
const activeReferences = computed({ get: () => referencesByStage[activeStage.value], set: value => { referencesByStage[activeStage.value] = value } })
const foundation = reactive({ goal: '', totalHours: 32, sessionCount: 16, requirements: '' })
const lessonRequirements = ref('')
const lessonBusy = ref(false); const pptBusy = ref(false); const generationRequested = ref(false)
const questionBankReady = ref(false)
const stages = computed(() => [
  { id: 'foundation' as const, step: '01', label: t('courseWorkbench.stages.foundation', '课程基础'), description: t('courseWorkbench.stages.foundationHelp', '大纲与教学日历'), icon: markRaw(Layers3) },
  { id: 'lesson' as const, step: '02', label: t('courseWorkbench.stages.lesson', '教案'), description: t('courseWorkbench.stages.lessonHelp', '按课次组织教学'), icon: markRaw(ClipboardList) },
  { id: 'question-bank' as const, step: '03', label: t('courseWorkbench.stages.questionBank', '题库'), description: t('courseWorkbench.stages.questionBankHelp', '可选 · 出题与组卷'), icon: markRaw(ListChecks) },
  { id: 'script' as const, step: '04', label: t('courseWorkbench.stages.script', '讲稿'), description: t('courseWorkbench.stages.scriptHelp', '轻量可编辑正文'), icon: markRaw(BookOpenText) },
  { id: 'ppt' as const, step: '05', label: t('courseWorkbench.stages.ppt', 'PPT'), description: t('courseWorkbench.stages.pptHelp', '与讲稿结构化同源'), icon: markRaw(Presentation) },
])
const activeStageDefinition = computed(() => stages.value.find(item => item.id === activeStage.value) || {
  id: 'companion' as const,
  step: '',
  label: t('courseWorkbench.supporting.title', '配套文档'),
  description: t('courseWorkbench.supporting.description', '从学校模板快速生成正式文件'),
  icon: markRaw(FileCheck2),
})
const selectedLesson = computed(() => lessonStore.lessons.find(item => item.lesson_unit_id === selectedLessonId.value))
const workingLessonRevision = computed(() => selectedLesson.value?.plan.revisions.find(item => item.revision_id === selectedLesson.value?.plan.working_revision_id))
const pptAsset = computed(() => selectedLesson.value?.plan.ppt_assets.find(item => item.role === 'primary') || selectedLesson.value?.plan.ppt_assets[0])
const generationTask = computed(() => generationStore.getTask(props.courseId))
const taskActive = computed(() => ['pending', 'running', 'paused', 'waiting_for_review'].includes(String(generationTask.value?.status || '')))
const generationFailed = computed(() => generationStore.generationStatus === 'error')
const generationRunning = computed(() => taskActive.value || generationStore.generationStatus === 'generating')
const showStreaming = computed(() => activeStage.value === 'foundation' && (generationRequested.value || taskActive.value))
const hasOutline = computed(() => courseStore.nodes.some(node => Number(node.node_level || 0) <= 2))
const outlinePreviewNodes = computed(() => courseStore.nodes.filter(node => Number(node.node_level || 0) <= 2).slice(0, 24))
const visibleStreamNodes = computed(() => courseStore.nodes.filter(node => node.node_content || generationStore.streamingContent[node.node_id]).slice(0, 20))
const generationProgress = computed(() => Math.max(2, Number(generationTask.value?.progress || generationStore.generationProgress || 0)))
const currentGenerationLabel = computed(() => generationStore.currentGeneratingNode || t('courseWorkbench.waitingForContent', 'AI 正在建立课程结构…'))
const generationError = computed(() => generationFailed.value ? String(generationStore.failureReport?.failed_nodes?.[0]?.error || t('courseWorkbench.generationFailed', '生成中断，可以从当前结果重试。')) : '')
const lessonJob = computed(() => selectedLessonId.value ? lessonStore.latestJobByLesson(selectedLessonId.value) : undefined)
const lessonJobLabel = computed(() => ['pending', 'running'].includes(String(lessonJob.value?.status || '')) ? `${t('courseWorkbench.generatingShort', '生成中')} ${Math.round(Number(lessonJob.value?.progress || 0))}%` : t('courseWorkbench.formalSaved', '已进入课程正式文件'))
const lessonPlanMarkdown = computed(() => { const plan = workingLessonRevision.value?.plan || {}; return [`# ${selectedLesson.value?.title || ''}`, plan.objectives ? `## 教学目标\n${String(plan.objectives)}` : '', plan.key_points ? `## 教学重点\n${String(plan.key_points)}` : '', plan.teaching_process ? `## 教学过程\n${String(plan.teaching_process)}` : ''].filter(Boolean).join('\n\n') })
const scriptNodes = computed(() => { const ids = new Set(selectedLesson.value?.sections.map(item => item.section_node_id) || []); return courseStore.nodes.filter(node => ids.has(node.node_id) || ids.has(String(node.parent_node_id || ''))) })
const scriptMarkdown = computed(() => scriptNodes.value.map(node => `## ${node.node_name}\n\n${node.node_content || ''}`).join('\n\n'))
const selectedLessonQuestionNodeIds = computed(() => selectedLesson.value?.sections.map(item => item.section_node_id).filter(Boolean) || [])
const readyStageCount = computed(() => stages.value.filter(item => stageReady(item.id)).length)

function stageReady(stage: CoreStageId) { if (stage === 'foundation') return hasOutline.value; if (stage === 'lesson') return lessonStore.lessons.some(item => Boolean(item.plan.working_revision_id)); if (stage === 'question-bank') return questionBankReady.value; if (stage === 'script') return courseStore.nodes.some(node => Boolean(node.node_content)); return lessonStore.lessons.some(item => item.plan.ppt_assets.length > 0) }
function nodeContent(node: any) { return generationStore.streamingContent[node.node_id] || node.node_content || '' }
function stopGeneration() { void generationStore.stopGeneration() }
function generationBindings(references: CourseReferenceItem[]) { return references.map(item => ({ asset_id: item.material_asset_id, purpose: item.role === 'primary' ? 'content_source' as const : 'supplement' as const, priority: item.role === 'primary' ? 'core' as const : 'supporting' as const, authority: item.role === 'primary' ? 'primary' as const : 'secondary' as const, usage_policy: item.role === 'primary' ? 'must_use' as const : 'prefer' as const, reuse_policy: 'reference_only' as const, rights_basis: 'teacher_asserted' as const, source_metadata: {}, source_label: item.filename })) }
async function saveRelationships(targetId: string, targetType: string, label: string) { const refs = activeReferences.value; const packageId = refs[0]?.package_id || String((await http.get('/api/teacher-course-spaces', teacherRequestConfig({ params: { course_id: props.courseId }, silentError: true }))).data?.[0]?.package_id || ''); if (!packageId) return; await http.put(`/api/teacher-course-spaces/${packageId}/relationships`, { target_id: targetId, target_type: targetType, target_label: label, sources: refs.map(item => ({ source_asset_id: item.asset_id, role: item.role })) }, teacherRequestConfig({ silentError: true })) }
async function submitFoundation() { generationRequested.value = true; try { await saveRelationships('managed:outline', 'outline', t('courseFiles.names.outline', '课程大纲')); emit('generateOutline', { subject: props.courseTitle, options: { ...props.generationOptions, requirements: [props.generationOptions.requirements, foundation.requirements].filter(Boolean).join('\n'), course_intent: { schema_version: 'course_intent_v1', type: 'systematic', learning_goal: foundation.goal }, teacher_course_brief: { schema_version: 'teacher_course_brief_v1', target_audience: props.generationOptions.teacher_course_brief?.target_audience || '大学生', total_class_hours: foundation.totalHours, lesson_duration_minutes: props.generationOptions.teacher_course_brief?.lesson_duration_minutes || 45, teaching_context: props.generationOptions.teacher_course_brief?.teaching_context || 'classroom', section_count: foundation.sessionCount }, material_bindings: generationBindings(activeReferences.value) }, references: activeReferences.value }) } catch { generationRequested.value = false } }
async function generateLessonPlan() { if (!selectedLesson.value) return; lessonBusy.value = true; try { await saveRelationships(`lesson-plan:${selectedLessonId.value}`, 'lesson_plan', selectedLesson.value.title); const primary = activeReferences.value.find(item => item.role === 'primary'); await lessonStore.generateLesson(props.courseId, selectedLessonId.value, primary ? { packageId: primary.package_id, assetId: primary.asset_id } : undefined, lessonRequirements.value) } finally { lessonBusy.value = false } }
async function generatePpt() { if (!selectedLesson.value) return; if (pptAsset.value) { window.location.assign(`/course/${props.courseId}/ppt?lesson=${selectedLessonId.value}`); return } const revision = workingLessonRevision.value?.revision_id; if (!revision) return; pptBusy.value = true; try { await saveRelationships(`ppt:${selectedLessonId.value}`, 'ppt', `${selectedLesson.value.title} PPT`); await lessonStore.generatePpt(props.courseId, selectedLessonId.value, revision) } finally { pptBusy.value = false } }
async function handleCompanionSaved(document: { document_id: string; title: string; revision_id: string }) { await saveRelationships(`companion-document:${document.document_id}`, 'companion_document', document.title) }
async function loadQuestionBankStatus() { if (!props.courseId) return; try { const response = await http.get(`/api/courses/${props.courseId}/question-bank`, teacherRequestConfig({ silentError: true })); questionBankReady.value = Number(response.data?.total || 0) > 0 } catch { questionBankReady.value = false } }

watch(() => props.generationOptions, options => { const intent = options.course_intent as any; foundation.goal = String(intent?.learning_goal || options.requirements || props.courseTitle); foundation.totalHours = Number(options.teacher_course_brief?.total_class_hours || 32); foundation.sessionCount = Number(options.teacher_course_brief?.section_count || 16); foundation.requirements = String(options.requirements || '') }, { immediate: true, deep: true })
watch(() => props.initialStage, stage => { activeStage.value = stage })
watch(activeStage, () => { if (workbenchCenter.value) workbenchCenter.value.scrollTop = 0 }, { flush: 'post' })
watch(() => lessonStore.lessons, lessons => { if (!selectedLessonId.value && lessons[0]) selectedLessonId.value = lessons[0].lesson_unit_id }, { immediate: true, deep: true })
watch(() => props.courseId, () => { void loadQuestionBankStatus() }, { immediate: true })
watch(taskActive, active => { if (!active) generationRequested.value = false })
</script>

<style scoped>
.teacher-workbench{height:100%;min-height:0;display:grid;grid-template-columns:238px minmax(520px,1fr) 310px;overflow:hidden;background:#f3f5f9}.stage-rail{min-height:0;display:flex;flex-direction:column;border-right:1px solid #e4e9f1;background:#fff}.stage-rail>header{display:grid;gap:4px;padding:21px 18px 16px}.stage-rail>header strong{color:#1f2a40;font-size:15px}.stage-rail>header small{color:#64748b;font-size:12px}.stage-rail nav{display:grid;gap:4px;padding:4px 9px}.stage-rail nav button{min-height:66px;display:grid;grid-template-columns:26px 22px minmax(0,1fr) 18px;align-items:center;gap:8px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.stage-rail nav button:hover{background:#f6f7fb}.stage-rail nav button.active{color:#4338ca;background:#eef0ff}.stage-rail nav button>span{font-size:11px;font-weight:750}.stage-rail nav button>div{min-width:0;display:grid;gap:3px}.stage-rail nav strong{color:#334155;font-size:13px}.stage-rail nav small{overflow:hidden;color:#64748b;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.stage-rail nav button.active strong{color:#3730a3}.stage-rail nav button>svg:last-child{color:#16a34a}.stage-rail>footer{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:9px;margin-top:auto;padding:16px 18px;color:#64748b;font-size:12px}.stage-rail>footer>div{height:4px;overflow:hidden;border-radius:2px;background:#e8ecf3}.stage-rail>footer i{height:100%;display:block;background:#5b57e8}.workbench-center{min-width:0;min-height:0;overflow:auto;padding:24px 26px 52px}.center-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;max-width:860px;margin:0 auto 18px}.center-heading>div{display:grid;gap:4px}.center-heading small{color:#6366f1;font-size:11px;font-weight:800}.center-heading h2{margin:0;color:#172033;font-size:24px;letter-spacing:-.018em}.center-heading p{margin:0;color:#64748b;font-size:13px}.center-heading>button,.formal-surface>header button,.generation-surface>header button{min-height:36px;display:flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.stage-form,.formal-surface,.generation-surface,.lesson-stage{max-width:860px;margin:0 auto;border:1px solid #e0e6ef;border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(30,41,59,.05)}.stage-form{display:grid;gap:20px;padding:26px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.form-field{display:grid;gap:8px}.form-field>span,.lesson-selector>span{color:#334155;font-size:13px;font-weight:700}.form-field b{color:#dc2626}.form-field input,.form-field select,.form-field textarea,.lesson-selector select{width:100%;min-height:44px;padding:10px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px}.form-field textarea{resize:vertical;line-height:1.6}.form-field input:focus,.form-field select:focus,.form-field textarea:focus,.lesson-selector select:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.stage-form>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:2px}.stage-form>footer>span{color:#64748b;font-size:12px}.primary{min-height:42px;display:flex;align-items:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:13px;font-weight:750;cursor:pointer;box-shadow:0 7px 18px rgba(81,75,220,.16)}.primary:disabled{opacity:.48;cursor:not-allowed}.generation-surface{overflow:hidden}.generation-surface>header,.formal-surface>header{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-bottom:1px solid #e7ebf2}.generation-surface>header>div{display:flex;align-items:center;gap:10px;color:#4f46e5}.generation-surface>header span,.formal-surface>header>div{display:grid;gap:3px}.generation-surface>header strong,.formal-surface>header strong{color:#263147;font-size:13px}.generation-surface>header small,.formal-surface>header small{color:#64748b;font-size:11px}.generation-progress{height:3px;background:#e8ebf5}.generation-progress i{width:100%;height:100%;display:block;transform-origin:left;background:#5b57e8;transition:transform .25s ease-out}.stream-content,.formal-surface>article{max-height:calc(100vh - 260px);overflow:auto;padding:22px 28px 42px}.stream-content section,.formal-surface article section{margin-bottom:26px}.stream-content h3,.formal-surface h3{margin:0 0 10px;color:#202b40;font-size:17px}.stream-waiting{min-height:260px;display:flex;align-items:center;justify-content:center;gap:9px;color:#64748b;font-size:13px}.stream-caret{width:2px;height:18px;display:inline-block;background:#5b57e8;animation:blink .8s steps(1) infinite}.generation-error{margin:0;padding:12px 20px;color:#b91c1c;background:#fff1f2;font-size:12px}.generation-error button{border:0;color:inherit;background:transparent;font-weight:750;text-decoration:underline;cursor:pointer}.lesson-stage{padding:0 0 24px}.lesson-selector{display:grid;grid-template-columns:110px minmax(0,1fr);align-items:center;gap:14px;padding:18px 22px;border-bottom:1px solid #e7ebf2}.stage-form--lesson{border:0;box-shadow:none}.prerequisite,.empty-asset{min-height:260px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;color:#64748b;font-size:13px}.prerequisite strong{color:#334155}.prerequisite button{padding:7px 10px;border:1px solid #d7dde7;border-radius:7px;color:#4f46e5;background:#fff;font-weight:700;cursor:pointer}.lesson-formal{margin:20px 20px 0;border-radius:10px;box-shadow:none}.lesson-formal>article{max-height:calc(100vh - 360px)}.formal-surface ol{display:grid;gap:8px;padding-left:22px;color:#475569;font-size:13px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes blink{50%{opacity:0}}
.companion-entry{display:grid;gap:7px;margin:10px 9px 0;padding-top:14px;border-top:1px solid #e7ebf2}.companion-entry>small{padding:0 10px;color:#64748b;font-size:11px;font-weight:700}.companion-entry>button{min-height:58px;display:grid;grid-template-columns:22px minmax(0,1fr) 16px;align-items:center;gap:9px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.companion-entry>button:hover{background:#f6f7fb}.companion-entry>button.active{color:#4338ca;background:#eef0ff}.companion-entry>button>div{min-width:0;display:grid;gap:3px}.companion-entry strong{color:#334155;font-size:13px}.companion-entry small{overflow:hidden;color:#64748b;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.companion-entry>button.active strong{color:#3730a3}
.question-workbench-surface{max-width:1060px;margin:0 auto;padding:0;border-top:0}
@media(max-width:1050px){.teacher-workbench{grid-template-columns:190px minmax(0,1fr) 280px}.workbench-center{padding-inline:18px}.stage-rail nav button{grid-template-columns:23px minmax(0,1fr)}.stage-rail nav button>svg,.stage-rail nav button>svg:last-child{display:none}}
@media(max-width:760px){.teacher-workbench{height:auto;min-height:100%;grid-template-columns:1fr;overflow:auto}.stage-rail{display:block;border-right:0;border-bottom:1px solid #e4e9f1}.stage-rail>header,.stage-rail>footer{display:none}.stage-rail nav{grid-template-columns:repeat(5,minmax(0,1fr));overflow:auto;padding:8px}.stage-rail nav button{min-width:108px;min-height:50px;grid-template-columns:22px minmax(0,1fr);padding:6px 8px}.stage-rail nav small{display:none}.workbench-center{overflow:visible;padding:18px 12px 30px}.center-heading h2{font-size:21px}.center-heading>button{font-size:0;width:38px;padding:0;justify-content:center}.stage-form{padding:19px 16px}.form-grid{grid-template-columns:1fr}.stage-form>footer{align-items:stretch;flex-direction:column}.primary{justify-content:center}.lesson-selector{grid-template-columns:1fr}.stream-content,.formal-surface>article{max-height:none;padding-inline:18px}.reference-tray{border-left:0;border-top:1px solid #e4e9f1}}
.outline-list{margin:0;padding:0!important;list-style:none}.outline-list li{min-height:38px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 10px;border-bottom:1px solid #edf1f6;color:#334155}.outline-list li[data-level="2"]{padding-left:28px;color:#64748b}.outline-list small{color:#94a3b8;font-size:11px}
.stream-failed{color:#b91c1c;background:#fffafa}
</style>
