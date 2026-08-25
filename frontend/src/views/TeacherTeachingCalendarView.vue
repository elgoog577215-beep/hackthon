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

    <Transition name="home-surface" mode="out-in">
      <TeacherCourseLibraryView v-if="activeHomeTab === 'courses'" key="courses" embedded />

      <div v-else key="calendar" class="home-layout">
      <aside class="course-rail" :aria-label="t('teacherHome.courseRail')">
        <header>
          <div>
            <strong>{{ t('teacherHome.courseFilterTitle') }}</strong>
            <span v-if="selectedCourse">{{ t('teacherHome.courseFilterSelectedHint').replace('{course}', selectedCourse.course_name) }}</span>
            <span v-else>{{ t('teacherHome.courseFilterHint') }}</span>
          </div>
          <button v-if="selectedCourseId" type="button" class="course-filter-reset" @click="clearCourseFilter">{{ t('teacherHome.allSessions') }}</button>
        </header>

        <div class="course-list" role="group" :aria-label="t('teacherHome.courseFilterAria')">
          <article
            v-for="(course, index) in recentCourses"
            :key="course.course_id"
            class="course-entry"
            :class="{ active: selectedCourseId === course.course_id }"
          >
            <button
              type="button"
              class="course-entry__focus"
              :aria-pressed="selectedCourseId === course.course_id"
              @click="focusCourse(course)"
            >
              <span class="course-icon" :data-color="index % 4" aria-hidden="true"><BookOpen :size="16" /></span>
              <span class="course-entry__copy">
                <strong>{{ course.course_name }}</strong>
                <small>{{ courseShortcutMeta(course) }}</small>
                <em>{{ courseShortcutStatus(course) }}</em>
              </span>
            </button>
            <button type="button" class="course-entry__open" :title="t('teacherHome.enterCourseNamed').replace('{name}', course.course_name)" :aria-label="t('teacherHome.enterCourseNamed').replace('{name}', course.course_name)" @click="openCourse(course.course_id)">
              <ArrowUpRight :size="15" />
            </button>
          </article>
          <div v-if="!recentCourses.length" class="course-list-empty">
            <BookOpen :size="22" />
            <strong>{{ t('teacherHome.noRecentCourses') }}</strong>
            <span>{{ t('teacherHome.noRecentCoursesHelp') }}</span>
          </div>
        </div>
        <footer>
          <button type="button" @click="switchHomeTab('courses')">{{ t('teacherHome.viewAllCourses') }}<ChevronRight :size="15" /></button>
        </footer>
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

        <AppErrorNotice v-if="calendarError" class="calendar-issue" :presentation="calendarError" compact>
          <template #action><button type="button" @click="loadCalendar">{{ t('common.retry') }}</button></template>
        </AppErrorNotice>

        <p v-if="selectedCourse && !visibleSessions.length" class="calendar-filter-status" role="status">
          {{ t('teacherHome.courseFilterEmpty').replace('{course}', selectedCourse.course_name) }}
        </p>

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
              <time>
                <span class="week-session__period">{{ block.periodLabel }}</span>
                <span class="week-session__clock">{{ block.timeLabel }}</span>
              </time>
              <strong class="week-session__course">{{ block.session.course_title || t('teacherHome.untitledCourse') }}</strong>
              <small class="week-session__topic">{{ block.session.content_summary || t('teacherHome.contentPending') }}</small>
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
          <div class="session-inspector-body">
            <section class="session-focus">
              <div class="session-heading">
                <span class="session-number">{{ t('teacherHome.sessionNumber').replace('{number}', String(selectedSession.sequence)) }}</span>
                <h2>{{ selectedSession.content_summary || t('teacherHome.contentPending') }}</h2>
                <div v-if="sessionClassSummary.length" class="session-class-summary">
                  <span v-for="item in sessionClassSummary" :key="item">{{ item }}</span>
                </div>
              </div>
              <dl class="session-details">
                <div><CalendarDays :size="16" /><dt>{{ t('teacherHome.dateTime') }}</dt><dd>{{ sessionDateTime(selectedSession) }}</dd></div>
                <div><MapPin :size="16" /><dt>{{ t('teacherHome.location') }}</dt><dd>{{ selectedSession.location || t('teacherHome.locationPending') }}</dd></div>
                <div><UserRound :size="16" /><dt>{{ t('teacherHome.sessionPanel.teacher') }}</dt><dd>{{ selectedSession.teacher_name || t('teacherHome.sessionPanel.teacherPending') }}</dd></div>
              </dl>
            </section>

            <section class="preparation-summary" aria-labelledby="session-preparation-title">
              <header>
                <strong id="session-preparation-title">{{ t('teacherHome.sessionPanel.preparationTitle') }}</strong>
                <span>{{ preparationReadyLabel }}</span>
              </header>
              <div class="preparation-list">
                <article>
                  <span class="preparation-icon" :data-tone="outlinePreparation.tone"><ListTree :size="16" /></span>
                  <div><strong>{{ t('teacherHome.sessionPanel.outline') }}</strong><small>{{ outlinePreparation.detail }}</small></div>
                  <span class="preparation-state" :data-tone="outlinePreparation.tone">{{ outlinePreparation.label }}</span>
                </article>
                <article>
                  <span class="preparation-icon" :data-tone="lessonPlanPreparation.tone"><ClipboardCheck :size="16" /></span>
                  <div><strong>{{ t('teacherHome.lessonPlan') }}</strong><small>{{ lessonPlanPreparation.detail }}</small></div>
                  <span class="preparation-state" :data-tone="lessonPlanPreparation.tone">{{ lessonPlanPreparation.label }}</span>
                </article>
                <article>
                  <span class="preparation-icon" :data-tone="pptPreparation.tone"><Presentation :size="16" /></span>
                  <div><strong>PPT</strong><small>{{ pptPreparation.detail }}</small></div>
                  <span class="preparation-state" :data-tone="pptPreparation.tone">{{ pptPreparation.label }}</span>
                </article>
              </div>
            </section>
          </div>
          <footer class="inspector-actions">
            <button type="button" class="primary" @click="openPreparation(selectedSession)">{{ preparationPrimaryLabel }}<ArrowUpRight :size="15" /></button>
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
    </Transition>

    <TeacherCourseCreateView v-if="courseCreateOpen" @close="closeCourseCreate" />
    <CourseWorkbench v-model="workbenchOpen" :course-id="workbenchCourseId" surface="teacher" />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowUpRight, BookOpen, CalendarDays, CalendarRange, CheckCircle2, ChevronLeft, ChevronRight,
  ClipboardCheck, Clock3, Columns3, LibraryBig, ListTodo, ListTree, LoaderCircle, MapPin,
  Plus, Presentation, RefreshCw, UserRound, X,
} from 'lucide-vue-next'
import AppErrorNotice from '../components/AppErrorNotice.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import TeachingCalendarMonthGrid from '../components/TeachingCalendarMonthGrid.vue'
import TeacherCourseCreateView from './TeacherCourseCreateView.vue'
import TeacherCourseLibraryView from './TeacherCourseLibraryView.vue'
import { activeLocale, t } from '../shared/i18n'
import { useCourseStore, type Course } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import {
  TEACHING_CALENDAR_SAVED_EVENT, TEACHING_CALENDAR_SAVED_STORAGE_KEY,
  useTeachingCalendarStore, type ClassSession,
} from '../stores/teachingCalendar'
import type { TeacherLessonAuthoringView, TeacherLessonJob } from '../stores/teacherLessonAuthoring'
import { toAppError } from '../utils/app-error'
import { coursePreparationLabel, coursePreparationState } from '../utils/course-preparation'
import http, { teacherRequestConfig } from '../utils/http'
import { ZJU_CLASS_PERIODS, resolveZjuClassPeriodRange } from '../utils/zju-class-periods'

