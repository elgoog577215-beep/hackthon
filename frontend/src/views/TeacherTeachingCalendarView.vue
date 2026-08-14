<template>
  <section class="teacher-total-calendar">
    <header class="product-bar">
      <button type="button" class="brand" @click="router.push('/courses')"><img src="/qizhi-favicon.svg" alt="" /><strong>启智</strong></button>
      <nav aria-label="教师工作台">
        <button type="button" @click="router.push('/courses')">{{ t('teacherWorkbench.courseWorkbench', '课程工作台') }}</button><ChevronRight :size="14" /><strong>{{ t('teacherCalendar.total', '教学总日历') }}</strong>
      </nav>
      <div class="product-actions"><button type="button" @click="refresh"><RefreshCw :size="17" :class="{ spin: store.loading }" />{{ t('common.refresh', '刷新') }}</button></div>
    </header>

    <nav class="workspace-tabs" aria-label="教师工作台分类">
      <button type="button" @click="router.push('/courses')"><LayoutGrid :size="16" />{{ t('teacherCalendar.myCourses', '我的课程') }}</button>
      <button type="button" class="active" aria-current="page"><CalendarRange :size="16" />{{ t('teacherCalendar.total', '教学总日历') }}</button>
    </nav>

    <main class="calendar-main">
      <div class="status-bar" role="status">
        <strong>{{ monthLabel }}</strong><span>{{ t('teacherCalendar.courseCount', '课程') }} {{ courseCount }}</span><span>{{ t('teacherCalendar.sessions', '已排期') }} {{ officialSessions.length }}</span><span>待完善 {{ incompleteSessions.length }}</span><span v-if="conflictCount" class="conflict-status">冲突 {{ conflictCount }}</span><span class="spacer"></span><span>{{ t('teacherCalendar.totalReadOnly', '在单课程日历中修改') }}</span>
      </div>

      <section class="workspace">
        <header class="toolbar">
          <div class="segmented" role="tablist">
            <button type="button" data-testid="total-month-view" :class="{ active: view === 'month' }" @click="view = 'month'"><CalendarDays :size="15" />{{ t('teacherCalendar.month', '月历') }}</button>
            <button type="button" data-testid="total-week-view" :class="{ active: view === 'week' }" @click="view = 'week'"><Columns3 :size="15" />{{ t('teacherCalendar.week', '周历') }}</button>
            <button type="button" data-testid="total-list-view" :class="{ active: view === 'list' }" @click="view = 'list'"><List :size="15" />{{ t('teacherCalendar.list', '列表') }}</button>
          </div>
          <el-popover trigger="click" placement="bottom-start" :width="260">
            <div class="course-filter-panel"><header><strong>显示课程</strong><button type="button" @click="selectedCourseIds = []">全部</button></header><label v-for="course in courseOptions" :key="course.id"><input type="checkbox" :checked="courseSelected(course.id)" @change="toggleCourse(course.id)" /><i :data-color="course.color"></i><span>{{ course.title }}</span></label></div>
            <template #reference><button type="button" class="filter-button"><SlidersHorizontal :size="15" />课程筛选<span v-if="selectedCourseIds.length">{{ selectedCourseIds.length }}</span></button></template>
          </el-popover>
          <button type="button" class="incomplete-toggle" :class="{ active: showIncomplete }" @click="showIncomplete = !showIncomplete">待完善 {{ incompleteSessions.length }}</button>
          <span class="toolbar-spacer"></span>
          <button type="button" aria-label="上一周期" @click="movePeriod(-1)"><ChevronLeft :size="16" /></button><strong>{{ periodLabel }}</strong><button type="button" aria-label="下一周期" @click="movePeriod(1)"><ChevronRight :size="16" /></button><button type="button" @click="goToday">{{ t('teacherCalendar.today', '今天') }}</button>
        </header>

        <div v-if="store.error" class="issue-bar" role="alert"><TriangleAlert :size="16" /><span>{{ store.error }}</span><button type="button" @click="load">{{ t('common.retry', '重试') }}</button></div>
        <div v-if="store.loading && !store.totalSessions.length" class="empty-state"><LoaderCircle class="spin" :size="22" />{{ t('teacherCalendar.loadingTotal', '正在汇总教学日历') }}</div>

        <div v-else-if="view === 'month'" class="month-view">
          <TeachingCalendarMonthGrid :month="monthCursor" :sessions="visibleSessions" show-course @select="openSession" @prepare="openPreparation" />
          <div v-if="!visibleSessions.length" class="calendar-empty-hint">
            <CalendarRange :size="19" /><span><strong>{{ t('teacherCalendar.totalEmpty', '当前范围还没有已排期课次') }}</strong><small>先在任一课程的教学日历中排期，这里会自动按课程颜色汇总。</small></span><button type="button" @click="router.push('/courses')">返回我的课程</button>
          </div>
        </div>

        <div v-else-if="view === 'week'" class="week-view">
          <section v-for="day in weekDays" :key="day.date">
            <header><strong>{{ day.label }}</strong><span>{{ day.date.slice(5) }}</span></header>
            <button v-for="session in day.sessions" :key="session.session_id" type="button" :data-color="session.course_color_key ?? 0" :class="{ conflict: session.has_conflict, incomplete: session.calendar_layer === 'incomplete' }" @click="openSession(session)">
              <time>{{ session.start_time?.slice(0, 5) || '--:--' }}</time><strong>{{ session.course_title }}</strong><span>{{ session.content_summary }}</span><small>{{ session.location || t('teacherCalendar.locationUnset', '地点未定') }}</small>
              <em v-if="session.has_conflict">排课冲突</em><em v-else-if="session.calendar_layer === 'incomplete'">待完善</em>
            </button>
            <p v-if="!day.sessions.length">{{ t('teacherCalendar.noClass', '无课') }}</p>
          </section>
        </div>

        <div v-else class="list-view">
          <table><thead><tr><th>{{ t('teacherCalendar.columns.date', '日期') }}</th><th>{{ t('teacherCalendar.course', '课程') }}</th><th>{{ t('teacherCalendar.columns.content', '教学内容') }}</th><th>{{ t('teacherCalendar.columns.location', '上课地点') }}</th><th>{{ t('teacherCalendar.columns.teacher', '教师') }}</th><th>{{ t('teacherCalendar.columns.type', '类型') }}</th></tr></thead>
            <tbody><tr v-for="session in visibleSessions" :key="session.session_id" data-testid="total-calendar-row" :class="{ conflict: session.has_conflict, incomplete: session.calendar_layer === 'incomplete' }" tabindex="0" @click="openSession(session)" @keydown.enter="openSession(session)"><td><strong>{{ session.date }}</strong><small>{{ session.start_time?.slice(0, 5) || '时间待定' }}<template v-if="session.end_time">—{{ session.end_time.slice(0, 5) }}</template></small></td><td><i :data-color="session.course_color_key ?? 0"></i>{{ session.course_title }}</td><td>{{ session.content_summary }}</td><td>{{ session.location || '—' }}</td><td>{{ session.teacher_name || '—' }}</td><td><span v-if="session.has_conflict" class="row-badge danger">冲突</span><span v-else-if="session.calendar_layer === 'incomplete'" class="row-badge">待完善</span><template v-else>{{ session.teaching_type }}</template></td></tr></tbody>
          </table>
          <div v-if="!visibleSessions.length" class="empty-state">{{ t('teacherCalendar.totalEmpty', '当前范围还没有已排期课次') }}</div>
        </div>
      </section>
    </main>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CalendarDays, CalendarRange, ChevronLeft, ChevronRight, Columns3, LayoutGrid, List, LoaderCircle, RefreshCw, SlidersHorizontal, TriangleAlert } from 'lucide-vue-next'
