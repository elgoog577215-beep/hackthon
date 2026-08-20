<template>
  <main class="course-workspace-page">
    <Teleport to="#app-header-route-actions">
      <div class="workspace-route-actions">
        <span class="same-source-state"><GitBranch :size="14" />{{ t('courseFiles.sameSource') }}</span>
        <button class="agent-action" type="button" @click="agentOpen = true"><Sparkles :size="16" />{{ t('courseFiles.teacherAgent') }}</button>
        <button class="preview-action" type="button" @click="openCoursePreview"><Eye :size="16" />{{ t('courseFiles.previewCourse') }}</button>
        <button class="task-action" type="button" :title="t('courseFiles.taskCenter')" :aria-label="t('courseFiles.taskCenter')" @click="workbenchOpen = true"><ListTodo :size="16" /></button>
      </div>
    </Teleport>

    <header class="workspace-local-header">
      <button class="back-button" type="button" @click="router.push({ name: 'course-library' })">
        <ArrowLeft :size="17" /><span>{{ t('courseFiles.backToCalendar') }}</span>
      </button>
      <div class="workspace-title">
        <span>{{ t('courseFiles.spaceLabel') }}</span>
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
      @open-teaching-plan="openLessonPlan"
      @open-tasks="workbenchOpen = true"
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

    <CourseWorkbench v-model="workbenchOpen" initial-section="tasks" :course-id="courseId" />

    <div v-if="agentOpen" class="teacher-agent-host">
      <SideAIPanel
        :visible="agentOpen"
        mode="teacher"
        quote-text=""
        quote-node-id=""
        entrypoint="global"
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
import { ArrowLeft, Eye, GitBranch, ListTodo, LoaderCircle, Sparkles, TriangleAlert } from 'lucide-vue-next'
import CourseOutlineReview from '../components/CourseOutlineReview.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import GenerationLessonPlan from '../components/GenerationLessonPlan.vue'
import SideAIPanel from '../components/SideAIPanel.vue'
import TeacherCourseSpaceView from './TeacherCourseSpaceView.vue'
import { t } from '../shared/i18n'
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

const courseId = computed(() => String(props.courseId || route.params.courseId || ''))
const courseTitle = computed(() => courseStore.courseList.find(item => item.course_id === courseId.value)?.course_name || courseStore.currentCourse?.course_name || '')
const generationTask = computed(() => generationStore.getTask(courseId.value))
const courseState = computed(() => {
  const status = String(generationTask.value?.status || courseStore.currentCourse?.generation_status || '')
  if (['running', 'pending', 'paused', 'waiting_for_review'].includes(status)) return 'working'
  if (['failed', 'error', 'conflict'].includes(status)) return 'attention'
  return courseStore.currentDocumentRevision ? 'ready' : 'draft'
})
const courseStateLabel = computed(() => t(`courseFiles.states.${courseState.value}`))
const selectedLesson = computed(() => lessonStore.lessons.find(item => item.lesson_unit_id === selectedLessonId.value))
const selectedLessonPlan = computed(() => selectedLesson.value?.plan?.revisions.find(item => item.revision_id === selectedLesson.value?.plan.working_revision_id)?.plan as any || null)
const selectedLessonTitle = computed(() => selectedLesson.value
  ? t('courseFiles.lessonDrawerTitle').replace('{title}', selectedLesson.value.title)
  : t('courseFiles.lessonPlan'))

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

function openCoursePreview() {
  void router.push({
    name: 'learning',
    params: { courseId: courseId.value },
    query: { teacherPreview: '1' },
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
.course-workspace-page { height:100%; min-height:0; display:grid; grid-template-rows:54px minmax(0,1fr); overflow:hidden; color:var(--lz-text-strong); }
.workspace-local-header { display:flex; align-items:center; gap:18px; padding:0 18px; border-bottom:1px solid var(--lz-border); background:rgba(255,255,255,.9); }
.back-button,.workspace-route-actions button { display:inline-flex; align-items:center; justify-content:center; gap:7px; border:0; background:transparent; color:var(--lz-text-secondary); font-size:12px; font-weight:700; cursor:pointer; }
.workspace-title { min-width:0; display:flex; align-items:baseline; gap:10px; }
.workspace-title span { color:var(--lz-text-muted); font-size:11px; }
.workspace-title strong { overflow:hidden; color:var(--lz-text-strong); font-size:15px; text-overflow:ellipsis; white-space:nowrap; }
.workspace-route-actions { display:flex; align-items:center; gap:8px; }
.workspace-route-actions button { min-height:34px; padding:0 9px; border:1px solid var(--lz-border); border-radius:9px; background:#fff; white-space:nowrap; }
.workspace-route-actions .agent-action { border-color:var(--lz-brand); color:#fff; background:var(--lz-brand); }
.workspace-route-actions .preview-action { color:var(--lz-brand-strong); border-color:var(--lz-brand-border); }
.workspace-route-actions .task-action { width:34px; padding:0; }
.same-source-state { display:inline-flex; align-items:center; gap:5px; color:#047857; font-size:10px; font-weight:800; white-space:nowrap; }
.workspace-state { padding:5px 8px; border-radius:999px; background:#f1f5f9; color:#64748b; font-size:11px; font-weight:700; }
.workspace-state[data-state="ready"] { background:#ecfdf5; color:#047857; }
.workspace-state[data-state="working"] { background:#eef2ff; color:#4f46e5; }
.workspace-state[data-state="attention"] { background:#fff7ed; color:#c2410c; }
.workspace-loading { min-height:360px; display:flex; align-items:center; justify-content:center; gap:10px; color:var(--lz-text-secondary); }
.workspace-loading.is-error { flex-direction:column; color:#b91c1c; }
.workspace-loading button { padding:7px 12px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; }
.drawer-empty { min-height:240px; display:grid; place-items:center; color:var(--lz-text-muted); }
.teacher-agent-host { position:fixed; z-index:520; top:80px; right:10px; bottom:10px; width:clamp(360px,28vw,420px); }
.teacher-agent-host :deep(.ai-teacher-panel) { height:100%; }
.spin { animation:spin 1s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:720px) {
  .course-workspace-page { grid-template-rows:48px minmax(0,1fr); }
  .workspace-local-header { padding:0 10px; gap:10px; }
  .back-button span,.workspace-title span { display:none; }
  .workspace-title small { display:none; }
  .workspace-route-actions { gap:5px; }
  .workspace-route-actions button { padding:0 7px; font-size:11px; }
  .same-source-state,.workspace-route-actions .task-action { display:none; }
  .teacher-agent-host { position:static; width:0; height:0; }
}
</style>
