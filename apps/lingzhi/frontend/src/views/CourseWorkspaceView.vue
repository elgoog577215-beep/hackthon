<template>
  <main class="course-workspace-page">
    <Teleport to="#app-header-route-context" defer>
      <div class="workspace-route-context">
        <button class="back-button" type="button" :aria-label="t('courseFiles.backToCourses')" @click="backToSource">
          <ArrowLeft :size="17" />
        </button>
        <FolderOpen :size="18" />
        <h1>{{ courseTitle || t('courseFiles.untitledCourse') }}</h1>
        <small class="workspace-state" :data-state="courseState">{{ courseStateLabel }}</small>
      </div>
    </Teleport>

    <Teleport to="#app-header-route-center" defer>
      <nav class="workspace-view-switch" :aria-label="t('courseFiles.views.label')">
        <button type="button" :class="{ active: workspaceView === 'categories' }" @click="changeWorkspaceView('categories')">
          <LayoutGrid :size="15" />{{ t('courseFiles.views.categories') }}
        </button>
        <button type="button" :class="{ active: workspaceView === 'files' }" @click="changeWorkspaceView('files')">
          <FolderTree :size="15" />{{ t('courseFiles.views.files') }}
        </button>
        <button type="button" :class="{ active: workspaceView === 'insights' }" @click="changeWorkspaceView('insights')"><ChartNoAxesCombined :size="15" />{{ t('workspaceUi.insights') }}</button>
      </nav>
    </Teleport>

    <Teleport to="#app-header-route-actions" defer>
      <div class="workspace-route-actions">
        <el-popover v-if="workspaceView === 'files'" placement="bottom-end" :width="280" trigger="click">
          <template #reference>
            <CourseWorkspaceHeaderAction :label="t('courseFiles.searchCurrent')" icon-only><Search :size="16" /></CourseWorkspaceHeaderAction>
          </template>
          <label class="workspace-search workspace-search--popover">
            <Search :size="15" />
            <input v-model="searchQuery" type="search" :placeholder="t('courseFiles.searchCurrent')" :aria-label="t('courseFiles.searchCurrent')" />
            <button v-if="searchQuery" type="button" :aria-label="t('courseFiles.clearSearch')" @click="searchQuery = ''"><X :size="14" /></button>
          </label>
        </el-popover>
        <CourseWorkspaceHeaderAction
          class="audit-action"
          :label="t('courseAuditUpdates.globalChange', '全局修改')"
          :display-label="t('courseFiles.headerActions.change')"
          :hint="t('courseAuditUpdates.openHint', '查看材料变化、生成关系和全课调整')"
          @click="openGlobalChange"
        >
          <ScanSearch :size="16" />
        </CourseWorkspaceHeaderAction>
        <CoursePublicationPanel ref="publicationPanel" :course-id="courseId" />
        <CourseWorkspaceHeaderAction class="preview-action" :label="t('courseFiles.previewCourse')" :display-label="t('courseFiles.headerActions.preview')" primary @click="openCoursePreview"><Eye :size="16" /></CourseWorkspaceHeaderAction>
      </div>
    </Teleport>

    <Transition name="workspace-load" mode="out-in">
      <section v-if="loading" key="loading" class="workspace-loading" role="status">
        <LoaderCircle :size="22" class="spin" />{{ t('courseFiles.loading') }}
      </section>
      <section v-else-if="loadError" key="error" class="workspace-error">
        <AppErrorNotice :presentation="loadError">
          <template #action>
            <button type="button" @click="loadError.status === 404 ? backToSource() : loadWorkspace()">
              {{ loadError.status === 404 ? t('courseFiles.backToCourses') : t('common.retry') }}
            </button>
          </template>
        </AppErrorNotice>
      </section>
      <section v-else key="ready" class="workspace-operating-shell">
        <Transition name="workspace-surface" mode="out-in">
          <TeacherCourseWorkbench
            ref="workbench"
            v-if="workspaceView === 'categories'"
            key="categories"
            :course-id="courseId"
            :course-title="courseTitle"
            :generation-options="courseGenerationOptions"
            :generation-starting="generationStarting"
            :material-refresh-token="materialRefreshToken"
            :initial-stage="requestedWorkbenchStage"
            :initial-lesson-id="requestedLessonId"
            :initial-knowledge="requestedKnowledge"
            :initial-companion-template-id="requestedTemplateId"
            :initial-issue-id="requestedIssueId"
            :initial-block-id="requestedBlockId"
            :initial-task-id="requestedTaskId"
            :expand-issue="expandRequestedIssue"
            v-model:outline-editing="outlineEditing"
            @generate-outline="startOutlineGeneration"
            @open-course-information="courseInformationOpen = true"
            @open-course-adjustment="openCourseAdjustment"
            @location-change="handleWorkbenchLocation"
          />
          <TeacherCourseSpaceView
            v-else-if="workspaceView === 'files'"
            key="files"
            embedded
            :course-id="courseId"
            :course-title="courseTitle"
            workspace-view="files"
            v-model:query="searchQuery"
            @open-outline="openOutlineEditor"
            @create-outline="prepareOutlineGeneration"
            @open-teaching-calendar="calendarOpen = true"
            @open-teaching-plan="openLessonPlan"
            @open-practice="openPractice"
            @open-script="openScript"
            @open-ppt="openPpt"
            @open-question-bank="openQuestionBankWorkbench"
            @open-companion-documents="openCompanionDocuments"
            @context-change="selectedContext = $event"
            @readiness-change="readiness = $event"
            @edit-baseline="courseInformationOpen = true"
          />
          <TeacherLearningAnalysis v-else key="insights" :course-id="courseId" @feedback="publicationPanel?.showFeedback()" />
        </Transition>
      </section>
    </Transition>

    <CourseBaselineDialog
      v-model="courseInformationOpen"
      :course-id="courseId"
      :initial-envelope="courseInformationEnvelope"
      @loaded="courseInformationEnvelope = $event"
      @updated="handleCourseInformationUpdated"
    />

    <CoursePreparationDialog
      v-if="!loading && !knowledgeFirstEnabled"
      :course-id="courseId"
      :course-title="courseTitle"
      :start-mode="route.query.prepare === 'blank' ? 'blank' : route.query.prepare === 'materials' ? 'materials' : undefined"
      @completed="handlePreparationCompleted"
      @knowledge="handleKnowledgeUpdated"
    />

    <el-drawer v-model="calendarOpen" class="teaching-calendar-drawer" size="min(1500px, 98vw)" :title="t('courseFiles.calendarDrawerTitle')">
      <TeacherCourseCalendarView />
    </el-drawer>

    <CourseEvolutionWorkspace
      v-model="courseAdjustmentOpen"
      :course-id="courseId"
      :course-title="courseTitle"
      :focus-plan-id="courseAdjustmentPlanId"
      @course-applied="handleCourseAdjustmentApplied"
    />

    <CourseDialogShell v-if="globalChangeChoiceOpen" :title="t('courseAuditUpdates.globalChangeChoiceTitle')" @close="globalChangeChoiceOpen = false">
          <div class="global-change-choice__options">
            <button type="button" @click="chooseGlobalChange('structure')">
              <span class="choice-icon"><LayoutGrid :size="20" /></span>
              <span><strong>{{ t('courseAuditUpdates.adjustStructure', '调整结构') }}</strong><small>{{ t('courseAuditUpdates.adjustStructureHint', '编辑讲次和课程顺序') }}</small></span>
              <ArrowRight :size="17" />
            </button>
            <button type="button" @click="chooseGlobalChange('semantic')">
              <span class="choice-icon"><ScanSearch :size="20" /></span>
              <span><strong>{{ t('courseAuditUpdates.globalSemantic', '全局语义') }}</strong><small>{{ t('courseAuditUpdates.globalSemanticHint', '用一句话说明要怎样改内容') }}</small></span>
              <ArrowRight :size="17" />
            </button>
          </div>
    </CourseDialogShell>

  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ChartNoAxesCombined, ArrowLeft, ArrowRight, Eye, FolderOpen, FolderTree, LayoutGrid, LoaderCircle, ScanSearch, Search, X } from 'lucide-vue-next'
