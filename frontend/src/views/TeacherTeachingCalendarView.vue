<template>
  <section class="teacher-home">
    <Teleport to="#app-header-route-center">
      <nav class="home-primary-tabs" :aria-label="t('teacherHome.primaryNavigation')">
        <button type="button" :class="{ active: activeHomeTab === 'calendar' }" :aria-current="activeHomeTab === 'calendar' ? 'page' : undefined" @click="switchHomeTab('calendar')">
          <CalendarDays :size="17" />{{ t('teacherHome.myCalendar') }}
        </button>
        <button type="button" :class="{ active: activeHomeTab === 'courses' }" :aria-current="activeHomeTab === 'courses' ? 'page' : undefined" @click="switchHomeTab('courses')">
          <LibraryBig :size="17" />{{ t('teacherHome.myCourses') }}
        </button>
      </nav>
    </Teleport>

    <Teleport to="#app-header-route-actions">
      <div class="home-header-actions">
        <button type="button" class="header-quiet" @click="openTaskCenter()">
          <ListTodo :size="16" />
          <span>{{ t('teacherHome.tasks') }}</span>
          <b v-if="actionTaskCount">{{ actionTaskCount }}</b>
        </button>
        <button type="button" class="header-primary" @click="openCourseCreate">
          <Plus :size="16" />{{ t('teacherHome.newCourse') }}
        </button>
      </div>
    </Teleport>

    <TeacherCourseLibraryView v-if="activeHomeTab === 'courses'" embedded />

    <div v-else class="home-layout">
      <aside class="course-rail" :aria-label="t('teacherHome.courseRail')">
        <header>
          <div>
            <strong>{{ t('teacherHome.myCourses') }}</strong>
            <span>{{ courseStore.courseList.length }} {{ t('teacherHome.courseUnit') }}</span>
          </div>
        </header>

        <div class="course-search" role="search">
          <Search :size="15" />
          <input v-model="courseQuery" type="search" :placeholder="t('teacherHome.searchCourse')" :aria-label="t('teacherHome.searchCourse')" />
          <button v-if="courseQuery" type="button" :aria-label="t('teacherHome.clearSearch')" @click="courseQuery = ''"><X :size="14" /></button>
        </div>

        <nav class="course-list">
          <button
            v-for="(course, index) in filteredCourses"
            :key="course.course_id"
            type="button"
            class="course-entry"
            @click="openCourse(course.course_id)"
          >
            <span class="course-icon" :data-color="index % 4" aria-hidden="true"><BookOpen :size="16" /></span>
            <span class="course-entry__copy">
              <strong>{{ course.course_name }}</strong>
              <small v-if="courseStatus(course.course_id)">{{ courseStatus(course.course_id) }}</small>
            </span>
            <ChevronRight :size="15" />
          </button>
          <div v-if="courseQuery.trim() && !filteredCourses.length" class="course-search-empty">
            <SearchX :size="22" />
            <strong>{{ t('teacherHome.noSearchResults') }}</strong>
            <button type="button" @click="courseQuery = ''">{{ t('teacherHome.clearSearch') }}</button>
          </div>
        </nav>
      </aside>

      <main class="calendar-surface">
        <header class="calendar-toolbar">
          <div class="calendar-title">
            <CalendarRange :size="19" />
            <strong>{{ periodLabel }}</strong>
          </div>
          <div class="view-switch" role="tablist" :aria-label="t('teacherHome.calendarView')">
            <button type="button" role="tab" :aria-selected="view === 'week'" :class="{ active: view === 'week' }" @click="view = 'week'">
              <Columns3 :size="14" />{{ t('teacherHome.week') }}
            </button>
            <button type="button" role="tab" :aria-selected="view === 'month'" :class="{ active: view === 'month' }" @click="view = 'month'">
              <CalendarDays :size="14" />{{ t('teacherHome.month') }}
            </button>
          </div>
          <span class="toolbar-spacer" />
          <div class="period-actions">
            <button type="button" :aria-label="t('teacherHome.previousPeriod')" @click="movePeriod(-1)"><ChevronLeft :size="16" /></button>
            <button type="button" @click="goToday">{{ t('teacherHome.today') }}</button>
            <button type="button" :aria-label="t('teacherHome.nextPeriod')" @click="movePeriod(1)"><ChevronRight :size="16" /></button>
            <button type="button" :aria-label="t('common.refresh')" @click="refresh"><RefreshCw :size="16" :class="{ spin: calendarStore.loading }" /></button>
          </div>
        </header>

        <div v-if="calendarStore.error" class="calendar-issue" role="alert">
          <TriangleAlert :size="16" /><span>{{ calendarStore.error }}</span><button type="button" @click="loadCalendar">{{ t('common.retry') }}</button>
        </div>

        <div v-if="calendarStore.loading && !calendarStore.totalSessions.length" class="calendar-loading" role="status">
          <LoaderCircle class="spin" :size="22" />{{ t('teacherHome.loadingCalendar') }}
        </div>

        <div v-else-if="view === 'month'" class="month-canvas">
          <TeachingCalendarMonthGrid
            :month="monthCursor"
            :sessions="visibleSessions"
            :selected-date="selectedDate"
            show-course
            @select="selectSession"
            @prepare="openPreparation"
            @day="selectDay"
          />
        </div>

        <template v-else>
          <button v-if="unmatchedWeekSessions.length" type="button" class="week-unmatched" @click="selectFirstUnmatchedSession">
            <Clock3 :size="15" /><span>{{ t('teacherCalendar.unmatchedWeek', '本周有 {count} 个课次尚未匹配浙大标准节次').replace('{count}', String(unmatchedWeekSessions.length)) }}</span><strong>{{ t('teacherCalendar.viewSession', '查看课次') }}</strong>
          </button>

          <div class="week-canvas">
            <div class="total-week-grid" :aria-label="t('teacherCalendar.standardWeekAria', '浙江大学标准周课表')">
            <div class="week-corner">{{ t('teacherCalendar.periodAxis', '节次') }}</div>
            <div
              v-for="(day, dayIndex) in weekDays"
              :key="`header-${day.date}`"
              class="week-day-heading"
              :class="{ today: day.date === todayIso }"
              :style="{ gridColumn: String(dayIndex + 2), gridRow: '1' }"
            >
              <strong>{{ day.label }}</strong><span>{{ day.date.slice(5) }}</span>
            </div>
            <template v-for="(period, periodIndex) in classPeriods" :key="period.number">
              <div
                class="week-period"
                :class="{ 'section-start': period.number === 6 || period.number === 11 }"
                :style="{ gridColumn: '1', gridRow: String(periodIndex + 2) }"
              >
                <strong>{{ singlePeriodLabel(period.number) }}</strong><span>{{ period.start }}–{{ period.end }}</span>
              </div>
              <div
                v-for="(day, dayIndex) in weekDays"
                :key="`${day.date}-${period.number}`"
                class="week-slot"
                :class="{ 'section-start': period.number === 6 || period.number === 11, today: day.date === todayIso }"
                :style="{ gridColumn: String(dayIndex + 2), gridRow: String(periodIndex + 2) }"
              ></div>
            </template>
            <button
              v-for="block in weekSessionBlocks"
              :key="block.key"
              type="button"
              class="week-session"
              :data-color="block.session.course_color_key ?? 0"
              :class="{ active: selectedSession?.session_id === block.session.session_id, conflict: block.session.has_conflict }"
              :style="block.style"
              @click="selectSession(block.session)"
            >
              <time>{{ block.periodLabel }}<span>{{ block.timeLabel }}</span></time>
              <strong>{{ block.session.course_title || t('teacherHome.untitledCourse') }}</strong>
              <small>{{ block.session.content_summary || t('teacherHome.contentPending') }}</small>
            </button>
            </div>
          </div>
        </template>
      </main>

      <aside class="day-inspector" :aria-label="t('teacherHome.dayInspector')">
        <template v-if="selectedSession">
          <header>
            <div><small>{{ t('teacherHome.selectedSession') }}</small><strong>{{ selectedSession.course_title || t('teacherHome.untitledCourse') }}</strong></div>
            <button type="button" :aria-label="t('common.close')" @click="clearSelection"><X :size="16" /></button>
          </header>
          <section class="session-focus">
            <span class="session-number">{{ t('teacherHome.sessionNumber').replace('{number}', String(selectedSession.sequence)) }}</span>
            <h2>{{ selectedSession.content_summary || t('teacherHome.contentPending') }}</h2>
            <dl>
              <div><dt><CalendarDays :size="14" />{{ t('teacherHome.dateTime') }}</dt><dd>{{ sessionDateTime(selectedSession) }}</dd></div>
              <div><dt><MapPin :size="14" />{{ t('teacherHome.location') }}</dt><dd>{{ selectedSession.location || t('teacherHome.locationPending') }}</dd></div>
              <div><dt><Clock3 :size="14" />{{ t('teacherHome.classHours') }}</dt><dd>{{ selectedSession.credit_hours || 2 }}</dd></div>
            </dl>
          </section>
          <section class="preparation-summary">
            <header><strong>{{ t('teacherHome.preparation') }}</strong></header>
            <div><span>{{ t('teacherHome.lessonPlan') }}</span><strong>{{ selectedSession.lesson_plan_status || t('teacherHome.notCreated') }}</strong></div>
            <div><span>PPT</span><strong>{{ selectedSession.ppt_status || t('teacherHome.notCreated') }}</strong></div>
          </section>
          <footer class="inspector-actions">
            <button type="button" class="primary" @click="openPreparation(selectedSession)">{{ t('teacherHome.continuePreparing') }}<ArrowUpRight :size="15" /></button>
            <button type="button" @click="enterSession(selectedSession)">{{ t('teacherHome.enterSession') }}</button>
          </footer>
        </template>

        <template v-else-if="selectedDate">
          <header>
            <div><small>{{ t('teacherHome.selectedDate') }}</small><strong>{{ selectedDateLabel }}</strong></div>
            <button type="button" :aria-label="t('common.close')" @click="clearSelection"><X :size="16" /></button>
          </header>
          <section class="today-list">
            <div class="today-list__heading"><strong>{{ t('teacherHome.daySchedule') }}</strong><span>{{ selectedDateSessions.length }}</span></div>
            <button v-for="session in selectedDateSessions" :key="session.session_id || `${session.course_id}-${session.sequence}`" type="button" @click="selectSession(session)">
              <time>{{ session.start_time?.slice(0, 5) || '--:--' }}</time>
              <span><strong>{{ session.course_title || t('teacherHome.untitledCourse') }}</strong><small>{{ session.content_summary || t('teacherHome.contentPending') }}</small></span>
              <ChevronRight :size="14" />
            </button>
            <div v-if="!selectedDateSessions.length" class="today-empty"><CalendarDays :size="24" /><strong>{{ t('teacherHome.noClassOnDate') }}</strong></div>
          </section>
        </template>

        <template v-else>
          <header><div><small>{{ t('teacherHome.today') }}</small><strong>{{ todayLabel }}</strong></div></header>
          <section class="today-list">
            <div class="today-list__heading"><strong>{{ t('teacherHome.upcoming') }}</strong><span>{{ upcomingSessions.length }}</span></div>
            <button v-for="session in upcomingSessions" :key="session.session_id || `${session.course_id}-${session.sequence}`" type="button" @click="selectSession(session)">
              <time>{{ session.date?.slice(5) }}<br />{{ session.start_time?.slice(0, 5) || '--:--' }}</time>
              <span><strong>{{ session.course_title }}</strong><small>{{ session.content_summary }}</small></span>
              <ChevronRight :size="14" />
            </button>
            <div v-if="!upcomingSessions.length" class="today-empty"><CheckCircle2 :size="24" /><strong>{{ t('teacherHome.noUpcoming') }}</strong></div>
          </section>
        </template>
      </aside>
    </div>

    <TeacherCourseCreateView v-if="courseCreateOpen" @close="closeCourseCreate" />
    <CourseWorkbench v-model="workbenchOpen" :course-id="workbenchCourseId" surface="teacher" />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowUpRight, BookOpen, CalendarDays, CalendarRange, CheckCircle2, ChevronLeft, ChevronRight,
  Clock3, Columns3, LibraryBig, ListTodo, LoaderCircle, MapPin, Plus, RefreshCw,
  Search, SearchX, TriangleAlert, X,
} from 'lucide-vue-next'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import TeachingCalendarMonthGrid from '../components/TeachingCalendarMonthGrid.vue'
import TeacherCourseCreateView from './TeacherCourseCreateView.vue'
import TeacherCourseLibraryView from './TeacherCourseLibraryView.vue'
import { activeLocale, t } from '../shared/i18n'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import {
  TEACHING_CALENDAR_SAVED_EVENT, TEACHING_CALENDAR_SAVED_STORAGE_KEY,
  useTeachingCalendarStore, type ClassSession,
} from '../stores/teachingCalendar'
import { ZJU_CLASS_PERIODS, resolveZjuClassPeriodRange } from '../utils/zju-class-periods'

