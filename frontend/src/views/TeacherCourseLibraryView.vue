<template>
  <section
    class="course-library glass-panel-elevated"
    :class="{ 'course-library--paginated': totalPages > 1, 'course-library--embedded': embedded }"
  >
    <header class="library-header">
      <div>
        <p>{{ t('teacherCourseLibrary.eyebrow', '我的课程') }}</p>
        <h1>{{ t('teacherCourseLibrary.title', '课程工作台') }}</h1>
        <span>{{ t('teacherCourseLibrary.subtitle', '管理教学大纲、教学日历、分讲教案、PPT 与学生发布版本。') }}</span>
      </div>
      <div v-if="!embedded" class="library-actions">
        <nav class="library-global-actions" :aria-label="t('courseLibrary.globalActions', '课程库全局操作')">
          <button
            type="button"
            class="global-action-button"
            data-testid="switch-to-student-surface"
            @click="router.push({ name: 'course-library' })"
          >
            <BookOpenText :size="17" />
            <span class="action-label">学生端</span>
          </button>
          <button
            type="button"
            class="global-action-button"
            data-testid="open-teacher-calendar"
            @click="router.push({ name: 'teacher-teaching-calendar' })"
          >
            <CalendarRange :size="17" />
            <span class="action-label">{{ t('teacherCalendar.total', '教学总日历') }}</span>
          </button>
          <button
            type="button"
            class="global-action-button task-center-button"
            data-testid="open-course-workbench"
            :title="workbenchLabel"
            :aria-label="workbenchLabel"
            @click="openTaskCenter()"
          >
            <LayoutDashboard :size="17" />
            <span class="action-label">{{ workbenchLabel }}</span>
            <span v-if="actionRequiredTaskCount" class="action-count">{{ actionRequiredTaskCount }}</span>
          </button>
        </nav>
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
                  <strong>{{ t('teacherCourseLibrary.newBlankCourse', '进入新建课程') }}</strong>
                  <small>{{ t('teacherCourseLibrary.newBlankCourseHelp', '先填课程信息，再选择大纲起点') }}</small>
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

    <div class="library-toolbar">
      <label>
        <Search :size="16" />
        <input
          v-model="query"
          type="search"
          :aria-label="t('courseLibrary.search', '搜索课程')"
          :placeholder="t('courseLibrary.search', '搜索课程')"
        />
      </label>
      <div class="library-toolbar__end">
        <div class="library-toolbar__summary" :aria-label="t('teacherCourseLibrary.statusSummary')">
          <span>{{ t('teacherCourseLibrary.allCourses') }} <strong>{{ filteredCourses.length }}</strong></span>
          <span>{{ t('teacherCourseLibrary.attentionCourses') }} <strong :class="{ attention: attentionCourseCount > 0 }">{{ attentionCourseCount }}</strong></span>
          <span>{{ t('teacherCourseLibrary.publishedCourses') }} <strong>{{ publishedCourseCount }}</strong></span>
        </div>
        <div class="library-view-switch" role="group" :aria-label="t('teacherCourseLibrary.viewMode')">
          <button type="button" :class="{ active: displayMode === 'grid' }" :aria-pressed="displayMode === 'grid'" :title="t('teacherCourseLibrary.cardView')" @click="displayMode = 'grid'">
            <Grid2X2 :size="16" /><span>{{ t('teacherCourseLibrary.cardView') }}</span>
          </button>
          <button type="button" :class="{ active: displayMode === 'list' }" :aria-pressed="displayMode === 'list'" :title="t('teacherCourseLibrary.listView')" @click="displayMode = 'list'">
            <List :size="16" /><span>{{ t('teacherCourseLibrary.listView') }}</span>
          </button>
        </div>
      </div>
    </div>

    <div v-if="courseStore.loading" class="library-state">
      <LoaderCircle class="spin" :size="22" />
      <span>{{ t('courseLibrary.loading', '正在读取课程') }}</span>
    </div>

    <div v-else-if="!filteredCourses.length" class="library-state empty">
      <BookOpenText :size="28" />
      <strong>{{ query ? t('courseLibrary.noMatch', '没有匹配的课程') : t('courseLibrary.emptyTitle', '还没有课程') }}</strong>
      <span>{{ query ? t('courseLibrary.noMatchBody', '换一个关键词试试。') : t('teacherCourseLibrary.emptyBody', '新建课程后，从教学大纲开始组织教学。') }}</span>
    </div>

    <section v-else class="course-collection">
      <header class="course-collection__header">
        <strong>{{ query ? t('teacherCourseLibrary.searchResults') : t('teacherCourseLibrary.collectionTitle') }}</strong>
        <span>{{ t('teacherCourseLibrary.collectionSummary').replace('{count}', String(filteredCourses.length)) }}</span>
      </header>
      <div ref="courseGridRef" class="course-grid" :data-view="displayMode" data-layout="responsive-three-column">
        <article
        v-for="{ course, status } in courseCards"
        :key="course.course_id"
        class="course-item glass-panel"
        :class="{ 'course-item--menu-open': openCourseMenuId === course.course_id }"
        :data-state="status.tone"
      >
        <button
          type="button"
          class="course-main"
          :title="status.active ? status.detail : formatCourseTitle(course.course_name)"
          @click="handleCoursePrimary(course.course_id)"
        >
          <CourseCover :course-id="course.course_id" :title="course.course_name" />
          <span class="course-copy">
            <h2>{{ formatCourseTitle(course.course_name) }}</h2>
            <span class="course-status" :class="`course-status--${status.tone}`">
              <span class="course-status__dot" aria-hidden="true"></span>
              <span>{{ status.label }}</span>
              <strong v-if="status.active">{{ Math.round(status.progress) }}%</strong>
            </span>
            <span
              v-if="status.active"
              class="generation-progress"
              role="progressbar"
              :aria-label="status.detail"
              :aria-valuenow="Math.round(status.progress)"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <span class="progress-track"><span :style="{ width: `${status.progress}%` }"></span></span>
            </span>
            <span class="teacher-asset-summary">{{ teacherAssetSummary(course, status.active) }}</span>
          </span>
        </button>

        <div
          class="course-actions"
          :data-course-menu-root="course.course_id"
          @keydown.esc.stop.prevent="closeCourseMenu"
        >
          <button
            v-if="!status.active"
            type="button"
            class="course-primary-action"
            @click="openCourse(course.course_id)"
          >
            {{ t('courseLibrary.openHint', '进入课程') }}
            <ArrowRight :size="17" />
          </button>
          <button
            v-else-if="status.retryable"
            type="button"
            class="course-primary-action"
            @click="openTaskCenter(course.course_id)"
          >
            {{ t('courseLibrary.retry', '重试') }}
          </button>

          <button
            type="button"
            class="course-menu-trigger"
            :data-testid="`course-actions-${course.course_id}`"
            aria-haspopup="menu"
            :aria-controls="`course-menu-${course.course_id}`"
            :aria-expanded="openCourseMenuId === course.course_id"
            :aria-label="t('courseLibrary.moreActions', '更多操作')"
            :title="t('courseLibrary.moreActions', '更多操作')"
            @click.stop="toggleCourseMenu(course.course_id)"
          >
            <Ellipsis :size="20" />
          </button>

          <Transition name="course-menu">
            <div
              v-if="openCourseMenuId === course.course_id"
              :id="`course-menu-${course.course_id}`"
              class="course-menu"
              :data-testid="`course-menu-${course.course_id}`"
              role="menu"
              @click.stop
            >
              <button
                type="button"
                class="course-menu__item"
                role="menuitem"
                :data-testid="`open-course-production-${course.course_id}`"
                @click="openCourseProduction(course.course_id)"
              >
                <Workflow :size="15" />
                <span>{{ t('courseLibrary.productionEntry', '课程生产') }}</span>
              </button>
              <button
                type="button"
                class="course-menu__item course-menu__item--danger"
                role="menuitem"
                :data-testid="`delete-course-${course.course_id}`"
                @click="deleteCourse(course.course_id, formatCourseTitle(course.course_name))"
              >
                <Trash2 :size="15" />
                <span>{{ t('courseLibrary.delete', '删除课程') }}</span>
              </button>
            </div>
          </Transition>
        </div>
        </article>
      </div>
    </section>

    <Teleport to="body">
      <Transition name="pagination-dock">
        <nav
          v-if="!courseStore.loading && totalPages > 1"
          class="library-pagination-dock"
          :aria-label="t('courseLibrary.pagination.label', '课程分页')"
        >
          <button
            type="button"
            class="pagination-button pagination-button--direction"
            :disabled="currentPage === 1"
            :aria-label="t('courseLibrary.pagination.previous', '上一页')"
            @click="selectPage(currentPage - 1)"
          >
            <ChevronLeft :size="17" />
            <span>{{ t('courseLibrary.pagination.previous', '上一页') }}</span>
          </button>

          <span class="pagination-pages" role="group" :aria-label="t('courseLibrary.pagination.pageSelection', '页面选择')">
            <template v-for="item in paginationItems" :key="`page-${item}`">
              <span v-if="typeof item === 'string'" class="pagination-ellipsis" aria-hidden="true">…</span>
              <button
                v-else
                type="button"
                class="pagination-button pagination-button--page"
                :class="{ active: item === currentPage }"
                :aria-current="item === currentPage ? 'page' : undefined"
                :aria-label="pageNumberLabel(item)"
                @click="selectPage(item)"
              >
                {{ item }}
              </button>
            </template>
          </span>

          <button
            type="button"
            class="pagination-button pagination-button--direction"
            :disabled="currentPage === totalPages"
            :aria-label="t('courseLibrary.pagination.next', '下一页')"
            @click="selectPage(currentPage + 1)"
          >
            <span>{{ t('courseLibrary.pagination.next', '下一页') }}</span>
            <ChevronRight :size="17" />
          </button>

          <form class="pagination-jump" @submit.prevent="jumpToPage">
            <label for="course-page-jump">{{ t('courseLibrary.pagination.jumpTo', '跳至') }}</label>
            <input
              id="course-page-jump"
              v-model="pageJumpInput"
              type="number"
              inputmode="numeric"
              min="1"
              :max="totalPages"
              :aria-label="t('courseLibrary.pagination.jumpInput', '跳转页码')"
            />
            <span>{{ t('courseLibrary.pagination.pageUnit', '页') }}</span>
            <button
              type="submit"
              class="pagination-jump__submit"
              :aria-label="t('courseLibrary.pagination.jump', '跳转')"
            >
              {{ t('courseLibrary.pagination.jump', '跳转') }}
            </button>
          </form>
        </nav>
      </Transition>
    </Teleport>

    <CourseGenerationDialog
      v-model="createDialogOpen"
      :busy="creating"
      @generate="generateCourse"
      @error="message => ElMessage.error(message)"
    />
    <CourseWorkbench
      v-model="workbenchOpen"
      :course-id="selectedWorkbenchCourseId"
      surface="teacher"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, BookOpenText, CalendarRange, ChevronDown, ChevronLeft, ChevronRight, Ellipsis, FilePlus2, Grid2X2, LayoutDashboard, List, LoaderCircle, Plus, Search, Trash2, Upload, Workflow } from 'lucide-vue-next'
