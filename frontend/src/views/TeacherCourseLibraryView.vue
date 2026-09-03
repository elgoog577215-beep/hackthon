<template>
  <section class="course-library" :class="{ 'course-library--embedded': embedded }">
    <div class="library-toolbar" :class="{ 'library-toolbar--selecting': selectedCount > 0 }">
      <template v-if="selectedCount > 0">
        <p class="selection-summary" aria-live="polite">
          {{ t('teacherCourseLibrary.management.selectedCount').replace('{count}', String(selectedCount)) }}
        </p>
        <span class="toolbar-spacer" />
        <button type="button" class="toolbar-button" :disabled="deleting" @click="clearSelection">
          {{ t('teacherCourseLibrary.management.clearSelection') }}
        </button>
        <button
          type="button"
          class="toolbar-button toolbar-button--danger"
          data-testid="delete-selected-courses"
          :disabled="deleting"
          @click="deleteSelectedCourses"
        >
          <LoaderCircle v-if="deleting" class="spin" :size="16" />
          <Trash2 v-else :size="16" />
          {{ t('teacherCourseLibrary.management.deleteSelected') }}
        </button>
      </template>

      <template v-else>
        <label class="library-search">
          <Search :size="16" aria-hidden="true" />
          <input
            v-model="query"
            type="search"
            :aria-label="t('teacherCourseLibrary.searchPlaceholder')"
            :placeholder="t('teacherCourseLibrary.searchPlaceholder')"
          />
        </label>
        <UiSelectMenu
          data-testid="course-status-filter"
          :model-value="statusFilter"
          :options="statusMenuOptions"
          :label="t('teacherCourseLibrary.statusLabel')"
          :accessibility-label="t('teacherCourseLibrary.statusFilter')"
          @update:model-value="setStatusFilter"
        />
        <UiSelectMenu
          data-testid="course-term-filter"
          :model-value="termFilter"
          :options="termMenuOptions"
          :label="t('teacherCourseLibrary.termLabel')"
          :accessibility-label="t('teacherCourseLibrary.termFilter')"
          @update:model-value="setTermFilter"
        />
        <span v-if="courseStore.loading && courseStore.courseList.length" class="toolbar-loading" role="status">
          <LoaderCircle class="spin" :size="15" />{{ t('courseLibrary.loading', '正在读取课程') }}
        </span>
      </template>
    </div>

    <p v-if="courseStore.courseListError && courseStore.courseList.length" class="library-inline-error" role="status">
      <span>{{ t('teacherCourseLibrary.management.refreshFailed') }}</span>
      <button type="button" :disabled="courseStore.loading" @click="refreshCourses">
        {{ t('common.retry', '重试') }}
      </button>
    </p>

    <div v-if="courseStore.loading && !courseStore.courseList.length" class="library-state" role="status">
      <LoaderCircle class="spin" :size="22" />
      <span>{{ t('courseLibrary.loading', '正在读取课程') }}</span>
    </div>

    <div v-else-if="courseStore.courseListError && !courseStore.courseList.length" class="library-state library-state--error" role="alert">
      <strong>{{ t('teacherCourseLibrary.management.loadFailed') }}</strong>
      <span>{{ t('teacherCourseLibrary.management.loadFailedHelp') }}</span>
      <button type="button" :disabled="courseStore.loading" @click="refreshCourses">
        {{ t('common.retry', '重试') }}
      </button>
    </div>

    <div v-else-if="!filteredCourses.length" class="library-state library-state--empty">
      <BookOpenText :size="26" aria-hidden="true" />
      <strong>{{ hasActiveFilters ? t('courseLibrary.noMatch', '没有匹配的课程') : t('courseLibrary.emptyTitle', '还没有课程') }}</strong>
      <span>{{ hasActiveFilters ? t('teacherCourseLibrary.noFilterMatchBody') : t('teacherCourseLibrary.emptyBody') }}</span>
    </div>

    <div v-else class="course-table-region">
      <table class="course-table">
        <caption class="sr-only">{{ t('teacherCourseLibrary.management.tableLabel') }}</caption>
        <thead>
          <tr>
            <th class="selection-column" scope="col">
              <input
                type="checkbox"
                :checked="allVisibleSelected"
                :indeterminate="someVisibleSelected"
                :aria-label="t('teacherCourseLibrary.management.selectPage')"
                :disabled="deleting"
                @change="toggleVisibleSelection"
              />
            </th>
            <th scope="col" :aria-sort="sortAria('name')">
              <button type="button" class="column-sort" :aria-label="sortLabel(t('teacherCourseLibrary.columns.course'))" @click="toggleSort('name')">
                {{ t('teacherCourseLibrary.columns.course') }}<component :is="sortIcon('name')" :size="13" />
              </button>
            </th>
            <th scope="col" :aria-sort="sortAria('status')">
              <button type="button" class="column-sort" :aria-label="sortLabel(t('courseTasks.nodes', '内容进度'))" @click="toggleSort('status')">
                {{ t('courseTasks.nodes', '内容进度') }}<component :is="sortIcon('status')" :size="13" />
              </button>
            </th>
            <th scope="col" :aria-sort="sortAria('nextSession')">
              <button type="button" class="column-sort" :aria-label="sortLabel(t('teacherCourseLibrary.columns.time'))" @click="toggleSort('nextSession')">
                {{ t('teacherCourseLibrary.columns.time') }}<component :is="sortIcon('nextSession')" :size="13" />
              </button>
            </th>
            <th scope="col" :aria-sort="sortAria('term')">
              <button type="button" class="column-sort" :aria-label="sortLabel(t('teacherCourseLibrary.columns.term'))" @click="toggleSort('term')">
                {{ t('teacherCourseLibrary.columns.term') }}<component :is="sortIcon('term')" :size="13" />
              </button>
            </th>
            <th scope="col" :aria-sort="sortAria('updated')">
              <button type="button" class="column-sort" :aria-label="sortLabel(t('teacherCourseLibrary.columns.lastEdited'))" @click="toggleSort('updated')">
                {{ t('teacherCourseLibrary.columns.lastEdited') }}<component :is="sortIcon('updated')" :size="13" />
              </button>
            </th>
            <th class="actions-column" scope="col">{{ t('teacherCourseLibrary.columns.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="{ course, production } in courseRows" :key="course.course_id" :class="{ selected: selectedCourseIds.has(course.course_id) }">
            <td class="selection-column">
              <input
                type="checkbox"
                :checked="selectedCourseIds.has(course.course_id)"
                :aria-label="t('teacherCourseLibrary.management.selectCourse').replace('{name}', formatCourseTitle(course.course_name))"
                :disabled="deleting"
                @change="toggleCourseSelection(course.course_id, $event)"
              />
            </td>
            <td class="course-cell">
              <button type="button" class="course-main" @click="openCourse(course.course_id)">
                <span class="course-identity">
                  <strong>{{ formatCourseTitle(course.course_name) }}</strong>
                  <small v-if="course.course_code">{{ course.course_code }}</small>
                </span>
              </button>
            </td>
            <td class="course-production-cell">
              <strong class="course-production-summary" :data-tone="production.tone" role="status">
                {{ production.label }}
              </strong>
            </td>
            <td class="course-session">
              <strong>{{ courseNextSessionWhen(course) }}</strong>
              <small v-if="course.next_session?.location">{{ course.next_session.location }}</small>
            </td>
            <td class="course-term">{{ courseTermLabel(course) }}</td>
            <td class="course-updated">{{ courseUpdatedLabel(course) }}</td>
            <td class="actions-column">
              <span class="course-actions">
                <button type="button" class="course-action" @click="openCourse(course.course_id, production.stage)">
                  {{ production.actionLabel }}<ChevronRight :size="14" />
                </button>
                <button
                  type="button"
                  class="delete-course-button"
                  :data-testid="`delete-course-${course.course_id}`"
                  :aria-label="t('teacherCourseLibrary.management.deleteCourse').replace('{name}', formatCourseTitle(course.course_name))"
                  :title="t('courseLibrary.delete', '删除课程')"
                  :disabled="deleting"
                  @click="deleteCourse(course.course_id, formatCourseTitle(course.course_name))"
                >
                  <Trash2 :size="16" />
                </button>
              </span>
            </td>
          </tr>
        </tbody>
      </table>

      <nav v-if="totalPages > 1" class="library-pagination" :aria-label="t('courseLibrary.pagination.label', '课程分页')">
        <button type="button" class="pagination-direction" :disabled="currentPage === 1" :aria-label="t('courseLibrary.pagination.previous', '上一页')" @click="selectPage(currentPage - 1)">
          <ChevronLeft :size="16" />{{ t('courseLibrary.pagination.previous', '上一页') }}
        </button>
        <span class="pagination-pages" role="group" :aria-label="t('courseLibrary.pagination.pageSelection', '页面选择')">
          <template v-for="item in paginationItems" :key="`page-${item}`">
            <span v-if="typeof item === 'string'" class="pagination-ellipsis" aria-hidden="true">…</span>
            <button v-else type="button" :class="{ active: item === currentPage }" :aria-current="item === currentPage ? 'page' : undefined" :aria-label="pageNumberLabel(item)" @click="selectPage(item)">
              {{ item }}
            </button>
          </template>
        </span>
        <button type="button" class="pagination-direction" :disabled="currentPage === totalPages" :aria-label="t('courseLibrary.pagination.next', '下一页')" @click="selectPage(currentPage + 1)">
          {{ t('courseLibrary.pagination.next', '下一页') }}<ChevronRight :size="16" />
        </button>
      </nav>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, ArrowUp, ArrowUpDown, BookOpenText, ChevronLeft, ChevronRight, LoaderCircle, Search, Trash2 } from 'lucide-vue-next'
import UiSelectMenu from '../components/UiSelectMenu.vue'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'
import { activeLocale, t } from '../shared/i18n'
import { coursePreparationState } from '../utils/course-preparation'
import { formatCourseTitle } from '../utils/course-presentation'
import type { Course } from '../stores/course'
import type { Task } from '../stores/types'

const router = useRouter()
const route = useRoute()
const { embedded = false } = defineProps<{ embedded?: boolean }>()
const { course: courseStore, generation: generationStore } = useTeacherCourseRuntime()
const COURSES_PER_PAGE = 9
type CourseStatusFilter = 'all' | 'preparing' | 'prepared'
type CourseSortMode = 'name' | 'status' | 'nextSession' | 'term' | 'updated'
type CourseSortDirection = 'ascending' | 'descending'
type WorkbenchStage = 'foundation' | 'lesson' | 'script' | 'ppt'
type CourseProductionSummary = {
  planned_lessons?: number
  outline_ready?: boolean
  ready_lesson_plans?: number
  ready_handouts?: number
  ready_ppts?: number
  outline_confirmed?: boolean
  confirmed_lesson_plans?: number
  confirmed_handouts?: number
  confirmed_ppts?: number
  current_production?: {
    target?: 'lesson_plan' | 'script' | 'ppt'
    status?: string
    completed?: number
    total?: number
    failed?: number
    progress?: number
    message?: string
    updated_at?: string
  }
}
type ProductionTaskView = {
  label: string
  tone: 'active' | 'attention'
  actionLabel: string
  stage: WorkbenchStage
}
type CourseProductionView = {
  label: string
  tone: 'ready' | 'active' | 'attention' | 'idle'
  actionLabel: string
  stage?: WorkbenchStage
}

const query = ref(String(route.query.q || ''))
const statusFilter = ref<CourseStatusFilter>(['preparing', 'prepared'].includes(String(route.query.status)) ? route.query.status as CourseStatusFilter : 'all')
const termFilter = ref(String(route.query.term || 'all'))
const sortMode = ref<CourseSortMode>(['name', 'status', 'nextSession', 'term', 'updated'].includes(String(route.query.sort)) ? route.query.sort as CourseSortMode : 'updated')
const sortDirection = ref<CourseSortDirection>(route.query.dir === 'ascending' ? 'ascending' : 'descending')
const currentPage = ref(1)
const selectedCourseIds = ref<Set<string>>(new Set())
const deleting = ref(false)
const COURSE_PROGRESS_REFRESH_MS = 5000
let progressRefreshTimer: number | null = null
let progressRefreshPending = false

const termFilterOptions = computed(() => {
  const options = new Map<string, string>()
  courseStore.courseList.forEach(course => {
    const value = courseTermKey(course)
    if (value) options.set(value, courseTermLabel(course))
  })
  return Array.from(options, ([value, label]) => ({ value, label })).sort((left, right) => right.label.localeCompare(left.label, localeTag()))
})
const searchedCourses = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return courseStore.courseList
  return courseStore.courseList.filter(course => [course.course_name, course.course_code, course.academic_year, course.term].some(value => String(value || '').toLocaleLowerCase().includes(keyword)))
})
const termFilteredCourses = computed(() => termFilter.value === 'all' ? searchedCourses.value : searchedCourses.value.filter(course => courseTermKey(course) === termFilter.value))
const filteredCourses = computed(() => sortCourses(statusFilter.value === 'all' ? termFilteredCourses.value : termFilteredCourses.value.filter(course => courseFilterKey(course) === statusFilter.value)))
const statusFilterOptions = computed<Array<{ value: CourseStatusFilter; label: string; count: number }>>(() => {
  const counts: Record<CourseStatusFilter, number> = { all: termFilteredCourses.value.length, preparing: 0, prepared: 0 }
  termFilteredCourses.value.forEach(course => { counts[courseFilterKey(course)] += 1 })
  return [
    { value: 'all', label: t('teacherCourseLibrary.allCourses'), count: counts.all },
    { value: 'preparing', label: t('teacherCourseLibrary.preparingCourses'), count: counts.preparing },
    { value: 'prepared', label: t('teacherCourseLibrary.preparedCourses'), count: counts.prepared },
  ]
})
const statusMenuOptions = computed(() => statusFilterOptions.value.map(option => ({ value: option.value, label: option.label, count: option.count })))
const termMenuOptions = computed(() => [{ value: 'all', label: t('teacherCourseLibrary.allTerms') }, ...termFilterOptions.value])
const hasActiveFilters = computed(() => Boolean(query.value.trim()) || statusFilter.value !== 'all' || termFilter.value !== 'all')
const totalPages = computed(() => Math.max(1, Math.ceil(filteredCourses.value.length / COURSES_PER_PAGE)))
const paginatedCourses = computed(() => {
  const start = (currentPage.value - 1) * COURSES_PER_PAGE
  return filteredCourses.value.slice(start, start + COURSES_PER_PAGE)
})
const courseRows = computed(() => paginatedCourses.value.map(course => ({ course, production: courseProduction(course) })))
const visibleCourseIds = computed(() => paginatedCourses.value.map(course => course.course_id))
const selectedCount = computed(() => selectedCourseIds.value.size)
const allVisibleSelected = computed(() => visibleCourseIds.value.length > 0 && visibleCourseIds.value.every(id => selectedCourseIds.value.has(id)))
const someVisibleSelected = computed(() => !allVisibleSelected.value && visibleCourseIds.value.some(id => selectedCourseIds.value.has(id)))
const paginationItems = computed<Array<number | 'start-ellipsis' | 'end-ellipsis'>>(() => {
  const pages = totalPages.value
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1)
  if (currentPage.value <= 4) return [1, 2, 3, 4, 5, 'end-ellipsis', pages]
  if (currentPage.value >= pages - 3) return [1, 'start-ellipsis', pages - 4, pages - 3, pages - 2, pages - 1, pages]
  return [1, 'start-ellipsis', currentPage.value - 1, currentPage.value, currentPage.value + 1, 'end-ellipsis', pages]
})

