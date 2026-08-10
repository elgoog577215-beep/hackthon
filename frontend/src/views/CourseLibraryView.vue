<template>
  <section class="course-library glass-panel-elevated">
    <Teleport to="#app-header-route-actions">
      <nav class="library-global-actions" :aria-label="t('courseLibrary.globalActions', '课程库全局操作')">
        <button
          type="button"
          class="global-action-button"
          data-testid="open-teacher-course-space"
          @click="router.push('/teacher-course-space')"
        >
          <FolderOpen :size="17" />
          <span class="action-label">{{ t('courseLibrary.teacherSpace', '教师文件空间') }}</span>
        </button>
        <button
          type="button"
          class="global-action-button task-center-button"
          :title="t('courseLibrary.tasks', '课程任务')"
          :aria-label="t('courseLibrary.tasks', '课程任务')"
          @click="openTaskCenter()"
        >
          <ListChecks :size="17" />
          <span class="action-label">{{ t('courseLibrary.tasks', '课程任务') }}</span>
          <span v-if="attentionTaskCount" class="action-count">{{ attentionTaskCount }}</span>
        </button>
      </nav>
    </Teleport>

    <header class="library-header">
      <div>
        <p>{{ t('courseLibrary.eyebrow', '课程库') }}</p>
        <h1>{{ t('courseLibrary.title', '选择一门课程继续学习') }}</h1>
        <span>{{ t('courseLibrary.subtitle', '课程生成会在后台继续，离开页面不会中断任务。') }}</span>
      </div>
      <div class="library-actions">
        <input ref="fileInput" type="file" accept=".md,.markdown,text/markdown" class="sr-only" @change="importCourse" />
        <div ref="createMenuRef" class="create-course-menu" @keydown.esc.stop.prevent="closeCreateMenu(true)">
          <button
            ref="createMenuTriggerRef"
            type="button"
            class="primary-button create-course-trigger"
            data-testid="create-course-menu-trigger"
            aria-haspopup="menu"
            aria-controls="create-course-menu"
            :aria-expanded="createMenuOpen"
            @click="toggleCreateMenu"
          >
            <Plus :size="17" />
            {{ t('courseLibrary.newCourse', '新建课程') }}
            <ChevronDown class="create-course-trigger__chevron" :class="{ open: createMenuOpen }" :size="15" />
          </button>

          <Transition name="create-menu">
            <div v-if="createMenuOpen" id="create-course-menu" class="create-course-menu__panel" role="menu">
              <button
                ref="createMenuFirstItemRef"
                type="button"
                class="create-course-menu__item"
                role="menuitem"
                data-testid="create-blank-course"
                @click="openBlankCourse"
              >
                <span class="create-course-menu__icon"><FilePlus2 :size="19" /></span>
                <span>
                  <strong>{{ t('courseLibrary.newBlankCourse', '新建空白课程') }}</strong>
                  <small>{{ t('courseLibrary.newBlankCourseHelp', '从零开始创建课程') }}</small>
                </span>
              </button>
              <button
                type="button"
                class="create-course-menu__item"
                role="menuitem"
                data-testid="import-markdown-course"
                @click="openMarkdownImport"
              >
                <span class="create-course-menu__icon"><Upload :size="19" /></span>
                <span>
                  <strong>{{ t('courseLibrary.import', '导入 Markdown') }}</strong>
                  <small>{{ t('courseLibrary.importHelp', '上传 .md 文件快速生成') }}</small>
                </span>
              </button>
            </div>
          </Transition>
        </div>
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
          <div class="course-footer-actions">
            <button
              type="button"
              class="course-review-button"
              :data-testid="`open-question-bank-review-${course.course_id}`"
              :title="t('questionBank.openReview', '打开题库质量管理')"
              @click="openQuestionBankReview(course.course_id)"
            >
              <ShieldCheck :size="14" />
              <span>{{ t('questionBank.reviewEntry', '题库管理') }}</span>
            </button>
            <button type="button" :title="t('courseLibrary.delete', '删除课程')" @click="deleteCourse(course.course_id, course.course_name)">
              <Trash2 :size="15" />
            </button>
          </div>
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
    <QuestionBankReviewCenter
      v-model="questionBankReviewOpen"
      :course-id="selectedReviewCourseId"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, BookMarked, BookOpenText, ChevronDown, FilePlus2, FolderOpen, History, ListChecks, LoaderCircle, Plus, Search, ShieldCheck, Trash2, Upload } from 'lucide-vue-next'