import AppErrorNotice from '../components/AppErrorNotice.vue'
import CourseBaselineDialog from '../components/CourseBaselineDialog.vue'
import CoursePreparationDialog from '../components/CoursePreparationDialog.vue'
import CourseEvolutionWorkspace from '../components/CourseEvolutionWorkspace.vue'
import CourseDialogShell from '../components/CourseDialogShell.vue'
import TeacherCourseWorkbench from '../components/TeacherCourseWorkbench.vue'
import TeacherLearningAnalysis from '../components/TeacherLearningAnalysis.vue'
import CoursePublicationPanel from '../components/CoursePublicationPanel.vue'
import CourseWorkspaceHeaderAction from '../components/CourseWorkspaceHeaderAction.vue'
import TeacherCourseCalendarView from './TeacherCourseCalendarView.vue'
import TeacherCourseSpaceView from './TeacherCourseSpaceView.vue'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { coursePreparationLabel, coursePreparationState } from '../utils/course-preparation'
import { toAppError, type AppErrorPresentation } from '../utils/app-error'
import { readWorkspaceLocation, workspaceLocationQuery, type WorkspaceLocation } from '../shared/course-workspace-navigation'
import http, { teacherReadRequestConfig } from '../utils/http'

const props = defineProps<{ courseId: string; mode?: string }>()
const route = useRoute()
const router = useRouter()
const workbench = ref<{ finishEditing: () => Promise<boolean> } | null>(null)
const finishWorkbenchEditing = async () => await workbench.value?.finishEditing() ?? true
const publicationPanel = ref<InstanceType<typeof CoursePublicationPanel> | null>(null)
async function changeWorkspaceView(view: 'files' | 'categories' | 'insights') {
  if (view !== workspaceView.value && !await finishWorkbenchEditing()) return
  workspaceView.value = view
}
onBeforeRouteLeave(finishWorkbenchEditing)
const synchronizingLocation = ref(false)
onBeforeRouteUpdate(() => synchronizingLocation.value ? true : finishWorkbenchEditing())
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const lessonStore = useTeacherLessonAuthoringStore()
const courseWorkspace = useCourseWorkspaceStore()
const loading = ref(true)
const loadError = ref<AppErrorPresentation | null>(null)
const outlineEditing = ref(false)
const calendarOpen = ref(false)
const knowledgeFirstEnabled = ref(false)
async function handleKnowledgeUpdated() { await loadWorkspace() }
const courseInformationOpen = ref(false)
const courseAdjustmentOpen = ref(false)
const globalChangeChoiceOpen = ref(false)
const courseAdjustmentPlanId = ref('')
const generationStarting = ref(false)
const materialRefreshToken = ref(0)
const selectedContext = ref({ lessonId: '', nodeId: '', label: '', type: '', path: '' })
const readiness = ref({ required: 0, ready: 0, pending: 0 })
const workspaceView = ref<WorkspaceLocation['view']>(readWorkspaceLocation(route.query).view)
const requestedWorkbenchStage = ref<'foundation' | 'lesson' | 'question-bank' | 'script' | 'ppt' | 'companion'>('foundation')
const requestedLessonId = ref('')
const requestedKnowledge = ref(false)
const requestedTemplateId = ref('')
const requestedIssueId = computed(() => String(route.query.issue || ''))
const requestedBlockId = computed(() => String(route.query.block || ''))
const requestedTaskId = computed(() => String(route.query.task || ''))
const expandRequestedIssue = computed(() => route.query.expandIssue === '1')
const searchQuery = ref('')
const courseGenerationOptions = ref<CourseGenerationOptions & { subject?: string }>({})
const courseInformationEnvelope = ref<any | null>(null)
const stableCourseTitle = ref('')
let workspaceLoadToken = 0