import TeachingCalendarMonthGrid from '../components/TeachingCalendarMonthGrid.vue'
import { t } from '../shared/i18n'
import { TEACHING_CALENDAR_SAVED_EVENT, TEACHING_CALENDAR_SAVED_STORAGE_KEY, useTeachingCalendarStore, type ClassSession } from '../stores/teachingCalendar'

const router = useRouter()
const store = useTeachingCalendarStore()
const view = ref<'month' | 'week' | 'list'>('month')
const cursor = ref(new Date())
const showIncomplete = ref(false)
const selectedCourseIds = ref<string[]>([])
const pad = (value: number) => String(value).padStart(2, '0')
const iso = (value: Date) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
const monthCursor = computed(() => `${cursor.value.getFullYear()}-${pad(cursor.value.getMonth() + 1)}-01`)
const monthLabel = computed(() => `${cursor.value.getFullYear()}年${cursor.value.getMonth() + 1}月`)
const weekStart = computed(() => { const value = new Date(cursor.value); value.setHours(12, 0, 0, 0); value.setDate(value.getDate() - ((value.getDay() + 6) % 7)); return value })
const weekEnd = computed(() => { const value = new Date(weekStart.value); value.setDate(value.getDate() + 6); return value })
const weekdayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const officialSessions = computed(() => store.totalSessions.filter(item => item.calendar_layer !== 'incomplete'))
const incompleteSessions = computed(() => store.totalSessions.filter(item => item.calendar_layer === 'incomplete'))
const courseOptions = computed(() => Array.from(new Map(store.totalSessions.map(item => [item.course_id || '', { id: item.course_id || '', title: item.course_title || '未命名课程', color: item.course_color_key ?? 0 }])).values()).filter(item => item.id))
const baseVisibleSessions = computed(() => showIncomplete.value ? store.totalSessions : officialSessions.value)
const conflictIds = computed(() => {
  const ids = new Set<string>()
  const rows = baseVisibleSessions.value.filter(item => item.date && item.start_time && item.end_time && item.teacher_name)
  rows.forEach((left, index) => rows.slice(index + 1).forEach(right => {
    if (left.date !== right.date || left.teacher_name.trim() !== right.teacher_name.trim()) return
    if (String(left.start_time) < String(right.end_time) && String(right.start_time) < String(left.end_time)) {
      if (left.session_id) ids.add(left.session_id)
      if (right.session_id) ids.add(right.session_id)
    }
  }))
  return ids
})
const visibleSessions = computed(() => baseVisibleSessions.value
  .filter(item => !selectedCourseIds.value.length || selectedCourseIds.value.includes(item.course_id || ''))
  .map(item => ({ ...item, has_conflict: Boolean(item.session_id && conflictIds.value.has(item.session_id)) })))