import CourseGenerationDialog from '../components/CourseGenerationDialog.vue'
import CourseTaskCenter from '../components/CourseTaskCenter.vue'
import QuestionBankReviewCenter from '../components/QuestionBankReviewCenter.vue'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { t } from '../shared/i18n'
import { courseProductionTaskDetail } from '../utils/course-production'
import { latestResumableCourse, resumeKindLabel } from '../utils/learning-resume'

const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const query = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const createMenuRef = ref<HTMLElement | null>(null)
const createMenuTriggerRef = ref<HTMLButtonElement | null>(null)
const createMenuFirstItemRef = ref<HTMLButtonElement | null>(null)
const createMenuOpen = ref(false)
const createDialogOpen = ref(false)
const taskCenterOpen = ref(false)
const selectedTaskCourseId = ref('')
const questionBankReviewOpen = ref(false)
const selectedReviewCourseId = ref('')
const creating = ref(false)

const filteredCourses = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return courseStore.courseList
  return courseStore.courseList.filter(course => course.course_name.toLocaleLowerCase().includes(keyword))
})
const attentionTaskCount = computed(() => Array.from(generationStore.tasks.values()).filter(taskNeedsAttention).length)
const latestResumeCourse = computed(() => latestResumableCourse(courseStore.courseList))

onMounted(async () => {
  document.addEventListener('pointerdown', closeCreateMenuOnOutsidePointer)
  courseStore.currentCourseId = ''
  courseStore.currentCourseVersionId = ''
  courseStore.currentNode = null
  generationStore.restoreGenerationState()
  await Promise.all([courseStore.fetchCourseList(), generationStore.fetchGlobalTasks()])
  generationStore.startGlobalMonitor()
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeCreateMenuOnOutsidePointer)
})

async function toggleCreateMenu() {
  createMenuOpen.value = !createMenuOpen.value
  if (createMenuOpen.value) {
    await nextTick()
    createMenuFirstItemRef.value?.focus()
  }
}

function closeCreateMenu(restoreFocus = false) {
  createMenuOpen.value = false
  if (restoreFocus) createMenuTriggerRef.value?.focus()
}

function closeCreateMenuOnOutsidePointer(event: PointerEvent) {
  if (!createMenuOpen.value || createMenuRef.value?.contains(event.target as Node)) return
  closeCreateMenu()
}

function openBlankCourse() {
  closeCreateMenu()
  createDialogOpen.value = true
}

function openMarkdownImport() {
  closeCreateMenu()
  fileInput.value?.click()
}

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
    detail: courseProductionTaskDetail(task)
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
  void router.push({
    name: 'learning',
    params: { courseId, ...(nodeId ? { nodeId } : {}) },
  })
}

function openGeneratingCourse(courseId: string) {
  void router.push({ name: 'learning', params: { courseId } })
}

function openTaskCenter(courseId = '') {
  selectedTaskCourseId.value = courseId
  taskCenterOpen.value = true
}