const router = useRouter()
const route = useRoute()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const calendarStore = useTeachingCalendarStore()
const courseQuery = ref('')
const view = ref<'month' | 'week'>('week')
const cursor = ref(new Date())
const selectedSession = ref<ClassSession | null>(null)
const selectedDate = ref<string | null>(null)
const workbenchOpen = ref(false)
const workbenchCourseId = ref('')

const pad = (value: number) => String(value).padStart(2, '0')
const iso = (value: Date) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
const todayIso = iso(new Date())
const monthCursor = computed(() => `${cursor.value.getFullYear()}-${pad(cursor.value.getMonth() + 1)}-01`)
const weekStart = computed(() => {
  const value = new Date(cursor.value)
  value.setHours(12, 0, 0, 0)
  value.setDate(value.getDate() - ((value.getDay() + 6) % 7))
  return value
})
const weekEnd = computed(() => { const value = new Date(weekStart.value); value.setDate(value.getDate() + 6); return value })
const monthLabel = computed(() => t('teacherHome.monthLabel').replace('{year}', String(cursor.value.getFullYear())).replace('{month}', String(cursor.value.getMonth() + 1)))
const periodLabel = computed(() => view.value === 'week' ? `${iso(weekStart.value)} — ${iso(weekEnd.value)}` : monthLabel.value)
const todayLabel = computed(() => new Intl.DateTimeFormat(document.documentElement.lang || 'zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date()))
const weekdayNames = computed(() => [1, 2, 3, 4, 5, 6, 7].map(index => t(`teacherHome.weekdays.${index}`)))
const activeHomeTab = computed<'calendar' | 'courses'>(() => route.query.view === 'courses' ? 'courses' : 'calendar')
const courseCreateOpen = computed(() => route.query.create === 'course')
const filteredCourses = computed(() => {
  const keyword = courseQuery.value.trim().toLocaleLowerCase()
  return keyword ? courseStore.courseList.filter(course => course.course_name.toLocaleLowerCase().includes(keyword)) : courseStore.courseList
})
const visibleSessions = computed(() => calendarStore.totalSessions.filter(item => item.calendar_layer !== 'incomplete'))
const selectedDateSessions = computed(() => selectedDate.value ? visibleSessions.value
  .filter(item => item.date === selectedDate.value)
  .sort((left, right) => String(left.start_time || '').localeCompare(String(right.start_time || ''))) : [])
const selectedDateLabel = computed(() => {
  if (!selectedDate.value) return ''
  const value = new Date(`${selectedDate.value}T12:00:00`)
  if (Number.isNaN(value.getTime())) return selectedDate.value
  return new Intl.DateTimeFormat(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(value)
})
const weekDays = computed(() => Array.from({ length: 7 }, (_, index) => {
  const value = new Date(weekStart.value)
  value.setDate(value.getDate() + index)
  const date = iso(value)
  return { date, label: weekdayNames.value[index], sessions: visibleSessions.value.filter(item => item.date === date) }
}))
const classPeriods = ZJU_CLASS_PERIODS
const weekSessionBlocks = computed(() => weekDays.value.flatMap((day, dayIndex) => day.sessions.flatMap(session => {
  const range = resolveZjuClassPeriodRange(session.start_time, session.end_time)
  if (!range) return []
  return [{
    key: session.session_id || `${session.course_id}-${day.date}-${session.sequence}`,
    session,
    periodLabel: classPeriodRangeLabel(range.startIndex, range.endIndex),
    timeLabel: `${session.start_time?.slice(0, 5)}–${session.end_time?.slice(0, 5)}`,
    style: {
      gridColumn: String(dayIndex + 2),
      gridRow: `${range.startIndex + 2} / span ${range.endIndex - range.startIndex + 1}`,
    },
  }]
})))
const matchedWeekSessions = computed(() => new Set(weekSessionBlocks.value.map(block => block.session)))
const unmatchedWeekSessions = computed(() => weekDays.value.flatMap(day => day.sessions).filter(session => !matchedWeekSessions.value.has(session)))
function singlePeriodLabel(number: number) { return t('teacherCalendar.periodSingle', '第 {start} 节').replace('{start}', String(number)) }
function classPeriodRangeLabel(startIndex: number, endIndex: number) {
  const start = ZJU_CLASS_PERIODS[startIndex]?.number
  const end = ZJU_CLASS_PERIODS[endIndex]?.number
  if (!start || !end) return ''
  return start === end
    ? singlePeriodLabel(start)
    : t('teacherCalendar.periodRange', '第 {start}–{end} 节').replace('{start}', String(start)).replace('{end}', String(end))
}
const upcomingSessions = computed(() => [...visibleSessions.value]
  .filter(item => String(item.date || '') >= todayIso)
  .sort((left, right) => `${left.date || ''}${left.start_time || ''}`.localeCompare(`${right.date || ''}${right.start_time || ''}`))
  .slice(0, 6))
const actionTaskCount = computed(() => Array.from(generationStore.tasks.values()).filter(task => (
  ['paused', 'waiting_for_review', 'conflict', 'error'].includes(task.status)
  || (task.status === 'completed_with_warnings'
    && task.publicationAllowed !== true
    && task.recovery?.state !== 'completed')
)).length)

function loadRange() {
  if (view.value === 'week') return { from: iso(weekStart.value), to: iso(weekEnd.value) }
  const from = new Date(cursor.value.getFullYear(), cursor.value.getMonth(), 1, 12)
  const to = new Date(cursor.value.getFullYear(), cursor.value.getMonth() + 1, 0, 12)
  return { from: iso(from), to: iso(to) }
}
async function loadCalendar() { const range = loadRange(); try { await calendarStore.loadTotal(range.from, range.to, true) } catch { /* store owns the visible error */ } }
async function refresh() { await Promise.all([courseStore.fetchCourseList({ surface: 'teacher' }), generationStore.fetchGlobalTasks(), loadCalendar()]) }
function clearSelection() { selectedSession.value = null; selectedDate.value = null }
function movePeriod(delta: number) { clearSelection(); const value = new Date(cursor.value); view.value === 'week' ? value.setDate(value.getDate() + delta * 7) : value.setMonth(value.getMonth() + delta); cursor.value = value }
function goToday() { clearSelection(); cursor.value = new Date() }
function selectSession(session: ClassSession) { selectedSession.value = session; selectedDate.value = session.date || null }
function selectFirstUnmatchedSession() { const session = unmatchedWeekSessions.value[0]; if (session) selectSession(session) }
function selectDay(date: string) {
  selectedSession.value = null
  selectedDate.value = date
  const value = new Date(`${date}T12:00:00`)
  if (!Number.isNaN(value.getTime()) && (value.getFullYear() !== cursor.value.getFullYear() || value.getMonth() !== cursor.value.getMonth())) cursor.value = value
}
function switchHomeTab(tab: 'calendar' | 'courses') { void router.replace({ name: 'course-library', query: tab === 'courses' ? { view: 'courses' } : {} }) }
function openCourse(courseId: string) { if (courseId) void router.push({ name: 'course-workspace', params: { courseId, mode: 'setup' } }) }
function openCourseCreate() { void router.push({ name: 'course-library', query: { ...route.query, create: 'course' } }) }
function closeCourseCreate() {
  const query = { ...route.query }
  delete query.create
  void router.replace({ name: 'course-library', query })
}
function openPreparation(session: ClassSession) { if (session.course_id) void router.push({ name: 'course-workspace', params: { courseId: session.course_id, mode: 'setup' }, query: { lesson: session.lesson_unit_id || '', returnTo: '/courses?view=calendar' } }) }
function enterSession(session: ClassSession) {
  if (!session.course_id) return
  void router.push({
    name: 'learning',
    params: { courseId: session.course_id, ...(session.lesson_unit_id ? { nodeId: session.lesson_unit_id } : {}) },
    query: { teacherPreview: '1', returnTo: route.fullPath },
  })
}
function openTaskCenter(courseId = '') { workbenchCourseId.value = courseId; workbenchOpen.value = true }
function sessionDateTime(session: ClassSession) {
  const date = session.date || t('teacherHome.datePending')
  const start = session.start_time?.slice(0, 5) || '--:--'
  const end = session.end_time?.slice(0, 5)
  return `${date} · ${start}${end ? `–${end}` : ''}`
}
function courseStatus(courseId: string) {
  const task = generationStore.getTask(courseId)
  if (!task) return ''
  return ({ running: t('teacherHome.courseGenerating'), pending: t('teacherHome.courseQueued'), paused: t('teacherHome.coursePaused'), waiting_for_review: t('teacherHome.courseReview'), error: t('teacherHome.courseError') } as Record<string, string>)[task.status] || ''
}
function refreshAfterCalendarSave() { void loadCalendar() }
function refreshAfterStorage(event: StorageEvent) { if (event.key === TEACHING_CALENDAR_SAVED_STORAGE_KEY) void loadCalendar() }
function refreshWhenVisible() { if (document.visibilityState === 'visible') void loadCalendar() }

watch([cursor, view], () => { void loadCalendar() })
onMounted(async () => {
  courseStore.currentCourseId = ''
  await refresh()
  window.addEventListener(TEACHING_CALENDAR_SAVED_EVENT, refreshAfterCalendarSave)
  window.addEventListener('storage', refreshAfterStorage)
  window.addEventListener('focus', refreshAfterCalendarSave)
  document.addEventListener('visibilitychange', refreshWhenVisible)
})
onBeforeUnmount(() => {
  window.removeEventListener(TEACHING_CALENDAR_SAVED_EVENT, refreshAfterCalendarSave)
  window.removeEventListener('storage', refreshAfterStorage)
  window.removeEventListener('focus', refreshAfterCalendarSave)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
})
</script>

<style scoped>
.teacher-home,.teacher-home *{box-sizing:border-box}.teacher-home{width:100%;height:100%;min-height:0;overflow:hidden;color:var(--lz-text);background:var(--lz-surface)}button,input{font:inherit}.home-primary-tabs{width:min(100%,360px);height:46px;justify-self:center;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:center;gap:4px;padding:5px;border:1px solid var(--lz-border);border-radius:16px;background:var(--lz-surface-subtle)}.home-primary-tabs button{min-width:0;height:34px;display:flex;align-items:center;justify-content:center;gap:8px;padding:0 16px;border:0;border-radius:11px;color:var(--lz-text-secondary);background:transparent;font-size:13px;font-weight:750;white-space:nowrap;cursor:pointer;transition:color .16s ease,background-color .16s ease,box-shadow .16s ease}.home-primary-tabs button:hover:not(.active){color:var(--lz-text);background:rgb(255 255 255 / 48%)}.home-primary-tabs button.active{color:var(--lz-brand-strong);background:#fff;box-shadow:0 3px 10px rgb(15 23 42 / 10%)}.home-primary-tabs button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:1px}.home-header-actions{display:flex;align-items:center;gap:8px}.home-header-actions button{height:38px;display:inline-flex;align-items:center;gap:7px;padding:0 13px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer}.header-quiet{border:1px solid var(--lz-border);color:var(--lz-text-secondary);background:var(--lz-surface)}.header-quiet b{min-width:20px;padding:1px 6px;border-radius:10px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:12px}.header-primary{border:1px solid var(--lz-brand);color:#fff;background:var(--lz-brand)}
.home-layout{height:100%;min-height:0;display:grid;grid-template-columns:250px minmax(600px,1fr) 300px}.course-rail{min-width:0;min-height:0;display:grid;grid-template-rows:64px 48px minmax(0,1fr);border-right:1px solid var(--lz-border);background:var(--lz-surface-subtle)}.course-rail>header{display:flex;align-items:center;padding:0 16px}.course-rail>header>div{min-width:0;display:grid;gap:3px}.course-rail>header strong{font-size:15px}.course-rail>header span{color:var(--lz-text-muted);font-size:12px}.course-search{height:40px;display:flex;align-items:center;gap:8px;margin:0 12px;padding:0 9px 0 11px;border:1px solid transparent;border-radius:9px;color:var(--lz-text-muted);background:rgb(226 232 240 / 58%)}.course-search:focus-within{border-color:color-mix(in srgb,var(--lz-brand) 36%,var(--lz-border));background:#fff;box-shadow:0 0 0 3px var(--lz-brand-soft)}.course-search input{min-width:0;width:100%;border:0;outline:0;color:var(--lz-text);background:transparent;font-size:13px}.course-search input::-webkit-search-cancel-button{display:none}.course-search>button{width:26px;height:26px;flex:none;display:grid;place-items:center;padding:0;border:0;border-radius:6px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.course-search>button:hover{color:var(--lz-text-strong);background:rgb(203 213 225 / 56%)}.course-list{min-height:0;overflow:auto;padding:7px}.course-entry{width:100%;min-height:56px;display:grid;grid-template-columns:34px minmax(0,1fr) 16px;align-items:center;gap:9px;padding:7px 8px;border:0;border-radius:9px;color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.course-entry:hover,.course-entry:focus-visible{outline:0;background:#fff}.course-entry:focus-visible{box-shadow:inset 0 0 0 2px var(--lz-brand)}.course-icon{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.course-icon[data-color="1"]{color:var(--lz-success);background:var(--lz-success-soft)}.course-icon[data-color="2"]{color:var(--lz-warning);background:var(--lz-warning-soft)}.course-icon[data-color="3"]{color:var(--lz-danger);background:var(--lz-danger-soft)}.course-entry__copy{min-width:0;display:grid;gap:3px}.course-entry__copy strong,.course-entry__copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.course-entry__copy strong{color:var(--lz-text-strong);font-size:13px}.course-entry__copy small{color:var(--lz-text-muted);font-size:12px}.course-search-empty{min-height:180px;display:grid;place-content:center;justify-items:center;gap:9px;padding:20px;color:var(--lz-text-muted);text-align:center}.course-search-empty strong{color:var(--lz-text-secondary);font-size:14px}.course-search-empty button{padding:6px 9px;border:0;border-radius:6px;color:var(--lz-brand-strong);background:transparent;font-size:12px;font-weight:700;cursor:pointer}
.calendar-surface{min-width:0;min-height:0;display:grid;grid-template-rows:64px auto minmax(0,1fr);background:var(--lz-surface)}
.calendar-toolbar{display:flex;align-items:center;gap:14px;padding:0 16px;border-bottom:1px solid var(--lz-border);background:rgb(255 255 255 / 72%)}
.calendar-title{min-width:0;display:flex;align-items:center;gap:9px}.calendar-title>svg{color:var(--lz-brand)}.calendar-title strong{font-size:16px}.toolbar-spacer{flex:1}
.view-switch{display:flex;border-bottom:1px solid var(--lz-border)}.view-switch button{height:38px;display:flex;align-items:center;gap:6px;padding:0 12px;border:0;border-bottom:2px solid transparent;color:var(--lz-text-secondary);background:transparent;font-size:13px;cursor:pointer}.view-switch button.active{border-bottom-color:var(--lz-brand);color:var(--lz-brand-strong)}
.period-actions{display:flex;align-items:center;gap:6px}.period-actions button{height:36px;min-width:36px;display:grid;place-items:center;padding:0 10px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);font-size:13px;cursor:pointer;transition:border-color .16s ease,color .16s ease,background-color .16s ease}.period-actions button:hover{border-color:color-mix(in srgb,var(--lz-brand) 34%,var(--lz-border));color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.period-actions button:focus-visible{outline:2px solid color-mix(in srgb,var(--lz-brand) 45%,transparent);outline-offset:2px}
.calendar-issue{min-height:40px;display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--lz-warning-border);color:var(--lz-warning);background:var(--lz-warning-soft);font-size:13px}.calendar-issue span{flex:1}.calendar-issue button{height:28px;border:1px solid var(--lz-warning-border);border-radius:6px;background:var(--lz-surface)}
.calendar-loading{height:100%;display:flex;align-items:center;justify-content:center;gap:8px;color:var(--lz-text-muted);font-size:13px}
.month-canvas{position:relative;min-width:0;min-height:0;overflow:auto;padding:10px}.month-canvas :deep(.month-grid){min-height:100%;overflow:hidden}
.week-unmatched{min-height:38px;display:flex;align-items:center;gap:7px;padding:7px 12px;border:0;border-bottom:1px solid var(--lz-warning-border);color:var(--lz-text-secondary);background:var(--lz-warning-soft);font-size:12px;text-align:left;cursor:pointer}.week-unmatched svg{color:var(--lz-warning)}.week-unmatched span{flex:1}.week-unmatched strong{color:var(--lz-warning);font-size:12px}
.week-canvas{grid-row:3;min-width:0;min-height:0;overflow:auto;padding:10px 12px 16px;background:#f7f8fb;scrollbar-gutter:stable}
.total-week-grid{--week-gridline:#edf0f5;--week-gridline-strong:#dfe4ec;min-width:900px;display:grid;grid-template-columns:82px repeat(7,minmax(116px,1fr));grid-template-rows:50px repeat(13,62px);position:relative;overflow:clip;border:1px solid #e3e7ee;border-radius:14px;background:#fff;box-shadow:0 10px 28px rgb(15 23 42 / 5.5%),0 1px 2px rgb(15 23 42 / 4%);isolation:isolate}
.week-corner,.week-day-heading,.week-period{position:sticky;z-index:3;background:#fbfcfe}
.week-corner{top:0;left:0;z-index:5;display:grid;place-items:center;border-right:1px solid var(--week-gridline);border-bottom:1px solid var(--week-gridline-strong);color:var(--lz-text-secondary);font-size:11px;font-weight:700}
.week-day-heading{top:0;display:flex;align-items:center;justify-content:center;gap:7px;border-right:1px solid var(--week-gridline);border-bottom:1px solid var(--week-gridline-strong);color:var(--lz-text-secondary)}
.week-day-heading strong{color:var(--lz-text);font-size:12px;font-weight:720}.week-day-heading span{color:var(--lz-text-secondary);font-size:11px;font-variant-numeric:tabular-nums}
.week-day-heading.today{color:var(--lz-brand-strong);background:#fbfbff}.week-day-heading.today strong{color:var(--lz-brand-strong)}.week-day-heading.today span{padding:3px 7px;border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-weight:700}
.week-period{left:0;display:grid;place-content:center;gap:3px;border-right:1px solid var(--week-gridline-strong);border-bottom:1px solid var(--week-gridline);color:var(--lz-text-secondary);text-align:center}
.week-period strong{font-size:11px;font-weight:720}.week-period span{color:var(--lz-text-secondary);font-size:10px;font-variant-numeric:tabular-nums}
.week-slot{border-right:1px solid var(--week-gridline);border-bottom:1px solid var(--week-gridline);background:#fff}.week-slot.today{background:#fdfdff}.week-slot.section-start,.week-period.section-start{border-top:1px solid var(--week-gridline-strong)}
.week-session{--course-color:#5147d9;--course-surface:color-mix(in srgb,var(--course-color) 7%,#fff);--course-border:color-mix(in srgb,var(--course-color) 18%,#e5e8ef);z-index:2;min-width:0;container-type:inline-size;display:grid;align-content:start;gap:6px;margin:0;padding:10px 12px;overflow:hidden;border:1px solid var(--course-border);border-radius:0;color:var(--lz-text-secondary);background:var(--course-surface);text-align:left;cursor:pointer;transition:border-color .16s ease,background-color .16s ease}
.week-session[data-color="1"],.week-session[data-color="5"]{--course-color:#087f6b}.week-session[data-color="2"],.week-session[data-color="6"]{--course-color:#a16207}.week-session[data-color="3"],.week-session[data-color="7"]{--course-color:#b9385c}
.week-session:hover{z-index:4;border-color:color-mix(in srgb,var(--course-color) 34%,#dfe3ea);background:color-mix(in srgb,var(--course-color) 10%,#fff)}
.week-session.active{z-index:4;border-color:var(--course-color);background:color-mix(in srgb,var(--course-color) 11%,#fff);box-shadow:inset 0 0 0 1px var(--course-color)}
.week-session.conflict{outline:2px solid var(--lz-danger);outline-offset:-3px}
.week-session time{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:6px;color:var(--course-color);font-size:10px;font-weight:780;font-variant-numeric:tabular-nums;white-space:nowrap}.week-session time::before{width:6px;height:6px;border-radius:50%;background:var(--course-color);box-shadow:0 0 0 3px color-mix(in srgb,var(--course-color) 10%,transparent);content:""}.week-session time span{justify-self:end;color:color-mix(in srgb,var(--course-color) 70%,var(--lz-text-secondary));font-size:9px;font-weight:650}
.week-session strong,.week-session small{overflow:visible;text-overflow:clip;white-space:normal;overflow-wrap:anywhere}.week-session strong{color:var(--lz-text-strong);font-size:11px;font-weight:740;line-height:1.45}.week-session small{color:var(--lz-text-secondary);font-size:10px;line-height:1.5}.week-session:focus-visible{z-index:4;outline:3px solid color-mix(in srgb,var(--course-color) 28%,transparent);outline-offset:-3px}
@container(max-width:135px){.week-session time{grid-template-columns:auto minmax(0,1fr)}.week-session time span{grid-column:2;justify-self:start}}
.day-inspector{min-width:0;min-height:0;display:grid;grid-template-rows:64px minmax(0,1fr) auto;border-left:1px solid var(--lz-border);background:var(--lz-surface)}.day-inspector>header{display:flex;align-items:center;justify-content:space-between;padding:0 16px;border-bottom:1px solid var(--lz-border)}.day-inspector>header>div{min-width:0;display:grid;gap:3px}.day-inspector>header small{color:var(--lz-text-muted);font-size:12px}.day-inspector>header strong{overflow:hidden;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.day-inspector>header button{width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.session-focus{align-content:start;display:grid;gap:14px;padding:20px 16px;border-bottom:1px solid var(--lz-border)}.session-number{width:max-content;color:var(--lz-text-muted);font-size:12px;font-weight:700}.session-focus h2{margin:0;font-size:18px;line-height:1.45}.session-focus dl{display:grid;gap:11px;margin:3px 0 0}.session-focus dl>div{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px}.session-focus dt{display:flex;align-items:center;gap:6px;color:var(--lz-text-muted);font-size:12px}.session-focus dd{margin:0;color:var(--lz-text-secondary);font-size:13px}.preparation-summary{align-self:start;display:grid;padding:16px}.preparation-summary>header{margin-bottom:7px}.preparation-summary>header strong{font-size:14px}.preparation-summary>div{min-height:42px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--lz-border);font-size:13px}.preparation-summary>div strong{color:var(--lz-text-secondary)}.inspector-actions{display:grid;gap:8px;padding:14px 16px;border-top:1px solid var(--lz-border)}.inspector-actions button{height:40px;display:flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);font-size:13px;font-weight:700;cursor:pointer}.inspector-actions button.primary{border-color:var(--lz-brand);color:#fff;background:var(--lz-brand)}.today-list{min-height:0;overflow:auto;padding:12px 14px}.today-list__heading{height:40px;display:flex;align-items:center;justify-content:space-between}.today-list__heading strong{font-size:14px}.today-list__heading span{color:var(--lz-text-muted);font-size:12px}.today-list>button{width:100%;min-height:64px;display:grid;grid-template-columns:48px minmax(0,1fr) 15px;align-items:center;gap:9px;padding:8px 2px;border:0;border-bottom:1px solid var(--lz-border);color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.today-list time{color:var(--lz-brand-strong);font-size:12px;line-height:1.5}.today-list button>span{min-width:0;display:grid;gap:3px}.today-list button strong,.today-list button small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.today-list button strong{font-size:13px}.today-list button small{color:var(--lz-text-muted);font-size:12px}.today-empty{min-height:230px;display:grid;place-content:center;justify-items:center;gap:9px;color:var(--lz-text-muted);text-align:center}.today-empty strong{color:var(--lz-text-strong);font-size:14px}.spin{animation:home-spin .85s linear infinite}@keyframes home-spin{to{transform:rotate(360deg)}}
@media(max-width:1200px){.home-layout{grid-template-columns:220px minmax(0,1fr) 260px}.session-focus,.preparation-summary{padding-left:13px;padding-right:13px}}
@media(max-width:980px){.teacher-home{overflow:auto}.home-layout{height:auto;min-height:100%;grid-template-columns:220px minmax(580px,1fr)}.course-rail,.calendar-surface{min-height:650px}.day-inspector{grid-column:1/-1;min-height:350px;border-top:1px solid var(--lz-border);border-left:0}}
@media(max-width:820px){.home-layout{display:block}.course-rail{min-height:0;grid-template-columns:minmax(130px,.7fr) minmax(190px,1.3fr);grid-template-rows:56px 92px;border-right:0;border-bottom:1px solid var(--lz-border)}.course-rail>header{grid-column:1}.course-search{grid-column:2;margin:8px 12px}.course-list{grid-column:1/-1;display:grid;grid-auto-flow:column;grid-auto-columns:minmax(190px,220px);gap:4px;overflow-x:auto;overflow-y:hidden;padding:5px 12px 10px}.course-entry{min-height:72px}.course-search-empty{min-height:72px;display:flex;justify-content:start}.calendar-surface{min-height:650px}}
@media(max-width:620px){.home-primary-tabs button{gap:6px;padding-inline:8px;font-size:12px}.home-header-actions .header-quiet{display:none}.home-header-actions .header-primary{width:38px;padding:0;justify-content:center;font-size:0}.calendar-surface{min-height:680px;grid-template-rows:auto auto minmax(0,1fr)}.calendar-toolbar{min-height:102px;display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-rows:auto auto;gap:8px;padding:9px 10px}.calendar-title{grid-column:1}.view-switch{grid-column:2}.toolbar-spacer{display:none}.period-actions{grid-column:1/-1;justify-self:end}.month-canvas{padding:6px}}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
