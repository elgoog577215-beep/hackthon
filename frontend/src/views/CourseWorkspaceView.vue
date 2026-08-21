<template>
  <main class="course-workspace-page">
    <Teleport to="#app-header-route-actions">
      <div class="workspace-route-actions">
        <button class="agent-action" type="button" @click="agentOpen = true"><Sparkles :size="16" />{{ t('courseFiles.teacherAgent') }}</button>
        <button class="preview-action" type="button" @click="openCoursePreview"><Eye :size="16" />{{ t('courseFiles.previewCourse') }}</button>
        <button class="task-action" type="button" :title="t('courseFiles.taskCenter')" :aria-label="t('courseFiles.taskCenter')" @click="openTasks"><ListTodo :size="16" /></button>
      </div>
    </Teleport>

    <header class="workspace-local-header">
      <button class="back-button" type="button" @click="router.push({ name: 'course-library' })">
        <ArrowLeft :size="17" /><span>{{ t('courseFiles.backToCalendar') }}</span>
      </button>
      <div class="workspace-title">
        <FolderOpen :size="16" />
        <strong>{{ courseTitle || t('courseFiles.untitledCourse') }}</strong>
        <small class="workspace-state" :data-state="courseState">{{ courseStateLabel }}</small>
      </div>
    </header>

    <section v-if="loading" class="workspace-loading" role="status">
      <LoaderCircle :size="22" class="spin" />{{ t('courseFiles.loading') }}
    </section>
    <section v-else-if="loadError" class="workspace-loading is-error" role="alert">
      <TriangleAlert :size="22" /><strong>{{ t('courseFiles.loadFailed') }}</strong><span>{{ loadError }}</span>
      <button type="button" @click="loadWorkspace">{{ t('common.retry') }}</button>
    </section>
    <TeacherCourseSpaceView
      v-else
      embedded
      :course-id="courseId"
      :course-title="courseTitle"
      @open-outline="outlineOpen = true"
      @create-outline="generationDialogOpen = true"
      @open-teaching-plan="openLessonPlan"
      @open-tasks="openTasks"
      @open-practice="openPractice"
      @context-change="selectedContext = $event"
      @readiness-change="readiness = $event"
    />

    <el-drawer v-model="outlineOpen" size="min(1040px, 92vw)" :title="t('courseFiles.outlineEditor')" destroy-on-close>
      <CourseOutlineReview
        :course-id="courseId"
        :course-name="courseTitle"
        :nodes="courseStore.nodes"
        :task="generationTask"
        @confirmed="handleOutlineConfirmed"
      />
    </el-drawer>

    <el-drawer v-model="lessonOpen" size="min(1120px, 94vw)" :title="selectedLessonTitle" destroy-on-close>
      <GenerationLessonPlan
        v-if="selectedLessonPlan"
        :plan="selectedLessonPlan"
        :nodes="courseStore.nodes"
        :lesson-unit-id="selectedLessonId"
        :course-id="courseId"
        prefer-provided-plan
        prefer-section-view
        embedded
      />
      <div v-else class="drawer-empty">{{ t('courseFiles.lessonPlanUnavailable') }}</div>
    </el-drawer>

    <CourseWorkbench
      v-model="workbenchOpen"
      :course-id="courseId"
      surface="teacher"
    />
    <CourseGenerationDialog
      v-model="generationDialogOpen"
      :busy="generationStarting"
      :initial-subject="courseTitle"
      @generate="startOutlineGeneration"
    />

    <div v-if="agentOpen" class="teacher-agent-host">
      <SideAIPanel
        :visible="agentOpen"
        mode="teacher"
        :quote-text="agentContextText"
        :quote-node-id="selectedContext.lessonId"
        :entrypoint="selectedContext.nodeId ? 'selection' : 'global'"
        :scope-files="teacherAssistantFiles"
        @close="agentOpen = false"
        @block-applied="loadWorkspace"
        @course-applied="loadWorkspace"
      />
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Eye, FolderOpen, ListTodo, LoaderCircle, Sparkles, TriangleAlert } from 'lucide-vue-next'
import CourseOutlineReview from '../components/CourseOutlineReview.vue'
import CourseGenerationDialog from '../components/CourseGenerationDialog.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import GenerationLessonPlan from '../components/GenerationLessonPlan.vue'
import SideAIPanel from '../components/SideAIPanel.vue'
import TeacherCourseSpaceView from './TeacherCourseSpaceView.vue'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'

