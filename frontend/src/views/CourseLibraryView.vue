<template>
  <section class="course-library glass-panel-elevated">
    <header class="library-header">
      <div>
        <p>{{ t('courseLibrary.eyebrow', '课程库') }}</p>
        <h1>{{ t('courseLibrary.title', '选择一门课程继续学习') }}</h1>
        <span>{{ t('courseLibrary.subtitle', '课程生成会在后台继续，离开页面不会中断任务。') }}</span>
      </div>
      <div class="library-actions">
        <input ref="fileInput" type="file" accept=".md,.markdown,text/markdown" class="sr-only" @change="importCourse" />
        <button type="button" class="secondary-button task-center-button" :title="t('courseLibrary.tasks', '生成任务')" :aria-label="t('courseLibrary.tasks', '生成任务')" @click="openTaskCenter()">
          <ListChecks :size="16" />
          <span class="action-label">{{ t('courseLibrary.tasks', '生成任务') }}</span>
          <span v-if="attentionTaskCount" class="action-count">{{ attentionTaskCount }}</span>
        </button>
        <button type="button" class="secondary-button import-button" :title="t('courseLibrary.import', '导入 Markdown')" :aria-label="t('courseLibrary.import', '导入 Markdown')" @click="fileInput?.click()">
          <Upload :size="16" />
          <span class="action-label">{{ t('courseLibrary.import', '导入 Markdown') }}</span>
        </button>
        <button type="button" class="primary-button" @click="createDialogOpen = true">
          <Plus :size="16" />
          {{ t('courseLibrary.newCourse', '新建课程') }}
        </button>
      </div>
    </header>

    <button v-if="latestResumeCourse" type="button" class="resume-card" @click="openCourse(latestResumeCourse.course_id, latestResumeCourse.resume?.node_id)">
      <span class="resume-card__icon"><History :size="18" /></span>
      <span class="resume-card__copy">
        <small>{{ resumeKindLabel(latestResumeCourse.resume?.kind || 'reading') }}</small>
        <strong>{{ latestResumeCourse.course_name }}</strong>
        <span>{{ latestResumeCourse.resume?.node_name || t('courseLibrary.resume.locationFallback', '返回上次学习位置') }}</span>
      </span>
      <span class="resume-card__action">
        {{ t('courseLibrary.resume.open', '继续') }}
        <ArrowRight :size="16" />
      </span>
    </button>

    <div class="library-toolbar">
      <label>
        <Search :size="16" />
        <input v-model="query" type="search" :placeholder="t('courseLibrary.search', '搜索课程')" />
      </label>
      <span>{{ filteredCourses.length }} {{ t('courseLibrary.courseUnit', '门课程') }}</span>
    </div>

    <div v-if="courseStore.loading" class="library-state">
      <LoaderCircle class="spin" :size="22" />
      <span>{{ t('courseLibrary.loading', '正在读取课程') }}</span>
    </div>

    <div v-else-if="!filteredCourses.length" class="library-state empty">
      <BookOpenText :size="28" />
      <strong>{{ query ? t('courseLibrary.noMatch', '没有匹配的课程') : t('courseLibrary.emptyTitle', '还没有课程') }}</strong>
      <span>{{ query ? t('courseLibrary.noMatchBody', '换一个关键词试试。') : t('courseLibrary.emptyBody', '新建课程或导入已有 Markdown 开始学习。') }}</span>
    </div>

    <div v-else class="course-grid">
      <article v-for="course in filteredCourses" :key="course.course_id" class="course-item glass-panel">
        <button type="button" class="course-main" @click="openCourse(course.course_id)">
          <div class="course-mark"><BookMarked :size="19" /></div>
          <div class="course-copy">
            <span v-if="courseStatus(course.course_id).visible">{{ courseStatus(course.course_id).label }}</span>
            <h2>{{ course.course_name }}</h2>
            <p>{{ course.node_count || 0 }} {{ t('courseLibrary.nodes', '个学习节点') }}</p>
          </div>
        </button>

        <button v-if="courseStatus(course.course_id).active" type="button" class="generation-progress" @click="openTaskCenter(course.course_id)">
          <div>
            <span>{{ courseStatus(course.course_id).detail }}</span>
            <strong>{{ Math.round(courseStatus(course.course_id).progress) }}%</strong>
          </div>
          <div class="progress-track"><span :style="{ width: `${courseStatus(course.course_id).progress}%` }"></span></div>
        </button>

        <footer>
          <span>{{ t('courseLibrary.openHint', '打开课程') }}</span>
          <button type="button" :title="t('courseLibrary.delete', '删除课程')" @click="deleteCourse(course.course_id, course.course_name)">
            <Trash2 :size="15" />
          </button>
        </footer>
      </article>
    </div>

    <CourseGenerationDialog
      v-model="createDialogOpen"
      :busy="creating"
      @generate="generateCourse"
      @error="message => ElMessage.error(message)"
    />
    <CourseTaskCenter v-model="taskCenterOpen" :course-id="selectedTaskCourseId" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, BookMarked, BookOpenText, History, ListChecks, LoaderCircle, Plus, Search, Trash2, Upload } from 'lucide-vue-next'