type PreparationTone = 'ready' | 'working' | 'review' | 'warning' | 'missing' | 'error'
type PreparationState = { label: string; detail: string; tone: PreparationTone }

const router = useRouter()
const route = useRoute()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const calendarStore = useTeachingCalendarStore()
const view = ref<'month' | 'week'>('week')
const cursor = ref(new Date())
const selectedCourseId = ref('')
const selectedSession = ref<ClassSession | null>(null)
const selectedDate = ref<string | null>(null)
const workbenchOpen = ref(false)
const workbenchCourseId = ref('')
const sessionAuthoringView = ref<TeacherLessonAuthoringView | null>(null)
const sessionPreparationLoading = ref(false)
const sessionPreparationError = ref('')
let sessionPreparationRequest = 0

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
const calendarError = computed(() => calendarStore.error ? toAppError(calendarStore.error, {
  title: t('teacherHome.calendarLoadFailed', '教学日历读取失败'),
  fallback: t('teacherHome.calendarLoadFailed', '教学日历读取失败'),
}) : null)
const courseCreateOpen = computed(() => route.query.create === 'course')
const recentCourses = computed(() => {
  const candidates = new Map(courseStore.courseList.map(course => [course.course_id, course]))
  calendarStore.totalSessions.forEach(session => {
    if (!session.course_id || !session.date || session.date < todayIso || candidates.has(session.course_id)) return
    candidates.set(session.course_id, {
      course_id: session.course_id,
      course_name: session.course_title || session.content_summary,
      node_count: 0,
    })
  })
  const sorted = [...candidates.values()].sort((left, right) => (
    courseShortcutPriority(left) - courseShortcutPriority(right)
      || courseNextSessionTime(left) - courseNextSessionTime(right)
      || courseUpdatedTime(right) - courseUpdatedTime(left)
  ))
  const focused = sorted.filter(course => courseShortcutPriority(course) < 3)
  if (focused.length >= 6) return focused.slice(0, 6)
  const focusedIds = new Set(focused.map(course => course.course_id))
  return [...focused, ...sorted.filter(course => !focusedIds.has(course.course_id))].slice(0, 6)
})
const selectedCourse = computed(() => {
  if (!selectedCourseId.value) return undefined
  return recentCourses.value.find(course => course.course_id === selectedCourseId.value)
    || courseStore.courseList.find(course => course.course_id === selectedCourseId.value)
})
const visibleSessions = computed(() => calendarStore.totalSessions.filter(item => (
  item.calendar_layer !== 'incomplete'
  && (!selectedCourseId.value || item.course_id === selectedCourseId.value)
)))
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
const actionTaskCount = computed(() => Array.from(generationStore.tasks.values()).filter(taskNeedsAction).length)
const sessionClassSummary = computed(() => {
  const session = selectedSession.value
  if (!session) return []
  return [
    session.teaching_type,
    t('teacherHome.sessionPanel.hours').replace('{hours}', String(session.credit_hours || 2)),
    session.group_code ? t('teacherHome.sessionPanel.group').replace('{group}', session.group_code) : '',
  ].filter(Boolean)
})
const sessionLesson = computed(() => {
  const session = selectedSession.value
  const authoringView = sessionAuthoringView.value
  if (!session?.lesson_unit_id || !authoringView || authoringView.course_id !== session.course_id) return undefined
  return authoringView.lessons.find(item => item.lesson_unit_id === session.lesson_unit_id)
})
const outlinePreparation = computed<PreparationState>(() => {
  const session = selectedSession.value
  if (!session?.lesson_unit_id) return preparationState('missing', 'notLinked', 'outlineMissing')
  return preparationState('ready', 'linked', 'outlineLinked')
})
const lessonPlanPreparation = computed<PreparationState>(() => {
  if (!selectedSession.value?.lesson_unit_id) return preparationState('missing', 'notCreated', 'planNeedsOutline')
  if (sessionPreparationLoading.value) return preparationState('working', 'syncing', 'statusSyncing')
  if (sessionPreparationError.value) return preparationState('error', 'readFailed', 'statusUnavailable')
  const lesson = sessionLesson.value
  const job = latestSessionJob('plan')
  if (job && ['pending', 'running'].includes(job.status)) return preparationState('working', 'generating', 'planWorking')
  const revision = lesson?.plan.revisions.find(item => item.revision_id === lesson.plan.working_revision_id)
  if (!revision) {
    if (job?.status === 'failed') return preparationState('error', 'failed', 'planFailed')
    return preparationState('missing', 'notCreated', 'planMissing')
  }
  if (lesson?.plan.source_state === 'stale') return preparationState('warning', 'needsUpdate', 'planStale')
  if (revision.status === 'confirmed' || lesson?.plan.confirmed_revision_id === revision.revision_id) return preparationState('ready', 'confirmed', 'planReady')
  return preparationState('review', 'awaitingReview', 'planDraft')
})
const pptPreparation = computed<PreparationState>(() => {
  if (!selectedSession.value?.lesson_unit_id) return preparationState('missing', 'notCreated', 'pptNeedsOutline')
  if (sessionPreparationLoading.value) return preparationState('working', 'syncing', 'statusSyncing')
  if (sessionPreparationError.value) return preparationState('error', 'readFailed', 'statusUnavailable')
  const job = latestSessionJob('ppt')
  if (job && ['pending', 'running'].includes(job.status)) return preparationState('working', 'generating', 'pptWorking')
  const lesson = sessionLesson.value
  const ppt = lesson?.plan.ppt_assets.find(item => item.role === 'primary') || lesson?.plan.ppt_assets[0]
  if (!ppt?.working_revision_id) {
    if (job?.status === 'failed') return preparationState('error', 'failed', 'pptFailed')
    const planReady = Boolean(lesson?.plan.working_revision_id)
    return preparationState('missing', 'notCreated', planReady ? 'pptMissing' : 'pptNeedsPlan')
  }
  if (ppt.source_state === 'stale') return preparationState('warning', 'needsUpdate', 'pptStale')
  return preparationState('ready', 'generated', 'pptReady')
})
const preparationReadyLabel = computed(() => t('teacherHome.sessionPanel.preparationProgress')
  .replace('{ready}', String([outlinePreparation.value, lessonPlanPreparation.value, pptPreparation.value].filter(item => item.tone === 'ready').length)))
