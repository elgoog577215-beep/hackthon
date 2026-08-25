<template>
  <section
    class="course-library glass-panel-elevated"
    :class="{ 'course-library--paginated': totalPages > 1, 'course-library--embedded': embedded }"
  >
    <div class="library-toolbar">
      <label class="library-search">
        <Search :size="16" />
        <input
          v-model="query"
          type="search"
          :aria-label="t('teacherCourseLibrary.searchPlaceholder')"
          :placeholder="t('teacherCourseLibrary.searchPlaceholder')"
        />
      </label>
      <label class="library-select">
        <span class="sr-only">{{ t('teacherCourseLibrary.statusFilter') }}</span>
        <select v-model="statusFilter" :aria-label="t('teacherCourseLibrary.statusFilter')">
          <option v-for="option in statusFilterOptions" :key="option.value" :value="option.value">
            {{ statusOptionLabel(option) }}
          </option>
        </select>
      </label>
      <label class="library-select">
        <span class="sr-only">{{ t('teacherCourseLibrary.termFilter') }}</span>
        <select v-model="termFilter" :aria-label="t('teacherCourseLibrary.termFilter')">
          <option value="all">{{ t('teacherCourseLibrary.allTerms') }}</option>
          <option v-for="option in termFilterOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <label class="library-select">
        <span class="sr-only">{{ t('teacherCourseLibrary.sortBy') }}</span>
        <select v-model="sortMode" :aria-label="t('teacherCourseLibrary.sortBy')">
          <option value="priority">{{ t('teacherCourseLibrary.sortPriority') }}</option>
          <option value="nextSession">{{ t('teacherCourseLibrary.sortNextSession') }}</option>
          <option value="term">{{ t('teacherCourseLibrary.sortTerm') }}</option>
          <option value="name">{{ t('teacherCourseLibrary.sortName') }}</option>
        </select>
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
      <div v-if="displayMode === 'list'" class="course-list-columns" aria-hidden="true">
        <span>{{ t('teacherCourseLibrary.columns.course') }}</span>
        <span>{{ t('teacherCourseLibrary.columns.status') }}</span>
        <span>{{ t('teacherCourseLibrary.columns.time') }}</span>
        <span>{{ t('teacherCourseLibrary.columns.location') }}</span>
        <span>{{ t('teacherCourseLibrary.columns.term') }}</span>
        <span>{{ t('teacherCourseLibrary.columns.version') }}</span>
        <span>{{ t('teacherCourseLibrary.columns.actions') }}</span>
      </div>
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
            <span class="course-identity">
              <CourseCover :course-id="course.course_id" :title="course.course_name" variant="glyph" />
              <span class="course-identity__copy">
                <h2>{{ formatCourseTitle(course.course_name) }}</h2>
                <span v-if="course.course_code" class="course-identity__meta">{{ course.course_code }}</span>
              </span>
            </span>
            <span class="course-status" :class="`course-status--${status.tone}`">
              <span class="course-status__dot" aria-hidden="true"></span>
              <span class="course-status__copy">
                <small>{{ t('teacherCourseLibrary.columns.status') }}</small>
                <strong>{{ status.label }}</strong>
              </span>
              <strong v-if="status.inProgress">{{ Math.round(status.progress) }}%</strong>
            </span>
            <span class="course-time course-field">
              <Clock3 class="course-field__icon" :size="17" aria-hidden="true" />
              <span class="course-field__copy">
                <small>{{ t('teacherCourseLibrary.columns.time') }}</small>
                <strong>{{ courseNextSessionWhen(course) }}</strong>
              </span>
            </span>
            <span class="course-location course-field">
              <MapPin class="course-field__icon" :size="17" aria-hidden="true" />
              <span class="course-field__copy">
                <small>{{ t('teacherCourseLibrary.columns.location') }}</small>
                <strong>{{ courseLocation(course) }}</strong>
              </span>
            </span>
            <span class="course-term course-field">
              <span class="course-field__copy">
                <small>{{ t('teacherCourseLibrary.columns.term') }}</small>
                <strong>{{ courseTermLabel(course) }}</strong>
              </span>
            </span>
            <span class="course-version course-field">
              <span class="course-field__copy">
                <small>{{ t('teacherCourseLibrary.columns.version') }}</small>
                <strong>{{ courseVersionLabel(course) }}</strong>
              </span>
            </span>
            <span
                v-if="status.inProgress"
                class="generation-progress"
                role="progressbar"
                :aria-label="status.detail"
                :aria-valuenow="Math.round(status.progress)"
                aria-valuemin="0"
                aria-valuemax="100"
              >
                <span class="progress-track"><span :style="{ width: `${status.progress}%` }"></span></span>
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
import { ArrowRight, BookOpenText, ChevronLeft, ChevronRight, Clock3, Ellipsis, Grid2X2, List, LoaderCircle, MapPin, Search, Trash2 } from 'lucide-vue-next'
import CourseCover from '../components/CourseCover.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'
import { activeLocale, t } from '../shared/i18n'
import { courseProductionTaskDetail } from '../utils/course-production'
import { coursePreparationLabel, coursePreparationState } from '../utils/course-preparation'
import { formatCourseTitle } from '../utils/course-presentation'
import type { Course } from '../stores/course'

