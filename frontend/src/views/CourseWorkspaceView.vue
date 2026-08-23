<template>
  <main class="course-workspace-page">
    <Teleport to="#app-header-route-context">
      <div class="workspace-route-context">
        <button class="back-button" type="button" :aria-label="t('courseFiles.backToCourses')" @click="backToSource">
          <ArrowLeft :size="17" />
        </button>
        <FolderOpen :size="18" />
        <h1>{{ courseTitle || t('courseFiles.untitledCourse') }}</h1>
        <small class="workspace-state" :data-state="courseState">{{ courseStateLabel }}</small>
      </div>
    </Teleport>

    <Teleport to="#app-header-route-center">
      <nav class="workspace-view-switch" :aria-label="t('courseFiles.views.label')">
        <button type="button" :class="{ active: workspaceView === 'categories' }" @click="workspaceView = 'categories'">
          <LayoutGrid :size="15" />{{ t('courseFiles.views.categories') }}
        </button>
        <button type="button" :class="{ active: workspaceView === 'files' }" @click="workspaceView = 'files'">
          <FolderTree :size="15" />{{ t('courseFiles.views.files') }}
        </button>
      </nav>
    </Teleport>

    <Teleport to="#app-header-route-actions">
      <div class="workspace-route-actions">
        <label v-if="workspaceView === 'files'" class="workspace-search workspace-search--inline">
          <Search :size="15" />
          <input v-model="searchQuery" type="search" :placeholder="t('courseFiles.searchCurrent')" :aria-label="t('courseFiles.searchCurrent')" />
          <button v-if="searchQuery" type="button" :aria-label="t('courseFiles.clearSearch')" @click="searchQuery = ''"><X :size="14" /></button>
        </label>
        <el-popover v-if="workspaceView === 'files'" placement="bottom-end" :width="280" trigger="click">
          <template #reference>
            <button class="search-action" type="button" :title="t('courseFiles.searchCurrent')" :aria-label="t('courseFiles.searchCurrent')"><Search :size="16" /></button>
          </template>
          <label class="workspace-search workspace-search--popover">
            <Search :size="15" />
            <input v-model="searchQuery" type="search" :placeholder="t('courseFiles.searchCurrent')" :aria-label="t('courseFiles.searchCurrent')" />
            <button v-if="searchQuery" type="button" :aria-label="t('courseFiles.clearSearch')" @click="searchQuery = ''"><X :size="14" /></button>
          </label>
        </el-popover>
        <button
          class="adjustment-action"
          type="button"
          :title="t('courseEvolution.workspace.openHint', '在独立工作区生成并审阅课程更新')"
          @click="openCourseAdjustment()"
        >
          <GitBranchPlus :size="16" />{{ t('courseEvolution.workspace.open', '调整课程') }}
        </button>
        <button class="preview-action" type="button" @click="openCoursePreview"><Eye :size="16" />{{ t('courseFiles.previewCourse') }}</button>
      </div>
    </Teleport>

    <section v-if="loading" class="workspace-loading" role="status">
      <LoaderCircle :size="22" class="spin" />{{ t('courseFiles.loading') }}
    </section>
    <section v-else-if="loadError" class="workspace-loading is-error" role="alert">
      <TriangleAlert :size="22" /><strong>{{ t('courseFiles.loadFailed') }}</strong><span>{{ loadError }}</span>
      <button type="button" @click="loadWorkspace">{{ t('common.retry') }}</button>
    </section>
    <section v-else class="workspace-operating-shell">
      <TeacherCourseWorkbench
        v-if="workspaceView === 'categories'"
        :course-id="courseId"
        :course-title="courseTitle"
        :generation-options="courseGenerationOptions"
        :generation-starting="generationStarting"
        :initial-stage="requestedWorkbenchStage"
        :initial-lesson-id="requestedLessonId"
        v-model:outline-editing="outlineEditing"
        @generate-outline="startOutlineGeneration"
        @outline-confirmed="handleOutlineConfirmed"
      />
      <TeacherCourseSpaceView
        v-else
        embedded
        :course-id="courseId"
        :course-title="courseTitle"
        workspace-view="files"
        v-model:query="searchQuery"
        @open-outline="openOutlineEditor"
        @create-outline="prepareOutlineGeneration"
        @open-teaching-calendar="calendarOpen = true"
        @open-teaching-plan="openLessonPlan"
        @open-tasks="openTasks"
        @open-practice="openPractice"
        @open-script="openScript"
        @open-ppt="openPpt"
        @open-question-bank="openQuestionBankWorkbench"
        @open-companion-documents="openCompanionDocuments"
        @context-change="selectedContext = $event"
        @readiness-change="readiness = $event"
      />
    </section>

    <el-drawer v-model="calendarOpen" class="teaching-calendar-drawer" size="min(1500px, 98vw)" :title="t('courseFiles.calendarDrawerTitle')">
      <TeacherCourseCalendarView embedded />
    </el-drawer>

    <CourseWorkbench
      v-model="workbenchOpen"
      :course-id="courseId"
      surface="teacher"
    />

    <CourseEvolutionWorkspace
      v-model="courseAdjustmentOpen"
      :course-id="courseId"
      :course-title="courseTitle"
      :section-id="courseAdjustmentSectionId"
      :section-title="courseAdjustmentSectionTitle"
      :focus-plan-id="courseAdjustmentFocusPlanId"
      @course-applied="handleCourseAdjustmentApplied"
    />

  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Eye, FolderOpen, FolderTree, GitBranchPlus, LayoutGrid, LoaderCircle, Search, TriangleAlert, X } from 'lucide-vue-next'