import CourseCover from '../components/CourseCover.vue'
import CourseGenerationDialog from '../components/CourseGenerationDialog.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { activeLocale, t } from '../shared/i18n'
import { courseProductionTaskDetail } from '../utils/course-production'
import { formatCourseTitle } from '../utils/course-presentation'
import type { Course } from '../stores/course'

const router = useRouter()
const { embedded = false } = defineProps<{ embedded?: boolean }>()
const { course: courseStore, generation: generationStore } = useTeacherCourseRuntime()
const COURSES_PER_PAGE = 9
const query = ref('')
const displayMode = ref<'grid' | 'list'>(localStorage.getItem('teacher_course_library_view') === 'list' ? 'list' : 'grid')
const currentPage = ref(1)
const pageJumpInput = ref('')
const courseGridRef = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const createMenuRef = ref<HTMLElement | null>(null)
const createMenuTriggerRef = ref<HTMLButtonElement | null>(null)
const createMenuFirstItemRef = ref<HTMLButtonElement | null>(null)
const createMenuOpen = ref(false)
const openCourseMenuId = ref('')
const createDialogOpen = ref(false)
const workbenchOpen = ref(false)
const selectedWorkbenchCourseId = ref('')
const creating = ref(false)

const orderedCourses = computed(() => [...courseStore.courseList].sort((left, right) => {
  const leftTime = Date.parse(left.updated_at || '') || 0
  const rightTime = Date.parse(right.updated_at || '') || 0
  return rightTime - leftTime
}))
const filteredCourses = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return orderedCourses.value
  return orderedCourses.value.filter(course => course.course_name.toLocaleLowerCase().includes(keyword))
})
const totalPages = computed(() => Math.max(1, Math.ceil(filteredCourses.value.length / COURSES_PER_PAGE)))
const paginatedCourses = computed(() => {
  const start = (currentPage.value - 1) * COURSES_PER_PAGE
  return filteredCourses.value.slice(start, start + COURSES_PER_PAGE)
})
const courseCards = computed(() => paginatedCourses.value.map(course => ({
  course,
  status: courseStatus(course),
})))
const attentionCourseCount = computed(() => filteredCourses.value.filter(course => courseStatus(course).active).length)
const publishedCourseCount = computed(() => filteredCourses.value.filter(course => course.is_published).length)
const paginationItems = computed<Array<number | 'start-ellipsis' | 'end-ellipsis'>>(() => {
  const pages = totalPages.value
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1)
  if (currentPage.value <= 4) return [1, 2, 3, 4, 5, 'end-ellipsis', pages]
  if (currentPage.value >= pages - 3) return [1, 'start-ellipsis', pages - 4, pages - 3, pages - 2, pages - 1, pages]
  return [1, 'start-ellipsis', currentPage.value - 1, currentPage.value, currentPage.value + 1, 'end-ellipsis', pages]
})
const workbenchLabel = computed(() => activeLocale.value === 'en' ? 'Task center' : '任务中心')
const actionRequiredTaskCount = computed(() => Array.from(generationStore.tasks.values()).filter(taskRequiresAction).length)

