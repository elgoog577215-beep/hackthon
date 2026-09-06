<template>
  <div class="month-grid" role="grid" :aria-label="monthLabel">
    <div v-for="label in weekdayLabels" :key="label" class="weekday" role="columnheader">{{ label }}</div>
    <div
      v-for="cell in cells"
      :key="cell.key"
      class="day-cell"
      :class="{ muted: !cell.inMonth, today: cell.isToday, selected: cell.date === selectedDate }"
      role="gridcell"
      tabindex="0"
      :aria-selected="cell.date === selectedDate"
      @click="emitDay(cell.date)"
      @keydown.enter="emitDay(cell.date)"
      @keydown.space.prevent="emitDay(cell.date)"
    >
      <span class="day-number">{{ cell.day }}</span>
      <span class="day-events">
        <el-popover
          v-for="session in cell.sessions.slice(0, 3)"
          :key="session.session_id || `${session.course_id}-${session.sequence}`"
          :trigger="['hover', 'focus']"
          placement="top-start"
          :width="292"
          :offset="8"
          :show-after="140"
          :hide-after="80"
          popper-class="calendar-session-popover"
        >
          <div class="event-popover" :data-color="session.course_color_key ?? 0">
            <header>
              <span class="course-heading">
                <strong>{{ session.course_title || t('teacherHome.untitledCourse', '未命名课程') }}</strong>
              </span>
              <span class="session-index">{{ t('teacherHome.sessionNumber', '第 {number} 课次').replace('{number}', String(session.sequence)) }}</span>
            </header>
            <section class="lesson-summary">
              <strong>{{ session.content_summary || t('teacherHome.contentPending', '教学内容待补充') }}</strong>
            </section>
            <div v-if="session.has_conflict" class="popover-warning">{{ t('teacherHome.calendarPopover.conflict', '同一教师在此时段还有其他课程') }}</div>
            <div v-else-if="session.calendar_layer === 'incomplete'" class="popover-warning">{{ t('teacherHome.calendarPopover.incomplete', '日期已填写，但时间尚未完整，暂未进入正式排期') }}</div>
            <dl>
              <div><dt><Clock3 :size="14" />{{ t('teacherHome.calendarPopover.time', '时间') }}</dt><dd>{{ sessionTime(session) }}</dd></div>
              <div><dt><MapPin :size="14" />{{ t('teacherHome.location', '地点') }}</dt><dd>{{ session.location || t('teacherHome.locationPending', '地点未定') }}</dd></div>
              <div v-if="session.teacher_name"><dt><UserRound :size="14" />{{ t('teacherHome.calendarPopover.teacher', '教师') }}</dt><dd>{{ session.teacher_name }}</dd></div>
            </dl>
            <div class="preparation-status">
              <span>{{ t('teacherProductionState.stages.outline', '大纲') }} {{ session.lesson_unit_id ? t('teacherHome.calendarPopover.linked', '已关联讲次') : t('teacherHome.calendarPopover.unlinked', '待关联') }}</span>
              <span>{{ t('teacherHome.lessonPlan', '教案') }} {{ session.lesson_plan_status || t('teacherHome.calendarPopover.openToCheck', '进入备课查看') }}</span>
              <span>{{ t('teacherProductionState.stages.script', '讲义') }} {{ session.script_status || t('teacherHome.calendarPopover.openToCheck', '进入备课查看') }}</span>
              <span>PPT {{ session.ppt_status || t('teacherHome.calendarPopover.openToCheck', '进入备课查看') }}</span>
            </div>
            <footer v-if="showCourse"><button type="button" @click="$emit('select', session)">{{ t('teacherHome.calendarPopover.viewSchedule', '查看排期') }}</button><button type="button" @click="$emit('prepare', session)">{{ t('teacherHome.calendarPopover.prepare', '进入备课') }} <ArrowUpRight :size="13" /></button></footer>
            <footer v-else>{{ t('teacherHome.calendarPopover.editSession', '点击课次进入编辑') }} <ArrowUpRight :size="13" /></footer>
          </div>
          <template #reference>
            <button
              type="button"
              class="event"
              :class="{ conflict: session.has_conflict, incomplete: session.calendar_layer === 'incomplete' }"
              :data-color="session.course_color_key ?? 0"
              :aria-label="eventAriaLabel(session)"
              @click.stop="$emit('select', session)"
            >
              <i></i><span>{{ showCourse ? session.course_title : session.content_summary }}</span>
            </button>
          </template>
        </el-popover>
        <small v-if="cell.sessions.length > 3">+{{ cell.sessions.length - 3 }}</small>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight, Clock3, MapPin, UserRound } from 'lucide-vue-next'