watch([query, statusFilter, termFilter, sortMode, sortDirection], () => {
  currentPage.value = 1
  clearSelection()
  if (!embedded) void router.replace({ query: libraryQuery() })
})
watch(totalPages, pages => { if (currentPage.value > pages) currentPage.value = pages })

onMounted(async () => {
  courseStore.currentCourseId = ''
  courseStore.currentCourseVersionId = ''
  courseStore.currentNode = null
  generationStore.restoreGenerationState()
  if (!embedded) await refreshCourses()
  progressRefreshTimer = window.setInterval(refreshCourseProgress, COURSE_PROGRESS_REFRESH_MS)
})

onBeforeUnmount(() => {
  if (progressRefreshTimer !== null) window.clearInterval(progressRefreshTimer)
  progressRefreshTimer = null
})

function setStatusFilter(value: string) { statusFilter.value = value as CourseStatusFilter }
function setTermFilter(value: string) { termFilter.value = value }
function clearSelection() { selectedCourseIds.value = new Set() }
function toggleCourseSelection(courseId: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  const next = new Set(selectedCourseIds.value)
  if (checked) next.add(courseId)
  else next.delete(courseId)
  selectedCourseIds.value = next
}
function toggleVisibleSelection(event: Event) { selectedCourseIds.value = (event.target as HTMLInputElement).checked ? new Set(visibleCourseIds.value) : new Set() }
function pageNumberLabel(page: number) { return t('courseLibrary.pagination.pageNumber', '第 {page} 页').replace('{page}', String(page)) }
async function selectPage(page: number) {
  const nextPage = Math.max(1, Math.min(totalPages.value, page))
  if (nextPage === currentPage.value) return
  currentPage.value = nextPage
  clearSelection()
  await nextTick()
  document.querySelector('.course-table-region')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}