function openQuestionBankReview(courseId: string) {
  selectedReviewCourseId.value = courseId
  questionBankReviewOpen.value = true
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
    openGeneratingCourse(result.courseId)
    void courseStore.fetchCourseList()
    ElMessage.success(t('courseLibrary.createStarted', '课程已开始生成，正在进入生成现场'))
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
    openTaskCenter(result.course_id)
    ElMessage.success(t('courseLibrary.importQueued', '导入任务已创建，可以在任务中心查看解析和保存进度'))
  } catch (error) {
    const detail = String((error as any)?.response?.data?.detail || '')
    ElMessage.error(detail || t('courseLibrary.importFailed', '课程导入失败'))
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
.library-global-actions { display:flex; align-items:center; justify-content:flex-end; gap:10px; }
.global-action-button { position:relative; min-height:36px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 10px; border:1px solid transparent; border-radius:10px; color:var(--lz-text-secondary); background:transparent; font-size:12px; font-weight:700; cursor:pointer; transition:transform .16s ease,color .16s ease,background .16s ease,border-color .16s ease; }
.global-action-button:hover,.global-action-button:focus-visible { transform:translateY(-1px); border-color:#e0e7ff; color:var(--lz-brand-strong); background:#f5f3ff; outline:none; }
.task-center-button > .action-count { min-width:19px; height:19px; display:inline-flex; align-items:center; justify-content:center; padding:0 5px; border-radius:10px; color:#fff; background:var(--lz-warning); font-size:9px; font-weight:800; }
.library-actions { display:flex; flex:0 0 auto; }
.create-course-menu { position:relative; }
.primary-button, .secondary-button { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 14px; border-radius:11px; font-size:12px; font-weight:700; cursor:pointer; }
.primary-button { border:1px solid transparent; background:linear-gradient(135deg,#6366f1,#8b5cf6); color:#fff; box-shadow:0 7px 16px rgba(99,102,241,.2); }
.secondary-button { border:1px solid rgba(203,213,225,.72); background:rgba(255,255,255,.72); color:var(--lz-text-secondary); }
.create-course-trigger { min-height:44px; padding:0 16px; font-size:13px; box-shadow:0 9px 20px rgba(99,102,241,.24); }
.create-course-trigger:focus-visible { outline:3px solid rgba(99,102,241,.18); outline-offset:2px; }
.create-course-trigger__chevron { margin-left:2px; transition:transform .18s ease; }
.create-course-trigger__chevron.open { transform:rotate(180deg); }
.create-course-menu__panel { position:absolute; z-index:60; top:calc(100% + 9px); right:0; width:270px; overflow:hidden; padding:7px; border:1px solid rgba(203,213,225,.78); border-radius:14px; background:rgba(255,255,255,.98); box-shadow:0 18px 42px rgba(51,65,85,.16),0 4px 12px rgba(79,70,229,.08); }
.create-course-menu__item { width:100%; display:grid; grid-template-columns:38px minmax(0,1fr); align-items:center; gap:10px; padding:11px; border:0; border-radius:10px; color:var(--lz-text); background:transparent; text-align:left; cursor:pointer; }
.create-course-menu__item + .create-course-menu__item { margin-top:2px; border-top:1px solid rgba(226,232,240,.76); border-radius:0 0 10px 10px; }
.create-course-menu__item:hover,.create-course-menu__item:focus-visible { color:var(--lz-brand-strong); background:var(--lz-brand-soft); outline:none; }
.create-course-menu__icon { width:36px; height:36px; display:grid; place-items:center; border-radius:10px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.create-course-menu__item strong,.create-course-menu__item small { display:block; }
.create-course-menu__item strong { font-size:12px; line-height:1.4; }
.create-course-menu__item small { margin-top:3px; color:var(--lz-text-muted); font-size:10px; line-height:1.4; }
.create-menu-enter-active,.create-menu-leave-active { transition:opacity .14s ease,transform .14s ease; transform-origin:top right; }
.create-menu-enter-from,.create-menu-leave-to { opacity:0; transform:translateY(-5px) scale(.98); }
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
.course-footer-actions { display:flex; align-items:center; gap:3px; }
.course-item footer .course-review-button { width:auto; display:inline-flex; align-items:center; gap:5px; padding:0 8px; color:var(--lz-brand-strong); }
.course-item footer .course-review-button:hover { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.library-state { min-height: 360px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--lz-text-muted); }
.library-state strong { color: var(--lz-text); font-size: 15px; }
.library-state span { font-size: 12px; }
.spin { animation: spin 1s linear infinite; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width:700px) {
  .course-library { padding:22px 20px 40px; border:0; border-radius:0; box-shadow:none; }
  .library-header { align-items:stretch; flex-direction:column; }
  .library-actions,.create-course-menu,.create-course-trigger { width:100%; }
  .create-course-menu__panel { left:0; right:0; width:auto; }
  .resume-card { margin-top:18px; grid-template-columns:38px minmax(0,1fr); padding:12px; }
  .resume-card__icon { width:38px; height:38px; }
  .resume-card__action { grid-column:2; }
  .library-toolbar { margin-top:18px; }
  .library-toolbar > span { display:none; }
  .course-grid { grid-template-columns:minmax(0,1fr); }
  .course-main { min-height:116px; grid-template-columns:38px minmax(0,1fr); padding:16px; }
  .course-copy h2 { white-space:normal; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
}
@media (max-width:620px) {
  .library-global-actions { gap:2px; }
  .global-action-button { width:40px; padding:0; }
  .global-action-button .action-label { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  .task-center-button > .action-count { position:absolute; top:-4px; right:-4px; min-width:17px; height:17px; padding:0 4px; }
}
</style>