import CourseEvolutionWorkspace from '../components/CourseEvolutionWorkspace.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import TeacherCourseWorkbench from '../components/TeacherCourseWorkbench.vue'
import TeacherCourseCalendarView from './TeacherCourseCalendarView.vue'
import TeacherCourseSpaceView from './TeacherCourseSpaceView.vue'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'
import http, { teacherRequestConfig } from '../utils/http'

const props = defineProps<{ courseId: string; mode?: string }>()
const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const lessonStore = useTeacherLessonAuthoringStore()
const loading = ref(true)
const loadError = ref('')
const outlineEditing = ref(false)
const calendarOpen = ref(false)
const workbenchOpen = ref(false)
const courseAdjustmentOpen = ref(false)
const courseAdjustmentFocusPlanId = ref('')
const courseAdjustmentSectionId = ref('')
const generationStarting = ref(false)
const selectedContext = ref({ lessonId: '', nodeId: '', label: '', type: '', path: '' })
const readiness = ref({ required: 0, ready: 0, pending: 0 })
const workspaceView = ref<'files' | 'categories'>('categories')
const requestedWorkbenchStage = ref<'foundation' | 'lesson' | 'question-bank' | 'script' | 'ppt' | 'companion'>('foundation')
const requestedLessonId = ref('')
const searchQuery = ref('')
const courseGenerationOptions = ref<CourseGenerationOptions & { subject?: string }>({})
const stableCourseTitle = ref('')

const courseId = computed(() => String(props.courseId || route.params.courseId || ''))
const courseTitle = computed(() => (
  courseStore.courseList.find(item => item.course_id === courseId.value)?.course_name
  || stableCourseTitle.value
  || courseStore.currentCourse?.course_name
  || ''
))
const generationTask = computed(() => generationStore.getTask(courseId.value))
const courseState = computed(() => {
  const status = String(generationTask.value?.status || courseStore.currentCourse?.generation_status || '')
  if (status === 'waiting_for_review') return 'review'
  if (['running', 'pending', 'paused'].includes(status)) return 'working'
  if (['failed', 'error', 'conflict'].includes(status)) return 'attention'
  if (readiness.value.required && readiness.value.pending) return 'draft'
  return courseStore.currentDocumentRevision ? 'ready' : 'draft'
})
const courseStateLabel = computed(() => t(`courseFiles.states.${courseState.value}`))
const courseAdjustmentSectionTitle = computed(() => (
  courseStore.nodes.find(node => node.node_id === courseAdjustmentSectionId.value)?.node_name || ''
))

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
  generationStore.observeCourse(courseId.value)
  loading.value = true
  loadError.value = ''
  try {
    await Promise.all([
      courseStore.fetchCourseList({ surface: 'teacher' }),
      generationStore.fetchGlobalTasks(),
    ])
    stableCourseTitle.value = courseStore.courseList.find(
      item => item.course_id === courseId.value,
    )?.course_name || stableCourseTitle.value
    await courseStore.loadCourse(courseId.value, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true })
    await lessonStore.load(courseId.value).catch(() => undefined)
    const courseResponse = await http.get(
      `/api/courses/${courseId.value}`,
      teacherRequestConfig({ silentError: true }),
    ).catch(() => ({ data: {} }))
    courseGenerationOptions.value = courseResponse.data?.generation_request || {}
    stableCourseTitle.value = String(
      courseResponse.data?.course_name || stableCourseTitle.value,
    )
    await nextTick()
    const requestedSection = String(route.query.section || '')
    const requestedStage = String(route.query.stage || '')
    if (['foundation', 'lesson', 'question-bank', 'script', 'ppt', 'companion'].includes(requestedStage)) {
      requestedWorkbenchStage.value = requestedStage as typeof requestedWorkbenchStage.value
    }
    requestedLessonId.value = String(route.query.lesson || '')
    if (requestedSection === 'outline') openOutlineEditor()
    if (requestedSection === 'calendar') calendarOpen.value = true
    if (route.query.generate === 'outline') {
      prepareOutlineGeneration()
      void router.replace({ query: { ...route.query, generate: undefined } })
    }
  } catch (error: any) {
    loadError.value = String(error?.response?.data?.detail || error?.message || t('courseFiles.loadFailed'))
  } finally {
    loading.value = false
  }
}