function applyWorkspaceLocation() {
  const location = readWorkspaceLocation(route.query)
  workspaceView.value = location.view
  requestedWorkbenchStage.value = location.stage
  requestedLessonId.value = location.lessonId
  requestedKnowledge.value = location.knowledge
  requestedTemplateId.value = location.companionTemplateId || ''
}
function handleWorkbenchLocation(location: Omit<WorkspaceLocation, 'view'>) {
  requestedWorkbenchStage.value = location.stage
  requestedLessonId.value = location.lessonId
  requestedKnowledge.value = location.knowledge
  requestedTemplateId.value = location.companionTemplateId || ''
}
watch(() => route.query, () => {
  if (!synchronizingLocation.value && !loading.value) applyWorkspaceLocation()
})
watch([workspaceView, requestedWorkbenchStage, requestedLessonId, requestedKnowledge, requestedTemplateId], async () => {
  if (loading.value) return
  const query = workspaceLocationQuery(route.query, {
    view: workspaceView.value, stage: requestedWorkbenchStage.value,
    lessonId: requestedLessonId.value, knowledge: requestedKnowledge.value,
    companionTemplateId: requestedTemplateId.value,
  }) as typeof route.query
  if (JSON.stringify(query) === JSON.stringify(route.query)) return
  synchronizingLocation.value = true
  try { await router.replace({ query }) }
  finally { synchronizingLocation.value = false }
}, { flush: 'post' })