import type { ClassSession } from '../stores/teachingCalendar'
import { activeLocale, t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  month: string
  sessions: ClassSession[]
  showCourse?: boolean
  selectedDate?: string | null
}>(), { showCourse: false })

const emit = defineEmits<{
  select: [session: ClassSession]
  prepare: [session: ClassSession]
  day: [date: string]
}>()

const weekdayLabels = computed(() => ['一', '二', '三', '四', '五', '六', '日'].map((fallback, index) => t(`teacherHome.weekdays.${index + 1}`, fallback)))
const pad = (value: number) => String(value).padStart(2, '0')
const iso = (value: Date) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
const base = computed(() => {
  const parsed = new Date(`${props.month.slice(0, 7)}-01T12:00:00`)
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed
})
const monthLabel = computed(() => new Intl.DateTimeFormat(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { year: 'numeric', month: 'long' }).format(base.value))
const cells = computed(() => {
  const first = new Date(base.value.getFullYear(), base.value.getMonth(), 1, 12)
  const offset = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(1 - offset)
  const today = iso(new Date())
  return Array.from({ length: 42 }, (_, index) => {
    const value = new Date(start)
    value.setDate(start.getDate() + index)
    const date = iso(value)
    return {
      key: date,
      date,
      day: value.getDate(),
      inMonth: value.getMonth() === base.value.getMonth(),
      isToday: date === today,
      sessions: props.sessions.filter(item => item.date === date && item.status !== 'cancelled'),
    }
  })
})

function sessionTime(session: ClassSession) {
  const date = session.date?.replace(/-/g, '/') || t('teacherHome.datePending', '日期未定')
  const start = session.start_time?.slice(0, 5) || '--:--'
  const end = session.end_time?.slice(0, 5)
  return `${date} · ${start}${end ? `–${end}` : ''}`
}
function eventAriaLabel(session: ClassSession) {
  return [session.course_title, session.content_summary, sessionTime(session), session.location].filter(Boolean).join(activeLocale.value === 'zh' ? '，' : ', ')
}
function emitDay(date: string) { emit('day', date) }
</script>

