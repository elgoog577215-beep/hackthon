<template>
  <section
    class="course-library glass-panel-elevated"
    :class="{ 'course-library--paginated': totalPages > 1, 'course-library--embedded': embedded }"
  >
    <div class="library-toolbar">
      <div class="library-status-filters" role="group" :aria-label="t('teacherCourseLibrary.statusFilter')">
        <button
          v-for="option in statusFilterOptions"
          :key="option.value"
          type="button"
          :class="{ active: statusFilter === option.value }"
          :aria-pressed="statusFilter === option.value"
          @click="statusFilter = option.value"
        >
          <span>{{ option.label }}</span>
          <strong>{{ option.count }}</strong>
        </button>
      </div>
      <label class="library-search">
        <Search :size="16" />
        <input
          v-model="query"
          type="search"
          :aria-label="t('courseLibrary.search', '搜索课程')"
          :placeholder="t('courseLibrary.search', '搜索课程')"
        />
      </label>
      <div class="library-view-switch" role="group" :aria-label="t('teacherCourseLibrary.viewMode')">
        <button type="button" :class="{ active: displayMode === 'grid' }" :aria-pressed="displayMode === 'grid'" :title="t('teacherCourseLibrary.cardView')" @click="displayMode = 'grid'">
          <Grid2X2 :size="16" /><span>{{ t('teacherCourseLibrary.cardView') }}</span>
        </button>
        <button type="button" :class="{ active: displayMode === 'list' }" :aria-pressed="displayMode === 'list'" :title="t('teacherCourseLibrary.listView')" @click="displayMode = 'list'">
          <List :size="16" /><span>{{ t('teacherCourseLibrary.listView') }}</span>
        </button>
      </div>
    </div>

    <div v-if="courseStore.loading" class="library-state">
      <LoaderCircle class="spin" :size="22" />
      <span>{{ t('courseLibrary.loading', '正在读取课程') }}</span>
    </div>

    <div v-else-if="!filteredCourses.length" class="library-state empty">
      <BookOpenText :size="28" />
      <strong>{{ hasActiveFilters ? t('courseLibrary.noMatch', '没有匹配的课程') : t('courseLibrary.emptyTitle', '还没有课程') }}</strong>
      <span>{{ hasActiveFilters ? t('teacherCourseLibrary.noFilterMatchBody') : t('teacherCourseLibrary.emptyBody', '新建课程后，从教学大纲开始组织教学。') }}</span>
    </div>

    <section v-else class="course-collection" :aria-label="t('teacherCourseLibrary.collectionTitle')">
      <p class="sr-only" aria-live="polite">{{ t('teacherCourseLibrary.collectionSummary').replace('{count}', String(filteredCourses.length)) }}</p>
      <div ref="courseGridRef" class="course-grid" :data-view="displayMode" data-layout="responsive-three-column">
        <article
        v-for="{ course, status, action } in courseCards"
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
            <span class="teacher-asset-summary">{{ teacherAssetSummary(course, status) }}</span>
          </span>
        </button>

        <div
          class="course-actions"
          :data-course-menu-root="course.course_id"
          @keydown.esc.stop.prevent="closeCourseMenu"
        >
          <button
            type="button"
            class="course-primary-action"
            @click="handleRecommendedAction(course, status)"
          >
            {{ action.label }}
            <ArrowRight :size="17" />
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
import { ArrowRight, BookOpenText, ChevronLeft, ChevronRight, Ellipsis, Grid2X2, List, LoaderCircle, Search, Trash2, Workflow } from 'lucide-vue-next'
import CourseCover from '../components/CourseCover.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'
import { activeLocale, t } from '../shared/i18n'
import { courseProductionTaskDetail } from '../utils/course-production'
import { formatCourseTitle } from '../utils/course-presentation'
import type { Course } from '../stores/course'