const courseId = computed(() => String(props.courseId || route.params.courseId || ''))
const courseTitle = computed(() => (
  courseStore.courseList.find(item => item.course_id === courseId.value)?.course_name
  || stableCourseTitle.value
  || courseStore.currentCourse?.course_name
  || ''
))
const generationTask = computed(() => generationStore.getTask(courseId.value))
const courseState = computed(() => coursePreparationState(
  courseStore.courseList.find(item => item.course_id === courseId.value) || courseStore.currentCourse,
  generationTask.value,
))
const courseStateLabel = computed(() => coursePreparationLabel(courseState.value))

function handleCourseInformationUpdated(payload: any) {
  courseInformationEnvelope.value = payload
  courseGenerationOptions.value = payload.information?.generation_request || courseGenerationOptions.value
  void courseStore.fetchCourseList({ surface: 'teacher' })
}

function backToSource() {
  const returnTo = String(route.query.returnTo || '')
  if (returnTo.startsWith('/courses')) {
    void router.push(returnTo)
    return
  }
  void router.push({ name: 'course-library', query: { view: 'courses' } })
}

async function loadWorkspace() {
  if (!courseId.value) return
  const requestedCourseId = courseId.value
  const loadToken = ++workspaceLoadToken
  applyWorkspaceLocation()
  generationStore.observeCourse(requestedCourseId)
  loading.value = true
  loadError.value = null
  courseInformationEnvelope.value = null
  knowledgeFirstEnabled.value = false
  try {
    const requestedSection = String(route.query.section || '')
    const requestedStage = String(route.query.stage || '')
    if (['foundation', 'lesson', 'question-bank', 'script', 'ppt', 'companion'].includes(requestedStage)) {
      requestedWorkbenchStage.value = requestedStage as typeof requestedWorkbenchStage.value
    }
    requestedLessonId.value = String(route.query.lesson || '')
    const loadBlueprintFirst = workspaceView.value === 'categories'
      && requestedWorkbenchStage.value === 'foundation'
    const loadTargetLessonFirst = workspaceView.value === 'categories'
      && ['lesson', 'script', 'ppt'].includes(requestedWorkbenchStage.value)
    if (loadTargetLessonFirst) courseStore.prepareCourseShell(requestedCourseId, false, 'teacher_lesson_summary')
    const primaryContentLoad = loadBlueprintFirst
      ? courseWorkspace.loadBlueprint(requestedCourseId)
      : loadTargetLessonFirst
        ? lessonStore.loadInitial(requestedCourseId, requestedLessonId.value)
        : courseStore.loadCourse(requestedCourseId, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true })
    const [courseInformation, primaryContent] = await Promise.all([
      http.get(
        `/api/courses/${requestedCourseId}/course-information`,
        teacherReadRequestConfig({ silentError: true, params: { view: 'summary' } }),
      ),
      primaryContentLoad,
    ])
    if (courseId.value !== requestedCourseId || loadToken !== workspaceLoadToken) return
    knowledgeFirstEnabled.value = ['knowledge_first_c17_v1', 'knowledge_first_generic_v1'].includes(courseInformation.data?.knowledge_first_workflow)
    if (loadBlueprintFirst) {
      const blueprint = primaryContent?.draft || primaryContent?.current || primaryContent || {}
      const blueprintNodes = Array.isArray(blueprint.nodes) ? blueprint.nodes : []
      courseStore.currentCourseId = requestedCourseId
      courseStore.applyGenerationOutlineDraft(blueprintNodes)
    }
    if (loadTargetLessonFirst) {
      requestedLessonId.value = String(primaryContent?.initial_lesson_id || requestedLessonId.value)
    }
    const information = courseInformation.data?.information || {}
    stableCourseTitle.value = courseStore.courseList.find(
      item => item.course_id === requestedCourseId,
    )?.course_name || String(information.course_name || stableCourseTitle.value)
    courseGenerationOptions.value = information.generation_request || {}
    stableCourseTitle.value = String(
      information.course_name || stableCourseTitle.value,
    )
    if (requestedSection === 'outline') openOutlineEditor()
    if (requestedSection === 'basic') courseInformationOpen.value = true
    if (requestedSection === 'calendar') calendarOpen.value = true
    if (route.query.generate === 'outline') {
      prepareOutlineGeneration()
      void router.replace({ query: { ...route.query, generate: undefined } })
    }
    loading.value = false
    if (!loadBlueprintFirst && !loadTargetLessonFirst) {
      const lessonLoad = lessonStore.loadSummary(requestedCourseId)
      void lessonLoad.catch(() => undefined)
    }
    void Promise.allSettled([
      generationStore.fetchGlobalTasks(),
    ])
  } catch (error: any) {
    if (loadToken === workspaceLoadToken) loadError.value = toAppError(error, {
      title: t('courseFiles.loadFailed', '课程读取失败'),
      fallback: t('courseFiles.loadFailed', '课程读取失败'),
    })
  } finally {
    if (loadToken === workspaceLoadToken) loading.value = false
  }
}