import CourseGenerationDialog from '../components/CourseGenerationDialog.vue'
import CourseTaskCenter from '../components/CourseTaskCenter.vue'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { t } from '../shared/i18n'
import { latestResumableCourse, resumeKindLabel } from '../utils/learning-resume'

const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const query = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const createDialogOpen = ref(false)
const taskCenterOpen = ref(false)
const selectedTaskCourseId = ref('')
const creating = ref(false)

const filteredCourses = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return courseStore.courseList
  return courseStore.courseList.filter(course => course.course_name.toLocaleLowerCase().includes(keyword))
})
const attentionTaskCount = computed(() => Array.from(generationStore.tasks.values()).filter(taskNeedsAttention).length)
const latestResumeCourse = computed(() => latestResumableCourse(courseStore.courseList))

onMounted(async () => {
  courseStore.currentCourseId = ''
  courseStore.currentCourseVersionId = ''
  courseStore.currentNode = null
  generationStore.restoreGenerationState()
  await Promise.all([courseStore.fetchCourseList(), generationStore.fetchGlobalTasks()])
  generationStore.startGlobalMonitor()
})

function courseStatus(courseId: string) {
  const task = generationStore.getTask(courseId)
  const publishedWarning = Boolean(task && isPublishedWarning(task))
  const active = Boolean(task && taskNeedsAttention(task))
  const labels: Record<string, string> = {
    pending: t('courseLibrary.status.pending', '等待生成'),
    running: t('courseLibrary.status.running', '正在生成'),
    paused: t('courseLibrary.status.paused', '已暂停'),
    waiting_for_review: t('courseLibrary.status.waitingReview', '等待处理'),
    conflict: t('courseLibrary.status.conflict', '需要确认'),
    error: t('courseLibrary.status.error', '生成失败'),
    completed_with_warnings: t('courseLibrary.status.warnings', '生成完成但有警告'),
    completed: t('courseLibrary.status.ready', '可以学习'),
  }
  return {
    active,
    visible: active || publishedWarning,
    label: publishedWarning
      ? t('courseLibrary.status.readyWithSuggestions', '可以学习，有优化建议')
      : labels[task?.status || 'completed'] || t('courseLibrary.status.ready', '可以学习'),
    detail: task?.currentStep
      || (task?.currentPhase ? t(`courseGeneration.phases.${task.currentPhase}`, task.currentPhase) : '')
      || t('courseLibrary.status.preparing', '正在准备课程'),
    progress: Math.max(0, Math.min(100, task?.progress || 0)),
  }
}

function isPublishedWarning(task: { status: string; publicationAllowed?: boolean; recovery?: { state: string } }) {
  return task.status === 'completed_with_warnings'
    && (task.publicationAllowed === true || task.recovery?.state === 'completed')
}

function taskNeedsAttention(task: { status: string; publicationAllowed?: boolean; recovery?: { state: string } }) {
  if (isPublishedWarning(task)) return false
  return ['pending', 'running', 'paused', 'waiting_for_review', 'conflict', 'error', 'completed_with_warnings'].includes(task.status)
}

function openCourse(courseId: string, nodeId?: string) {
  void router.push({ name: 'learning', params: { courseId, ...(nodeId ? { nodeId } : {}) } })
}

function openTaskCenter(courseId = '') {
  selectedTaskCourseId.value = courseId
  taskCenterOpen.value = true
}