watch(query, () => {
  currentPage.value = 1
  closeCourseMenu()
})

watch(displayMode, mode => localStorage.setItem('teacher_course_library_view', mode))

watch(totalPages, pages => {
  if (currentPage.value > pages) currentPage.value = pages
})

onMounted(async () => {
  document.addEventListener('pointerdown', closeOpenMenusOnOutsidePointer)
  courseStore.currentCourseId = ''
  courseStore.currentCourseVersionId = ''
  courseStore.currentNode = null
  generationStore.restoreGenerationState()
  if (!embedded) {
    await courseStore.fetchCourseList({ surface: 'teacher' })
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOpenMenusOnOutsidePointer)
})

async function toggleCreateMenu() {
  closeCourseMenu()
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

function closeOpenMenusOnOutsidePointer(event: PointerEvent) {
  if (createMenuOpen.value && !createMenuRef.value?.contains(event.target as Node)) closeCreateMenu()
  if (!openCourseMenuId.value) return
  const target = event.target instanceof Element ? event.target : null
  const courseMenuRoot = target?.closest<HTMLElement>('[data-course-menu-root]')
  if (courseMenuRoot?.dataset.courseMenuRoot !== openCourseMenuId.value) closeCourseMenu()
}

function openBlankCourse() {
  closeCreateMenu()
  void router.push({ name: 'teacher-course-create' })
}

function openMarkdownImport() {
  closeCreateMenu()
  fileInput.value?.click()
}

function toggleCourseMenu(courseId: string) {
  closeCreateMenu()
  openCourseMenuId.value = openCourseMenuId.value === courseId ? '' : courseId
}

function closeCourseMenu() {
  openCourseMenuId.value = ''
}

function pageNumberLabel(page: number) {
  return t('courseLibrary.pagination.pageNumber', '第 {page} 页').replace('{page}', String(page))
}

async function selectPage(page: number) {
  const nextPage = Math.max(1, Math.min(totalPages.value, page))
  if (nextPage === currentPage.value) return
  currentPage.value = nextPage
  pageJumpInput.value = ''
  closeCourseMenu()
  await nextTick()
  courseGridRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}

function jumpToPage() {
  const page = Number.parseInt(pageJumpInput.value, 10)
  if (!Number.isFinite(page)) return
  void selectPage(page)
}

function courseStatus(course: Course) {
  const task = generationStore.getTask(course.course_id)
  const emptyDraft = course.course_status === 'draft' && !task
  const publishedWarning = Boolean(task && isPublishedWarning(task))
  const active = Boolean(task && taskNeedsAttention(task))
  const labels: Record<string, string> = {
    pending: t('courseLibrary.status.pending', '等待生成'),
    running: t('courseLibrary.status.running', '正在生成'),
    paused: t('courseLibrary.status.paused', '已暂停'),
    waiting_for_review: t('teacherCourseLibrary.status.waitingReview', '等待教师确认'),
    conflict: t('courseLibrary.status.conflict', '需要确认'),
    error: t('courseLibrary.status.error', '生成失败'),
    completed_with_warnings: t('courseLibrary.status.warnings', '生成完成但有警告'),
    completed: t('teacherCourseLibrary.status.ready', '课程可维护'),
  }
  return {
    active,
    retryable: task?.status === 'error',
    tone: emptyDraft
      ? 'draft'
      : task?.status === 'error'
      ? 'danger'
      : active
        ? 'processing'
        : publishedWarning
          ? 'warning'
          : 'ready',
    label: emptyDraft
      ? t('teacherCourseLibrary.status.draft', '待开始备课')
      : publishedWarning
      ? t('teacherCourseLibrary.status.readyWithSuggestions', '已发布，有优化建议')
      : labels[task?.status || 'completed'] || t('teacherCourseLibrary.status.ready', '课程可维护'),
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

function taskRequiresAction(task: { status: string; publicationAllowed?: boolean; recovery?: { state: string } }) {
  if (isPublishedWarning(task)) return false
  return ['paused', 'waiting_for_review', 'conflict', 'error', 'completed_with_warnings'].includes(task.status)
}

function teacherAssetSummary(course: Course, active: boolean) {
  if (active) return t('teacherCourseLibrary.teacherSummary.generating', '大纲与教案正在生成，进入课程查看确认点')
  if (course.course_status === 'draft' && !course.is_published) {
    return t('teacherCourseLibrary.teacherSummary.empty', '空课程空间 · 从大纲开始新建或生成')
  }
  if (course.is_published) {
    return t('teacherCourseLibrary.teacherSummary.published', '大纲已确认 · {count} 个教学单元 · 可继续维护 PPT')
      .replace('{count}', String(course.node_count || 0))
  }
  return t('teacherCourseLibrary.teacherSummary.draft', '{count} 个教学单元 · 等待继续组织教学')
    .replace('{count}', String(course.node_count || 0))
}

function openCourse(courseId: string) {
  closeCourseMenu()
  void router.push({
    name: 'course-workspace',
    params: { courseId, mode: 'setup' },
    query: { returnTo: '/courses?view=courses' },
  })
}

function handleCoursePrimary(courseId: string) {
  openCourse(courseId)
}

function openGeneratingCourse(courseId: string) {
  void router.push({ name: 'teacher-course-production', params: { courseId } })
}

function openCourseProduction(courseId: string) {
  closeCourseMenu()
  void router.push({ name: 'course-workspace', params: { courseId, mode: 'setup' }, query: { returnTo: '/courses?view=courses' } })
}

function openTaskCenter(courseId = '') {
  closeCourseMenu()
  selectedWorkbenchCourseId.value = courseId
  workbenchOpen.value = true
}

async function generateCourse(payload: { subject: string; options: CourseGenerationOptions }) {
  if (creating.value) return
  creating.value = true
  try {
    const result = await courseStore.generateCourse(payload.subject, {
      ...payload.options,
      teacher_authoring_mode: 'lesson_assets_v1',
    })
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
  closeCourseMenu()
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
.course-library { --course-content-width:1280px; --course-grid-width:1280px; --course-card-height:140px; --course-grid-gap:14px; --course-cover-width:72px; width:100%; height:100%; overflow:auto; padding:30px clamp(18px,4vw,54px) 48px; border:1px solid rgba(255,255,255,.82); border-radius:var(--lz-radius-surface); background:rgba(255,255,255,.76); box-shadow:var(--lz-shadow-panel); backdrop-filter:none; -webkit-backdrop-filter:none; }
.course-library--embedded { border:0; border-radius:0; background:var(--lz-surface); box-shadow:none; }
.library-header { max-width:var(--course-content-width); margin:0 auto; display:flex; align-items:flex-end; justify-content:space-between; gap:24px; }
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
.library-toolbar { max-width:var(--course-content-width); margin:24px auto 14px; display:grid; grid-template-columns:minmax(240px,360px) minmax(0,1fr); align-items:center; gap:12px; }
.library-toolbar label { width:100%; height:44px; display:flex; align-items:center; gap:8px; padding:0 14px; border:1px solid rgba(203,213,225,.68); border-radius:999px; color:var(--lz-text-muted); background:rgba(255,255,255,.76); box-shadow:inset 0 1px 0 rgba(255,255,255,.8); }
.library-toolbar input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font-size: 12px; }
.library-toolbar__end { min-width:0; display:flex; align-items:center; justify-content:flex-end; gap:14px; }
.library-resume { min-width:0; height:44px; display:grid; grid-template-columns:28px minmax(0,1fr) auto; align-items:center; gap:9px; padding:0 12px 0 9px; overflow:hidden; border:1px solid rgba(134,239,172,.62); border-radius:12px; color:var(--lz-text); background:rgba(240,253,244,.52); box-shadow:inset 0 1px 0 rgba(255,255,255,.88); text-align:left; cursor:pointer; transition:border-color .18s ease,background .18s ease,box-shadow .18s ease; }
.library-resume:hover,.library-resume:focus-visible { border-color:rgba(74,222,128,.92); background:rgba(240,253,244,.9); box-shadow:0 5px 14px rgba(21,128,61,.08),inset 0 1px 0 rgba(255,255,255,.9); outline:none; }
.library-resume:focus-visible { box-shadow:0 0 0 3px rgba(34,197,94,.14),0 5px 14px rgba(21,128,61,.08); }
.library-resume__icon { width:28px; height:28px; display:grid; place-items:center; border-radius:9px; color:#15803d; background:rgba(220,252,231,.92); }
.library-resume__copy { min-width:0; display:flex; align-items:baseline; gap:6px; overflow:hidden; white-space:nowrap; }
.library-resume__label { flex:0 0 auto; color:#15803d; font-size:10px; font-weight:800; }
.library-resume__title,.library-resume__location { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.library-resume__title { flex:0 1 auto; color:var(--lz-text-strong); font-size:12px; font-weight:800; }
.library-resume__separator { flex:0 0 auto; color:rgba(148,163,184,.78); font-size:11px; }
.library-resume__location { flex:1 1 auto; color:var(--lz-text-muted); font-size:11px; }
.library-resume__action { display:inline-flex; align-items:center; gap:5px; color:#166534; font-size:11px; font-weight:800; white-space:nowrap; }
.library-resume__action svg { transition:transform .18s ease; }
.library-resume:hover .library-resume__action svg { transform:translateX(3px); }
.library-resume:focus-visible .library-resume__action svg { transform:translateX(3px); }
.library-toolbar__summary { justify-self:end; display:flex; align-items:center; color:var(--lz-text-muted); font-size:12px; white-space:nowrap; }
.library-toolbar__summary span { padding:0 11px; border-right:1px solid var(--lz-border); }
.library-toolbar__summary span:last-child { padding-right:0; border-right:0; }
.library-toolbar__summary strong { margin-left:4px; color:var(--lz-text-primary); font-size:13px; }
.library-toolbar__summary strong.attention { color:var(--lz-warning); }
.library-view-switch { flex:0 0 auto; height:38px; display:flex; align-items:center; gap:2px; padding:3px; border:1px solid var(--lz-border); border-radius:10px; background:var(--lz-fill); }
.library-view-switch button { height:30px; display:flex; align-items:center; gap:6px; padding:0 9px; border:0; border-radius:7px; color:var(--lz-text-muted); background:transparent; font-size:11px; font-weight:700; cursor:pointer; }
.library-view-switch button.active { color:var(--lz-brand-strong); background:var(--lz-surface); box-shadow:0 2px 7px rgb(79 70 229 / 10%); }
.library-view-switch button:focus-visible { outline:3px solid var(--lz-brand-soft); }
.course-collection { width:100%; max-width:var(--course-grid-width); margin:0 auto; }
.course-collection__header { height:36px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:11px; }
.course-collection__header strong { color:var(--lz-text-primary); font-size:13px; }
.course-grid { width:100%; margin:14px 0 0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); justify-content:start; gap:var(--course-grid-gap); }
.course-grid[data-view='list'] { --course-cover-width:44px; grid-template-columns:minmax(0,1fr); gap:8px; }
.course-grid[data-view='list'] .course-item { min-height:86px; grid-template-columns:minmax(0,1fr) 132px; border-radius:12px; }
.course-grid[data-view='list'] .course-main { min-height:84px; grid-template-columns:52px minmax(0,1fr); gap:14px; padding:10px 8px 10px 14px; border-radius:12px 0 0 12px; }
.course-grid[data-view='list'] .course-copy { display:grid; grid-template-columns:minmax(180px,1fr) minmax(170px,.72fr) minmax(220px,1fr); align-items:center; gap:18px; }
.course-grid[data-view='list'] .course-copy h2 { min-height:0; margin:0; display:block; overflow:hidden; font-size:14px; text-overflow:ellipsis; white-space:nowrap; }
.course-grid[data-view='list'] .teacher-asset-summary { margin:0; font-size:11px; }
.course-grid[data-view='list'] .generation-progress { grid-column:2; width:100%; margin-top:6px; }
.course-grid[data-view='list'] .course-actions { flex-direction:row; align-items:center; justify-content:flex-start; padding:10px 48px 10px 10px; }
.course-grid[data-view='list'] .course-menu-trigger { top:50%; right:12px; transform:translateY(-50%); }
.course-grid[data-view='list'] .course-menu { top:calc(50% + 22px); right:12px; }
.course-item { position:relative; min-width:0; min-height:var(--course-card-height); display:grid; grid-template-columns:minmax(0,1fr) 96px; overflow:visible; border:1px solid rgba(203,213,225,.74); border-radius:15px; background:rgba(255,255,255,.88); box-shadow:0 4px 14px rgba(79,70,229,.04),inset 0 1px 0 rgba(255,255,255,.94); transition:border-color .18s ease,box-shadow .18s ease,transform .18s ease; backdrop-filter:none; -webkit-backdrop-filter:none; }
.course-item:hover { border-color:rgba(165,180,252,.92); box-shadow:0 12px 28px rgba(79,70,229,.09); transform:translateY(-1px); }
.course-item--menu-open { z-index:30; }
.course-main { min-width:0; min-height:calc(var(--course-card-height) - 2px); display:grid; grid-template-columns:var(--course-cover-width) minmax(0,1fr); align-items:center; gap:14px; padding:13px 8px 13px 16px; border:0; border-radius:15px 0 0 15px; color:inherit; background:transparent; text-align:left; cursor:pointer; }
.course-main:focus-visible { outline:3px solid rgba(99,102,241,.18); outline-offset:-4px; }
.course-copy { min-width:0; display:flex; flex-direction:column; align-items:stretch; }
.course-copy h2 { min-height:43px; margin:0 0 8px; overflow:hidden; display:-webkit-box; color:var(--lz-text-strong); font-size:16px; font-weight:800; line-height:1.35; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
.teacher-asset-summary { display:block; margin-top:6px; overflow:hidden; color:var(--lz-text-muted); font-size:9px; line-height:1.45; text-overflow:ellipsis; white-space:nowrap; }
.course-status { display:flex; align-items:center; gap:7px; color:var(--lz-text-secondary); font-size:12px; line-height:1; }
.course-status strong { margin-left:2px; color:inherit; font-size:12px; font-weight:800; }
.course-status__dot { width:7px; height:7px; flex:0 0 auto; border-radius:50%; background:#22a45a; }
.course-status--processing { color:var(--lz-brand-strong); }
.course-status--processing .course-status__dot { background:var(--lz-brand); }
.course-status--danger { color:var(--lz-danger); }
.course-status--danger .course-status__dot { background:var(--lz-danger); }
.course-status--warning { color:#a16207; }
.course-status--warning .course-status__dot { background:#d97706; }
.course-status--draft { color:var(--lz-text-muted); }
.course-status--draft .course-status__dot { background:#94a3b8; }
.generation-progress { display:block; width:min(100%,260px); margin-top:10px; }
.progress-track { display:block; height:4px; overflow:hidden; border-radius:999px; background:var(--lz-surface-muted); }
.progress-track > span { display:block; height:100%; border-radius:inherit; background:var(--lz-brand); }
.course-item[data-state='danger'] .progress-track > span { background:var(--lz-danger); }
.course-actions { position:relative; min-width:0; display:flex; flex-direction:column; align-items:flex-end; justify-content:flex-end; padding:12px 14px; }
.course-primary-action { min-height:34px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 4px; border:0; border-radius:8px; color:var(--lz-brand-strong); background:transparent; font-size:12px; font-weight:800; white-space:nowrap; cursor:pointer; }
.course-primary-action:hover,.course-primary-action:focus-visible { color:#4f46e5; background:var(--lz-brand-soft); outline:none; }
.course-menu-trigger { position:absolute; top:12px; right:12px; width:32px; height:32px; display:grid; place-items:center; border:1px solid rgba(203,213,225,.72); border-radius:8px; color:var(--lz-text-secondary); background:rgba(255,255,255,.84); cursor:pointer; }
.course-menu-trigger:hover,.course-menu-trigger:focus-visible,.course-menu-trigger[aria-expanded='true'] { border-color:#c7d2fe; color:var(--lz-brand-strong); background:#f5f3ff; outline:none; }
.course-menu { position:absolute; z-index:50; top:52px; right:14px; width:160px; overflow:hidden; padding:4px; border:1px solid rgba(203,213,225,.82); border-radius:10px; background:#fff; box-shadow:0 12px 28px rgba(51,65,85,.16),0 3px 8px rgba(79,70,229,.07); }
.course-menu__item { width:100%; min-height:36px; display:flex; align-items:center; gap:8px; padding:0 9px; border:0; border-radius:7px; color:var(--lz-text); background:transparent; font-size:12px; font-weight:700; text-align:left; cursor:pointer; }
.course-menu__item:hover,.course-menu__item:focus-visible { color:var(--lz-brand-strong); background:var(--lz-brand-soft); outline:none; }
.course-menu__item--danger { margin-top:3px; border-top:1px solid rgba(226,232,240,.9); border-radius:0 0 7px 7px; color:var(--lz-danger); }
.course-menu__item--danger:hover,.course-menu__item--danger:focus-visible { color:var(--lz-danger); background:var(--lz-danger-soft); }
.course-menu-enter-active,.course-menu-leave-active { transition:opacity .14s ease,transform .14s ease; transform-origin:top right; }
.course-menu-enter-from,.course-menu-leave-to { opacity:0; transform:translateY(-4px) scale(.98); }
.course-library--paginated { padding-bottom:118px; }
.library-pagination-dock { position:fixed; z-index:90; left:50%; bottom:max(18px,env(safe-area-inset-bottom)); max-width:calc(100vw - 32px); min-height:54px; display:flex; align-items:center; justify-content:center; gap:8px; padding:8px 10px; border:1px solid rgba(203,213,225,.82); border-radius:16px; background:rgba(255,255,255,.94); box-shadow:0 18px 46px rgba(51,65,85,.2),0 4px 14px rgba(79,70,229,.1); backdrop-filter:blur(16px); transform:translateX(-50%); }
.pagination-pages { display:flex; align-items:center; gap:5px; }
.pagination-button { height:34px; display:inline-flex; align-items:center; justify-content:center; gap:5px; border:1px solid rgba(203,213,225,.76); border-radius:9px; color:var(--lz-text-secondary,#64748b); background:#fff; font-size:12px; font-weight:700; cursor:pointer; transition:border-color .15s ease,color .15s ease,background .15s ease,transform .15s ease; }
.pagination-button:hover:not(:disabled),.pagination-button:focus-visible { border-color:#a5b4fc; color:var(--lz-brand-strong,#4f46e5); background:var(--lz-brand-soft,#eef2ff); outline:none; transform:translateY(-1px); }
.pagination-button:disabled { color:var(--lz-text-muted,#94a3b8); background:var(--lz-surface-muted,#f1f5f9); cursor:not-allowed; opacity:.58; }
.pagination-button--direction { min-width:78px; padding:0 10px; }
.pagination-button--page { width:34px; padding:0; }
.pagination-button--page.active { border-color:transparent; color:#fff; background:linear-gradient(135deg,#6366f1,#8b5cf6); box-shadow:0 5px 12px rgba(99,102,241,.22); }
.pagination-ellipsis { width:22px; color:var(--lz-text-muted,#94a3b8); font-size:13px; text-align:center; }
.pagination-jump { display:flex; align-items:center; gap:5px; margin-left:3px; padding-left:11px; border-left:1px solid rgba(226,232,240,.92); color:var(--lz-text-muted,#94a3b8); font-size:11px; white-space:nowrap; }
.pagination-jump input { width:46px; height:32px; padding:0 5px; border:1px solid rgba(203,213,225,.84); border-radius:8px; color:var(--lz-text,#334155); background:#fff; font-size:12px; font-weight:700; text-align:center; outline:none; }
.pagination-jump input:focus { border-color:#a5b4fc; box-shadow:0 0 0 3px rgba(99,102,241,.12); }
.pagination-jump__submit { height:32px; padding:0 10px; border:0; border-radius:8px; color:var(--lz-brand-strong,#4f46e5); background:var(--lz-brand-soft,#eef2ff); font-size:11px; font-weight:800; cursor:pointer; }
.task-center-button > .action-count,
.create-course-menu__item small,
.library-resume__label,
.library-resume__separator,
.library-resume__location,
.library-resume__action,
.library-view-switch button,
.course-collection__header,
.course-grid[data-view='list'] .teacher-asset-summary,
.teacher-asset-summary,
.pagination-jump,
.pagination-jump__submit { font-size:12px; }
.pagination-jump__submit:hover,.pagination-jump__submit:focus-visible { color:#fff; background:var(--lz-brand,#6366f1); outline:none; }
.pagination-dock-enter-active,.pagination-dock-leave-active { transition:opacity .16s ease,transform .16s ease; }
.pagination-dock-enter-from,.pagination-dock-leave-to { opacity:0; transform:translate(-50%,8px); }
.library-state { min-height: 360px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--lz-text-muted); }
.course-library--empty .library-state { min-height:260px; }
.library-state strong { color: var(--lz-text); font-size: 15px; }
.library-state span { font-size: 12px; }
.spin { animation: spin 1s linear infinite; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width:1360px) {
  .course-grid { max-width:1040px; grid-template-columns:repeat(2,minmax(0,1fr)); }
}
@media (max-width:980px) {
  .library-toolbar { grid-template-columns:minmax(220px,320px) minmax(0,1fr); }
  .library-toolbar__summary { display:none; }
  .library-resume__location,.library-resume__separator { display:none; }
}
@media (max-width:860px) {
  .course-collection { max-width:620px; }
  .course-grid { grid-template-columns:minmax(0,1fr); }
  .course-grid[data-view='list'] .course-copy { grid-template-columns:minmax(0,1fr); gap:5px; }
  .course-grid[data-view='list'] .course-status,.course-grid[data-view='list'] .teacher-asset-summary { display:none; }
}
@media (max-width:700px) {
  .course-library { --course-card-height:150px; --course-cover-width:72px; padding:22px 20px 40px; border:0; border-radius:0; box-shadow:none; }
  .course-library--paginated { padding-bottom:126px; }
  .library-header { align-items:stretch; flex-direction:column; }
  .library-actions,.create-course-menu,.create-course-trigger { width:100%; }
  .create-course-menu__panel { left:0; right:0; width:auto; }
  .library-toolbar { margin-top:18px; grid-template-columns:minmax(0,1fr); gap:10px; }
  .library-toolbar__end { justify-content:space-between; }
  .library-view-switch button span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  .course-collection__header { height:auto; min-height:36px; gap:12px; }
  .library-resume { width:100%; }
  .course-item { min-height:var(--course-card-height); grid-template-columns:minmax(0,1fr) 96px; }
  .course-main { min-height:calc(var(--course-card-height) - 2px); grid-template-columns:var(--course-cover-width) minmax(0,1fr); gap:13px; padding:16px 5px 16px 14px; }
  .course-actions { padding:13px; }
  .course-menu-trigger { top:13px; right:13px; }
  .course-menu { top:51px; right:13px; }
  .course-copy h2 { white-space:normal; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
  .library-pagination-dock { width:calc(100vw - 24px); max-width:none; flex-wrap:wrap; gap:6px; padding:7px 8px; border-radius:14px; }
  .pagination-button--direction { min-width:34px; width:34px; padding:0; }
  .pagination-button--direction > span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  .pagination-jump { width:100%; justify-content:center; margin-left:0; padding:5px 0 0; border-top:1px solid rgba(226,232,240,.92); border-left:0; }
}
@media (max-width:620px) {
  .library-global-actions { gap:2px; }
  .global-action-button { width:40px; padding:0; }
  .global-action-button .action-label { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  .task-center-button > .action-count { position:absolute; top:-4px; right:-4px; min-width:17px; height:17px; padding:0 4px; }
}
@media (prefers-reduced-motion: reduce) {
  .library-resume,.library-resume__action svg { transition:none; }
  .library-resume:hover .library-resume__action svg,.library-resume:focus-visible .library-resume__action svg { transform:none; }
}
</style>