<style scoped>
.month-grid { min-width:0; height:100%; min-height:560px; display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); grid-template-rows:36px repeat(6,minmax(82px,1fr)); border-top:1px solid var(--lz-border); border-left:1px solid var(--lz-border); background:var(--lz-surface); }
.weekday { height:36px; display:grid; place-items:center; border-right:1px solid var(--lz-border); border-bottom:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:12px; font-weight:700; }
.day-cell { min-width:0; min-height:82px; display:grid; grid-template-rows:26px minmax(0,1fr); gap:3px; padding:6px; border:0; border-right:1px solid var(--lz-border); border-bottom:1px solid var(--lz-border); color:var(--lz-text-primary); background:var(--lz-surface); text-align:left; cursor:pointer; }
.day-cell:hover { background:var(--lz-fill); }.day-cell:focus-visible{outline:2px solid var(--lz-brand);outline-offset:-2px}.day-cell.muted { color:var(--lz-text-muted); background:color-mix(in srgb,var(--lz-fill) 48%,var(--lz-surface)); }.day-cell.selected{background:var(--lz-brand-soft);box-shadow:inset 0 0 0 2px var(--lz-brand)}.day-cell.today .day-number { color:#fff; background:var(--lz-brand); }
.day-number { width:26px; height:26px; display:grid; place-items:center; border-radius:50%; font-size:12px; font-weight:700; }
.day-events { min-width:0; display:grid; align-content:start; gap:4px; }.day-events :deep(.el-popper__trigger){min-width:0;display:block}.event { --course-accent:var(--lz-brand);--course-bg:var(--lz-brand-soft);width:100%; min-width:0; height:24px; display:flex; align-items:center; gap:6px; padding:0 6px; border:1px solid transparent; border-radius:5px; color:var(--lz-text-secondary); background:var(--course-bg); font-size:12px; cursor:pointer; }.event:hover,.event:focus-visible{color:var(--lz-brand-strong);border-color:color-mix(in srgb,var(--course-accent) 22%,transparent);outline:none}.event i { width:6px; height:6px; flex:0 0 auto; border-radius:50%; background:var(--course-accent); }.event span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.event[data-color="1"]{--course-accent:var(--lz-success);--course-bg:var(--lz-success-soft)}.event[data-color="2"]{--course-accent:var(--lz-warning);--course-bg:var(--lz-warning-soft)}.event[data-color="3"]{--course-accent:var(--lz-danger);--course-bg:var(--lz-danger-soft)}.event[data-color="4"]{--course-accent:color-mix(in srgb,var(--lz-brand) 52%,var(--lz-success));--course-bg:color-mix(in srgb,var(--lz-brand-soft) 55%,var(--lz-success-soft))}.event[data-color="5"]{--course-accent:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-warning));--course-bg:color-mix(in srgb,var(--lz-brand-soft) 58%,var(--lz-warning-soft))}.event[data-color="6"]{--course-accent:color-mix(in srgb,var(--lz-brand) 58%,var(--lz-danger));--course-bg:color-mix(in srgb,var(--lz-brand-soft) 58%,var(--lz-danger-soft))}.event[data-color="7"]{--course-accent:color-mix(in srgb,var(--lz-success) 58%,var(--lz-warning));--course-bg:color-mix(in srgb,var(--lz-success-soft) 58%,var(--lz-warning-soft))}
.day-events small { padding-left:6px; color:var(--lz-text-muted); font-size:12px; }
.event.conflict{border-color:var(--lz-danger);color:var(--lz-danger);background:var(--lz-danger-soft)}.event.incomplete{border-style:dashed;opacity:.78}.popover-warning{padding:7px 8px;color:var(--lz-warning);background:var(--lz-warning-soft);font-size:12px;line-height:1.45}
.event-popover{--course-accent:var(--lz-brand);--course-bg:var(--lz-brand-soft);display:grid;gap:12px;padding:14px;color:var(--lz-text);background:var(--lz-surface)}.event-popover[data-color="1"]{--course-accent:var(--lz-success);--course-bg:var(--lz-success-soft)}.event-popover[data-color="2"]{--course-accent:var(--lz-warning);--course-bg:var(--lz-warning-soft)}.event-popover[data-color="3"]{--course-accent:var(--lz-danger);--course-bg:var(--lz-danger-soft)}.event-popover header{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px}.course-heading{min-width:0}.course-heading strong{overflow:hidden;display:block;color:var(--lz-text-strong);font-size:14px;line-height:1.4;text-overflow:ellipsis;white-space:nowrap}.session-index{color:var(--lz-text-muted);font-size:12px;font-weight:700;white-space:nowrap}.lesson-summary{padding-bottom:11px;border-bottom:1px solid var(--lz-border)}.lesson-summary strong{display:-webkit-box;overflow:hidden;color:var(--lz-text);font-size:13px;font-weight:650;line-height:1.5;-webkit-box-orient:vertical;-webkit-line-clamp:2}.event-popover dl{display:grid;gap:8px;margin:0}.event-popover dl>div{display:grid;grid-template-columns:68px minmax(0,1fr);align-items:center;gap:8px}.event-popover dt{display:flex;align-items:center;gap:5px;color:var(--lz-text-muted);font-size:12px}.event-popover dd{min-width:0;margin:0;overflow:hidden;color:var(--lz-text-secondary);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.preparation-status{display:grid;gap:6px;color:var(--lz-text-secondary);font-size:12px}.event-popover footer{display:flex;align-items:center;justify-content:flex-end;gap:6px;padding-top:10px;border-top:1px solid var(--lz-border);color:var(--lz-brand-strong);font-size:12px;font-weight:650}.event-popover footer button{height:32px;display:inline-flex;align-items:center;gap:4px;padding:0 10px;border:1px solid var(--lz-border);border-radius:6px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}.event-popover footer button:last-child{border-color:var(--lz-brand);color:#fff;background:var(--lz-brand)}
:global(.calendar-session-popover.el-popper){overflow:hidden;padding:0!important;border:1px solid color-mix(in srgb,var(--lz-brand) 12%,var(--lz-border))!important;border-radius:var(--lz-radius-control)!important;background:var(--lz-surface)!important;box-shadow:var(--lz-shadow-overlay)!important}:global(.calendar-session-popover.el-popper .el-popper__arrow::before){border-color:color-mix(in srgb,var(--lz-brand) 12%,var(--lz-border))!important;background:var(--lz-surface)!important}
</style>