function localeTag() { return activeLocale.value === 'zh' ? 'zh-CN' : 'en-US' }
function courseTermKey(course: Course) {
  const academicYear = String(course.academic_year || '').trim()
  const term = String(course.term || '').trim()
  return academicYear || term ? `${academicYear}\u0000${term}` : ''
}
function courseTermLabel(course: Course) { return [course.academic_year, course.term].map(value => String(value || '').trim()).filter(Boolean).join(' ') || t('teacherCourseLibrary.termUnset') }
function parseCourseDate(value?: string) {
  if (!value) return null
  const parsed = new Date(value.includes('T') ? value : `${value}T12:00:00`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}
function courseNextSessionWhen(course: Course) {
  const session = course.next_session
  if (!session?.date) return t('teacherCourseLibrary.noUpcomingSession')
  const parsed = parseCourseDate(session.date)
  const date = parsed ? new Intl.DateTimeFormat(localeTag(), { month: 'short', day: 'numeric', weekday: 'short' }).format(parsed) : session.date
  const time = session.start_time?.slice(0, 5) || t('teacherHome.timePending')
  return t('teacherCourseLibrary.sessionWhen').replace('{date}', date).replace('{time}', time)
}
function courseUpdatedLabel(course: Course) {
  if (!course.updated_at) return '—'
  const parsed = new Date(course.updated_at)
  return Number.isNaN(parsed.getTime()) ? course.updated_at : new Intl.DateTimeFormat(localeTag(), { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(parsed)
}
function courseNextSessionTime(course: Course) { return Date.parse(`${course.next_session?.date || ''}T${course.next_session?.start_time || '23:59:59'}`) || Number.POSITIVE_INFINITY }
function courseUpdatedTime(course: Course) { return Date.parse(course.updated_at || '') || 0 }
function sortCourses(courses: Course[]) {
  return [...courses].sort((left, right) => {
    let result = 0
    if (sortMode.value === 'name') result = left.course_name.localeCompare(right.course_name, localeTag())
    else if (sortMode.value === 'status') result = coursePreparationState(left).localeCompare(coursePreparationState(right))
    else if (sortMode.value === 'term') result = courseTermLabel(left).localeCompare(courseTermLabel(right), localeTag())
    else if (sortMode.value === 'nextSession') result = courseNextSessionTime(left) - courseNextSessionTime(right)
    else result = courseUpdatedTime(left) - courseUpdatedTime(right)
    return result * (sortDirection.value === 'ascending' ? 1 : -1)
  })
}
function toggleSort(key: CourseSortMode) {
  if (sortMode.value === key) sortDirection.value = sortDirection.value === 'ascending' ? 'descending' : 'ascending'
  else { sortMode.value = key; sortDirection.value = key === 'updated' ? 'descending' : 'ascending' }
}
function sortIcon(key: CourseSortMode) { return sortMode.value !== key ? ArrowUpDown : sortDirection.value === 'ascending' ? ArrowUp : ArrowDown }
function sortAria(key: CourseSortMode): 'none' | 'ascending' | 'descending' { return sortMode.value === key ? sortDirection.value : 'none' }
function sortLabel(field: string) { return t('teacherCourseLibrary.sortBy').replace('{field}', field) }
function taskTargetLabel(target: string) {
  if (target === 'lesson_plan') return t('appError.domains.lessonPlan')
  if (target === 'script') return t('appError.domains.script')
  if (target === 'ppt') return t('appError.domains.ppt')
  if (target === 'import') return t('taskObservability.kind.import')
  return t('teacherWorkbench.nav.outline')
}
function globalTaskTarget(task: Task): { target: string; stage: WorkbenchStage } {
  if (task.taskType === 'course_import') return { target: 'import', stage: 'foundation' }
  if (task.taskType === 'teacher_outline_generation') return { target: 'outline', stage: 'foundation' }
  const phase = String(task.currentPhase || '').toLowerCase()
  if (/script|handout|content/.test(phase)) return { target: 'script', stage: 'script' }
  if (/lesson|teaching/.test(phase)) return { target: 'lesson_plan', stage: 'lesson' }
  return { target: 'outline', stage: 'foundation' }
}
function taskBatchCount(task: Task) {
  const detail = task.phaseDetail || {}
  const completed = Number(detail.completed_batches ?? task.recovery?.checkpoint?.completed_teaching_plan_batches ?? 0)
  const total = Number(detail.total_batches ?? task.recovery?.checkpoint?.total_teaching_plan_batches ?? 0)
  return { completed, total }
}
function productionTaskLabel(target: string, status: string, completed: number, total: number) {
  const count = total > 0 ? ` ${Math.max(0, Math.min(completed, total))}/${total}` : ''
  const key = status === 'waiting_for_input'
    ? 'waiting'
    : status === 'paused'
    ? 'paused'
    : ['failed', 'error', 'waiting_for_review', 'conflict'].includes(status) ? 'failed' : 'generating'
  return t(`teacherCourseLibrary.production.${key}`)
    .replace('{target}', taskTargetLabel(target))
    .replace('{count}', count)
}
function globalProductionTask(task?: Task): ProductionTaskView | null {
  if (!task || ['idle', 'completed', 'completed_with_warnings'].includes(task.status)) return null
  const target = globalTaskTarget(task)
  const { completed, total } = taskBatchCount(task)
  const attention = ['paused', 'waiting_for_input', 'error', 'failed', 'waiting_for_review', 'conflict'].includes(task.status)
  return {
    label: productionTaskLabel(target.target, task.status, completed, total),
    tone: attention ? 'attention' : 'active',
    actionLabel: task.status === 'waiting_for_input'
      ? t('teacherCourseLibrary.actions.continue')
      : attention ? t('teacherCourseLibrary.actions.resolve') : t('teacherCourseLibrary.actions.viewProgress'),
    stage: target.stage,
  }
}
function authoringProductionTask(course: Course): ProductionTaskView | null {
  const current = ((course.preparation_summary || {}) as CourseProductionSummary).current_production
  if (!current?.status) return null
  const completed = Math.max(0, Number(current.completed || 0))
  const total = Math.max(0, Number(current.total || 0))
  const failed = Math.max(0, Number(current.failed || 0))
  const target = String(current.target || 'lesson_plan')
  const attention = failed > 0 || ['paused', 'waiting_for_input', 'failed', 'error'].includes(current.status)
  const status = failed > 0 ? 'failed' : current.status
  return {
    label: productionTaskLabel(target, status, completed, total),
    tone: attention ? 'attention' : 'active',
    actionLabel: current.status === 'waiting_for_input'
      ? t('teacherCourseLibrary.actions.continue')
      : attention ? t('teacherCourseLibrary.actions.resolve') : t('teacherCourseLibrary.actions.viewProgress'),
    stage: target === 'outline'
      ? 'foundation'
      : target === 'script'
        ? 'script'
        : target === 'ppt' ? 'ppt' : 'lesson',
  }
}
function courseProduction(course: Course): CourseProductionView {
  const task = authoringProductionTask(course) || globalProductionTask(generationStore.getTask(course.course_id))
  if (task) return task
  const summary = (course.preparation_summary || {}) as CourseProductionSummary
  const total = Math.max(0, Number(summary.planned_lessons || course.node_count || 0))
  const complete = Boolean(summary.outline_ready ?? summary.outline_confirmed)
    && total > 0
    && Number(summary.ready_lesson_plans ?? summary.confirmed_lesson_plans ?? 0) >= total
    && Number(summary.ready_handouts ?? summary.confirmed_handouts ?? 0) >= total
    && Number(summary.ready_ppts ?? summary.confirmed_ppts ?? 0) >= total
  return {
    label: complete ? t('teacherCourseLibrary.production.complete') : t('teacherCourseLibrary.production.incomplete'),
    tone: complete ? 'ready' : 'idle',
    actionLabel: t('teacherCourseLibrary.actions.continue'),
  }
}
function courseFilterKey(course: Course): Exclude<CourseStatusFilter, 'all'> { return coursePreparationState(course) }
function libraryQuery() {
  return { view: 'courses', ...(query.value ? { q: query.value } : {}), ...(statusFilter.value !== 'all' ? { status: statusFilter.value } : {}), ...(termFilter.value !== 'all' ? { term: termFilter.value } : {}), sort: sortMode.value, dir: sortDirection.value }
}
function returnPath() {
  const routeName = router.hasRoute('course-library') ? 'course-library' : route.name
  if (routeName) return router.resolve({ name: routeName, query: libraryQuery() }).fullPath
  return router.resolve({ path: route.path || '/courses', query: libraryQuery() }).fullPath
}
function openCourse(courseId: string, stage?: WorkbenchStage) {
  void router.push({
    name: 'course-workspace',
    params: { courseId, mode: 'setup' },
    query: { returnTo: returnPath(), ...(stage ? { stage } : {}) },
  })
}
async function refreshCourses() { await courseStore.fetchCourseList({ surface: 'teacher' }) }
async function refreshCourseProgress() {
  if (document.visibilityState !== 'visible' || progressRefreshPending || deleting.value) return
  progressRefreshPending = true
  try {
    await courseStore.fetchCourseList({ surface: 'teacher', background: true })
  } finally {
    progressRefreshPending = false
  }
}
async function deleteCourse(courseId: string, courseName: string) {
  try {
    await ElMessageBox.confirm(t('teacherCourseLibrary.management.deleteConfirm').replace('{name}', courseName), t('courseLibrary.delete', '删除课程'), { type: 'warning', confirmButtonText: t('common.delete', '删除'), cancelButtonText: t('common.cancel', '取消') })
    deleting.value = true
    await courseStore.deleteCourse(courseId, { surface: 'teacher' })
    const next = new Set(selectedCourseIds.value)
    next.delete(courseId)
    selectedCourseIds.value = next
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(t('courseLibrary.deleteFailed', '删除失败'))
  } finally { deleting.value = false }
}
async function deleteSelectedCourses() {
  const ids = Array.from(selectedCourseIds.value)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(t('teacherCourseLibrary.management.deleteSelectedConfirm').replace('{count}', String(ids.length)), t('teacherCourseLibrary.management.deleteSelected'), { type: 'warning', confirmButtonText: t('common.delete', '删除'), cancelButtonText: t('common.cancel', '取消') })
    deleting.value = true
    const result = await courseStore.deleteCourses(ids, { surface: 'teacher' })
    selectedCourseIds.value = new Set(result.failed)
    if (!result.failed.length) ElMessage.success(t('teacherCourseLibrary.management.batchDeleted').replace('{count}', String(result.deleted.length)))
    else if (result.deleted.length) ElMessage.warning(t('teacherCourseLibrary.management.batchDeletePartial').replace('{deleted}', String(result.deleted.length)).replace('{failed}', String(result.failed.length)))
    else ElMessage.error(t('teacherCourseLibrary.management.batchDeleteFailed'))
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(t('teacherCourseLibrary.management.batchDeleteFailed'))
  } finally { deleting.value = false }
}
</script>

<style scoped>
.course-library,.course-library *{box-sizing:border-box}.course-library{width:100%;height:100%;overflow:auto;padding:24px clamp(20px,3.2vw,44px) 40px;color:var(--lz-text);background:var(--lz-surface)}.course-library--embedded{border:0;border-radius:0;box-shadow:none}
.library-toolbar{width:100%;max-width:1320px;min-height:42px;margin:0 auto 18px;display:flex;align-items:center;gap:10px}.library-search{height:42px;min-width:320px;flex:1 1 520px;display:flex;align-items:center;gap:9px;padding:0 13px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-muted);background:var(--lz-surface)}.library-search:focus-within{border-color:var(--lz-brand);box-shadow:0 0 0 3px color-mix(in srgb,var(--lz-brand) 12%,transparent)}.library-search input{min-width:0;flex:1;border:0;outline:0;color:var(--lz-text);background:transparent;font-size:13px}.library-search input::placeholder{color:var(--lz-text-muted)}.library-toolbar :deep(.ui-select-menu){width:164px;flex:0 0 164px}.toolbar-spacer{flex:1}.toolbar-loading{display:inline-flex;align-items:center;gap:6px;color:var(--lz-text-muted);font-size:12px;white-space:nowrap}
.library-toolbar--selecting{padding:0 2px}.selection-summary{margin:0;color:var(--lz-text-strong);font-size:14px;font-weight:750}.toolbar-button{height:36px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 12px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);font-size:13px;font-weight:700;cursor:pointer}.toolbar-button:hover:not(:disabled){border-color:var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.toolbar-button--danger{border-color:color-mix(in srgb,var(--lz-danger) 32%,var(--lz-border));color:var(--lz-danger)}.toolbar-button--danger:hover:not(:disabled){border-color:var(--lz-danger);color:var(--lz-danger);background:var(--lz-danger-soft)}.toolbar-button:disabled{opacity:.55;cursor:not-allowed}
.library-inline-error{max-width:1320px;min-height:38px;margin:-8px auto 12px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid color-mix(in srgb,var(--lz-danger) 22%,var(--lz-border));color:var(--lz-danger);font-size:12px}.library-inline-error button,.library-state button{height:32px;padding:0 11px;border:1px solid currentColor;border-radius:7px;color:inherit;background:transparent;font-size:12px;font-weight:700;cursor:pointer}
.course-table-region{width:100%;max-width:1320px;margin:0 auto;scroll-margin-top:18px;overflow-x:auto;border-top:1px solid var(--lz-border);border-bottom:1px solid var(--lz-border);background:var(--lz-surface)}.course-table{width:100%;min-width:1060px;border-collapse:collapse;table-layout:fixed;text-align:left}.course-table th{height:42px;padding:0 12px;border-bottom:1px solid var(--lz-border);color:var(--lz-text-muted);background:var(--lz-surface-subtle);font-size:11px;font-weight:750}.course-table th:nth-child(2){width:29%}.course-table th:nth-child(3){width:20%}.course-table th:nth-child(4){width:18%}.course-table th:nth-child(5){width:12%}.course-table th:nth-child(6){width:11%}.course-table th.actions-column{width:154px;text-align:center}.course-table th.selection-column{width:46px}.column-sort{height:100%;display:flex;align-items:center;gap:5px;padding:0;border:0;color:inherit;background:transparent;font:inherit;cursor:pointer}.column-sort:hover,.column-sort:focus-visible{color:var(--lz-brand-strong);outline:none}.column-sort:focus-visible{text-decoration:underline;text-underline-offset:4px}
.course-table td{height:66px;padding:8px 12px;border-bottom:1px solid color-mix(in srgb,var(--lz-border) 84%,transparent);color:var(--lz-text-secondary);font-size:13px;vertical-align:middle}.course-table tbody tr:last-child td{border-bottom:0}.course-table tbody tr:hover,.course-table tbody tr.selected{background:var(--lz-surface-subtle)}.course-table tbody tr.selected{background:var(--lz-brand-soft)}.selection-column{text-align:center}.selection-column input{width:16px;height:16px;margin:0;accent-color:var(--lz-brand);cursor:pointer}.selection-column input:focus-visible{outline:2px solid var(--lz-brand);outline-offset:3px}.selection-column input:disabled{cursor:not-allowed}
.course-cell{padding-top:6px!important;padding-bottom:6px!important}.course-main{width:100%;min-height:48px;display:block;padding:0;border:0;color:inherit;background:transparent;text-align:left;cursor:pointer}.course-main:focus-visible{outline:2px solid var(--lz-brand);outline-offset:3px;border-radius:6px}.course-identity{min-width:0;display:grid;gap:3px}.course-identity strong,.course-identity small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.course-identity strong{color:var(--lz-text-strong);font-size:14px;font-weight:760}.course-main:hover .course-identity strong{color:var(--lz-brand-strong)}.course-identity small{color:var(--lz-text-muted);font-size:11px}
.course-production-cell{padding-top:8px!important;padding-bottom:8px!important}.course-production-summary{display:block;overflow:hidden;color:var(--lz-text-secondary);font-size:13px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}.course-production-summary[data-tone='ready']{color:var(--lz-success)}.course-production-summary[data-tone='active']{color:var(--lz-brand-strong)}.course-production-summary[data-tone='attention']{color:var(--lz-danger)}.course-session{display:grid;align-content:center;gap:3px}.course-session strong{overflow:hidden;color:var(--lz-text-secondary);font-size:12px;font-weight:680;text-overflow:ellipsis;white-space:nowrap}.course-session small{overflow:hidden;color:var(--lz-text-muted);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.course-term,.course-updated{color:var(--lz-text-secondary);font-size:12px!important;font-variant-numeric:tabular-nums}
.actions-column{text-align:center}.course-actions{display:flex;align-items:center;justify-content:flex-end;gap:4px}.course-action{height:32px;display:inline-flex;align-items:center;justify-content:center;gap:3px;padding:0 9px;border:1px solid var(--lz-brand-border);border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-surface);font-size:11px;font-weight:750;white-space:nowrap;cursor:pointer}.course-action:hover,.course-action:focus-visible{border-color:var(--lz-brand);background:var(--lz-brand-soft);outline:none}.course-action:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--lz-brand) 24%,transparent)}.delete-course-button{width:32px;height:32px;display:inline-grid;place-items:center;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.delete-course-button:hover:not(:disabled),.delete-course-button:focus-visible{color:var(--lz-danger);background:var(--lz-danger-soft);outline:none}.delete-course-button:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--lz-danger) 28%,transparent)}.delete-course-button:disabled{opacity:.45;cursor:not-allowed}
.library-pagination{min-height:54px;display:flex;align-items:center;justify-content:center;gap:8px;border-top:1px solid var(--lz-border)}.library-pagination button{height:32px;min-width:32px;display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:0 9px;border:1px solid transparent;border-radius:7px;color:var(--lz-text-secondary);background:transparent;font-size:12px;font-weight:700;cursor:pointer}.library-pagination button:hover:not(:disabled),.library-pagination button:focus-visible{color:var(--lz-brand-strong);background:var(--lz-brand-soft);outline:none}.library-pagination button.active{color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.library-pagination button:disabled{color:var(--lz-text-muted);cursor:not-allowed;opacity:.52}.pagination-pages{display:flex;align-items:center;gap:2px}.pagination-ellipsis{width:24px;color:var(--lz-text-muted);text-align:center}.pagination-direction{min-width:78px!important}
.library-state{min-height:360px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;color:var(--lz-text-muted);text-align:center}.library-state strong{color:var(--lz-text-strong);font-size:15px}.library-state span{max-width:420px;font-size:12px;line-height:1.55}.library-state--error{color:var(--lz-danger)}.library-state--error strong{color:var(--lz-danger)}.library-state--error button{margin-top:4px}.spin{animation:spin .85s linear infinite}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:1100px){.course-library{padding-inline:20px}.library-toolbar{align-items:stretch;flex-wrap:wrap}.library-search{min-width:100%;flex-basis:100%}.course-table-region{max-width:100%}}@media(prefers-reduced-motion:reduce){.spin{animation:none}.course-main,.course-action,.delete-course-button,.toolbar-button,.library-pagination button{scroll-behavior:auto;transition:none}}
</style>