const props = defineProps<{ courseId: string; mode?: string }>()
const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const lessonStore = useTeacherLessonAuthoringStore()
const loading = ref(true)
const loadError = ref('')
const outlineOpen = ref(false)
const lessonOpen = ref(false)
const selectedLessonId = ref('')
const workbenchOpen = ref(false)
const agentOpen = ref(false)
const generationDialogOpen = ref(false)
const generationStarting = ref(false)
const selectedContext = ref({ lessonId: '', nodeId: '', label: '', type: '', path: '' })
const readiness = ref({ required: 0, ready: 0, pending: 0 })

const courseId = computed(() => String(props.courseId || route.params.courseId || ''))
const courseTitle = computed(() => courseStore.courseList.find(item => item.course_id === courseId.value)?.course_name || courseStore.currentCourse?.course_name || '')
const generationTask = computed(() => generationStore.getTask(courseId.value))
const courseState = computed(() => {
  const status = String(generationTask.value?.status || courseStore.currentCourse?.generation_status || '')
  if (['running', 'pending', 'paused', 'waiting_for_review'].includes(status)) return 'working'
  if (['failed', 'error', 'conflict'].includes(status)) return 'attention'
  if (readiness.value.required && readiness.value.pending) return 'draft'
  return courseStore.currentDocumentRevision ? 'ready' : 'draft'
})
const courseStateLabel = computed(() => t(`courseFiles.states.${courseState.value}`))
const selectedLesson = computed(() => lessonStore.lessons.find(item => item.lesson_unit_id === selectedLessonId.value))
const selectedLessonPlan = computed(() => selectedLesson.value?.plan?.revisions.find(item => item.revision_id === selectedLesson.value?.plan.working_revision_id)?.plan as any || null)
const selectedLessonTitle = computed(() => selectedLesson.value
  ? t('courseFiles.lessonDrawerTitle').replace('{title}', selectedLesson.value.title)
  : t('courseFiles.lessonPlan'))
const agentContextText = computed(() => selectedContext.value.nodeId
  ? t('courseFiles.agentContext')
    .replace('{label}', selectedContext.value.label)
    .replace('{path}', selectedContext.value.path || t('courseFiles.rootName'))
  : '')
const teacherAssistantFiles = computed(() => courseStore.nodes
  .filter(node => Number(node.node_level || 0) === 2 && Boolean(node.node_content || node.content_blocks?.length))
  .map(node => {
    const parent = courseStore.nodes.find(candidate => candidate.node_id === node.parent_node_id)
    return {
      id: node.node_id,
      nodeId: node.node_id,
      label: node.node_name,
      path: parent ? `${parent.node_name} / ${node.node_name}` : node.node_name,
    }
  }))

async function loadWorkspace() {
  if (!courseId.value) return
  loading.value = true
  loadError.value = ''
  try {
    await Promise.all([
      courseStore.fetchCourseList({ surface: 'teacher' }),
      generationStore.fetchGlobalTasks(),
    ])
    await courseStore.loadCourse(courseId.value, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true })
    await lessonStore.load(courseId.value).catch(() => undefined)
    await nextTick()
    const requestedSection = String(route.query.section || '')
    if (requestedSection === 'outline') outlineOpen.value = true
  } catch (error: any) {
    loadError.value = String(error?.response?.data?.detail || error?.message || t('courseFiles.loadFailed'))
  } finally {
    loading.value = false
  }
}