const router = useRouter()
const { embedded = false } = defineProps<{ embedded?: boolean }>()
const { course: courseStore, generation: generationStore } = useTeacherCourseRuntime()
const COURSES_PER_PAGE = 9
type CourseStatusFilter = 'all' | 'attention' | 'preparing' | 'prepared'
type CourseSortMode = 'priority' | 'nextSession' | 'term' | 'name'
const query = ref('')
const statusFilter = ref<CourseStatusFilter>('all')
const termFilter = ref('all')
const sortMode = ref<CourseSortMode>('priority')
const displayMode = ref<'grid' | 'list'>(localStorage.getItem('teacher_course_library_view') === 'list' ? 'list' : 'grid')
const currentPage = ref(1)
const courseGridRef = ref<HTMLElement | null>(null)
const openCourseMenuId = ref('')
const workbenchOpen = ref(false)
const selectedWorkbenchCourseId = ref('')

const termFilterOptions = computed(() => {
  const options = new Map<string, string>()
  courseStore.courseList.forEach(course => {
    const value = courseTermKey(course)
    if (value) options.set(value, courseTermLabel(course))
  })
  return Array.from(options, ([value, label]) => ({ value, label }))
    .sort((left, right) => right.label.localeCompare(left.label, localeTag()))
})
const searchedCourses = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return courseStore.courseList
  return courseStore.courseList.filter(course => [
    course.course_name,
    course.course_code,
    course.academic_year,
    course.term,
  ].some(value => String(value || '').toLocaleLowerCase().includes(keyword)))
})
const termFilteredCourses = computed(() => termFilter.value === 'all'
  ? searchedCourses.value
  : searchedCourses.value.filter(course => courseTermKey(course) === termFilter.value))
const filteredCourses = computed(() => sortCourses(statusFilter.value === 'all'
  ? termFilteredCourses.value
  : termFilteredCourses.value.filter(course => courseFilterKey(course) === statusFilter.value)))