const router = useRouter()
const { embedded = false } = defineProps<{ embedded?: boolean }>()
const { course: courseStore, generation: generationStore } = useTeacherCourseRuntime()
const COURSES_PER_PAGE = 9
type CourseStatusFilter = 'all' | 'not_started' | 'preparing' | 'attention' | 'prepared'
const query = ref('')
const statusFilter = ref<CourseStatusFilter>('all')
const displayMode = ref<'grid' | 'list'>(localStorage.getItem('teacher_course_library_view') === 'list' ? 'list' : 'grid')
const currentPage = ref(1)
const pageJumpInput = ref('')
const courseGridRef = ref<HTMLElement | null>(null)
const openCourseMenuId = ref('')
const workbenchOpen = ref(false)
const selectedWorkbenchCourseId = ref('')

const orderedCourses = computed(() => [...courseStore.courseList].sort((left, right) => {
  const leftTime = Date.parse(left.updated_at || '') || 0
  const rightTime = Date.parse(right.updated_at || '') || 0
  return rightTime - leftTime
}))
const searchedCourses = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return orderedCourses.value
  return orderedCourses.value.filter(course => course.course_name.toLocaleLowerCase().includes(keyword))
})
const filteredCourses = computed(() => statusFilter.value === 'all'
  ? searchedCourses.value
  : searchedCourses.value.filter(course => courseFilterKey(course) === statusFilter.value))