function openLessonPlan(lessonId: string) {
  selectedLessonId.value = lessonId
  lessonOpen.value = true
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

function openTasks() {
  workbenchOpen.value = true
}

async function startOutlineGeneration(payload: { subject: string; options: CourseGenerationOptions }) {
  if (generationStarting.value) return
  generationStarting.value = true
  try {
    const result = await courseStore.generateCourse(payload.subject || courseTitle.value, {
      ...payload.options,
      target_course_id: courseId.value,
      teacher_authoring_mode: 'lesson_assets_v1',
    })
    if (!result?.courseId) return
    generationDialogOpen.value = false
    await loadWorkspace()
    openTasks()
  } finally {
    generationStarting.value = false
  }
}

function openCoursePreview() {
  void router.push({
    name: 'learning',
    params: { courseId: courseId.value, ...(selectedContext.value.lessonId ? { nodeId: selectedContext.value.lessonId } : {}) },
    query: { teacherPreview: '1', returnTo: route.fullPath },
  })
}

async function handleOutlineConfirmed() {
  await Promise.all([
    courseStore.loadCourse(courseId.value, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true }),
    lessonStore.load(courseId.value).catch(() => undefined),
  ])
}

watch(courseId, (value, previous) => { if (value && value !== previous) void loadWorkspace() })
onMounted(loadWorkspace)
</script>

<style scoped>
.course-workspace-page { height:100%; min-height:0; display:grid; grid-template-rows:58px minmax(0,1fr); overflow:hidden; color:var(--lz-text-strong); }
.workspace-local-header { display:flex; align-items:center; gap:16px; padding:0 16px; border-bottom:1px solid var(--lz-border); background:#fff; }
.back-button,.workspace-route-actions button { display:inline-flex; align-items:center; justify-content:center; gap:7px; border:0; background:transparent; color:var(--lz-text-secondary); font-size:13px; font-weight:700; cursor:pointer; }
.workspace-title { min-width:0; display:flex; align-items:center; gap:8px; }
.workspace-title>svg { flex:none; color:#64748b; }
.workspace-title strong { overflow:hidden; color:var(--lz-text-strong); font-size:15px; text-overflow:ellipsis; white-space:nowrap; }
.workspace-route-actions { display:flex; align-items:center; gap:8px; }
.workspace-route-actions button { min-height:38px; padding:0 11px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; white-space:nowrap; }
.workspace-route-actions .agent-action { border-color:var(--lz-brand); color:#fff; background:var(--lz-brand); }
.workspace-route-actions .preview-action { color:var(--lz-brand-strong); border-color:var(--lz-brand-border); }
.workspace-route-actions .task-action { width:38px; padding:0; }
.workspace-state { padding:4px 7px; border-radius:6px; background:#f1f5f9; color:#64748b; font-size:12px; font-weight:700; }
.workspace-state[data-state="ready"] { background:#ecfdf5; color:#047857; }
.workspace-state[data-state="working"] { background:#eef2ff; color:#4f46e5; }
.workspace-state[data-state="attention"] { background:#fff7ed; color:#c2410c; }
.workspace-loading { min-height:360px; display:flex; align-items:center; justify-content:center; gap:10px; color:var(--lz-text-secondary); }
.workspace-loading.is-error { flex-direction:column; color:#b91c1c; }
.workspace-loading button { padding:7px 12px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; }
.drawer-empty { min-height:240px; display:grid; place-items:center; color:var(--lz-text-muted); }
.teacher-agent-host { position:fixed; z-index:610; inset:0; width:100vw; height:100dvh; }
.teacher-agent-host :deep(.ai-teacher-panel) { width:100%; height:100%; }
.spin { animation:spin 1s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:720px) {
  .course-workspace-page { grid-template-rows:52px minmax(0,1fr); }
  .workspace-local-header { padding:0 10px; gap:10px; }
  .back-button span { display:none; }
  .workspace-title small { display:none; }
  .workspace-route-actions { gap:5px; }
  .workspace-route-actions button { padding:0 8px; font-size:12px; }
  .workspace-route-actions .task-action { display:none; }
  .teacher-agent-host { position:fixed; inset:0; width:100vw; height:100dvh; }
}
</style>
