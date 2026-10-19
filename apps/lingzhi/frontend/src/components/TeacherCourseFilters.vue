<template>
  <div class="teacher-course-filters">
    <ElInput v-model="query" type="search" clearable size="large" :prefix-icon="Search" :placeholder="t('teacherCourseLibrary.searchPlaceholder')" :aria-label="t('teacherCourseLibrary.searchPlaceholder')" />
    <UiSelectMenu data-testid="course-status-filter" v-model="status" :options="statusOptions" :label="t('teacherCourseLibrary.statusLabel')" :accessibility-label="t('teacherCourseLibrary.statusFilter')" />
    <UiSelectMenu data-testid="course-term-filter" v-model="term" :options="termOptions" :label="t('teacherCourseLibrary.termLabel')" :accessibility-label="t('teacherCourseLibrary.termFilter')" />
    <UiSegmentedControl v-if="showViews" :model-value="view || 'courses'" :options="viewOptions" :accessibility-label="t('teacherHome.primaryNavigation')" @update:model-value="$emit('view', $event)" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElInput } from 'element-plus'
import { CalendarDays, List, Search } from 'lucide-vue-next'
import UiSelectMenu, { type UiSelectOption } from './UiSelectMenu.vue'
import UiSegmentedControl from './UiSegmentedControl.vue'
import { t } from '../shared/i18n'

defineProps<{ statusOptions: UiSelectOption[]; termOptions: UiSelectOption[]; view?: string; showViews?: boolean }>()
defineEmits<{ view: [value: string] }>()
const query = defineModel<string>('query', { required: true })
const status = defineModel<string>('status', { required: true })
const term = defineModel<string>('term', { required: true })
const viewOptions = computed(() => [
  { value: 'courses', label: t('teacherHome.myCourses'), icon: List },
  { value: 'calendar', label: t('teacherHome.myCalendar'), icon: CalendarDays },
])
</script>

<style scoped>
.teacher-course-filters { width:100%; min-width:0; display:flex; align-items:center; gap:12px; }
.teacher-course-filters > .el-input { flex:1; min-width:180px; margin-right:auto; max-width:520px; font-size:15px; }
.teacher-course-filters > .ui-select-menu { width:170px; flex:none; }
.teacher-course-filters > .ui-segmented-control { flex:none; --ui-segment-font-size:15px; }
@media(max-width:1100px) { .teacher-course-filters { flex-wrap:wrap; } .teacher-course-filters > .el-input { max-width:none; flex-basis:100%; } }
</style>