async function generateCourse(payload: { subject: string; options: CourseGenerationOptions }) {
  if (creating.value) return
  creating.value = true
  try {
    const result = await courseStore.generateCourse(payload.subject, payload.options)
    if (!result?.courseId) {
      ElMessage.error(t('courseLibrary.createFailed', '课程创建失败'))
      return
    }
    createDialogOpen.value = false
    await courseStore.fetchCourseList()
    openTaskCenter(result.courseId)
    ElMessage.success(t('courseLibrary.createStarted', '课程已经进入后台生成队列'))
  } catch {
    ElMessage.error(t('courseLibrary.createFailed', '课程创建失败'))
  } finally {
    creating.value = false
  }
}

async function importCourse(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  try {
    const result = await courseStore.importMarkdown(file)
    openCourse(result.course_id)
  } catch {
    ElMessage.error(t('courseLibrary.importFailed', '课程导入失败'))
  } finally {
    target.value = ''
  }
}

async function deleteCourse(courseId: string, courseName: string) {
  try {
    await ElMessageBox.confirm(
      t('courseLibrary.deleteConfirm', '删除课程“{name}”？').replace('{name}', courseName),
      t('courseLibrary.delete', '删除课程'),
      { type: 'warning', confirmButtonText: t('common.delete', '删除'), cancelButtonText: t('common.cancel', '取消') },
    )
    await courseStore.deleteCourse(courseId)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(t('courseLibrary.deleteFailed', '删除失败'))
  }
}
</script>

