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

    <Transition name="workspace-load" mode="out-in">
      <section v-if="loading" key="loading" class="workspace-loading" role="status">
        <LoaderCircle :size="22" class="spin" />{{ t('courseFiles.loading') }}
      </section>
      <section v-else-if="loadError" key="error" class="workspace-error">
        <AppErrorNotice :presentation="loadError">
          <template #action><button type="button" @click="loadWorkspace">{{ t('common.retry') }}</button></template>
        </AppErrorNotice>
      </section>
      <section v-else key="ready" class="workspace-operating-shell">
        <Transition name="workspace-surface" mode="out-in">
          <TeacherCourseWorkbench
            v-if="workspaceView === 'categories'"
            key="categories"
            :course-id="courseId"
            :course-title="courseTitle"
            :generation-options="courseGenerationOptions"
            :generation-starting="generationStarting"
            :initial-stage="requestedWorkbenchStage"
            :initial-lesson-id="requestedLessonId"
            v-model:outline-editing="outlineEditing"
            @generate-outline="startOutlineGeneration"
            @outline-confirmed="handleOutlineConfirmed"
            @open-course-information="courseInformationOpen = true"
          />
          <TeacherCourseSpaceView
            v-else
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
            @open-tasks="openTasks"
            @open-practice="openPractice"
            @open-script="openScript"
            @open-ppt="openPpt"
            @open-question-bank="openQuestionBankWorkbench"
            @open-companion-documents="openCompanionDocuments"
            @context-change="selectedContext = $event"
            @readiness-change="readiness = $event"
            @edit-baseline="courseInformationOpen = true"
          />
        </Transition>
      </section>
    </Transition>

    <CourseBaselineDialog
      v-model="courseInformationOpen"
      :course-id="courseId"
      @updated="handleCourseInformationUpdated"
    />

    <el-drawer v-model="calendarOpen" class="teaching-calendar-drawer" size="min(1500px, 98vw)" :title="t('courseFiles.calendarDrawerTitle')">
      <TeacherCourseCalendarView embedded />
    </el-drawer>

    <CourseWorkbench
      v-model="workbenchOpen"
      :course-id="courseId"
      surface="teacher"
    />

  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Eye, FolderOpen, FolderTree, GitBranchPlus, LayoutGrid, LoaderCircle, Search, X } from 'lucide-vue-next'
import AppErrorNotice from '../components/AppErrorNotice.vue'
import CourseBaselineDialog from '../components/CourseBaselineDialog.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import TeacherCourseWorkbench from '../components/TeacherCourseWorkbench.vue'
import TeacherCourseCalendarView from './TeacherCourseCalendarView.vue'
import TeacherCourseSpaceView from './TeacherCourseSpaceView.vue'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'
import { coursePreparationLabel, coursePreparationState } from '../utils/course-preparation'
import { toAppError, type AppErrorPresentation } from '../utils/app-error'
import http, { teacherRequestConfig } from '../utils/http'

const props = defineProps<{ courseId: string; mode?: string }>()
const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const lessonStore = useTeacherLessonAuthoringStore()
const loading = ref(true)
const loadError = ref<AppErrorPresentation | null>(null)
const outlineEditing = ref(false)
const calendarOpen = ref(false)
const workbenchOpen = ref(false)
const courseInformationOpen = ref(false)
const generationStarting = ref(false)
const selectedContext = ref({ lessonId: '', nodeId: '', label: '', type: '', path: '' })
const readiness = ref({ required: 0, ready: 0, pending: 0 })
const workspaceView = ref<'files' | 'categories'>(
  route.query.view === 'files' || route.query.prepare === '1' ? 'files' : 'categories',
)
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
const courseState = computed(() => coursePreparationState(
  courseStore.courseList.find(item => item.course_id === courseId.value) || courseStore.currentCourse,
  generationTask.value,
))
const courseStateLabel = computed(() => coursePreparationLabel(courseState.value))

function handleCourseInformationUpdated(payload: any) {
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
  if (route.query.view === 'files' || route.query.prepare === '1') workspaceView.value = 'files'
  generationStore.observeCourse(courseId.value)
  loading.value = true
  loadError.value = null
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
    loadError.value = toAppError(error, {
      title: t('courseFiles.loadFailed', '课程读取失败'),
      fallback: t('courseFiles.loadFailed', '课程读取失败'),
    })
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

function openCourseAdjustment(payload?: { planId?: string; sectionId?: string }) {
  void router.push({
    name: 'course-change-workspace',
    params: {
      courseId: courseId.value,
      ...(payload?.planId ? { planId: payload.planId } : {}),
    },
  })
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
.course-workspace-page { height:100%; min-height:0; overflow:hidden; color:var(--lz-text-strong); background:transparent; }
.workspace-operating-shell { position:relative; width:100%; height:100%; min-width:0; min-height:0; display:grid; grid-template-columns:minmax(0,1fr); overflow:hidden; background:transparent; }
.workspace-operating-shell > :deep(.file-space) { min-width:0; min-height:0; }
.workspace-load-enter-active,.workspace-surface-enter-active { transition:opacity .2s cubic-bezier(.16,1,.3,1),transform .22s cubic-bezier(.16,1,.3,1); }
.workspace-load-leave-active,.workspace-surface-leave-active { transition:opacity .11s ease-in,transform .13s ease-in; }
.workspace-load-enter-from,.workspace-surface-enter-from { opacity:0; transform:translateY(6px); }
.workspace-load-leave-to,.workspace-surface-leave-to { opacity:0; transform:translateY(-3px); }
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
.workspace-state[data-state="prepared"] { background:#ecfdf5; color:#047857; }
.workspace-state[data-state="preparing"] { background:#eef2ff; color:#4f46e5; }
.workspace-loading { min-height:360px; display:flex; align-items:center; justify-content:center; gap:10px; color:var(--lz-text-secondary); }
.workspace-error { min-height:360px; display:grid; place-items:center; padding:28px; }
.workspace-error :deep(.app-error-notice) { width:min(620px,100%); }
.drawer-empty { min-height:240px; display:grid; place-items:center; color:var(--lz-text-muted); }
:global(.teaching-calendar-drawer .el-drawer__body) { min-height:0; overflow:hidden; padding:0; }
.spin { animation:spin 1s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:1050px) {
  .workspace-route-actions>button:not(.adjustment-action) { width:38px; padding:0; font-size:0; }
  .workspace-route-actions>.adjustment-action { min-width:108px; padding:0 10px; font-size:12px; }
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
@media (prefers-reduced-motion:reduce) {
  .spin { animation:none; }
  .workspace-load-enter-active,.workspace-load-leave-active,
  .workspace-surface-enter-active,.workspace-surface-leave-active { transition:none; }
  .workspace-load-enter-from,.workspace-load-leave-to,
  .workspace-surface-enter-from,.workspace-surface-leave-to { transform:none; }
}
</style>