function openLessonPlan(lessonId: string) {
  requestedKnowledge.value = false
  requestedWorkbenchStage.value = 'lesson'
  requestedLessonId.value = lessonId
  workspaceView.value = 'categories'
}

function openOutlineEditor() {
  requestedKnowledge.value = false
  requestedWorkbenchStage.value = 'foundation'
  workspaceView.value = 'categories'
  outlineEditing.value = true
}

function openQuestionBankWorkbench() {
  requestedKnowledge.value = false
  requestedWorkbenchStage.value = 'question-bank'
  workspaceView.value = 'categories'
}

function openCompanionDocuments() {
  requestedKnowledge.value = false
  requestedWorkbenchStage.value = 'companion'
  workspaceView.value = 'categories'
}

function openPractice(lessonId: string) {
  const lesson = lessonStore.lessons.find(item => item.lesson_unit_id === lessonId)
  const normalizedTitle = lesson?.title.replace(/^第\s*\d+\s*[讲章节]\s*/, '').trim() || ''
  const matchingNode = courseStore.nodes.find(node => node.node_id === lessonId)
    || courseStore.nodes.find(node => (
      Number(node.node_level || 0) === 1
      && normalizedTitle
      && node.node_name.replace(/^第\s*\d+\s*[讲章节]\s*/, '').trim() === normalizedTitle
    ))
  const targetNode = courseStore.nodes.find(node => node.parent_node_id === matchingNode?.node_id)
    || matchingNode
    || courseStore.nodes.find(node => Number(node.node_level || 0) === 2)
  void router.push({
    name: 'learning',
    params: { courseId: courseId.value, ...(targetNode ? { nodeId: targetNode.node_id } : {}) },
    query: { teacherPreview: '1', returnTo: route.fullPath, workspace: 'question-book' },
  })
}

function openPpt(lessonId: string) {
  requestedKnowledge.value = false
  requestedWorkbenchStage.value = 'ppt'
  requestedLessonId.value = lessonId
  workspaceView.value = 'categories'
}

