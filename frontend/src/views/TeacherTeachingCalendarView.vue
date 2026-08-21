<template>
  <section class="teacher-home">
    <Teleport to="#app-header-route-actions">
      <div class="home-header-actions">
        <button type="button" class="header-quiet" @click="openTaskCenter()">
          <ListTodo :size="16" />
          <span>{{ t('teacherHome.tasks') }}</span>
          <b v-if="actionTaskCount">{{ actionTaskCount }}</b>
        </button>
        <button type="button" class="header-primary" @click="createDialogOpen = true">
          <Plus :size="16" />{{ t('teacherHome.newCourse') }}
        </button>
      </div>
    </Teleport>

    <div class="home-layout">
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
            <span class="course-icon" :data-color="index % 8" aria-hidden="true"><BookOpen :size="16" /></span>
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
            <button type="button" role="tab" :aria-selected="view === 'month'" :class="{ active: view === 'month' }" @click="view = 'month'">
              <CalendarDays :size="14" />{{ t('teacherHome.month') }}
            </button>
            <button type="button" role="tab" :aria-selected="view === 'week'" :class="{ active: view === 'week' }" @click="view = 'week'">
              <Columns3 :size="14" />{{ t('teacherHome.week') }}
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
            show-course
            @select="selectSession"
            @prepare="openPreparation"
          />
        </div>

        <div v-else class="week-canvas">
          <section v-for="day in weekDays" :key="day.date" :class="{ today: day.date === todayIso }">
            <header><strong>{{ day.label }}</strong><span>{{ day.date.slice(5) }}</span></header>
            <button
              v-for="session in day.sessions"
              :key="session.session_id || `${session.course_id}-${session.sequence}`"
              type="button"
              :data-color="session.course_color_key ?? 0"
              :class="{ active: selectedSession?.session_id === session.session_id }"
              @click="selectSession(session)"
            >
              <time>{{ session.start_time?.slice(0, 5) || t('teacherHome.timePending') }}</time>
              <strong>{{ session.course_title || t('teacherHome.untitledCourse') }}</strong>
              <span>{{ session.content_summary || t('teacherHome.contentPending') }}</span>
            </button>
            <p v-if="!day.sessions.length">{{ t('teacherHome.noClass') }}</p>
          </section>
        </div>
      </main>

      <aside class="day-inspector" :aria-label="t('teacherHome.dayInspector')">
        <template v-if="selectedSession">
          <header>
            <div><small>{{ t('teacherHome.selectedSession') }}</small><strong>{{ selectedSession.course_title || t('teacherHome.untitledCourse') }}</strong></div>
            <button type="button" :aria-label="t('common.close')" @click="selectedSession = null"><X :size="16" /></button>
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

    <CreateCourseSpaceDialog
      v-model="createDialogOpen"
      :busy="creating"
      @create="createCourseSpace"
    />
    <CourseWorkbench v-model="workbenchOpen" :course-id="workbenchCourseId" surface="teacher" />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowUpRight, BookOpen, CalendarDays, CalendarRange, CheckCircle2, ChevronLeft, ChevronRight,
  Clock3, Columns3, ListTodo, LoaderCircle, MapPin, Plus, RefreshCw, Search, SearchX,
  TriangleAlert, X,
} from 'lucide-vue-next'
import CreateCourseSpaceDialog from '../components/CreateCourseSpaceDialog.vue'
import CourseWorkbench from '../components/CourseWorkbench.vue'
import TeachingCalendarMonthGrid from '../components/TeachingCalendarMonthGrid.vue'
import { t } from '../shared/i18n'
import { useCourseStore } from '../stores/course'
import { useGenerationStore } from '../stores/generation'
import {
  TEACHING_CALENDAR_SAVED_EVENT, TEACHING_CALENDAR_SAVED_STORAGE_KEY,
  useTeachingCalendarStore, type ClassSession,
} from '../stores/teachingCalendar'