const weekDays = computed(() => Array.from({ length: 7 }, (_, index) => { const value = new Date(weekStart.value); value.setDate(value.getDate() + index); const date = iso(value); return { date, label: weekdayNames[index], sessions: visibleSessions.value.filter(item => item.date === date) } }))
const courseCount = computed(() => new Set(store.totalSessions.map(item => item.course_id)).size)
const conflictCount = computed(() => conflictIds.value.size)
const periodLabel = computed(() => view.value === 'week' ? `${iso(weekStart.value)} — ${iso(weekEnd.value)}` : monthLabel.value)

function loadRange() {
  if (view.value === 'week') return { from: iso(weekStart.value), to: iso(weekEnd.value) }
  const from = new Date(cursor.value.getFullYear(), cursor.value.getMonth(), 1, 12)
  const to = new Date(cursor.value.getFullYear(), cursor.value.getMonth() + 1, 0, 12)
  return { from: iso(from), to: iso(to) }
}
async function load() { const range = loadRange(); try { await store.loadTotal(range.from, range.to, true) } catch { /* exact error remains visible */ } }
async function refresh() { await load(); if (!store.error) ElMessage.success('教学总日历已刷新') }
function movePeriod(delta: number) { const value = new Date(cursor.value); if (view.value === 'week') value.setDate(value.getDate() + delta * 7); else value.setMonth(value.getMonth() + delta); cursor.value = value }
function goToday() { cursor.value = new Date() }
function openSession(session: ClassSession) { if (!session.course_id) return; void router.push({ name: 'teacher-course-calendar', params: { courseId: session.course_id }, query: { session: session.session_id || '' } }) }
function openPreparation(session: ClassSession) { if (!session.course_id) return; void router.push({ name: 'teacher-course-production', params: { courseId: session.course_id }, query: { stage: 'teaching', node: session.lesson_unit_id || undefined, from: 'total-calendar' } }) }
function courseSelected(courseId: string) { return !selectedCourseIds.value.length || selectedCourseIds.value.includes(courseId) }
function toggleCourse(courseId: string) {
  if (!selectedCourseIds.value.length) selectedCourseIds.value = courseOptions.value.map(item => item.id).filter(id => id !== courseId)
  else if (selectedCourseIds.value.includes(courseId)) selectedCourseIds.value = selectedCourseIds.value.filter(id => id !== courseId)
  else selectedCourseIds.value = [...selectedCourseIds.value, courseId]
  if (selectedCourseIds.value.length === courseOptions.value.length) selectedCourseIds.value = []
}
function refreshAfterCalendarSave() { void load() }
function refreshAfterStorage(event: StorageEvent) { if (event.key === TEACHING_CALENDAR_SAVED_STORAGE_KEY) void load() }
function refreshWhenVisible() { if (document.visibilityState === 'visible') void load() }