function openScript(lessonId: string) {
  requestedKnowledge.value = false
  requestedWorkbenchStage.value = 'script'
  requestedLessonId.value = lessonId
  workspaceView.value = 'categories'
}

function openCourseAdjustment(payload?: { planId?: string; sectionId?: string }) {
  courseAdjustmentPlanId.value = payload?.planId || ''
  courseAdjustmentOpen.value = true
}

function handleCourseAdjustmentApplied() {
  materialRefreshToken.value += 1
  void Promise.allSettled([
    courseStore.loadCourse(courseId.value, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true }),
    lessonStore.load(courseId.value),
    courseStore.fetchTeacherCourseProductionState(courseId.value),
  ])
}

async function openGlobalChange() { if (await finishWorkbenchEditing()) globalChangeChoiceOpen.value = true }
function chooseGlobalChange(kind: 'structure' | 'semantic') {
  globalChangeChoiceOpen.value = false
  if (kind === 'structure') { openCourseAdjustment(); return }
  void router.push({
    name: 'course-audit-updates',
    params: { courseId: courseId.value },
    query: { ...auditCenterReturnQuery('changes'), mode: 'semantic' },
  })
}

function openMaterialAudit() {
  void router.push({
    name: 'course-audit-updates',
    params: { courseId: courseId.value },
    query: auditCenterReturnQuery('materials'),
  })
}

function auditCenterReturnQuery(view: 'materials' | 'changes') {
  const query: Record<string, string> = { view }
  const workspaceQuery: Record<string, string> = {}
  let returnLabel = t('courseAuditUpdates.returnWorkbench', '返回备课工作台')
  if (workspaceView.value === 'files') {
    workspaceQuery.view = 'files'
    returnLabel = t('courseAuditUpdates.returnFiles', '返回课程文件')
  } else {
    workspaceQuery.stage = requestedKnowledge.value ? 'knowledge' : requestedWorkbenchStage.value
    if (requestedTemplateId.value && requestedWorkbenchStage.value === 'companion') workspaceQuery.template = requestedTemplateId.value
    if (requestedLessonId.value) workspaceQuery.lesson = requestedLessonId.value
    const stageLabels: Record<string, string> = {
      foundation: t('courseAuditUpdates.stageFoundation', '课程大纲'),
      lesson: t('courseAuditUpdates.stageLesson', '教案'),
      'question-bank': t('courseAuditUpdates.stageQuestionBank', '题库'),
      script: t('courseAuditUpdates.stageScript', '讲义'),
      ppt: 'PPT',
      companion: t('courseAuditUpdates.stageCompanion', '配套文档'),
    }
    returnLabel = t('courseAuditUpdates.returnStage', '返回{stage}').replace('{stage}', stageLabels[requestedWorkbenchStage.value] || t('courseAuditUpdates.returnWorkbench', '备课工作台'))
  }
  const resolved = router.resolve({
    name: 'course-workspace',
    params: { courseId: courseId.value, mode: 'build' },
    query: workspaceQuery,
  })
  query.returnTo = resolved.fullPath
  query.returnLabel = returnLabel
  return query
}

async function startOutlineGeneration(payload: { subject: string; options: CourseGenerationOptions }) {
  if (generationStarting.value) return
  generationStarting.value = true
  try {
    const result = await courseStore.generateCourse(
      payload.subject || courseTitle.value,
      {
        ...payload.options,
        target_course_id: courseId.value,
        teacher_authoring_mode: 'lesson_assets_v1',
      },
      'teacher',
    )
    if (!result?.courseId) return
    generationStore.observeCourse(courseId.value)
  } finally {
    generationStarting.value = false
  }
}

function prepareOutlineGeneration() {
  requestedWorkbenchStage.value = 'foundation'
  workspaceView.value = 'categories'
}

function openCoursePreview() {
  void router.push({
    name: 'learning',
    params: { courseId: courseId.value, ...(selectedContext.value.lessonId ? { nodeId: selectedContext.value.lessonId } : {}) },
    query: { teacherPreview: '1', returnTo: route.fullPath },
  })
}

