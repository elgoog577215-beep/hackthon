<template>
  <section class="schedule-picker" :aria-labelledby="titleId">
    <header class="schedule-heading">
      <div>
        <strong :id="titleId">{{ t('teacherCourseCreate.scheduleTitle', '上课时间') }}</strong>
        <span>{{ t('teacherCourseCreate.scheduleHelp', '每格 45 分钟，可选择多个星期和任意节次') }}</span>
      </div>
      <button v-if="modelValue.length" type="button" class="clear-selection" @click="emit('update:modelValue', [])">
        {{ t('teacherCourseCreate.clearSchedule', '清空') }}
      </button>
    </header>

    <div class="schedule-scroll">
      <div class="schedule-grid" role="grid" :aria-label="t('teacherCourseCreate.scheduleGridLabel', '每周上课时间表')">
        <div class="grid-corner" aria-hidden="true">{{ t('teacherCourseCreate.periodUnit', '节次') }}</div>
        <div v-for="day in weekdays" :key="day.value" class="weekday-heading" role="columnheader">{{ day.label }}</div>

        <template v-for="period in periods" :key="period.number">
          <div class="period-heading" role="rowheader">
            <b>{{ period.number }}</b>
            <span>{{ period.start }}–{{ period.end }}</span>
          </div>
          <button
            v-for="day in weekdays"
            :key="`${day.value}-${period.number}`"
            type="button"
            class="schedule-cell"
            :class="{ selected: isSelected(day.value, period.number) }"
            :aria-pressed="isSelected(day.value, period.number)"
            :aria-label="`${day.label}第${period.number}节，${period.start}至${period.end}`"
            role="gridcell"
            @click="toggle(day.value, period.number)"
          >
            <Check v-if="isSelected(day.value, period.number)" :size="15" aria-hidden="true" />
          </button>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Check } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import { ZJU_CLASS_PERIODS } from '../utils/zju-class-periods'

export type CourseScheduleSlot = { weekday: number; period: number }

const props = defineProps<{ modelValue: CourseScheduleSlot[] }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: CourseScheduleSlot[]): void }>()
const titleId = 'zju-course-schedule-title'
const periods = ZJU_CLASS_PERIODS
const weekdays = [
  { value: 1, label: t('teacherCourseCreate.weekdays.monday', '周一') },
  { value: 2, label: t('teacherCourseCreate.weekdays.tuesday', '周二') },
  { value: 3, label: t('teacherCourseCreate.weekdays.wednesday', '周三') },
  { value: 4, label: t('teacherCourseCreate.weekdays.thursday', '周四') },
  { value: 5, label: t('teacherCourseCreate.weekdays.friday', '周五') },
  { value: 6, label: t('teacherCourseCreate.weekdays.saturday', '周六') },
  { value: 7, label: t('teacherCourseCreate.weekdays.sunday', '周日') },
]

function isSelected(weekday: number, period: number) {
  return props.modelValue.some(item => item.weekday === weekday && item.period === period)
}

function toggle(weekday: number, period: number) {
  const key = `${weekday}-${period}`
  const next = props.modelValue
    .filter(item => `${item.weekday}-${item.period}` !== key)
    .concat(isSelected(weekday, period) ? [] : [{ weekday, period }])
    .sort((a, b) => a.weekday - b.weekday || a.period - b.period)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.schedule-picker{grid-column:1/-1;display:grid;gap:12px;padding-top:2px}.schedule-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.schedule-heading>div{display:grid;gap:4px}.schedule-heading strong{color:#334155;font-size:13px}.schedule-heading span{color:#64748b;font-size:12px}.clear-selection{padding:3px 0;border:0;color:#514bdc;background:transparent;font:inherit;font-size:12px;font-weight:700;cursor:pointer}.clear-selection:focus-visible{outline:2px solid #514bdc;outline-offset:3px;border-radius:3px}.schedule-scroll{overflow:auto;border:1px solid #dfe5ee;border-radius:10px;background:#fff}.schedule-grid{min-width:720px;display:grid;grid-template-columns:112px repeat(7,minmax(72px,1fr));align-items:stretch}.grid-corner,.weekday-heading,.period-heading{display:flex;align-items:center;justify-content:center;min-height:38px;border-right:1px solid #e8edf4;border-bottom:1px solid #e8edf4;color:#475569;background:#f8fafc;font-size:12px;font-weight:700}.weekday-heading:last-of-type{border-right:0}.period-heading{min-height:44px;justify-content:flex-start;gap:7px;padding:0 10px}.period-heading b{width:17px;color:#334155;font-size:12px}.period-heading span{color:#718096;font-size:10px;font-weight:550}.schedule-cell{min-height:44px;display:grid;place-items:center;border:0;border-right:1px solid #edf1f6;border-bottom:1px solid #edf1f6;color:#fff;background:#fff;cursor:pointer}.schedule-cell:nth-child(8n){border-right:0}.schedule-cell:hover{background:#f2f1ff}.schedule-cell.selected{background:#5b57e8}.schedule-cell.selected:hover{background:#4f4ad6}.schedule-cell:focus-visible{position:relative;z-index:1;outline:2px solid #2f2a9f;outline-offset:-3px}@media(max-width:680px){.schedule-scroll{margin-inline:0}}@media(prefers-reduced-motion:reduce){.schedule-cell{transition:none}}
</style>