function openLessonPlan(lessonId: string) {
  requestedWorkbenchStage.value = 'lesson'
  requestedLessonId.value = lessonId
  workspaceView.value = 'categories'
}

function openOutlineEditor() {
  requestedWorkbenchStage.value = 'foundation'
  workspaceView.value = 'categories'
  outlineEditing.value = true
}

function openQuestionBankWorkbench() {
  requestedWorkbenchStage.value = 'question-bank'
  workspaceView.value = 'categories'
}

function openCompanionDocuments() {
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
  requestedWorkbenchStage.value = 'ppt'
  requestedLessonId.value = lessonId
  workspaceView.value = 'categories'
}

function openScript(lessonId: string) {
  requestedWorkbenchStage.value = 'script'
  requestedLessonId.value = lessonId
  workspaceView.value = 'categories'
}

function openTasks() {
  workbenchOpen.value = true
}

function resolveAdjustmentSectionId(preferred = '') {
  for (const candidateId of [preferred, selectedContext.value.lessonId, selectedContext.value.nodeId]) {
    if (!candidateId) continue
    const candidate = courseStore.nodes.find(node => node.node_id === candidateId)
    if (candidate && Number(candidate.node_level || 0) >= 2) return candidate.node_id
    const child = courseStore.nodes.find(node => (
      node.parent_node_id === candidateId
      && Number(node.node_level || 0) >= 2
    ))
    if (child) return child.node_id
  }
  return courseStore.nodes.find(node => (
    Number(node.node_level || 0) >= 2
    && Boolean(node.node_content || node.course_blocks?.length || node.content_blocks?.length)
  ))?.node_id || courseStore.nodes.find(node => Number(node.node_level || 0) >= 2)?.node_id || ''
}

function openCourseAdjustment(payload?: { planId?: string; sectionId?: string }) {
  courseAdjustmentFocusPlanId.value = payload?.planId || ''
  courseAdjustmentSectionId.value = resolveAdjustmentSectionId(payload?.sectionId)
  courseAdjustmentOpen.value = true
}

async function handleCourseAdjustmentApplied() {
  await loadWorkspace()
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

async function handleOutlineConfirmed() {
  outlineEditing.value = false
  await Promise.all([
    courseStore.loadCourse(courseId.value, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true }),
    lessonStore.load(courseId.value).catch(() => undefined),
  ])
  requestedWorkbenchStage.value = 'lesson'
}

watch(courseId, (value, previous) => {
  if (previous && previous !== value) generationStore.unobserveCourse(previous)
  if (value && value !== previous) void loadWorkspace()
})
onMounted(loadWorkspace)
onBeforeUnmount(() => { if (courseId.value) generationStore.unobserveCourse(courseId.value) })
</script>