const statusFilterOptions = computed<Array<{ value: CourseStatusFilter; label: string; count: number }>>(() => {
  const counts: Record<CourseStatusFilter, number> = {
    all: searchedCourses.value.length,
    not_started: 0,
    preparing: 0,
    attention: 0,
    prepared: 0,
  }
  searchedCourses.value.forEach(course => { counts[courseFilterKey(course)] += 1 })
  return [
    { value: 'all', label: t('teacherCourseLibrary.allCourses'), count: counts.all },
    { value: 'not_started', label: t('teacherCourseLibrary.notStartedCourses'), count: counts.not_started },
    { value: 'preparing', label: t('teacherCourseLibrary.preparingCourses'), count: counts.preparing },
    { value: 'attention', label: t('teacherCourseLibrary.attentionCourses'), count: counts.attention },
    { value: 'prepared', label: t('teacherCourseLibrary.preparedCourses'), count: counts.prepared },
  ]
})
const hasActiveFilters = computed(() => Boolean(query.value.trim()) || statusFilter.value !== 'all')
const totalPages = computed(() => Math.max(1, Math.ceil(filteredCourses.value.length / COURSES_PER_PAGE)))
const paginatedCourses = computed(() => {
  const start = (currentPage.value - 1) * COURSES_PER_PAGE
  return filteredCourses.value.slice(start, start + COURSES_PER_PAGE)
})
const courseCards = computed(() => paginatedCourses.value.map(course => {
  const status = courseStatus(course)
  return {
    course,
    status,
    action: recommendedAction(course, status),
  }
}))
const paginationItems = computed<Array<number | 'start-ellipsis' | 'end-ellipsis'>>(() => {
  const pages = totalPages.value
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1)
  if (currentPage.value <= 4) return [1, 2, 3, 4, 5, 'end-ellipsis', pages]
  if (currentPage.value >= pages - 3) return [1, 'start-ellipsis', pages - 4, pages - 3, pages - 2, pages - 1, pages]
  return [1, 'start-ellipsis', currentPage.value - 1, currentPage.value, currentPage.value + 1, 'end-ellipsis', pages]
})
watch([query, statusFilter], () => {
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

function closeOpenMenusOnOutsidePointer(event: PointerEvent) {
  if (!openCourseMenuId.value) return
  const target = event.target instanceof Element ? event.target : null
  const courseMenuRoot = target?.closest<HTMLElement>('[data-course-menu-root]')
  if (courseMenuRoot?.dataset.courseMenuRoot !== openCourseMenuId.value) closeCourseMenu()
}

function toggleCourseMenu(courseId: string) {
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
    pending: t('teacherCourseLibrary.status.preparing'),
    running: t('teacherCourseLibrary.status.preparing'),
    paused: t('teacherCourseLibrary.status.needsAction'),
    waiting_for_review: t('teacherCourseLibrary.status.waitingReview'),
    conflict: t('teacherCourseLibrary.status.needsAction'),
    error: t('teacherCourseLibrary.status.needsAction'),
    completed_with_warnings: t('teacherCourseLibrary.status.needsAction'),
    completed: t('teacherCourseLibrary.status.ready'),
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
      ? t('teacherCourseLibrary.status.draft')
      : publishedWarning
      ? t('teacherCourseLibrary.status.readyWithSuggestions')
      : labels[task?.status || 'completed'] || t('teacherCourseLibrary.status.ready'),
    detail: courseProductionTaskDetail(task)
      || (task?.currentPhase ? t(`courseGeneration.phases.${task.currentPhase}`, task.currentPhase) : '')
      || t('courseLibrary.status.preparing', '正在准备课程'),
    progress: Math.max(0, Math.min(100, task?.progress || 0)),
  }
}

function courseFilterKey(course: Course): Exclude<CourseStatusFilter, 'all'> {
  const task = generationStore.getTask(course.course_id)
  if (course.course_status === 'draft' && !task) return 'not_started'
  if (task && taskRequiresAction(task)) return 'attention'
  if (task && ['pending', 'running'].includes(task.status)) return 'preparing'
  return 'prepared'
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

function teacherAssetSummary(course: Course, status: ReturnType<typeof courseStatus>) {
  if (status.active) {
    return t('teacherCourseLibrary.teacherSummary.generating')
      .replace('{progress}', String(Math.round(status.progress)))
  }
  if (course.course_status === 'draft' && !course.is_published) {
    return t('teacherCourseLibrary.teacherSummary.empty')
  }
  if (course.next_session?.date) {
    const dateValue = new Date(`${course.next_session.date}T00:00:00`)
    const dateLabel = Number.isNaN(dateValue.getTime())
      ? course.next_session.date
      : new Intl.DateTimeFormat(activeLocale.value === 'en' ? 'en-US' : 'zh-CN', {
          month: 'short',
          day: 'numeric',
        }).format(dateValue)
    return t('teacherCourseLibrary.teacherSummary.scheduled')
      .replace('{count}', String(course.node_count || 0))
      .replace('{date}', dateLabel)
      .replace('{time}', String(course.next_session.start_time || '').slice(0, 5))
      .replace('{sequence}', String(course.next_session.sequence || 0))
  }
  return t(course.is_published
    ? 'teacherCourseLibrary.teacherSummary.published'
    : 'teacherCourseLibrary.teacherSummary.draft')
    .replace('{count}', String(course.node_count || 0))
}

function recommendedAction(course: Course, status: ReturnType<typeof courseStatus>) {
  if (status.active && ['danger', 'warning'].includes(status.tone)) {
    return { label: t('teacherCourseLibrary.actions.resolve') }
  }
  if (status.active) return { label: t('teacherCourseLibrary.actions.viewProgress') }
  if (course.course_status === 'draft' && !course.is_published) {
    return { label: t('teacherCourseLibrary.actions.start') }
  }
  if (status.tone === 'warning') {
    return { label: t('teacherCourseLibrary.actions.reviewSuggestions') }
  }
  if (course.next_session) return { label: t('teacherCourseLibrary.actions.prepareNext') }
  return { label: t('teacherCourseLibrary.actions.continue') }
}

function handleRecommendedAction(course: Course, status: ReturnType<typeof courseStatus>) {
  if (status.active) {
    openTaskCenter(course.course_id)
    return
  }
  openCourse(course.course_id)
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

function openCourseProduction(courseId: string) {
  closeCourseMenu()
  void router.push({ name: 'course-workspace', params: { courseId, mode: 'setup' }, query: { returnTo: '/courses?view=courses' } })
}

function openTaskCenter(courseId = '') {
  closeCourseMenu()
  selectedWorkbenchCourseId.value = courseId
  workbenchOpen.value = true
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
.course-library { --course-content-width:1280px; --course-grid-width:1280px; --course-card-height:140px; --course-grid-gap:14px; --course-cover-width:72px; width:100%; height:100%; overflow:auto; padding:18px clamp(18px,3vw,36px) 40px; border:1px solid rgba(255,255,255,.82); border-radius:var(--lz-radius-surface); background:rgba(255,255,255,.76); box-shadow:var(--lz-shadow-panel); backdrop-filter:none; -webkit-backdrop-filter:none; }
.course-library--embedded { border:0; border-radius:0; background:var(--lz-surface); box-shadow:none; }
.library-toolbar { max-width:var(--course-content-width); margin:0 auto 14px; display:grid; grid-template-columns:minmax(0,1fr) minmax(260px,420px) auto; align-items:center; gap:14px; }
.library-search { width:100%; height:38px; display:flex; align-items:center; gap:8px; padding:0 12px; border:1px solid rgba(203,213,225,.76); border-radius:10px; color:var(--lz-text-muted); background:var(--lz-surface); }
.library-search:focus-within { border-color:#a5b4fc; box-shadow:0 0 0 3px rgba(99,102,241,.1); }
.library-toolbar input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font-size: 12px; }
.library-status-filters { min-width:0; display:flex; align-items:center; gap:3px; overflow-x:auto; scrollbar-width:none; }
.library-status-filters::-webkit-scrollbar { display:none; }
.library-status-filters button { min-height:34px; flex:0 0 auto; display:inline-flex; align-items:center; gap:5px; padding:0 9px; border:0; border-radius:8px; color:var(--lz-text-secondary); background:transparent; font-size:12px; font-weight:700; white-space:nowrap; cursor:pointer; }
.library-status-filters button:hover { color:var(--lz-text-strong); background:var(--lz-fill); }
.library-status-filters button.active { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.library-status-filters button:focus-visible { outline:3px solid rgba(99,102,241,.14); outline-offset:-1px; }
.library-status-filters strong { min-width:18px; color:var(--lz-text-muted); font-size:11px; font-weight:750; text-align:center; }
.library-status-filters button.active strong { color:inherit; }
.library-view-switch { flex:0 0 auto; height:38px; display:flex; align-items:center; gap:2px; padding:3px; border:1px solid var(--lz-border); border-radius:10px; background:var(--lz-fill); }
.library-view-switch button { height:30px; display:flex; align-items:center; gap:6px; padding:0 9px; border:0; border-radius:7px; color:var(--lz-text-muted); background:transparent; font-size:11px; font-weight:700; cursor:pointer; }
.library-view-switch button.active { color:var(--lz-brand-strong); background:var(--lz-surface); box-shadow:0 2px 7px rgb(79 70 229 / 10%); }
.library-view-switch button:focus-visible { outline:3px solid var(--lz-brand-soft); }
.course-collection { width:100%; max-width:var(--course-grid-width); margin:0 auto; }
.course-grid { width:100%; margin:0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); justify-content:start; gap:var(--course-grid-gap); }
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
.library-view-switch button,
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
@media (max-width:1100px) {
  .library-toolbar { grid-template-columns:minmax(0,1fr) auto; }
  .library-status-filters { grid-column:1/-1; }
  .library-search { grid-column:1; }
  .library-view-switch { grid-column:2; }
}
@media (max-width:860px) {
  .course-collection { max-width:620px; }
  .course-grid { grid-template-columns:minmax(0,1fr); }
  .course-grid[data-view='list'] .course-copy { grid-template-columns:minmax(0,1fr); gap:5px; }
  .course-grid[data-view='list'] .course-status,.course-grid[data-view='list'] .teacher-asset-summary { display:none; }
}
@media (max-width:700px) {
  .course-library { --course-card-height:150px; --course-cover-width:72px; padding:14px 16px 40px; border:0; border-radius:0; box-shadow:none; }
  .course-library--paginated { padding-bottom:126px; }
  .library-toolbar { grid-template-columns:minmax(0,1fr) auto; gap:9px; }
  .library-view-switch button span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
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
</style>