const preparationPrimaryLabel = computed(() => {
  if (!selectedSession.value?.lesson_unit_id) return t('teacherHome.sessionPanel.linkOutline')
  if (lessonPlanPreparation.value.tone === 'missing') return t('teacherHome.sessionPanel.startLessonPlan')
  if (['review', 'warning', 'error', 'working'].includes(lessonPlanPreparation.value.tone)) return t('teacherHome.sessionPanel.reviewLessonPlan')
  if (pptPreparation.value.tone !== 'ready') return t('teacherHome.sessionPanel.preparePpt')
  return t('teacherHome.continuePreparing')
})
const preparationNextStage = computed<'lesson' | 'ppt'>(() => lessonPlanPreparation.value.tone === 'ready' && pptPreparation.value.tone !== 'ready' ? 'ppt' : 'lesson')

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
function clearCourseFilter() { selectedCourseId.value = ''; clearSelection() }
function focusCourse(course: Course) {
  if (selectedCourseId.value === course.course_id) return
  selectedCourseId.value = course.course_id
  clearSelection()
}
function openCourseCreate() { void router.push({ name: 'course-library', query: { ...route.query, create: 'course' } }) }
function closeCourseCreate() {
  const query = { ...route.query }
  delete query.create
  void router.replace({ name: 'course-library', query })
}
function openPreparation(session: ClassSession) {
  if (!session.course_id) return
  const query = session.lesson_unit_id
    ? { stage: preparationNextStage.value, lesson: session.lesson_unit_id, returnTo: '/courses?view=calendar' }
    : { section: 'calendar', returnTo: '/courses?view=calendar' }
  void router.push({ name: 'course-workspace', params: { courseId: session.course_id, mode: 'setup' }, query })
}
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
function preparationState(tone: PreparationTone, labelKey: string, detailKey: string): PreparationState {
  return {
    tone,
    label: t(`teacherHome.sessionPanel.states.${labelKey}`),
    detail: t(`teacherHome.sessionPanel.details.${detailKey}`),
  }
}
function latestSessionJob(kind: 'plan' | 'ppt'): TeacherLessonJob | undefined {
  const lessonId = selectedSession.value?.lesson_unit_id
  if (!lessonId) return undefined
  return [...(sessionAuthoringView.value?.jobs || [])].reverse().find(item => (
    item.lesson_unit_id === lessonId && item.type.includes(kind)
  ))
}
function taskNeedsAction(task: { status: string; publicationAllowed?: boolean; recovery?: { state?: string } }) {
  return ['paused', 'waiting_for_review', 'conflict', 'error'].includes(task.status)
    || (task.status === 'completed_with_warnings'
      && task.publicationAllowed !== true
      && task.recovery?.state !== 'completed')
}
function courseNextSessionTime(course: Course) {
  const session = courseShortcutSession(course)
  if (!session?.date) return Number.POSITIVE_INFINITY
  return Date.parse(`${session.date}T${session.start_time || '23:59:59'}`) || Number.POSITIVE_INFINITY
}
function courseUpdatedTime(course: Course) { return Date.parse(course.updated_at || '') || 0 }
function courseShortcutSession(course: Course) {
  const candidates = [
    course.next_session,
    ...calendarStore.totalSessions.filter(item => item.course_id === course.course_id && item.date && item.date >= todayIso),
  ].filter((item): item is NonNullable<typeof item> => Boolean(item?.date))
  return candidates.sort((left, right) => (
    Date.parse(`${left.date}T${left.start_time || '23:59:59'}`)
      - Date.parse(`${right.date}T${right.start_time || '23:59:59'}`)
  ))[0]
}
function courseShortcutPriority(course: Course) {
  if (courseShortcutSession(course)) return 0
  const task = generationStore.getTask(course.course_id)
  if (task && taskNeedsAction(task)) return 1
  if (task && ['pending', 'running'].includes(task.status)) return 2
  return 3
}
function courseShortcutMeta(course: Course) {
  const session = courseShortcutSession(course)
  if (!session?.date) return t('teacherHome.noUpcomingCourseSession')
  const value = new Date(`${session.date}T12:00:00`)
  const date = Number.isNaN(value.getTime())
    ? session.date
    : new Intl.DateTimeFormat(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', weekday: 'short' }).format(value)
  const time = session.start_time?.slice(0, 5) || t('teacherHome.timePending')
  return [date, time, session.content_summary].filter(Boolean).join(' · ')
}
function courseShortcutStatus(course: Course) {
  const session = courseShortcutSession(course)
  if (!session) return courseStatus(course.course_id)
  if (!session.lesson_plan_status && !session.ppt_status) {
    return courseStore.courseList.some(item => item.course_id === course.course_id)
      ? courseStatus(course.course_id)
      : t('teacherHome.preparationUnchecked')
  }
  return t('teacherHome.shortcutPreparation')
    .replace('{lessonPlan}', session.lesson_plan_status || t('teacherHome.preparationUnchecked'))
    .replace('{ppt}', session.ppt_status || t('teacherHome.preparationUnchecked'))
}
async function loadSessionPreparation(session: ClassSession | null) {
  const request = ++sessionPreparationRequest
  sessionAuthoringView.value = null
  sessionPreparationError.value = ''
  if (!session?.course_id || !session.lesson_unit_id) {
    sessionPreparationLoading.value = false
    return
  }
  sessionPreparationLoading.value = true
  try {
    const response = await http.get<TeacherLessonAuthoringView>(
      `/api/teacher/courses/${session.course_id}/lesson-authoring`,
      teacherRequestConfig({ silentError: true }),
    )
    if (request === sessionPreparationRequest) sessionAuthoringView.value = response.data
  } catch (error: any) {
    if (request === sessionPreparationRequest) sessionPreparationError.value = String(error?.response?.data?.detail?.message || error?.message || t('teacherHome.sessionPanel.details.statusUnavailable'))
  } finally {
    if (request === sessionPreparationRequest) sessionPreparationLoading.value = false
  }
}
function courseStatus(courseId: string) {
  const task = generationStore.getTask(courseId)
  const course = courseStore.courseList.find(item => item.course_id === courseId)
  return coursePreparationLabel(coursePreparationState(course, task))
}
function refreshAfterCalendarSave() { void loadCalendar() }
function refreshAfterStorage(event: StorageEvent) { if (event.key === TEACHING_CALENDAR_SAVED_STORAGE_KEY) void loadCalendar() }
function refreshWhenVisible() { if (document.visibilityState === 'visible') void loadCalendar() }

watch([cursor, view], () => { void loadCalendar() })
watch(selectedSession, session => { void loadSessionPreparation(session) })
onMounted(async () => {
  courseStore.currentCourseId = ''
  await refresh()
  window.addEventListener(TEACHING_CALENDAR_SAVED_EVENT, refreshAfterCalendarSave)
  window.addEventListener('storage', refreshAfterStorage)
  window.addEventListener('focus', refreshAfterCalendarSave)
  document.addEventListener('visibilitychange', refreshWhenVisible)
})
onBeforeUnmount(() => {
  sessionPreparationRequest += 1
  window.removeEventListener(TEACHING_CALENDAR_SAVED_EVENT, refreshAfterCalendarSave)
  window.removeEventListener('storage', refreshAfterStorage)
  window.removeEventListener('focus', refreshAfterCalendarSave)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
})
</script>

<style scoped>
.teacher-home,.teacher-home *{box-sizing:border-box}.teacher-home{width:100%;height:100%;min-height:0;overflow:hidden;color:var(--lz-text);background:var(--lz-surface)}button,input{font:inherit}.home-primary-tabs{width:min(100%,360px);height:46px;justify-self:center;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:center;gap:4px;padding:5px;border:1px solid var(--lz-border);border-radius:16px;background:var(--lz-surface-subtle)}.home-primary-tabs button{min-width:0;height:34px;display:flex;align-items:center;justify-content:center;gap:8px;padding:0 16px;border:0;border-radius:11px;color:var(--lz-text-secondary);background:transparent;font-size:13px;font-weight:750;white-space:nowrap;cursor:pointer;transition:color .16s ease,background-color .16s ease,box-shadow .16s ease}.home-primary-tabs button:hover:not(.active){color:var(--lz-text);background:rgb(255 255 255 / 48%)}.home-primary-tabs button.active{color:var(--lz-brand-strong);background:#fff;box-shadow:0 3px 10px rgb(15 23 42 / 10%)}.home-primary-tabs button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:1px}.home-header-actions{display:flex;align-items:center;gap:8px}.home-header-actions button{height:38px;display:inline-flex;align-items:center;gap:7px;padding:0 13px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer}.header-quiet{border:1px solid var(--lz-border);color:var(--lz-text-secondary);background:var(--lz-surface)}.header-quiet b{min-width:20px;padding:1px 6px;border-radius:10px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:12px}.header-primary{border:1px solid var(--lz-brand);color:#fff;background:var(--lz-brand)}
.home-surface-enter-active{transition:opacity .22s cubic-bezier(.16,1,.3,1),transform .24s cubic-bezier(.16,1,.3,1)}.home-surface-leave-active{transition:opacity .12s ease-in,transform .14s ease-in}.home-surface-enter-from{opacity:0;transform:translateY(7px)}.home-surface-leave-to{opacity:0;transform:translateY(-3px)}
.home-layout{height:100%;min-height:0;display:grid;grid-template-columns:250px minmax(600px,1fr) 300px}.course-rail{min-width:0;min-height:0;display:grid;grid-template-rows:64px minmax(0,1fr) 48px;border-right:1px solid var(--lz-border);background:var(--lz-surface-subtle)}.course-rail>header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 14px 0 16px}.course-rail>header>div{min-width:0;display:grid;gap:3px}.course-rail>header strong{font-size:15px}.course-rail>header span{color:var(--lz-text-muted);font-size:12px}.course-rail>header>button{height:28px;padding:0 8px;border:0;border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:11px;font-weight:750;cursor:pointer}.course-rail>header>button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:1px}.course-list{min-height:0;overflow:auto;padding:5px 7px 10px}.course-entry{position:relative;min-height:84px;display:grid;grid-template-columns:minmax(0,1fr) 34px;align-items:stretch;border-radius:10px;color:var(--lz-text-secondary);background:transparent}.course-entry:hover,.course-entry.active{background:#fff}.course-entry.active{box-shadow:inset 0 0 0 1px var(--lz-brand-border)}.course-entry__focus{min-width:0;display:grid;grid-template-columns:34px minmax(0,1fr);align-items:start;gap:9px;padding:10px 4px 10px 8px;border:0;border-radius:10px 0 0 10px;color:inherit;background:transparent;text-align:left;cursor:pointer}.course-entry__focus:focus-visible,.course-entry__open:focus-visible{outline:2px solid var(--lz-brand);outline-offset:-2px}.course-entry__open{display:grid;place-items:center;margin:6px 4px 6px 0;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.course-entry__open:hover{color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.course-icon{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.course-icon[data-color="1"]{color:var(--lz-success);background:var(--lz-success-soft)}.course-icon[data-color="2"]{color:var(--lz-warning);background:var(--lz-warning-soft)}.course-icon[data-color="3"]{color:var(--lz-danger);background:var(--lz-danger-soft)}.course-entry__copy{min-width:0;display:grid;gap:3px}.course-entry__copy strong,.course-entry__copy small,.course-entry__copy em{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.course-entry__copy strong{color:var(--lz-text-strong);font-size:13px}.course-entry__copy small{color:var(--lz-text-secondary);font-size:11px}.course-entry__copy em{color:var(--lz-text-muted);font-size:10px;font-style:normal}.course-list-empty{min-height:190px;display:grid;place-content:center;justify-items:center;gap:7px;padding:20px;color:var(--lz-text-muted);text-align:center}.course-list-empty strong{color:var(--lz-text-secondary);font-size:13px}.course-list-empty span{max-width:180px;font-size:11px;line-height:1.5}.course-rail>footer{display:flex;align-items:center;padding:0 10px;border-top:1px solid var(--lz-border)}.course-rail>footer button{width:100%;height:34px;display:flex;align-items:center;justify-content:space-between;padding:0 8px;border:0;border-radius:7px;color:var(--lz-brand-strong);background:transparent;font-size:12px;font-weight:750;cursor:pointer}.course-rail>footer button:hover{background:var(--lz-brand-soft)}.course-rail>footer button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:-1px}
.course-rail{grid-template-rows:72px minmax(0,1fr) 48px}.course-rail>header{padding:0 14px 0 16px}.course-rail>header span{line-height:1.4}.course-filter-reset{flex:none}.course-list{padding:5px 7px 10px}.course-entry{margin-bottom:2px;border:1px solid transparent}.course-entry.active{color:var(--lz-brand-strong);border-color:color-mix(in srgb,var(--lz-brand) 18%,transparent);background:var(--lz-brand-soft);box-shadow:none}.course-entry.active .course-icon{color:var(--lz-brand-strong);background:transparent}.course-entry.active .course-entry__copy strong,.course-entry.active .course-entry__open{color:var(--lz-brand-strong)}
.calendar-surface{min-width:0;min-height:0;display:grid;grid-template-rows:64px auto minmax(0,1fr);background:var(--lz-surface)}
.calendar-toolbar{display:flex;align-items:center;gap:14px;padding:0 16px;border-bottom:1px solid var(--lz-border);background:rgb(255 255 255 / 72%)}
.calendar-title{min-width:0;display:flex;align-items:center;gap:9px}.calendar-title>svg{color:var(--lz-brand)}.calendar-title strong{font-size:16px}.toolbar-spacer{flex:1}
.view-switch{display:flex;border-bottom:1px solid var(--lz-border)}.view-switch button{height:38px;display:flex;align-items:center;gap:6px;padding:0 12px;border:0;border-bottom:2px solid transparent;color:var(--lz-text-secondary);background:transparent;font-size:13px;cursor:pointer}.view-switch button.active{border-bottom-color:var(--lz-brand);color:var(--lz-brand-strong)}
.period-actions{display:flex;align-items:center;gap:6px}.period-actions button{height:36px;min-width:36px;display:grid;place-items:center;padding:0 10px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);font-size:13px;cursor:pointer;transition:border-color .16s ease,color .16s ease,background-color .16s ease}.period-actions button:hover{border-color:color-mix(in srgb,var(--lz-brand) 34%,var(--lz-border));color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.period-actions button:focus-visible{outline:2px solid color-mix(in srgb,var(--lz-brand) 45%,transparent);outline-offset:2px}
.calendar-issue{margin:10px 12px 0}
.calendar-loading{height:100%;display:flex;align-items:center;justify-content:center;gap:8px;color:var(--lz-text-muted);font-size:13px}
.month-canvas{position:relative;min-width:0;min-height:0;overflow:auto;padding:10px;animation:calendar-view-arrive .22s cubic-bezier(.16,1,.3,1)}.month-canvas :deep(.month-grid){min-height:100%;overflow:hidden}
.calendar-filter-status{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;border:0;clip:rect(0 0 0 0);white-space:nowrap}
.week-unmatched{min-height:38px;display:flex;align-items:center;gap:7px;padding:7px 12px;border:0;border-bottom:1px solid var(--lz-warning-border);color:var(--lz-text-secondary);background:var(--lz-warning-soft);font-size:12px;text-align:left;cursor:pointer}.week-unmatched svg{color:var(--lz-warning)}.week-unmatched span{flex:1}.week-unmatched strong{color:var(--lz-warning);font-size:12px}
.week-canvas{grid-row:3;min-width:0;min-height:0;overflow:auto;padding:0;background:#fff;scrollbar-gutter:stable;animation:calendar-view-arrive .22s cubic-bezier(.16,1,.3,1)}
.week-canvas::-webkit-scrollbar{width:8px;height:8px}.week-canvas::-webkit-scrollbar-track,.week-canvas::-webkit-scrollbar-corner{background:transparent}.week-canvas::-webkit-scrollbar-thumb{min-height:56px;border:2px solid transparent;border-radius:999px;background:color-mix(in srgb,var(--lz-brand) 24%,var(--lz-border));background-clip:padding-box}.week-canvas::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--lz-brand) 42%,var(--lz-border));background-clip:padding-box}
@keyframes calendar-view-arrive{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
.total-week-grid{--week-gridline:#edf0f5;--week-gridline-strong:#dfe4ec;min-width:980px;min-height:100%;display:grid;grid-template-columns:82px repeat(7,minmax(128px,1fr));grid-template-rows:50px repeat(13,62px);position:relative;overflow:clip;border:0;border-radius:0;background:#fff;box-shadow:none;isolation:isolate}
.week-corner,.week-day-heading,.week-period{position:sticky;z-index:3;background:#fbfcfe}
.week-corner{top:0;left:0;z-index:5;display:grid;place-items:center;border-right:1px solid var(--week-gridline);border-bottom:1px solid var(--week-gridline-strong);color:var(--lz-text-secondary);font-size:11px;font-weight:700}
.week-day-heading{top:0;display:flex;align-items:center;justify-content:center;gap:7px;border-right:1px solid var(--week-gridline);border-bottom:1px solid var(--week-gridline-strong);color:var(--lz-text-secondary)}
.week-day-heading strong{color:var(--lz-text);font-size:12px;font-weight:720}.week-day-heading span{color:var(--lz-text-secondary);font-size:11px;font-variant-numeric:tabular-nums}
.week-day-heading.today{color:var(--lz-brand-strong);background:#fbfbff}.week-day-heading.today strong{color:var(--lz-brand-strong)}.week-day-heading.today span{padding:3px 7px;border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-weight:700}
.week-period{left:0;display:grid;place-content:center;gap:3px;border-right:1px solid var(--week-gridline-strong);border-bottom:1px solid var(--week-gridline);color:var(--lz-text-secondary);text-align:center}
.week-period strong{font-size:11px;font-weight:720}.week-period span{color:var(--lz-text-secondary);font-size:10px;font-variant-numeric:tabular-nums}
.week-slot{border-right:1px solid var(--week-gridline);border-bottom:1px solid var(--week-gridline);background:#fff}.week-slot.today{background:#fdfdff}.week-slot.section-start,.week-period.section-start{border-top:1px solid var(--week-gridline-strong)}
.week-session{--course-color:#5147d9;--course-surface:color-mix(in srgb,var(--course-color) 7%,#fff);--course-border:color-mix(in srgb,var(--course-color) 18%,#e5e8ef);z-index:2;min-width:0;container-type:inline-size;display:grid;grid-template-columns:minmax(0,1fr);align-content:start;margin:0;padding:10px 8px;overflow:hidden;border:1px solid var(--course-border);border-radius:0;color:var(--lz-text-secondary);background:var(--course-surface);text-align:left;cursor:pointer;transition:border-color .16s ease,background-color .16s ease}
.week-session[data-color="1"],.week-session[data-color="5"]{--course-color:#087f6b}.week-session[data-color="2"],.week-session[data-color="6"]{--course-color:#a16207}.week-session[data-color="3"],.week-session[data-color="7"]{--course-color:#b9385c}
.week-session:hover{z-index:4;border-color:color-mix(in srgb,var(--course-color) 34%,#dfe3ea);background:color-mix(in srgb,var(--course-color) 10%,#fff)}
.week-session.active{z-index:4;border-color:var(--course-color);background:color-mix(in srgb,var(--course-color) 11%,#fff);box-shadow:inset 0 0 0 1px var(--course-color)}
.week-session.conflict{outline:2px solid var(--lz-danger);outline-offset:-3px}
.week-session time{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:0 0 9px;font-variant-numeric:tabular-nums;white-space:nowrap}
.week-session__period{color:var(--course-color);font-size:10px;font-weight:780;line-height:1.25}.week-session__clock{color:color-mix(in srgb,var(--course-color) 68%,var(--lz-text-secondary));font-size:9px;font-weight:650;line-height:1.25}
.week-session__course,.week-session__topic{display:block;overflow:visible;text-overflow:clip;text-wrap:pretty;white-space:normal;word-break:normal;word-break:auto-phrase;overflow-wrap:break-word}.week-session__course{margin:0 0 4px;color:var(--lz-text-strong);font-size:12px;font-weight:760;line-height:1.4}.week-session__topic{color:var(--lz-text-secondary);font-size:11px;line-height:1.55}.week-session:focus-visible{z-index:4;outline:3px solid color-mix(in srgb,var(--course-color) 28%,transparent);outline-offset:-3px}
@container(max-width:135px){.week-session time{display:grid;justify-content:start;gap:3px;margin-bottom:9px}.week-session__clock{justify-self:start}}
.day-inspector{min-width:0;min-height:0;display:grid;grid-template-rows:64px minmax(0,1fr) auto;border-left:1px solid var(--lz-border);background:var(--lz-surface)}.day-inspector>header{display:flex;align-items:center;justify-content:space-between;padding:0 16px;border-bottom:1px solid var(--lz-border)}.day-inspector>header>div{min-width:0;display:grid;gap:3px}.day-inspector>header small{color:var(--lz-text-muted);font-size:12px}.day-inspector>header strong{overflow:hidden;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.day-inspector>header button{width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.day-inspector>header button:hover{color:var(--lz-text-strong);background:var(--lz-fill)}.day-inspector>header button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:1px}.session-inspector-body{min-height:0;overflow:auto;scrollbar-gutter:stable}.session-focus{display:grid;gap:12px;padding:16px 16px 14px;border-bottom:1px solid var(--lz-border)}.session-heading{display:grid;gap:6px}.session-number{width:max-content;color:var(--lz-brand-strong);font-size:12px;font-weight:750}.session-focus h2{margin:0;color:var(--lz-text-strong);font-size:18px;letter-spacing:-.012em;line-height:1.42}.session-class-summary{display:flex;flex-wrap:wrap;gap:5px;color:var(--lz-text-secondary);font-size:12px}.session-class-summary span+span::before{margin-right:5px;color:var(--lz-text-muted);content:"·"}.session-details{display:grid;margin:0}.session-details>div{min-height:48px;display:grid;grid-template-columns:26px minmax(0,1fr);grid-template-rows:auto auto;align-content:center;column-gap:9px;padding:7px 0;border-bottom:1px solid color-mix(in srgb,var(--lz-border) 78%,transparent)}.session-details>div:last-child{border-bottom:0}.session-details svg{grid-row:1/3;align-self:center;color:var(--lz-text-muted)}.session-details dt{color:var(--lz-text-muted);font-size:11px;line-height:1.4}.session-details dd{min-width:0;margin:2px 0 0;color:var(--lz-text-secondary);font-size:13px;font-weight:650;line-height:1.45;overflow-wrap:anywhere}.session-details>div:first-child dd{font-variant-numeric:tabular-nums}.preparation-summary{display:grid;gap:8px;padding:14px 16px}.preparation-summary>header{display:flex;align-items:center;justify-content:space-between;gap:10px}.preparation-summary>header strong{color:var(--lz-text-strong);font-size:14px}.preparation-summary>header span{color:var(--lz-text-muted);font-size:11px;font-variant-numeric:tabular-nums}.preparation-list{display:grid}.preparation-list article{min-height:56px;display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid color-mix(in srgb,var(--lz-border) 78%,transparent)}.preparation-list article:last-child{border-bottom:0}.preparation-icon{width:32px;height:32px;display:grid;place-items:center;border-radius:8px;color:var(--lz-text-muted);background:var(--lz-surface-muted)}.preparation-icon[data-tone="ready"]{color:var(--lz-success);background:var(--lz-success-soft)}.preparation-icon[data-tone="working"],.preparation-icon[data-tone="review"]{color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.preparation-icon[data-tone="warning"],.preparation-icon[data-tone="error"]{color:var(--lz-warning);background:var(--lz-warning-soft)}.preparation-list article>div{min-width:0;display:grid;gap:3px}.preparation-list article>div strong{color:var(--lz-text-strong);font-size:13px}.preparation-list article>div small{color:var(--lz-text-muted);font-size:11px;line-height:1.42;overflow-wrap:anywhere}.preparation-state{align-self:start;margin-top:3px;padding:3px 6px;border-radius:6px;color:var(--lz-text-secondary);background:var(--lz-surface-muted);font-size:10px;font-weight:750;white-space:nowrap}.preparation-state[data-tone="ready"]{color:var(--lz-success);background:var(--lz-success-soft)}.preparation-state[data-tone="working"],.preparation-state[data-tone="review"]{color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.preparation-state[data-tone="warning"],.preparation-state[data-tone="error"]{color:var(--lz-warning);background:var(--lz-warning-soft)}.inspector-actions{display:grid;gap:8px;padding:12px 16px;border-top:1px solid var(--lz-border);background:var(--lz-surface)}.inspector-actions button{height:40px;display:flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);font-size:13px;font-weight:700;cursor:pointer}.inspector-actions button:hover{border-color:color-mix(in srgb,var(--lz-brand) 30%,var(--lz-border));color:var(--lz-brand-strong)}.inspector-actions button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}.inspector-actions button.primary{border-color:var(--lz-brand);color:#fff;background:var(--lz-brand)}.inspector-actions button.primary:hover{border-color:var(--lz-brand-strong);color:#fff;background:var(--lz-brand-strong)}.today-list{min-height:0;overflow:auto;padding:12px 14px}.today-list__heading{height:40px;display:flex;align-items:center;justify-content:space-between}.today-list__heading strong{font-size:14px}.today-list__heading span{color:var(--lz-text-muted);font-size:12px}.today-list>button{width:100%;min-height:64px;display:grid;grid-template-columns:48px minmax(0,1fr) 15px;align-items:center;gap:9px;padding:8px 2px;border:0;border-bottom:1px solid var(--lz-border);color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.today-list time{color:var(--lz-brand-strong);font-size:12px;line-height:1.5}.today-list button>span{min-width:0;display:grid;gap:3px}.today-list button strong,.today-list button small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.today-list button strong{font-size:13px}.today-list button small{color:var(--lz-text-muted);font-size:12px}.today-empty{min-height:230px;display:grid;place-content:center;justify-items:center;gap:9px;color:var(--lz-text-muted);text-align:center}.today-empty strong{color:var(--lz-text-strong);font-size:14px}.spin{animation:home-spin .85s linear infinite}@keyframes home-spin{to{transform:rotate(360deg)}}
.session-focus{gap:8px;padding-top:12px;padding-bottom:10px}
.session-details>div{min-height:42px;padding-top:5px;padding-bottom:5px}
.preparation-summary{gap:6px;padding-top:10px;padding-bottom:10px}
.preparation-list article{min-height:50px;padding-top:5px;padding-bottom:5px}
.inspector-actions{gap:7px;padding-top:8px;padding-bottom:8px}
.inspector-actions button{height:38px}
@media(max-width:1200px){.home-layout{grid-template-columns:220px minmax(0,1fr) 280px}.session-focus,.preparation-summary{padding-left:14px;padding-right:14px}}
@media(max-width:980px){.teacher-home{overflow:auto}.home-layout{height:auto;min-height:100%;grid-template-columns:220px minmax(580px,1fr)}.course-rail,.calendar-surface{min-height:650px}.day-inspector{grid-column:1/-1;min-height:350px;border-top:1px solid var(--lz-border);border-left:0}}
@media(max-width:820px){.home-layout{display:block}.course-rail{min-height:0;grid-template-columns:180px minmax(0,1fr);grid-template-rows:92px 42px;border-right:0;border-bottom:1px solid var(--lz-border)}.course-rail>header{grid-column:1;grid-row:1}.course-list{grid-column:2;grid-row:1;display:grid;grid-auto-flow:column;grid-auto-columns:minmax(210px,240px);gap:4px;overflow-x:auto;overflow-y:hidden;padding:5px 10px}.course-entry{min-height:82px}.course-rail>footer{grid-column:1/-1;grid-row:2}.calendar-surface{min-height:650px}}
@media(max-width:620px){.home-primary-tabs button{gap:6px;padding-inline:8px;font-size:12px}.home-header-actions .header-quiet{display:none}.home-header-actions .header-primary{width:38px;padding:0;justify-content:center;font-size:0}.calendar-surface{min-height:680px;grid-template-rows:auto auto minmax(0,1fr)}.calendar-toolbar{min-height:102px;display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-rows:auto auto;gap:8px;padding:9px 10px}.calendar-title{grid-column:1}.view-switch{grid-column:2}.toolbar-spacer{display:none}.period-actions{grid-column:1/-1;justify-self:end}.month-canvas{padding:6px}}
@media(prefers-reduced-motion:reduce){.spin,.month-canvas,.week-canvas{animation:none}.home-surface-enter-active,.home-surface-leave-active{transition:none}.home-surface-enter-from,.home-surface-leave-to{transform:none}}
</style>