watch([cursor, view], () => { void load() }, { immediate: true })
onMounted(() => {
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
.teacher-total-calendar{min-height:100vh;height:100vh;overflow:hidden;color:var(--lz-text-primary);background:var(--lz-canvas)}button{font:inherit}.product-bar{height:52px;display:grid;grid-template-columns:188px minmax(0,1fr) auto;align-items:center;border-bottom:1px solid var(--lz-border);background:var(--lz-surface)}.brand{height:100%;display:flex;align-items:center;gap:10px;padding:0 20px;border:0;border-right:1px solid var(--lz-border);color:var(--lz-text-primary);background:transparent;cursor:pointer}.brand img{width:25px;height:25px}.brand strong{font-size:17px}.product-bar nav{min-width:0;display:flex;align-items:center;gap:8px;padding:0 24px;color:var(--lz-text-muted);font-size:12px}.product-bar nav button{padding:0;border:0;color:inherit;background:transparent;cursor:pointer}.product-bar nav strong{color:var(--lz-text-primary)}.product-actions{padding-right:14px}.product-actions button{height:34px;display:flex;align-items:center;gap:6px;padding:0 11px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}.workspace-tabs{position:absolute;top:52px;bottom:0;left:0;width:188px;display:grid;align-content:start;gap:4px;padding:14px 8px;border-right:1px solid var(--lz-border);background:var(--lz-surface)}.workspace-tabs button{height:40px;display:flex;align-items:center;gap:8px;padding:0 12px;border:0;border-radius:8px;color:var(--lz-text-secondary);background:transparent;cursor:pointer}.workspace-tabs button.active{color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-weight:700}.calendar-main{height:calc(100vh - 52px);margin-left:188px;display:grid;grid-template-rows:42px minmax(0,1fr)}.status-bar{min-width:0;display:flex;align-items:center;padding:0 14px;border-bottom:1px solid var(--lz-border);background:var(--lz-surface);font-size:11px;white-space:nowrap}.status-bar>strong,.status-bar>span{padding:0 11px;border-right:1px solid var(--lz-border)}.status-bar>strong{padding-left:0}.status-bar .spacer{flex:1;border:0}.workspace{min-width:0;min-height:0;display:grid;grid-template-rows:auto auto minmax(0,1fr);background:var(--lz-surface)}.toolbar{height:48px;display:flex;align-items:center;gap:7px;padding:0 12px;border-bottom:1px solid var(--lz-border)}.toolbar>button{height:30px;display:grid;place-items:center;padding:0 9px;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}.toolbar>strong{min-width:125px;font-size:11px;text-align:center}.toolbar-spacer{flex:1}.segmented{display:flex;padding:2px;border:1px solid var(--lz-border);border-radius:8px;background:var(--lz-fill)}.segmented button{height:28px;display:flex;align-items:center;gap:5px;padding:0 10px;border:0;border-radius:6px;color:var(--lz-text-secondary);background:transparent;cursor:pointer}.segmented button.active{color:var(--lz-brand-strong);background:var(--lz-surface);box-shadow:0 1px 2px rgb(0 0 0/.06)}.issue-bar{min-height:38px;display:flex;align-items:center;gap:8px;padding:7px 12px;border-bottom:1px solid var(--lz-warning-border);color:var(--lz-text-secondary);background:var(--lz-warning-soft);font-size:10px}.issue-bar span{flex:1}.issue-bar button{height:26px;border:1px solid var(--lz-warning-border);border-radius:6px;background:var(--lz-surface)}.month-view,.list-view{min-width:0;min-height:0;overflow:auto;padding:12px}.week-view{min-width:760px;min-height:0;display:grid;grid-template-columns:repeat(7,minmax(100px,1fr));overflow:auto;padding:12px}.week-view section{min-width:0;border-top:1px solid var(--lz-border);border-left:1px solid var(--lz-border);border-bottom:1px solid var(--lz-border)}.week-view section:last-child{border-right:1px solid var(--lz-border)}.week-view section>header{height:40px;display:flex;align-items:center;justify-content:space-between;padding:0 8px;border-bottom:1px solid var(--lz-border);font-size:10px}.week-view section>header span{color:var(--lz-text-muted)}.week-view section>button{width:calc(100% - 10px);display:grid;gap:3px;margin:5px;padding:7px;border:0;border-left:3px solid var(--lz-brand);border-radius:6px;color:var(--lz-text-secondary);background:var(--lz-brand-soft);text-align:left;cursor:pointer}.week-view section>button time{color:var(--lz-brand-strong);font-size:9px;font-weight:700}.week-view section>button strong,.week-view section>button span,.week-view section>button small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.week-view section>button strong{font-size:10px}.week-view section>button span,.week-view section>button small{font-size:9px}.week-view section>p{margin:12px;color:var(--lz-text-muted);font-size:9px}.list-view table{width:100%;min-width:850px;border-collapse:collapse}.list-view th{height:34px;padding:0 10px;border-bottom:1px solid var(--lz-border);color:var(--lz-text-muted);background:var(--lz-fill);font-size:9px;text-align:left}.list-view td{height:48px;padding:7px 10px;border-bottom:1px solid var(--lz-border);font-size:10px}.list-view tr{cursor:pointer}.list-view tr:hover td{background:var(--lz-brand-soft)}.list-view td strong,.list-view td small{display:block}.list-view td small{margin-top:2px;color:var(--lz-text-muted)}.list-view td i{width:6px;height:6px;display:inline-block;margin-right:6px;border-radius:50%;background:var(--lz-brand)}.empty-state{height:100%;display:flex;align-items:center;justify-content:center;gap:8px;color:var(--lz-text-muted);font-size:11px}.spin{animation:spin .9s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.week-view section>button{border:1px solid var(--lz-brand-border);border-left-width:1px}
.week-view section>button[data-color="1"]{border-color:color-mix(in srgb,var(--lz-success) 32%,var(--lz-border));background:var(--lz-success-soft)}.week-view section>button[data-color="1"] time{color:var(--lz-success)}
.week-view section>button[data-color="2"]{border-color:color-mix(in srgb,var(--lz-warning) 32%,var(--lz-border));background:var(--lz-warning-soft)}.week-view section>button[data-color="2"] time{color:var(--lz-warning)}
.week-view section>button[data-color="3"]{border-color:color-mix(in srgb,var(--lz-danger) 25%,var(--lz-border));background:color-mix(in srgb,var(--lz-danger-soft) 58%,var(--lz-surface))}.week-view section>button[data-color="3"] time{color:var(--lz-danger)}
.week-view section>button[data-color="4"]{border-color:color-mix(in srgb,var(--lz-brand) 48%,var(--lz-success));background:color-mix(in srgb,var(--lz-brand-soft) 55%,var(--lz-success-soft))}.week-view section>button[data-color="4"] time{color:color-mix(in srgb,var(--lz-brand) 48%,var(--lz-success))}
.week-view section>button[data-color="5"]{border-color:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-warning));background:color-mix(in srgb,var(--lz-brand-soft) 58%,var(--lz-warning-soft))}.week-view section>button[data-color="5"] time{color:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-warning))}
.week-view section>button[data-color="6"]{border-color:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-danger));background:color-mix(in srgb,var(--lz-brand-soft) 58%,var(--lz-danger-soft))}.week-view section>button[data-color="6"] time{color:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-danger))}
.week-view section>button[data-color="7"]{border-color:color-mix(in srgb,var(--lz-success) 58%,var(--lz-warning));background:color-mix(in srgb,var(--lz-success-soft) 58%,var(--lz-warning-soft))}.week-view section>button[data-color="7"] time{color:color-mix(in srgb,var(--lz-success) 58%,var(--lz-warning))}
.list-view td i[data-color="1"]{background:var(--lz-success)}.list-view td i[data-color="2"]{background:var(--lz-warning)}.list-view td i[data-color="3"]{background:var(--lz-danger)}.list-view td i[data-color="4"]{background:color-mix(in srgb,var(--lz-brand) 48%,var(--lz-success))}.list-view td i[data-color="5"]{background:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-warning))}.list-view td i[data-color="6"]{background:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-danger))}.list-view td i[data-color="7"]{background:color-mix(in srgb,var(--lz-success) 58%,var(--lz-warning))}
.filter-button,.incomplete-toggle{height:30px!important;display:inline-flex!important;align-items:center;gap:5px}.filter-button span{min-width:17px;padding:1px 5px;border-radius:8px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:9px}.incomplete-toggle.active{border-color:var(--lz-warning-border)!important;color:var(--lz-warning)!important;background:var(--lz-warning-soft)!important}.course-filter-panel{display:grid;gap:3px}.course-filter-panel header{height:32px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--lz-border)}.course-filter-panel header strong{font-size:11px}.course-filter-panel header button{border:0;color:var(--lz-brand-strong);background:transparent;cursor:pointer;font-size:10px}.course-filter-panel label{min-height:34px;display:grid;grid-template-columns:18px 8px minmax(0,1fr);align-items:center;gap:7px;padding:0 5px;border-radius:6px;cursor:pointer}.course-filter-panel label:hover{background:var(--lz-fill)}.course-filter-panel i{width:7px;height:7px;border-radius:50%;background:var(--lz-brand)}.course-filter-panel i[data-color="1"]{background:var(--lz-success)}.course-filter-panel i[data-color="2"]{background:var(--lz-warning)}.course-filter-panel i[data-color="3"]{background:var(--lz-danger)}.course-filter-panel i[data-color="4"]{background:color-mix(in srgb,var(--lz-brand) 48%,var(--lz-success))}.course-filter-panel i[data-color="5"]{background:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-warning))}.course-filter-panel i[data-color="6"]{background:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-danger))}.course-filter-panel i[data-color="7"]{background:color-mix(in srgb,var(--lz-success) 58%,var(--lz-warning))}.course-filter-panel span{overflow:hidden;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.conflict-status{border:0!important;color:var(--lz-danger);font-weight:700}.week-view section>button em{width:max-content;padding:2px 5px;border-radius:5px;color:var(--lz-warning);background:var(--lz-warning-soft);font-style:normal;font-size:8px}.week-view section>button.conflict{border-color:var(--lz-danger);background:var(--lz-danger-soft)}.week-view section>button.conflict em{color:var(--lz-danger);background:transparent}.week-view section>button.incomplete{border-style:dashed;opacity:.8}.list-view tr.conflict td{background:var(--lz-danger-soft)}.list-view tr.incomplete td{color:var(--lz-text-muted)}.row-badge{padding:3px 6px;border-radius:6px;color:var(--lz-warning);background:var(--lz-warning-soft);font-size:9px}.row-badge.danger{color:var(--lz-danger);background:var(--lz-danger-soft)}
.month-view{position:relative}.calendar-empty-hint{position:absolute;top:92px;left:50%;width:min(520px,calc(100% - 48px));display:grid;grid-template-columns:28px minmax(0,1fr) auto;align-items:center;gap:10px;padding:12px 14px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-brand-strong);background:rgb(255 255 255 / 94%);box-shadow:0 8px 24px rgb(15 23 42 / 7%);transform:translateX(-50%)}.calendar-empty-hint span{display:grid;gap:3px}.calendar-empty-hint strong{color:var(--lz-text-primary);font-size:11px}.calendar-empty-hint small{color:var(--lz-text-muted);font-size:9px}.calendar-empty-hint button{height:30px;padding:0 9px;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-surface);cursor:pointer}
@media(max-width:900px){.product-bar{grid-template-columns:64px minmax(0,1fr) auto}.brand{justify-content:center;padding:0}.brand strong{display:none}.workspace-tabs{width:64px}.workspace-tabs button{justify-content:center;padding:0}.workspace-tabs button{font-size:0}.calendar-main{margin-left:64px}.status-bar>span:nth-of-type(n+3){display:none}}
@media(max-width:680px){.product-bar nav button,.product-bar nav svg,.product-actions button{font-size:0}.toolbar>strong{min-width:90px}.status-bar>span{display:none}}
</style>