const router = useRouter()
const route = useRoute()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const calendarStore = useTeachingCalendarStore()
const courseQuery = ref('')
const view = ref<'month' | 'week'>('month')
const cursor = ref(new Date())
const selectedSession = ref<ClassSession | null>(null)
const createDialogOpen = ref(false)
const creating = ref(false)
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
const filteredCourses = computed(() => {
  const keyword = courseQuery.value.trim().toLocaleLowerCase()
  return keyword ? courseStore.courseList.filter(course => course.course_name.toLocaleLowerCase().includes(keyword)) : courseStore.courseList
})
const visibleSessions = computed(() => calendarStore.totalSessions.filter(item => item.calendar_layer !== 'incomplete'))
const weekDays = computed(() => Array.from({ length: 7 }, (_, index) => {
  const value = new Date(weekStart.value)
  value.setDate(value.getDate() + index)
  const date = iso(value)
  return { date, label: weekdayNames.value[index], sessions: visibleSessions.value.filter(item => item.date === date) }
}))
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
function movePeriod(delta: number) { const value = new Date(cursor.value); view.value === 'week' ? value.setDate(value.getDate() + delta * 7) : value.setMonth(value.getMonth() + delta); cursor.value = value }
function goToday() { cursor.value = new Date() }
function selectSession(session: ClassSession) { selectedSession.value = session }
function openCourse(courseId: string) { if (courseId) void router.push({ name: 'course-workspace', params: { courseId, mode: 'setup' } }) }
function openPreparation(session: ClassSession) { if (session.course_id) void router.push({ name: 'course-workspace', params: { courseId: session.course_id, mode: 'setup' }, query: { lesson: session.lesson_unit_id || '' } }) }
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
async function createCourseSpace(payload: { course_name: string; academic_year: string; term: string }) {
  if (creating.value) return
  creating.value = true
  try {
    const result = await courseStore.createTeacherCourseSpace(payload)
    if (!result?.course_id) throw new Error(t('teacherHome.createFailed'))
    createDialogOpen.value = false
    await courseStore.fetchCourseList({ surface: 'teacher' })
    openCourse(result.course_id)
  } catch { ElMessage.error(t('teacherHome.createFailed')) } finally { creating.value = false }
}
function refreshAfterCalendarSave() { void loadCalendar() }
function refreshAfterStorage(event: StorageEvent) { if (event.key === TEACHING_CALENDAR_SAVED_STORAGE_KEY) void loadCalendar() }
function refreshWhenVisible() { if (document.visibilityState === 'visible') void loadCalendar() }