async function handlePreparationCompleted(payload?: { openAudit?: boolean }) {
  materialRefreshToken.value += 1
  if (route.query.prepare) await router.replace({ query: { ...route.query, prepare: undefined } })
  if (payload?.openAudit) openMaterialAudit()
}

watch(courseId, (value, previous) => {
  if (previous && previous !== value) generationStore.unobserveCourse(previous)
  if (value && value !== previous) void loadWorkspace()
})
watch(
  [
    () => courseId.value,
    () => generationStore.getTask(courseId.value)?.status || '',
    () => lessonStore.jobs.map(job => `${job.id}:${job.status}`).join('|'),
  ],
  ([currentCourseId], previous) => {
    if (!currentCourseId || currentCourseId !== previous?.[0] || loading.value) return
    void courseStore.fetchTeacherCourseProductionState(currentCourseId).catch(() => undefined)
  },
)
onMounted(loadWorkspace)
onBeforeUnmount(() => { if (courseId.value) generationStore.unobserveCourse(courseId.value) })
</script>

<style scoped>
.course-workspace-page { height:100%; min-height:0; overflow:hidden; color:var(--lz-text-strong); background:transparent; }
.workspace-operating-shell { position:relative; width:100%; height:100%; min-width:0; min-height:0; display:grid; grid-template-columns:minmax(0,1fr); overflow:hidden; background:transparent; }
.workspace-operating-shell > :deep(.file-space) { min-width:0; min-height:0; }
.workspace-load-enter-active,.workspace-surface-enter-active { transition:opacity .2s cubic-bezier(.16,1,.3,1),transform .22s cubic-bezier(.16,1,.3,1); }
.workspace-load-leave-active,.workspace-surface-leave-active { transition:opacity .11s ease-in,transform .13s ease-in; }
.workspace-load-enter-from,.workspace-surface-enter-from { opacity:0; transform:translateY(6px); }
.workspace-load-leave-to,.workspace-surface-leave-to { opacity:0; transform:translateY(-3px); }
.workspace-route-context { min-width:0; display:flex; align-items:center; gap:9px; }
.workspace-route-context>svg { flex:none; color:var(--lz-brand); }
.workspace-route-context>h1 { min-width:0; margin:0; overflow:hidden; color:var(--lz-text-strong); font-family:inherit; font-size:22px; font-weight:800; letter-spacing:-.012em; line-height:1.2; text-overflow:ellipsis; white-space:nowrap; }
.back-button { display:inline-flex; align-items:center; justify-content:center; gap:7px; border:0; background:transparent; color:var(--lz-text-secondary); font-size:15px; font-weight:700; cursor:pointer; }
.back-button { width:34px; height:34px; flex:none; border-radius:8px; }
.back-button:hover { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.back-button:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.workspace-view-switch { display:flex; align-items:center; justify-content:center; gap:3px; width:max-content; margin:auto; padding:3px; border:1px solid var(--lz-border); border-radius:10px; background:#f5f6fa; }
.workspace-view-switch button { height:32px; display:inline-flex; align-items:center; gap:6px; padding:0 11px; border:0; border-radius:7px; color:var(--lz-text-secondary); background:transparent; font-size:15px; font-weight:700; cursor:pointer; }
.workspace-view-switch button:hover { color:var(--lz-text-strong); }
.workspace-view-switch button.active { color:var(--lz-brand-strong); background:#fff; box-shadow:0 2px 7px rgba(15,23,42,.08); }
.workspace-view-switch button:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.workspace-route-actions { display:flex; align-items:center; gap:8px; }
.workspace-search { height:38px; display:flex; align-items:center; gap:7px; padding:0 9px; border:1px solid var(--lz-border); border-radius:9px; color:var(--lz-text-muted); background:#f8fafc; }
.workspace-search--popover { width:100%; }
.workspace-search:focus-within { border-color:var(--lz-brand); background:#fff; box-shadow:0 0 0 3px var(--lz-brand-soft); }
.workspace-search input { min-width:0; flex:1; border:0; outline:0; color:var(--lz-text-strong); background:transparent; font-size:14px; }
.workspace-search button { width:24px; min-height:24px; padding:0; border:0; background:transparent; }
.workspace-state { flex:none; padding:4px 7px; border-radius:6px; background:#f1f5f9; color:#64748b; font-size:14px; font-weight:700; white-space:nowrap; }
.workspace-state[data-state="prepared"] { background:#ecfdf5; color:#047857; }
.workspace-state[data-state="preparing"] { background:#eef2ff; color:#4f46e5; }
.workspace-loading { min-height:360px; display:flex; align-items:center; justify-content:center; gap:10px; color:var(--lz-text-secondary); }
.workspace-error { min-height:360px; display:grid; place-items:center; padding:28px; }
.workspace-error :deep(.app-error-notice) { width:min(620px,100%); }
.drawer-empty { min-height:240px; display:grid; place-items:center; color:var(--lz-text-muted); }
:global(.teaching-calendar-drawer .el-drawer__body) { min-height:0; overflow:hidden; padding:0; }
.global-change-choice { position:fixed; inset:0; z-index:1400; display:grid; place-items:center; padding:24px; }
.global-change-choice__backdrop { position:absolute; inset:0; width:100%; height:100%; border:0; background:rgba(15,23,42,.42); cursor:default; }
.global-change-choice__panel { position:relative; width:min(560px,100%); padding:30px; border:1px solid var(--lz-border); border-radius:12px; color:var(--lz-text-strong); background:#fff; box-shadow:0 24px 70px rgba(15,23,42,.2); }
.global-change-choice__panel header small { color:var(--lz-brand-strong); font-size:13px; font-weight:700; }
.global-change-choice__panel h2 { margin:7px 0 6px; font-size:24px; line-height:1.35; }
.global-change-choice__panel header p { margin:0 0 22px; color:var(--lz-text-secondary); font-size:15px; line-height:1.6; }
.global-change-choice__options { display:grid; gap:10px; padding:20px; }
.global-change-choice__options button { display:grid; grid-template-columns:40px minmax(0,1fr) 18px; align-items:center; gap:12px; min-height:70px; padding:12px 14px; border:1px solid var(--lz-border); border-radius:8px; color:var(--lz-text-primary); background:#fff; text-align:left; cursor:pointer; }
.global-change-choice__options button:hover { border-color:var(--lz-brand); background:var(--lz-brand-soft); }
.global-change-choice__options button:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.global-change-choice__options button>span:nth-child(2) { display:grid; gap:3px; }
.global-change-choice__options strong { font-size:16px; }
.global-change-choice__options small { color:var(--lz-text-secondary); font-size:14px; }
.choice-icon { width:36px; height:36px; display:grid; place-items:center; border-radius:8px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.global-change-choice__options button>svg { color:var(--lz-text-muted); }
.spin { animation:spin 1s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:720px) {
  .workspace-route-context { display:flex; gap:6px; }
  .workspace-route-context>svg,.workspace-state { display:none; }
  .workspace-route-context>h1 { max-width:52vw; font-size:16px; }
  .workspace-view-switch button { width:34px; padding:0; }
  .workspace-view-switch button svg { margin:auto; }
  .workspace-view-switch button { font-size:0; }
  .workspace-route-actions { gap:5px; }
}
@media (min-width:721px) and (max-width:1180px) {
  .workspace-route-context>h1 { max-width:280px; }
  .workspace-state { display:none; }
}
@media (prefers-reduced-motion:reduce) {
  .spin { animation:none; }
  .workspace-load-enter-active,.workspace-load-leave-active,
  .workspace-surface-enter-active,.workspace-surface-leave-active { transition:none; }
  .workspace-load-enter-from,.workspace-load-leave-to,
  .workspace-surface-enter-from,.workspace-surface-leave-to { transform:none; }
}
@media (max-width:560px) {
  .global-change-choice { padding:16px; }
  .global-change-choice__panel { padding:22px; }
  .global-change-choice__panel h2 { font-size:21px; }
}
</style>