const statusFilterOptions = computed<Array<{ value: CourseStatusFilter; label: string; count: number }>>(() => {
  const counts: Record<CourseStatusFilter, number> = {
    all: termFilteredCourses.value.length,
    attention: 0,
    preparing: 0,
    prepared: 0,
  }
  termFilteredCourses.value.forEach(course => { counts[courseFilterKey(course)] += 1 })
  return [
    { value: 'all', label: t('teacherCourseLibrary.allCourses'), count: counts.all },
    { value: 'attention', label: t('teacherCourseLibrary.attentionCourses'), count: counts.attention },
    { value: 'preparing', label: t('teacherCourseLibrary.preparingCourses'), count: counts.preparing },
    { value: 'prepared', label: t('teacherCourseLibrary.preparedCourses'), count: counts.prepared },
  ]
})
const hasActiveFilters = computed(() => Boolean(query.value.trim()) || statusFilter.value !== 'all' || termFilter.value !== 'all')
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
watch([query, statusFilter, termFilter, sortMode], () => {
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

function statusOptionLabel(option: { label: string; count: number }) {
  return `${option.label} · ${option.count}`
}

function pageNumberLabel(page: number) {
  return t('courseLibrary.pagination.pageNumber', '第 {page} 页').replace('{page}', String(page))
}

async function selectPage(page: number) {
  const nextPage = Math.max(1, Math.min(totalPages.value, page))
  if (nextPage === currentPage.value) return
  currentPage.value = nextPage
  closeCourseMenu()
  await nextTick()
  courseGridRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}

function localeTag() {
  return activeLocale.value === 'zh' ? 'zh-CN' : 'en-US'
}

function courseTermKey(course: Course) {
  const academicYear = String(course.academic_year || '').trim()
  const term = String(course.term || '').trim()
  return academicYear || term ? `${academicYear}\u0000${term}` : ''
}

function courseTermLabel(course: Course) {
  return [course.academic_year, course.term].map(value => String(value || '').trim()).filter(Boolean).join(' ')
    || t('teacherCourseLibrary.termUnset')
}

function parseCourseDate(value?: string) {
  if (!value) return null
  const parsed = new Date(value.includes('T') ? value : `${value}T12:00:00`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function courseNextSessionWhen(course: Course) {
  const session = course.next_session
  if (!session?.date) return t('teacherCourseLibrary.noUpcomingSession')
  const parsed = parseCourseDate(session.date)
  const date = parsed
    ? new Intl.DateTimeFormat(localeTag(), { month: 'short', day: 'numeric', weekday: 'short' }).format(parsed)
    : session.date
  const time = session.start_time?.slice(0, 5) || t('teacherHome.timePending')
  return t('teacherCourseLibrary.sessionWhen').replace('{date}', date).replace('{time}', time)
}

function courseLocation(course: Course) {
  return course.next_session?.location || t('teacherCourseLibrary.locationPending')
}

function courseVersionLabel(course: Course) {
  const versionId = String(course.current_course_version_id || '').trim()
  const numbered = /^cv(\d+)$/i.exec(versionId)
  if (numbered) return `V${numbered[1]}`
  return versionId ? t('teacherCourseLibrary.currentVersion') : t('teacherCourseLibrary.versionPending')
}

function courseNextSessionTime(course: Course) {
  return Date.parse(`${course.next_session?.date || ''}T${course.next_session?.start_time || '23:59:59'}`) || Number.POSITIVE_INFINITY
}

function courseUpdatedTime(course: Course) {
  return Date.parse(course.updated_at || '') || 0
}

function coursePriority(course: Course) {
  const status = courseStatus(course)
  if (status.needsAction) return 0
  if (status.inProgress) return 1
  if (course.next_session) return 2
  return 3
}

function sortCourses(courses: Course[]) {
  return [...courses].sort((left, right) => {
    if (sortMode.value === 'name') return left.course_name.localeCompare(right.course_name, localeTag())
    if (sortMode.value === 'term') return courseTermLabel(right).localeCompare(courseTermLabel(left), localeTag())
    if (sortMode.value === 'nextSession') {
      return courseNextSessionTime(left) - courseNextSessionTime(right)
        || courseUpdatedTime(right) - courseUpdatedTime(left)
    }
    return coursePriority(left) - coursePriority(right)
      || courseNextSessionTime(left) - courseNextSessionTime(right)
      || courseUpdatedTime(right) - courseUpdatedTime(left)
  })
}

function courseStatus(course: Course) {
  const task = generationStore.getTask(course.course_id)
  const preparation = coursePreparationState(course, task)
  const inProgress = Boolean(task && ['pending', 'running'].includes(task.status))
  const needsAction = Boolean(task && taskRequiresAction(task))
  return {
    active: inProgress || needsAction,
    inProgress,
    needsAction,
    retryable: task?.status === 'error',
    tone: task?.status === 'error' ? 'danger' : needsAction ? 'warning' : preparation === 'prepared' ? 'ready' : 'processing',
    label: coursePreparationLabel(preparation),
    detail: courseProductionTaskDetail(task)
      || (task?.currentPhase ? t(`courseGeneration.phases.${task.currentPhase}`, task.currentPhase) : '')
      || t('courseLibrary.status.preparing', '正在准备课程'),
    progress: Math.max(0, Math.min(100, task?.progress || 0)),
  }
}

function courseFilterKey(course: Course): Exclude<CourseStatusFilter, 'all'> {
  const task = generationStore.getTask(course.course_id)
  if (task && taskRequiresAction(task)) return 'attention'
  return coursePreparationState(course, task)
}

function taskRequiresAction(task: { status: string; publicationAllowed?: boolean; recovery?: { state: string } }) {
  if (task.status === 'completed_with_warnings'
    && (task.publicationAllowed === true || task.recovery?.state === 'completed')) return false
  return ['paused', 'waiting_for_review', 'conflict', 'error', 'completed_with_warnings'].includes(task.status)
}

function recommendedAction(course: Course, status: ReturnType<typeof courseStatus>) {
  if (status.needsAction) {
    return { label: t('teacherCourseLibrary.actions.resolve') }
  }
  if (status.active) return { label: t('teacherCourseLibrary.actions.viewProgress') }
  if (course.course_status === 'draft' && !course.is_published) {
    return { label: t('teacherCourseLibrary.actions.start') }
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
.course-library { --course-content-width:1320px; --course-grid-width:1320px; --course-grid-gap:18px; --course-cover-width:52px; width:100%; height:100%; overflow:auto; padding:24px clamp(20px,3.2vw,44px) 48px; border:0; border-radius:var(--lz-radius-surface); background:#fbfcff; box-shadow:none; }
.course-library--embedded { border:0; border-radius:0; background:var(--lz-surface); box-shadow:none; }
.library-toolbar { max-width:var(--course-content-width); margin:0 auto 22px; display:grid; grid-template-columns:minmax(320px,1fr) 156px 156px 156px auto; align-items:center; gap:10px; }
.library-search { width:100%; height:42px; display:flex; align-items:center; gap:9px; padding:0 14px; border:1px solid #dbe2ee; border-radius:12px; color:#64748b; background:#fff; transition:border-color .16s ease,box-shadow .16s ease; }
.library-search:focus-within,.library-select:focus-within { border-color:#a5b4fc; box-shadow:0 4px 14px rgba(79,70,229,.08),0 0 0 3px rgba(99,102,241,.09); }
.library-toolbar input { min-width:0; flex:1; border:0; outline:0; color:#334155; background:transparent; font-size:13px; }
.library-toolbar input::placeholder { color:#64748b; }
.library-select{height:42px;display:flex;align-items:center;padding:0 10px;border:1px solid #dbe2ee;border-radius:12px;background:#fff;transition:border-color .16s ease,box-shadow .16s ease}
.library-select select{width:100%;min-width:0;border:0;outline:0;color:#475569;background:transparent;font-size:12px;font-weight:680;cursor:pointer}
.library-view-switch { flex:0 0 auto; height:42px; display:flex; align-items:center; gap:2px; padding:4px; border:1px solid #dbe2ee; border-radius:12px; background:#f8fafc; }
.library-view-switch button { height:32px; display:flex; align-items:center; gap:6px; padding:0 10px; border:0; border-radius:8px; color:#64748b; background:transparent; font-size:12px; font-weight:700; cursor:pointer; }
.library-view-switch button.active { color:#4f46e5; background:#fff; box-shadow:0 3px 9px rgba(51,65,85,.09); }
.library-view-switch button:focus-visible { outline:3px solid var(--lz-brand-soft); }
.course-collection { width:100%; max-width:var(--course-grid-width); margin:0 auto; }
.course-grid { width:100%; margin:0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); justify-content:start; gap:var(--course-grid-gap); }
.course-list-columns{min-width:1120px;display:grid;grid-template-columns:minmax(280px,1.45fr) 130px 150px 150px 140px 90px 118px;gap:0;padding:0 0 10px;border-bottom:1px solid #e6eaf2;color:#64748b;font-size:11px;font-weight:750}
.course-list-columns span{padding:0 14px}.course-list-columns span:last-child{padding-left:16px}
.course-grid[data-view='list'] { --course-cover-width:38px; min-width:1120px; display:block; }
.course-item { position:relative; min-width:0; min-height:198px; display:grid; grid-template-rows:minmax(0,1fr) 46px; overflow:visible; border:1px solid #e1e6ef; border-radius:15px; background:#fff; box-shadow:none; transition:border-color .18s ease,background .18s ease,transform .18s cubic-bezier(.2,.8,.2,1); }
.course-item:hover { border-color:#bfc8f7; background:#fefeff; transform:translateY(-2px); }
.course-item--menu-open { z-index:30; }
.course-main { min-width:0; display:grid; grid-template-columns:minmax(0,1fr) auto; grid-template-areas:'identity status' 'time time' 'location location' 'progress progress'; align-content:start; gap:14px 12px; padding:20px 20px 16px; border:0; border-radius:15px 15px 0 0; color:inherit; background:transparent; text-align:left; cursor:pointer; }
.course-main:focus-visible { outline:3px solid rgba(99,102,241,.18); outline-offset:-4px; }
.course-identity{grid-area:identity;min-width:0;display:grid;grid-template-columns:var(--course-cover-width) minmax(0,1fr);align-items:center;gap:13px}
.course-identity__copy{min-width:0;display:grid;gap:5px}.course-identity h2{margin:0;overflow:hidden;display:-webkit-box;color:#1e293b;font-size:16px;font-weight:800;line-height:1.35;-webkit-box-orient:vertical;-webkit-line-clamp:2}.course-identity__meta{display:none;overflow:hidden;color:#64748b;font-size:11px;text-overflow:ellipsis;white-space:nowrap}
.course-field{min-width:0;display:flex;align-items:center;gap:9px;color:#64748b}.course-field__icon{flex:0 0 auto;color:#94a3b8}.course-field__copy{min-width:0;display:grid;gap:2px}.course-field small,.course-status__copy small{color:#64748b;font-size:10px;font-weight:650}.course-field strong{overflow:hidden;color:#475569;font-size:12px;font-weight:720;text-overflow:ellipsis;white-space:nowrap}
.course-time{grid-area:time}.course-location{grid-area:location}.course-term{grid-area:term;display:none}.course-version{grid-area:version;display:none}
.course-status{grid-area:status;min-width:0;display:flex;align-items:center;align-self:start;gap:7px;padding:6px 9px;border-radius:999px;color:#166534;background:#f0fdf4}
.course-status__copy{min-width:0;display:grid}.course-status__copy small{display:none}.course-status__copy strong{overflow:hidden;color:inherit;font-size:11px;font-weight:780;text-overflow:ellipsis;white-space:nowrap}.course-status>strong{margin-left:0;color:inherit;font-size:11px;font-weight:800}
.course-status__dot { width:7px; height:7px; flex:0 0 auto; border-radius:50%; background:#22a45a; }
.course-status--processing { color:#4338ca; background:#eef2ff; }
.course-status--processing .course-status__dot { background:var(--lz-brand); }
.course-status--danger { color:#b91c1c; background:#fef2f2; }
.course-status--danger .course-status__dot { background:var(--lz-danger); }
.course-status--warning { color:#a16207; background:#fffbeb; }
.course-status--warning .course-status__dot { background:#d97706; }
.course-status--draft { color:#64748b; background:#f1f5f9; }
.course-status--draft .course-status__dot { background:#94a3b8; }
.generation-progress { grid-area:progress; display:block; width:100%; }
.progress-track { display:block; height:4px; overflow:hidden; border-radius:999px; background:var(--lz-surface-muted); }
.progress-track > span { display:block; height:100%; border-radius:inherit; background:var(--lz-brand); }
.course-item[data-state='danger'] .progress-track > span { background:var(--lz-danger); }
.course-actions { position:relative; min-width:0; display:flex; align-items:center; justify-content:flex-end; gap:4px; padding:6px 10px 6px 14px; border-top:1px solid #edf0f5; }
.course-primary-action { min-height:34px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 9px; border:0; border-radius:8px; color:var(--lz-brand-strong); background:transparent; font-size:12px; font-weight:800; white-space:nowrap; cursor:pointer; }
.course-primary-action:hover,.course-primary-action:focus-visible { color:#4f46e5; background:var(--lz-brand-soft); outline:none; }
.course-menu-trigger { width:32px; height:32px; flex:0 0 auto; display:grid; place-items:center; border:1px solid transparent; border-radius:8px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.course-menu-trigger:hover,.course-menu-trigger:focus-visible,.course-menu-trigger[aria-expanded='true'] { border-color:#c7d2fe; color:var(--lz-brand-strong); background:#f5f3ff; outline:none; }
.course-menu { position:absolute; z-index:50; right:10px; bottom:42px; width:160px; overflow:hidden; padding:4px; border:1px solid rgba(203,213,225,.82); border-radius:10px; background:#fff; box-shadow:0 12px 28px rgba(51,65,85,.16),0 3px 8px rgba(79,70,229,.07); }
.course-menu__item { width:100%; min-height:36px; display:flex; align-items:center; gap:8px; padding:0 9px; border:0; border-radius:7px; color:var(--lz-text); background:transparent; font-size:12px; font-weight:700; text-align:left; cursor:pointer; }
.course-menu__item:hover,.course-menu__item:focus-visible { color:var(--lz-brand-strong); background:var(--lz-brand-soft); outline:none; }
.course-menu__item--danger { color:var(--lz-danger); }
.course-menu__item--danger:hover,.course-menu__item--danger:focus-visible { color:var(--lz-danger); background:var(--lz-danger-soft); }
.course-grid[data-view='list'] .course-item{min-height:82px;display:grid;grid-template-columns:minmax(0,1fr) 118px;grid-template-rows:none;margin:0;border:0;border-bottom:1px solid #e6eaf2;border-radius:0;background:transparent;box-shadow:none;transform:none}
.course-grid[data-view='list'] .course-item:hover{background:#f8faff;box-shadow:none}
.course-grid[data-view='list'] .course-main{min-height:81px;grid-template-columns:minmax(280px,1.45fr) 130px 150px 150px 140px 90px;grid-template-areas:'identity status time location term version';align-items:center;gap:0;padding:8px 0;border-radius:0}
.course-grid[data-view='list'] .course-identity,.course-grid[data-view='list'] .course-field,.course-grid[data-view='list'] .course-status{padding:0 12px}
.course-grid[data-view='list'] .course-identity{grid-template-columns:var(--course-cover-width) minmax(0,1fr);gap:10px}.course-grid[data-view='list'] .course-identity h2{display:block;overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.course-grid[data-view='list'] .course-identity__meta{display:block;font-size:10px}
.course-grid[data-view='list'] .course-field{display:block}.course-grid[data-view='list'] .course-field__icon,.course-grid[data-view='list'] .course-field small,.course-grid[data-view='list'] .course-status__copy small{display:none}.course-grid[data-view='list'] .course-field strong{display:block;white-space:normal}.course-grid[data-view='list'] .course-status{align-self:center;padding:0 12px;border-radius:0;background:transparent}.course-grid[data-view='list'] .course-term,.course-grid[data-view='list'] .course-version{display:block}.course-grid[data-view='list'] .generation-progress{display:none}
.course-grid[data-view='list'] .course-actions{justify-content:flex-start;padding:8px 8px 8px 16px;border-top:0;border-left:1px solid #edf0f5}.course-grid[data-view='list'] .course-menu{right:8px;bottom:auto;top:64px}
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
.library-view-switch button { font-size:12px; }
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
  .library-toolbar { grid-template-columns:minmax(260px,1fr) repeat(3,minmax(132px,1fr)) auto; }
}
@media (max-width:860px) {
  .course-collection { max-width:620px; }
  .course-grid:not([data-view='list']) { grid-template-columns:minmax(0,1fr); }
  .library-toolbar { grid-template-columns:repeat(4,minmax(0,1fr)); }
  .library-search { grid-column:1/-1; }
  .course-list-columns { display:none; }
  .course-grid[data-view='list'] { min-width:0; }
  .course-grid[data-view='list'] .course-item { min-height:0; grid-template-columns:minmax(0,1fr); grid-template-rows:auto 44px; margin:0 0 12px; border:1px solid #e1e6ef; border-radius:14px; background:#fff; }
  .course-grid[data-view='list'] .course-main { min-height:0; grid-template-columns:repeat(2,minmax(0,1fr)); grid-template-areas:'identity identity' 'status term' 'time location' 'version version'; align-items:start; gap:15px 12px; padding:16px; border-radius:14px 14px 0 0; }
  .course-grid[data-view='list'] .course-identity,.course-grid[data-view='list'] .course-field,.course-grid[data-view='list'] .course-status { padding:0; }
  .course-grid[data-view='list'] .course-field { display:flex; align-items:flex-start; }
  .course-grid[data-view='list'] .course-field__copy { gap:3px; }
  .course-grid[data-view='list'] .course-field small,.course-grid[data-view='list'] .course-status__copy small { display:block; }
  .course-grid[data-view='list'] .course-field strong { white-space:normal; }
  .course-grid[data-view='list'] .course-status { align-self:start; gap:7px; }
  .course-grid[data-view='list'] .course-status__dot { margin-top:5px; }
  .course-grid[data-view='list'] .course-actions { justify-content:flex-end; padding:5px 9px; border-top:1px solid #edf0f5; border-left:0; }
  .course-grid[data-view='list'] .course-menu { right:8px; top:auto; bottom:40px; }
}
@media (max-width:700px) {
  .course-library { --course-cover-width:48px; padding:16px 14px 40px; border:0; border-radius:0; box-shadow:none; }
  .course-library--paginated { padding-bottom:126px; }
  .library-toolbar { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-bottom:16px; }
  .library-search{grid-column:1/-1}.library-view-switch{grid-column:2;justify-self:end}
  .library-view-switch button span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  .course-main{padding:18px 16px 14px;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:'identity status' 'time time' 'location location' 'progress progress'}
  .course-status{padding:5px 8px}.course-status__dot{width:6px;height:6px}
  .library-pagination-dock { width:calc(100vw - 24px); max-width:none; flex-wrap:wrap; gap:6px; padding:7px 8px; border-radius:14px; }
  .pagination-button--direction { min-width:34px; width:34px; padding:0; }
  .pagination-button--direction > span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
}
@media (prefers-reduced-motion:reduce) {
  .course-item,.library-search,.library-select { transition:none; }
}
</style>