watch([cursor, view], () => { void loadCalendar() })
onMounted(async () => {
  courseStore.currentCourseId = ''
  await refresh()
  if (route.query.create === '1') {
    createDialogOpen.value = true
    void router.replace({ name: 'course-library' })
  }
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
.teacher-home,.teacher-home *{box-sizing:border-box}.teacher-home{width:100%;height:100%;min-height:0;overflow:hidden;color:var(--lz-text);background:var(--lz-surface)}button,input{font:inherit}.home-header-actions{display:flex;align-items:center;gap:8px}.home-header-actions button{height:38px;display:inline-flex;align-items:center;gap:7px;padding:0 13px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer}.header-quiet{border:1px solid var(--lz-border);color:var(--lz-text-secondary);background:var(--lz-surface)}.header-quiet b{min-width:20px;padding:1px 6px;border-radius:10px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:12px}.header-primary{border:1px solid var(--lz-brand);color:#fff;background:var(--lz-brand)}
.home-layout{height:100%;min-height:0;display:grid;grid-template-columns:292px minmax(600px,1fr) 310px}.course-rail{min-width:0;min-height:0;display:grid;grid-template-rows:64px 48px minmax(0,1fr);border-right:1px solid var(--lz-border);background:var(--lz-fill)}.course-rail>header{display:flex;align-items:center;padding:0 16px}.course-rail>header>div{display:grid;gap:3px}.course-rail>header strong{font-size:16px}.course-rail>header span{color:var(--lz-text-muted);font-size:12px}.course-search{height:40px;display:flex;align-items:center;gap:8px;margin:0 12px;padding:0 10px 0 12px;border:1px solid transparent;border-radius:8px;color:var(--lz-text-muted);background:#eef2f7}.course-search:focus-within{border-color:var(--lz-brand-border);background:var(--lz-surface);box-shadow:0 0 0 3px var(--lz-brand-soft)}.course-search input{min-width:0;width:100%;border:0;outline:0;color:var(--lz-text);background:transparent;font-size:13px}.course-search input::-webkit-search-cancel-button{display:none}.course-search>button{width:26px;height:26px;display:grid;place-items:center;padding:0;border:0;border-radius:6px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.course-search>button:hover{color:var(--lz-text-strong);background:#e2e8f0}.course-list{min-height:0;overflow:auto;padding:8px}.course-entry{width:100%;min-height:58px;display:grid;grid-template-columns:34px minmax(0,1fr) 16px;align-items:center;gap:10px;padding:7px 9px;border:0;border-radius:8px;color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.course-entry:hover,.course-entry:focus-visible{outline:0;background:var(--lz-surface)}.course-icon{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.course-icon[data-color="1"]{color:var(--lz-success);background:var(--lz-success-soft)}.course-icon[data-color="2"]{color:var(--lz-warning);background:var(--lz-warning-soft)}.course-icon[data-color="3"]{color:var(--lz-danger);background:var(--lz-danger-soft)}.course-entry__copy{min-width:0;display:grid;gap:3px}.course-entry__copy strong,.course-entry__copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.course-entry__copy strong{color:var(--lz-text-strong);font-size:13px}.course-entry__copy small{color:var(--lz-text-muted);font-size:12px}.course-search-empty{min-height:180px;display:grid;place-content:center;justify-items:center;gap:9px;padding:20px;color:var(--lz-text-muted);text-align:center}.course-search-empty strong{color:var(--lz-text-secondary);font-size:14px}.course-search-empty button{padding:6px 9px;border:0;border-radius:6px;color:var(--lz-brand-strong);background:transparent;font-size:12px;font-weight:700;cursor:pointer}
.calendar-surface{min-width:0;min-height:0;display:grid;grid-template-rows:64px auto minmax(0,1fr);background:var(--lz-surface)}.calendar-toolbar{display:flex;align-items:center;gap:14px;padding:0 16px;border-bottom:1px solid var(--lz-border)}.calendar-title{min-width:0;display:flex;align-items:center;gap:9px}.calendar-title>svg{color:var(--lz-brand)}.calendar-title strong{font-size:16px}.toolbar-spacer{flex:1}.view-switch{display:flex;border-bottom:1px solid var(--lz-border)}.view-switch button{height:38px;display:flex;align-items:center;gap:6px;padding:0 12px;border:0;border-bottom:2px solid transparent;color:var(--lz-text-secondary);background:transparent;font-size:13px;cursor:pointer}.view-switch button.active{border-bottom-color:var(--lz-brand);color:var(--lz-brand-strong)}.period-actions{display:flex;align-items:center;gap:6px}.period-actions button{height:36px;min-width:36px;display:grid;place-items:center;padding:0 10px;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-text-secondary);background:var(--lz-surface);font-size:13px;cursor:pointer}.calendar-issue{min-height:40px;display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--lz-warning-border);color:var(--lz-warning);background:var(--lz-warning-soft);font-size:13px}.calendar-issue span{flex:1}.calendar-issue button{height:28px;border:1px solid var(--lz-warning-border);border-radius:6px;background:var(--lz-surface)}.calendar-loading{height:100%;display:flex;align-items:center;justify-content:center;gap:8px;color:var(--lz-text-muted);font-size:13px}.month-canvas{position:relative;min-width:0;min-height:0;overflow:auto;padding:10px}.month-canvas :deep(.month-grid){min-height:100%;overflow:hidden}.week-canvas{min-width:720px;min-height:0;display:grid;grid-template-columns:repeat(7,minmax(100px,1fr));overflow:auto;padding:10px}.week-canvas>section{min-width:0;border:1px solid var(--lz-border);border-right:0}.week-canvas>section:last-child{border-right:1px solid var(--lz-border)}.week-canvas>section>header{height:42px;display:flex;align-items:center;justify-content:space-between;padding:0 9px;border-bottom:1px solid var(--lz-border);font-size:12px}.week-canvas>section.today>header{color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.week-canvas>section>button{width:calc(100% - 10px);display:grid;gap:4px;margin:5px;padding:8px;border:1px solid var(--lz-brand-border);border-radius:7px;color:var(--lz-text-secondary);background:var(--lz-brand-soft);text-align:left;cursor:pointer}.week-canvas>section>button.active{border-color:var(--lz-brand)}.week-canvas time{color:var(--lz-brand-strong);font-size:12px;font-weight:700}.week-canvas button strong,.week-canvas button span{overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.week-canvas section>p{margin:12px;color:var(--lz-text-muted);font-size:12px}
.day-inspector{min-width:0;min-height:0;display:grid;grid-template-rows:64px minmax(0,1fr) auto;border-left:1px solid var(--lz-border);background:var(--lz-surface)}.day-inspector>header{display:flex;align-items:center;justify-content:space-between;padding:0 16px;border-bottom:1px solid var(--lz-border)}.day-inspector>header>div{min-width:0;display:grid;gap:3px}.day-inspector>header small{color:var(--lz-text-muted);font-size:12px}.day-inspector>header strong{overflow:hidden;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.day-inspector>header button{width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.session-focus{align-content:start;display:grid;gap:14px;padding:20px 16px;border-bottom:1px solid var(--lz-border)}.session-number{width:max-content;color:var(--lz-text-muted);font-size:12px;font-weight:700}.session-focus h2{margin:0;font-size:18px;line-height:1.45}.session-focus dl{display:grid;gap:11px;margin:3px 0 0}.session-focus dl>div{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px}.session-focus dt{display:flex;align-items:center;gap:6px;color:var(--lz-text-muted);font-size:12px}.session-focus dd{margin:0;color:var(--lz-text-secondary);font-size:13px}.preparation-summary{align-self:start;display:grid;padding:16px}.preparation-summary>header{margin-bottom:7px}.preparation-summary>header strong{font-size:14px}.preparation-summary>div{min-height:42px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--lz-border);font-size:13px}.preparation-summary>div strong{color:var(--lz-text-secondary)}.inspector-actions{display:grid;gap:8px;padding:14px 16px;border-top:1px solid var(--lz-border)}.inspector-actions button{height:40px;display:flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);font-size:13px;font-weight:700;cursor:pointer}.inspector-actions button.primary{border-color:var(--lz-brand);color:#fff;background:var(--lz-brand)}.today-list{min-height:0;overflow:auto;padding:12px 14px}.today-list__heading{height:40px;display:flex;align-items:center;justify-content:space-between}.today-list__heading strong{font-size:14px}.today-list__heading span{color:var(--lz-text-muted);font-size:12px}.today-list>button{width:100%;min-height:64px;display:grid;grid-template-columns:48px minmax(0,1fr) 15px;align-items:center;gap:9px;padding:8px 2px;border:0;border-bottom:1px solid var(--lz-border);color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.today-list time{color:var(--lz-brand-strong);font-size:12px;line-height:1.5}.today-list button>span{min-width:0;display:grid;gap:3px}.today-list button strong,.today-list button small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.today-list button strong{font-size:13px}.today-list button small{color:var(--lz-text-muted);font-size:12px}.today-empty{min-height:230px;display:grid;place-content:center;justify-items:center;gap:9px;color:var(--lz-text-muted);text-align:center}.today-empty strong{color:var(--lz-text-strong);font-size:14px}.spin{animation:home-spin .85s linear infinite}@keyframes home-spin{to{transform:rotate(360deg)}}
@media(max-width:1100px){.home-layout{grid-template-columns:250px minmax(0,1fr) 260px}.session-focus,.preparation-summary{padding-left:13px;padding-right:13px}}
@media(max-width:820px){.teacher-home{overflow:auto}.home-layout{height:auto;min-height:100%;grid-template-columns:210px minmax(560px,1fr)}.day-inspector{grid-column:1/-1;min-height:320px;border-top:1px solid var(--lz-border);border-left:0}.course-rail{min-height:650px}.calendar-surface{min-height:650px}}
@media(max-width:620px){.home-header-actions .header-quiet span{display:none}.home-layout{display:block}.course-rail{min-height:0;grid-template-rows:58px 46px auto}.course-list{max-height:230px}.calendar-surface{min-height:680px;grid-template-rows:auto auto minmax(0,1fr)}.calendar-toolbar{min-height:102px;display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-rows:auto auto;gap:8px;padding:9px 10px}.calendar-title{grid-column:1}.view-switch{grid-column:2}.toolbar-spacer{display:none}.period-actions{grid-column:1/-1;justify-self:end}.month-canvas{padding:6px}.day-inspector{min-height:350px}}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
