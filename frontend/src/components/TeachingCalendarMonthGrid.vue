<template>
  <div class="month-grid" role="grid" :aria-label="monthLabel">
    <div v-for="label in weekdayLabels" :key="label" class="weekday" role="columnheader">{{ label }}</div>
    <div
      v-for="cell in cells"
      :key="cell.key"
      type="button"
      class="day-cell"
      :class="{ muted: !cell.inMonth, today: cell.isToday }"
      role="gridcell"
      tabindex="0"
      @click="emitDay(cell.date)"
      @keydown.enter="emitDay(cell.date)"
      @keydown.space.prevent="emitDay(cell.date)"
    >
      <span class="day-number">{{ cell.day }}</span>
      <span class="day-events">
        <button
          v-for="session in cell.sessions.slice(0, 3)"
          :key="session.session_id || `${session.course_id}-${session.sequence}`"
          type="button"
          class="event"
          :data-color="session.course_color_key ?? 0"
          :title="eventTitle(session)"
          @click.stop="$emit('select', session)"
        >
          <i></i><span>{{ showCourse ? session.course_title : session.content_summary }}</span>
        </button>
        <small v-if="cell.sessions.length > 3">+{{ cell.sessions.length - 3 }}</small>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ClassSession } from '../stores/teachingCalendar'

const props = withDefaults(defineProps<{
  month: string
  sessions: ClassSession[]
  showCourse?: boolean
}>(), { showCourse: false })

const emit = defineEmits<{
  select: [session: ClassSession]
  day: [date: string]
}>()

const weekdayLabels = ['一', '二', '三', '四', '五', '六', '日']
const pad = (value: number) => String(value).padStart(2, '0')
const iso = (value: Date) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
const base = computed(() => {
  const parsed = new Date(`${props.month.slice(0, 7)}-01T12:00:00`)
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed
})
const monthLabel = computed(() => `${base.value.getFullYear()}年${base.value.getMonth() + 1}月`)
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

function eventTitle(session: ClassSession) {
  return [session.course_title, session.content_summary, session.start_time?.slice(0, 5), session.location].filter(Boolean).join(' · ')
}
function emitDay(date: string) { emit('day', date) }
</script>

<style scoped>
.month-grid { min-width:600px; height:100%; min-height:560px; display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); grid-template-rows:30px repeat(6,minmax(82px,1fr)); border-top:1px solid var(--lz-border); border-left:1px solid var(--lz-border); background:var(--lz-surface); }
.weekday { height:30px; display:grid; place-items:center; border-right:1px solid var(--lz-border); border-bottom:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:10px; font-weight:700; }
.day-cell { min-width:0; min-height:82px; display:grid; grid-template-rows:22px minmax(0,1fr); gap:2px; padding:5px; border:0; border-right:1px solid var(--lz-border); border-bottom:1px solid var(--lz-border); color:var(--lz-text-primary); background:var(--lz-surface); text-align:left; cursor:pointer; }
.day-cell:hover { background:var(--lz-fill); }.day-cell.muted { color:var(--lz-text-muted); background:color-mix(in srgb,var(--lz-fill) 48%,var(--lz-surface)); }.day-cell.today .day-number { color:#fff; background:var(--lz-brand); }
.day-number { width:22px; height:22px; display:grid; place-items:center; border-radius:50%; font-size:10px; font-weight:700; }
.day-events { min-width:0; display:grid; align-content:start; gap:3px; }.event { min-width:0; height:20px; display:flex; align-items:center; gap:5px; padding:0 5px; border:0; border-radius:5px; color:var(--lz-text-secondary); background:var(--lz-brand-soft); font-size:9px; cursor:pointer; }.event i { width:5px; height:5px; flex:0 0 auto; border-radius:50%; background:var(--lz-brand); }.event span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.event[data-color="1"],.event[data-color="5"] { background:var(--lz-success-soft); }.event[data-color="1"] i,.event[data-color="5"] i { background:var(--lz-success); }.event[data-color="2"],.event[data-color="6"] { background:var(--lz-warning-soft); }.event[data-color="2"] i,.event[data-color="6"] i { background:var(--lz-warning); }.event[data-color="3"],.event[data-color="7"] { background:var(--lz-danger-soft); }.event[data-color="3"] i,.event[data-color="7"] i { background:var(--lz-danger); }
.day-events small { padding-left:5px; color:var(--lz-text-muted); font-size:9px; }
</style>