<style scoped>
.course-workspace-page { height:100%; min-height:0; overflow:hidden; color:var(--lz-text-strong); background:#f3f5f9; }
.workspace-operating-shell { position:relative; width:100%; height:100%; min-width:0; min-height:0; display:grid; grid-template-columns:minmax(0,1fr); overflow:hidden; background:#f3f5f9; }
.workspace-operating-shell > :deep(.file-space) { min-width:0; min-height:0; }
.workspace-route-context { min-width:0; display:flex; align-items:center; gap:9px; }
.workspace-route-context>svg { flex:none; color:var(--lz-brand); }
.workspace-route-context>h1 { min-width:0; margin:0; overflow:hidden; color:var(--lz-text-strong); font-family:inherit; font-size:18px; font-weight:800; letter-spacing:-.012em; line-height:1.2; text-overflow:ellipsis; white-space:nowrap; }
.back-button,.workspace-route-actions button { display:inline-flex; align-items:center; justify-content:center; gap:7px; border:0; background:transparent; color:var(--lz-text-secondary); font-size:13px; font-weight:700; cursor:pointer; }
.back-button { width:34px; height:34px; flex:none; border-radius:8px; }
.back-button:hover { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.back-button:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.workspace-view-switch { display:flex; align-items:center; justify-content:center; gap:3px; width:max-content; margin:auto; padding:3px; border:1px solid var(--lz-border); border-radius:10px; background:#f5f6fa; }
.workspace-view-switch button { height:32px; display:inline-flex; align-items:center; gap:6px; padding:0 11px; border:0; border-radius:7px; color:var(--lz-text-secondary); background:transparent; font-size:12px; font-weight:700; cursor:pointer; }
.workspace-view-switch button:hover { color:var(--lz-text-strong); }
.workspace-view-switch button.active { color:var(--lz-brand-strong); background:#fff; box-shadow:0 2px 7px rgba(15,23,42,.08); }
.workspace-view-switch button:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.workspace-route-actions { display:flex; align-items:center; gap:8px; }
.workspace-route-actions button { min-height:38px; padding:0 11px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; white-space:nowrap; }
.workspace-search { height:38px; display:flex; align-items:center; gap:7px; padding:0 9px; border:1px solid var(--lz-border); border-radius:9px; color:var(--lz-text-muted); background:#f8fafc; }
.workspace-search--inline { width:clamp(160px,16vw,240px); }
.workspace-search--popover { width:100%; }
.workspace-search:focus-within { border-color:var(--lz-brand); background:#fff; box-shadow:0 0 0 3px var(--lz-brand-soft); }
.workspace-search input { min-width:0; flex:1; border:0; outline:0; color:var(--lz-text-strong); background:transparent; font-size:12px; }
.workspace-search button { width:24px; min-height:24px; padding:0; border:0; background:transparent; }
.workspace-route-actions .search-action { display:none; width:38px; padding:0; }
.workspace-route-actions .adjustment-action { border-color:#d7d9ff; color:#5148dc; background:#f8f8ff; }
.workspace-route-actions .adjustment-action:hover { border-color:#8580f5; background:#f0f0ff; }
.workspace-route-actions .preview-action { color:var(--lz-brand-strong); border-color:var(--lz-brand-border); }
.workspace-state { flex:none; padding:4px 7px; border-radius:6px; background:#f1f5f9; color:#64748b; font-size:12px; font-weight:700; white-space:nowrap; }
.workspace-state[data-state="ready"] { background:#ecfdf5; color:#047857; }
.workspace-state[data-state="review"] { background:#fff7ed; color:#c2410c; }
.workspace-state[data-state="working"] { background:#eef2ff; color:#4f46e5; }
.workspace-state[data-state="attention"] { background:#fff7ed; color:#c2410c; }
.workspace-loading { min-height:360px; display:flex; align-items:center; justify-content:center; gap:10px; color:var(--lz-text-secondary); }
.workspace-loading.is-error { flex-direction:column; color:#b91c1c; }
.workspace-loading button { padding:7px 12px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; }
.drawer-empty { min-height:240px; display:grid; place-items:center; color:var(--lz-text-muted); }
:global(.teaching-calendar-drawer .el-drawer__body) { min-height:0; overflow:hidden; padding:0; }
.spin { animation:spin 1s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:1050px) {
  .workspace-route-actions>button { width:38px; padding:0; font-size:0; }
  .workspace-route-actions>button svg { margin:auto; }
}
@media (max-width:720px) {
  .workspace-route-context { display:flex; gap:6px; }
  .workspace-route-context>svg,.workspace-state { display:none; }
  .workspace-route-context>h1 { max-width:52vw; font-size:16px; }
  .workspace-view-switch button { width:34px; padding:0; }
  .workspace-view-switch button svg { margin:auto; }
  .workspace-view-switch button { font-size:0; }
  .workspace-route-actions { gap:5px; }
  .workspace-route-actions>button { width:36px; padding:0; font-size:0; }
  .workspace-route-actions>button svg { margin:auto; }
}
@media (max-width:1500px) {
  .workspace-search--inline { display:none; }
  .workspace-route-actions .search-action { display:inline-flex; }
}
@media (min-width:721px) and (max-width:1180px) {
  .workspace-route-context>h1 { max-width:280px; }
  .workspace-state { display:none; }
}
</style>