<style scoped>
.course-library { width:100%; height:100%; overflow:auto; padding:30px clamp(18px,4vw,54px) 48px; border:1px solid rgba(255,255,255,.82); border-radius:var(--lz-radius-surface); background:rgba(255,255,255,.76); box-shadow:var(--lz-shadow-panel); backdrop-filter:none; -webkit-backdrop-filter:none; }
.library-header { max-width: 1280px; margin: 0 auto; display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; }
.library-header p { margin: 0 0 7px; color: var(--lz-brand); font-size: 12px; font-weight: 700; }
.library-header h1 { margin:0; color:#312e81; font-size:clamp(25px,3vw,32px); line-height:1.2; }
.library-header > div:first-child > span { display:block; margin-top:8px; color:var(--lz-text-secondary); font-size:13px; }
.library-actions { display: flex; gap: 8px; flex: 0 0 auto; }
.task-center-button { position: relative; }
.task-center-button > .action-count { min-width:18px; height:18px; display:inline-flex; align-items:center; justify-content:center; padding:0 5px; border-radius:9px; color:#fff; background:var(--lz-warning); font-size:9px; }
.primary-button, .secondary-button { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 14px; border-radius:11px; font-size:12px; font-weight:700; cursor:pointer; }
.primary-button { border:1px solid transparent; background:linear-gradient(135deg,#6366f1,#8b5cf6); color:#fff; box-shadow:0 7px 16px rgba(99,102,241,.2); }
.secondary-button { border:1px solid rgba(203,213,225,.72); background:rgba(255,255,255,.72); color:var(--lz-text-secondary); }
.resume-card { width:100%; max-width:1280px; min-width:0; margin:24px auto 0; display:grid; grid-template-columns:42px minmax(0,1fr) auto; align-items:center; gap:13px; padding:14px 16px; border:1px solid rgba(134,239,172,.72); border-radius:14px; color:var(--lz-text); background:linear-gradient(105deg,#f0fdf4,#fff); text-align:left; box-shadow:0 7px 20px rgba(21,128,61,.07); cursor:pointer; }
.resume-card:hover { border-color:#4ade80; box-shadow:0 10px 24px rgba(21,128,61,.11); }
.resume-card__icon { width:42px; height:42px; display:grid; place-items:center; border-radius:12px; color:#fff; background:#15803d; }
.resume-card__copy { min-width:0; display:flex; flex-direction:column; }
.resume-card__copy small { color:#15803d; font-size:10px; font-weight:800; }
.resume-card__copy strong,.resume-card__copy span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.resume-card__copy strong { margin-top:2px; color:var(--lz-text-strong); font-size:14px; }
.resume-card__copy span { margin-top:2px; color:var(--lz-text-muted); font-size:11px; }
.resume-card__action { display:inline-flex; align-items:center; gap:5px; color:#166534; font-size:12px; font-weight:800; }
.library-toolbar { max-width: 1280px; margin: 28px auto 14px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.library-toolbar label { width:min(360px,100%); height:38px; display:flex; align-items:center; gap:8px; padding:0 12px; border:1px solid rgba(203,213,225,.68); border-radius:999px; color:var(--lz-text-muted); background:rgba(255,255,255,.76); box-shadow:inset 0 1px 0 rgba(255,255,255,.8); }
.library-toolbar input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font-size: 12px; }
.library-toolbar > span { color: var(--lz-text-muted); font-size: 12px; }
.course-grid { width:100%; max-width:1280px; margin:0 auto; display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr)); gap:14px; }
.course-item { min-width:0; overflow:hidden; border:1px solid rgba(255,255,255,.88); border-radius:16px; background:rgba(255,255,255,.78); box-shadow:0 5px 18px rgba(79,70,229,.06),inset 0 1px 0 rgba(255,255,255,.9); transition:border-color .18s ease,box-shadow .18s ease,transform .18s ease; backdrop-filter:none; -webkit-backdrop-filter:none; }
.course-item:hover { border-color:rgba(165,180,252,.9); box-shadow:0 14px 30px rgba(79,70,229,.12); transform:translateY(-2px); }
.course-main { width: 100%; min-height: 128px; display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; align-items: start; gap: 12px; padding: 18px; border: 0; background: transparent; text-align: left; cursor: pointer; }
.course-mark { width:40px; height:40px; display:grid; place-items:center; border-radius:12px; color:#fff; background:linear-gradient(135deg,#818cf8,#8b5cf6); box-shadow:0 6px 14px rgba(99,102,241,.18); }
.course-copy { min-width: 0; }
.course-copy > span { color: var(--lz-brand-strong); font-size: 10px; font-weight: 700; }
.course-copy h2 { margin: 8px 0 7px; overflow: hidden; color: var(--lz-text-strong); font-size: 16px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.course-copy p { margin: 0; color: var(--lz-text-muted); font-size: 11px; }
.generation-progress { width:100%; padding: 0 18px 15px; border:0; color:inherit; background:transparent; text-align:left; cursor:pointer; }
.generation-progress > div:first-child { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 6px; color: var(--lz-text-secondary); font-size: 10px; }
.generation-progress span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.progress-track { height: 4px; overflow: hidden; border-radius: 2px; background: var(--lz-surface-muted); }
.progress-track span { display: block; height: 100%; background: var(--lz-brand); }
.course-item footer { min-height:40px; display:flex; align-items:center; justify-content:space-between; padding:0 12px 0 18px; border-top:1px solid rgba(226,232,240,.72); color:var(--lz-text-muted); font-size:10px; }
.course-item footer button { width: 28px; height: 28px; display: grid; place-items: center; border: 0; border-radius: 5px; color: var(--lz-text-muted); background: transparent; cursor: pointer; }
.course-item footer button:hover { color: var(--lz-danger); background: var(--lz-danger-soft); }
.library-state { min-height: 360px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--lz-text-muted); }
.library-state strong { color: var(--lz-text); font-size: 15px; }
.library-state span { font-size: 12px; }
.spin { animation: spin 1s linear infinite; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width:700px) {
  .course-library { padding:22px 20px 40px; border:0; border-radius:0; box-shadow:none; }
  .library-header { align-items:stretch; flex-direction:column; }
  .library-actions { width:100%; display:grid; grid-template-columns:44px 44px minmax(0,1fr); gap:8px; }
  .library-actions button { min-width:0; padding-inline:10px; }
  .library-actions .task-center-button,.library-actions .import-button { width:44px; padding:0; }
  .library-actions .task-center-button .action-label,.library-actions .import-button .action-label { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  .task-center-button > .action-count { position:absolute; top:-5px; right:-5px; }
  .resume-card { margin-top:18px; grid-template-columns:38px minmax(0,1fr); padding:12px; }
  .resume-card__icon { width:38px; height:38px; }
  .resume-card__action { grid-column:2; }
  .library-toolbar { margin-top:18px; }
  .library-toolbar > span { display:none; }
  .course-grid { grid-template-columns:minmax(0,1fr); }
  .course-main { min-height:116px; grid-template-columns:38px minmax(0,1fr); padding:16px; }
  .course-copy h2 { white-space:normal; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
}
</style>
